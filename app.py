#!/usr/bin/env python3
# ─────────────── app.py ───────────────

import os
import json
import time
from datetime import datetime, timedelta, timezone
import functools
from functools import wraps
from typing import Optional
import logging
import base64
from collections import deque
from urllib3.util.retry import Retry
from dotenv import load_dotenv
import requests
from flask import (
    Flask, render_template, redirect,
    url_for, flash, request, abort,
    jsonify, Response, make_response, g, send_from_directory
)
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt, set_access_cookies, get_jwt_identity, unset_jwt_cookies, verify_jwt_in_request
from flask_wtf import FlaskForm, CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException, HTTPError
import logging.config
import subprocess
import hmac
import hashlib
import uuid

from config import (
    SECRET_KEY, WTF_CSRF_SECRET_KEY, JWT_SECRET_KEY, 
    GITHUB_SECRET, SUPABASE_URL, SUPABASE_KEY
)
from supabase_client import db
from supabase_logger import SupabaseLogger

# ─────────────── Конфигурация Flask ───────────────
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['WTF_CSRF_SECRET_KEY'] = WTF_CSRF_SECRET_KEY
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_ACCESS_COOKIE_PATH'] = '/'
app.config['JWT_COOKIE_CSRF_PROTECT'] = True
app.config['GITHUB_SECRET'] = GITHUB_SECRET

# Initialize Supabase logger
logger = SupabaseLogger(db.admin_client)

# ─────────────── Настройка логирования ───────────────

LOG_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s %(levelname)-8s [%(name)s] %(message)s'
        },
        'request': {
            'format': '%(asctime)s %(levelname)-8s [%(remote_addr)s] %(method)s %(path)s %(status_code)s %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'INFO'
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True
        }
    }
}
logging.config.dictConfig(LOG_CONFIG)

# также направляем werkzeug (Flask's HTTP request log) в ту же систему
logging.getLogger('werkzeug').handlers = logging.getLogger().handlers
logging.getLogger('werkzeug').setLevel(logging.INFO)
# ─────────────── Расширения ───────────────
csrf = CSRFProtect(app)
jwt = JWTManager(app)

# ─────────────── Параметры rate-limiting и HTTP-клиент ок ───────────────
_MAX_CALLS = 600
_WINDOW_SEC = 10 * 60
_call_times = deque()
_session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500,502,503,504], raise_on_status=False)
_adapter = HTTPAdapter(max_retries=retries)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


# ─────────────── Формы ───────────────
class CheckForm(FlaskForm):
    nickname = StringField('Никнейм', validators=[DataRequired(), Length(max=64)])
    submit = SubmitField('Проверить')


class AdminLoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(max=64)])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6, max=128)])
    submit = SubmitField('Войти')


class AdminRegisterForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(max=64)])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    role = SelectField('Роль',
                       choices=[('admin', 'Admin'), ('moderator', 'Moderator'), ('owner', 'Owner')],
                       validators=[DataRequired()])
    submit = SubmitField('Зарегистрировать')


class BlacklistForm(FlaskForm):
    nickname = StringField('Никнейм', validators=[DataRequired(), Length(max=64)])
    reason = StringField('Причина', validators=[DataRequired(), Length(max=256)])
    submit = SubmitField('Добавить')


class UpdateReasonForm(FlaskForm):
    reason = StringField('Новая причина', validators=[DataRequired(), Length(max=256)])
    submit = SubmitField('Сохранить')


class WhitelistForm(FlaskForm):
    uuid = StringField('UUID', validators=[DataRequired(), Length(max=36)])
    action = SelectField(
        'Действие',
        choices=[('add', 'Добавить'), ('delete', 'Удалить')],
        validators=[DataRequired()]
    )
    submit = SubmitField('Применить')


# ─────────────── Утилиты и декораторы ───────────────

@jwt.unauthorized_loader
def custom_missing_token(reason):
    return render_template('403.html'), 403

@jwt.invalid_token_loader
def custom_invalid_token(reason):
    return render_template('403.html'), 403

@jwt.expired_token_loader
def custom_expired_token(jwt_header, jwt_payload):
    return render_template('403.html'), 403

@jwt.revoked_token_loader
def custom_revoked_token(jwt_header, jwt_payload):
    return render_template('403.html'), 403

@jwt.needs_fresh_token_loader
def custom_needs_fresh_token(jwt_header, jwt_payload):
    return render_template('403.html'), 403

@jwt.invalid_token_loader
def custom_invalid_csrf(reason):
    return render_template('403.html'), 403

@app.context_processor
def inject_user():
    current_user = None
    current_role = None
    try:
        # Если токен есть — подставит в контекст, если нет — не бросит исключение
        verify_jwt_in_request(optional=True)
        current_user = get_jwt_identity()
        claims = get_jwt()
        current_role = claims.get('role')
    except Exception:
        pass
    return {
        'current_user': current_user,
        'current_role': current_role
    }

def _throttle():
    now = time.time()
    while _call_times and _call_times[0] <= now - _WINDOW_SEC:
        _call_times.popleft()
    if len(_call_times) >= _MAX_CALLS:
        time.sleep(_WINDOW_SEC - (now - _call_times[0]) + 0.1)
        return _throttle()
    _call_times.append(now)


@functools.lru_cache(maxsize=512)
def get_uuid_from_nickname(nickname: str) -> Optional[str]:
    """
    Получить Minecraft UUID по нику через Mojang API.
    — Кэш на 512 записей.
    — Учитывает лимит 600/10мин.
    — Разные уровни логирования для 404 и 429.
    """
    name = nickname.strip()
    if not name:
        return None

    _throttle()
    url = f"https://api.mojang.com/users/profiles/minecraft/{name}"

    try:
        resp = _session.get(url, timeout=5)
        # Обрабатываем 429 вручную
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 5.0
            app.logger.warning(f"429 for '{name}', retrying after {delay}s")
            time.sleep(delay)
            return get_uuid_from_nickname(name)  # повторяем после задержки

        resp.raise_for_status()
        data = resp.json()
        uuid = data.get("id")
        if not uuid:
            app.logger.info(f"Nickname '{name}' not found (empty response).")
        return uuid

    except HTTPError as e:
        status = e.response.status_code if e.response else None
        if status == 404:
            # Никнейм не существует
            app.logger.debug(f"UUID for '{name}' not found (404).")
        else:
            app.logger.error(f"Mojang API HTTP {status} for '{name}'")
    except ValueError as e:
        app.logger.error(f"JSON parse error for '{name}': {e}")
    except RequestException as e:
        app.logger.error(f"Network error retrieving UUID for '{name}': {e}")
    return None


@functools.lru_cache(maxsize=512)
def get_name_from_uuid(uuid: str) -> Optional[str]:
    """
    Получить текущий ник по UUID через Minecraft Services API.
    Эндпоинт: https://api.minecraftservices.com/minecraft/profile/lookup/{uuid}
    """
    u = uuid.replace('-', '').strip()
    if not u:
        return None

    _throttle()
    url = f"https://api.minecraftservices.com/minecraft/profile/lookup/{u}"

    try:
        resp = _session.get(url, timeout=5)
        # 429: учитываем Retry-After
        if resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            delay = float(ra) if ra else 5.0
            app.logger.warning(f"429 for '{u}', retry after {delay}s")
            time.sleep(delay)
            return get_name_from_uuid(u)

        resp.raise_for_status()
        data = resp.json()
        name = data.get("name")
        if not name:
            app.logger.info(f"No name field in response for '{u}'")
        return name

    except HTTPError as e:
        status = e.response.status_code if e.response else None
        if status == 404:
            app.logger.debug(f"UUID '{u}' not found (404).")
        else:
            app.logger.error(f"HTTP {status} for lookup/{u}")
    except (ValueError, RequestException) as e:
        app.logger.error(f"Error fetching name for '{u}': {e}")
    return None


# Декоратор для проверки входа в админ панель
def role_required(*allowed_roles):
    """
    Доступ разрешён, если роль пользователя в allowed_roles или роль == 'owner'.
    """
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get('role', '').lower()
            # если не в списке allowed_roles и не owner — 403
            if user_role not in [r.lower() for r in allowed_roles] and user_role != 'owner':
                return jsonify({'msg': 'Недостаточно прав'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# --- Helper for Audit Logging ---
def log_admin_action(action_type: str, target_type: Optional[str] = None, target_identifier: Optional[str] = None, details: Optional[str] = None):
    try:
        # Ensure we are in a request context with a JWT
        verify_jwt_in_request(optional=True) # Use optional to avoid error if called outside a protected route, though it should be.
        current_user_identity = get_jwt_identity()
        if current_user_identity:
            db.add_audit_log(
                admin_username=current_user_identity,
                action_type=action_type,
                target_type=target_type,
                target_identifier=str(target_identifier) if target_identifier is not None else None,
                details=details
            )
        else:
            app.logger.warning("Attempted to log admin action without a JWT identity (e.g. user not logged in or no token).")
    except Exception as e:
        # Log an error if audit logging fails, but don't let it break the main action
        app.logger.error(f"Failed to log admin action '{action_type}': {e}")


# --- Маршруты публичного сайта ---
@app.route("/", methods=["GET", "POST"])
def index():
    form = CheckForm()
    result = None
    if form.validate_on_submit():
        name = form.nickname.data.strip()
        entry = db.get_blacklist_entry(name)
        if entry:
            new_uuid = get_uuid_from_nickname(name)
            if new_uuid and new_uuid.lower() != entry['uuid'].lower():
                db.update_blacklist_entry(entry['id'], {
                    'uuid': new_uuid,
                    'nickname': name
                })
                entry['uuid'] = new_uuid
                entry['nickname'] = name
            result = {"message": f"{name}, вы в ЧС!", "reason": entry['reason'], "color": "red"}
        else:
            result = {"message": f"{name}, вы не в ЧС!", "color": "green"}
        db.add_check_log(check_source='main_page_check') # Log the check
        # If AJAX/fetch/XHR, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes['application/json'] > request.accept_mimetypes['text/html']:
            return jsonify(result)
    return render_template("index.html", form=form, result=result)


@app.route("/fullist")
def fullist():
    return render_template("fullist.html")


@app.route("/ave")
def ave():
    return render_template("ave.html")


@app.route("/contacts")
def contacts():
    return render_template("contacts.html")


@app.route("/offline")
def offline():
    return render_template("offline.html")


# ─────────────── Ошибки ───────────────
@app.errorhandler(400)
def bad_request(error):
    return render_template('400.html'), 400

@app.errorhandler(401)
def unauthorized(error):
    return render_template('401.html'), 401

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500


# Контекстный процессор для получения текущего года
@app.context_processor
def inject_current_year():
    return {'current_year': lambda: datetime.now().year}


# ─────────────── Админ-панель ───────────────
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        user = db.get_admin_user(form.username.data)
        if user and check_password_hash(user['password_hash'], form.password.data):
            access_token = create_access_token(identity=user['username'], additional_claims={'role': user['role']})
            resp = make_response(redirect(url_for('admin_panel')))
            set_access_cookies(resp, access_token)
            return resp
        flash('Неверный логин или пароль', 'danger')
    return render_template('admin_login.html', form=form)


@app.route('/admin/logout')
def admin_logout():
    resp = make_response(redirect(url_for('admin_login')))
    unset_jwt_cookies(resp)
    flash('Вы вышли из админ-панели', 'info')
    return resp


@app.route("/admin/register", methods=["GET", "POST"])
@role_required("owner")
def admin_register():
    form = AdminRegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        role = form.role.data

        if db.get_admin_user(username):
            flash("Пользователь с таким именем уже существует.", "warning")
        else:
            password_hash = generate_password_hash(password)
            if db.create_admin_user(username, password_hash, role):
                log_admin_action("CREATE_ADMIN_USER", target_type="admin_user", target_identifier=username, details=f"Role: {role}")
                flash("Пользователь успешно зарегистрирован.", "success")
                return redirect(url_for("admin_panel"))
            else:
                flash("Ошибка при создании пользователя.", "danger")

    return render_template("admin_register.html", form=form)


@app.route("/admin", methods=["GET", "POST"])
@role_required("owner", "admin", "moderator")
def admin_panel():
    form = BlacklistForm()
    result = None
    if form.validate_on_submit():
        nick = form.nickname.data.strip()
        reason = form.reason.data.strip()
        uuid_val = get_uuid_from_nickname(nick)
        if not uuid_val:
            result = {"error": "Не удалось получить UUID."}
        elif db.get_blacklist_entry(nick):
            result = {"error": "Уже в черном списке."}
        else:
            existing_by_uuid = db.client.table('blacklist_entry').select('id').eq('uuid', uuid_val).execute()
            if existing_by_uuid.data:
                result = {"error": f"Пользователь с UUID {uuid_val} уже в черном списке."}
            elif db.add_blacklist_entry(nick, uuid_val, reason):
                log_admin_action("ADD_BLACKLIST", target_type="blacklist_entry", target_identifier=nick, details=f"UUID: {uuid_val}, Reason: {reason}")
                result = {"message": "Запись добавлена в ЧС.", "success": True}
            else:
                result = {"error": "Ошибка при добавлении записи."}
        # If AJAX/fetch/XHR, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes['application/json'] > request.accept_mimetypes['text/html']:
            return jsonify(result)
        # Otherwise, use flash and redirect for normal POST
        if result.get('error'):
            flash(result['error'], 'danger')
        else:
            flash(result['message'], 'success')
        return redirect(url_for('admin_panel'))
    entries = db.get_all_blacklist_entries()['items']
    return render_template("admin_panel.html", form=form, entries=entries)


@app.route("/admin/update_reason/<int:entry_id>", methods=["GET", "POST"])
@role_required("owner", "admin", "moderator")
def update_reason(entry_id):
    entry = db.get_blacklist_entry_by_id(entry_id)
    if not entry:
        abort(404)
        
    original_reason = entry['reason']
    form = UpdateReasonForm(reason=original_reason)

    if form.validate_on_submit():
        new_reason = form.reason.data.strip()
        if new_reason != original_reason:
            if db.update_blacklist_entry(entry_id, {'reason': new_reason}):
                log_admin_action("UPDATE_BLACKLIST_REASON", target_type="blacklist_entry", target_identifier=str(entry_id), details=f"Old: '{original_reason}', New: '{new_reason}'")
                flash("Причина изменена.", "success")
            else:
                flash("Ошибка при обновлении причины.", "danger")
        else:
            flash("Новая причина совпадает со старой.", "info")
        return redirect(url_for('admin_panel'))
    return render_template("update_reason.html", form=form, entry=entry)


@app.route("/admin/delete/<int:entry_id>", methods=["POST"])
@role_required("owner", "admin")
def delete_entry(entry_id):
    entry_to_delete = db.get_blacklist_entry_by_id(entry_id)  # Get details before deleting for logging
    if entry_to_delete:
        if db.delete_blacklist_entry(entry_id):
            log_admin_action(
                "DELETE_BLACKLIST",
                target_type="blacklist_entry",
                target_identifier=str(entry_id),
                details=f"Nickname: {entry_to_delete.get('nickname')}, UUID: {entry_to_delete.get('uuid')}"
            )
            flash("Запись удалена из ЧС.", "success")
        else:
            flash("Ошибка при удалении записи.", "danger")
    else:
        flash("Запись не найдена для удаления.", "warning")
    return redirect(url_for('admin_panel'))


@app.route("/admin/users", methods=["GET"])
@role_required("owner")
def admin_users():
    users = db.get_all_admin_users()
    return render_template('admin_users.html', users=users)

@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@role_required("owner")
def delete_user(user_id):
    current_user_identity = get_jwt_identity() # Renamed from current to avoid conflict
    user_to_delete = db.get_admin_user_by_id(user_id) # Get details before deleting
    if not user_to_delete:
        abort(404)
        
    if user_to_delete['username'] == current_user_identity:
        flash("Нельзя удалить себя.", "warning")
    else:
        if db.delete_admin_user(user_id):
            log_admin_action("DELETE_ADMIN_USER", target_type="admin_user", target_identifier=user_to_delete['username'])
            flash("Пользователь удалён.", "success")
        else:
            flash("Ошибка при удалении пользователя.", "danger")
    return redirect(url_for('admin_users'))

@app.route("/admin/whitelist", methods=["GET", "POST"])
@role_required("owner")
def admin_whitelist():
    form = WhitelistForm()
    
    current_user_identity = get_jwt_identity() # For logging who added/deleted

    if form.validate_on_submit():
        uuid_to_modify = form.uuid.data.strip()
        action = form.action.data

        if not uuid_to_modify:
            flash("UUID не может быть пустым.", "warning")
            return redirect(url_for('admin_whitelist'))

        if action == "add":
            if not db.is_whitelisted(uuid_to_modify):
                if db.add_to_whitelist(uuid_to_modify, added_by=current_user_identity):
                    log_admin_action("ADD_WHITELIST_SUPABASE", target_type="whitelist_player", target_identifier=uuid_to_modify, details=f"Added by: {current_user_identity}")
                    flash(f"UUID {uuid_to_modify} добавлен в whitelist (Supabase).", "success")
                else:
                    flash(f"Ошибка при добавлении UUID {uuid_to_modify} в Supabase.", "danger")
            else:
                flash(f"UUID {uuid_to_modify} уже в whitelist (Supabase).", "info")
        elif action == "delete":
            if db.is_whitelisted(uuid_to_modify): # Check if it exists before attempting delete
                if db.remove_from_whitelist(uuid_to_modify):
                    log_admin_action("DELETE_WHITELIST_SUPABASE", target_type="whitelist_player", target_identifier=uuid_to_modify, details=f"Removed by: {current_user_identity}")
                    flash(f"UUID {uuid_to_modify} удален из whitelist (Supabase).", "success")
                else:
                    flash(f"Ошибка при удалении UUID {uuid_to_modify} из Supabase.", "danger")
            else:
                flash(f"UUID {uuid_to_modify} не найден в whitelist (Supabase) для удаления.", "warning")
        return redirect(url_for('admin_whitelist'))
    
    # Handle direct deletion from the list if a form with 'uuid_to_delete_direct' and 'action=delete_direct' is POSTed
    # This is an alternative to the main form, often used for buttons next to each item in a list.
    if request.method == "POST" and request.form.get("action_direct") == "delete":
        uuid_to_delete_direct = request.form.get("uuid_to_delete_direct")
        if uuid_to_delete_direct:
            if db.is_whitelisted(uuid_to_delete_direct):
                if db.remove_from_whitelist(uuid_to_delete_direct):
                    log_admin_action("DELETE_WHITELIST_SUPABASE", target_type="whitelist_player", target_identifier=uuid_to_delete_direct, details=f"Deleted via button by: {current_user_identity}")
                    flash(f"UUID {uuid_to_delete_direct} удален из whitelist (через кнопку, Supabase).", "success")
                else:
                    flash(f"Ошибка при удалении {uuid_to_delete_direct} из Supabase.", "danger")
            else:
                flash(f"UUID {uuid_to_delete_direct} не найден для удаления.", "warning")
            return redirect(url_for('admin_whitelist'))

    whitelist_entries = db.get_all_whitelist_entries()
    
    return render_template("admin_whitelist.html", form=form, whitelist_entries=whitelist_entries)

# New API endpoint for the mod
@app.route("/api/whitelist/all", methods=["GET"])
def api_get_all_whitelisted_uuids():
    try:
        uuids = db.get_all_whitelisted_uuids()
        return jsonify(uuids) # Returns a simple JSON array of UUID strings
    except Exception as e:
        app.logger.error(f"Error in /api/whitelist/all: {e}")
        return jsonify({"error": "Failed to fetch whitelist", "message": str(e)}), 500

@app.route("/admin/update_nicknames", methods=["POST"])
@role_required("owner")
def update_nicknames_route(): 
    if request.method == "POST":
        try:
            all_entries_data = db.get_all_blacklist_entries(page=1, per_page=10000) 
            entries = all_entries_data.get('items', [])
            
            updated_count = 0
            failed_fetch_count = 0
            no_change_count = 0
            log_details = []

            if not entries:
                flash("Черный список пуст. Нечего обновлять.", "info")
                log_admin_action(action_type="update_nicknames", details="Attempted on empty blacklist.")
                return redirect(url_for('admin_panel'))

            for entry in entries:
                current_uuid = entry.get('uuid')
                old_nickname = entry.get('nickname')
                entry_id = entry.get('id')

                if not current_uuid or not entry_id:
                    app.logger.warning(f"Skipping entry due to missing uuid or id: {entry}")
                    failed_fetch_count += 1
                    log_details.append(f"Skipped entry: missing uuid/id for {old_nickname or 'Unknown'}")
                    continue

                new_nickname = get_name_from_uuid(current_uuid)

                if new_nickname is None:
                    app.logger.warning(f"Failed to fetch new nickname for UUID: {current_uuid} (old: {old_nickname})")
                    failed_fetch_count += 1
                    log_details.append(f"Failed fetch for UUID {current_uuid} (was {old_nickname})")
                    continue

                if new_nickname != old_nickname:
                    db.update_blacklist_entry_nickname(entry_id, new_nickname)
                    updated_count += 1
                    log_details.append(f"Updated: {old_nickname} -> {new_nickname} (UUID: {current_uuid})")
                    app.logger.info(f"Updated nickname for UUID {current_uuid}: {old_nickname} -> {new_nickname}")
                else:
                    no_change_count +=1
                    log_details.append(f"No change: {old_nickname} (UUID: {current_uuid})")
            
            summary_message = f"Обновление никнеймов завершено. Обновлено: {updated_count}. Не удалось получить: {failed_fetch_count}. Без изменений: {no_change_count}."
            flash(summary_message, "success" if updated_count > 0 or no_change_count > 0 else "warning")
            log_admin_action(action_type="update_nicknames", details=summary_message + " Details: " + "; ".join(log_details))

        except Exception as e:
            app.logger.error(f"Error updating nicknames: {e}", exc_info=True)
            flash(f"Произошла ошибка при обновлении никнеймов: {e}", "error")
            log_admin_action(action_type="update_nicknames", details=f"Error: {e}")
        
        return redirect(url_for('admin_panel'))
    else:
        # GET request, shouldn't happen with methods=["POST"] but good to handle
        abort(405)

@app.before_request
def block_sensitive_paths():
    p = request.path
    forbidden = [
        '/.env',
        '/asuka',
        '/.git', '/.aws', '/wp-', '/.ht', '/config', '/settings'
    ]
    # точное совпадение или префикс
    if any(p == f or p.startswith(f) for f in forbidden):
        abort(403)

@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    return send_from_directory(
        os.path.join(app.root_path, ''),  # корень проекта
        'sitemap.xml',
        mimetype='application/xml'
    )

@app.route('/robots.txt', methods=['GET'])
def robots():
    return send_from_directory(
        os.path.join(app.root_path, ''),  # корень проекта
        'robots.txt',
        mimetype='text/plain'
    )

@app.route('/dashboard')
@app.route('/login')
@app.route('/secret')
@app.route('/old')
@app.route('/porno')
@app.route('/leviathan')
def shmok():
    """
    Единый эндпоинт для трёх URL,
    возвращает шаблон shmok.html с видео.
    """
    return render_template('dox.html')


@app.route('/api/check', methods=['GET'])
def api_check():
    nickname = request.args.get('nickname', '').strip()
    if not nickname:
        payload = {'error': 'Параметр nickname обязателен и не может быть пустым'}
        text = json.dumps(payload, ensure_ascii=False)
        return Response(text, status=400, mimetype='application/json')

    entry = db.get_blacklist_entry(nickname)
    if entry:
        new_uuid = get_uuid_from_nickname(nickname)
        if new_uuid and new_uuid.lower() != entry['uuid'].lower():
            db.update_blacklist_entry(entry['id'], {
                'uuid': new_uuid,
                'nickname': nickname
            })
            entry['uuid'] = new_uuid
            entry['nickname'] = nickname

        payload = {
            'in_blacklist': True,
            'nickname': entry['nickname'],
            'uuid': entry['uuid'],
            'reason': entry['reason'],
            'created_at': entry['created_at']
        }
    else:
        payload = {'in_blacklist': False}

    db.add_check_log(check_source='api_check') # Log the check
    text = json.dumps(payload, ensure_ascii=False)
    return Response(text, status=200, mimetype='application/json')

@app.route("/admin/map", methods=["GET"])
@role_required("owner", "admin")
def admin_map():
    return render_template("admin_map.html")

@app.route("/admin/audit_log", methods=["GET"])
@role_required("owner")
def admin_audit_log():
    page = request.args.get('page', 1, type=int)
    per_page = 20 # Or make this configurable
    
    logs_data = db.get_audit_logs(page=page, per_page=per_page)
    
    return render_template("admin_audit_log.html", 
                           logs=logs_data.get('items', []),
                           page=logs_data.get('page'),
                           per_page=logs_data.get('per_page'),
                           total_items=logs_data.get('total_items'),
                           has_more=logs_data.get('has_more'))

@app.route('/api/fullist')
def api_full_blacklist():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        search_query = request.args.get('q', '').strip().lower()
        
        # Parameters for sorting and filtering are removed

        # Validate parameters
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 20

        # Get paginated results with search
        result = db.get_all_blacklist_entries(page=page, per_page=per_page, search=search_query)
        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Error in api_full_blacklist: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@app.route("/api/uuid/<nickname>", methods=["GET"])
def api_uuid_lookup(nickname):
    """
    Возвращает UUID игрока по его никнейму через Mojang API.
    """
    nickname = nickname.strip()
    if not nickname:
        return Response(json.dumps({"error": "Ник не должен быть пустым"}, ensure_ascii=False),
                        status=400, mimetype="application/json")

    try:
        r = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{nickname}", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return Response(json.dumps({"nickname": data["name"], "uuid": data["id"]}, ensure_ascii=False),
                            mimetype="application/json")
        else:
            return Response(json.dumps({"error": "UUID не найден"}, ensure_ascii=False),
                            status=404, mimetype="application/json")
    except Exception as e:
        app.logger.exception("Ошибка при обращении к Mojang API")
        return Response(json.dumps({"error": "Ошибка при обращении к Mojang API"}, ensure_ascii=False),
                        status=500, mimetype="application/json")


@app.before_request
def start_timer():
    g.start_time = time.time()


@app.after_request
def log_request(response):
    duration = time.time() - getattr(g, 'start_time', time.time())
    extra = {
        'remote_addr': request.remote_addr,
        'method': request.method,
        'path': request.path,
        'status_code': response.status_code
    }
    logging.getLogger('request').info('Request processed', extra=extra)
    return response


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Handle any uncaught exception"""
    error_id = str(uuid.uuid4())
    app.logger.exception(f'Unhandled exception {error_id}:')
    
    # Log additional request information
    app.logger.error(f"""
    Error ID: {error_id}
    URL: {request.url}
    Method: {request.method}
    IP: {request.remote_addr}
    User Agent: {request.user_agent}
    """)
    
    return render_template('500.html', error_id=error_id), 500


@app.route("/swagger")
@role_required("owner", "admin")
def swagger_ui():
    return redirect("/static/swagger/index.html")


# ─────────────── API: Периодические данные для PWA ───────────────
@app.route("/api/latest-data", methods=["GET"])
def api_latest_data():
    """
    Возвращает последние записи из черного списка для периодического кеширования.
    Опциональный параметр ?limit=<int> (макс. 100) задает число записей, по умолчанию 10.
    """
    # Определяем параметр limit
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 100))

    # Получаем последние записи
    result = db.get_all_blacklist_entries(page=1, per_page=limit)
    entries = result.get('items', [])

    # Формируем JSON-пayload
    payload = [
        {
            "nickname": e.get('nickname'),
            "uuid": e.get('uuid'),
            "reason": e.get('reason'),
            "created_at": e.get('created_at') # Supabase returns ISO string directly
        }
        for e in entries
    ]

    # Отдаем JSON без \u-эскейпов
    return Response(
        json.dumps(payload, ensure_ascii=False),
        mimetype="application/json"
    )

@csrf.exempt
@app.route("/api/locations/view", methods=["GET"])
@role_required("owner", "admin")
def api_locations_view():
    try:
        # Fetch locations from the last hour, most recent first
        response = db.client.table('player_locations')\
            .select('uuid, x, y, z, client_timestamp, created_at')\
            .order('created_at', desc=True)\
            .limit(100)\
            .execute()

        if response.error:
            app.logger.error(f"Error fetching locations from Supabase: {response.error.message}")
            return jsonify({"error": "Failed to fetch locations", "details": response.error.message}), 500

        locations_data = response.data
        results = []

        # Get a unique set of UUIDs to fetch nicknames and avatars efficiently
        unique_uuids = list(set(loc['uuid'] for loc in locations_data if loc['uuid']))

        nicknames_cache = {}
        avatars_cache = {}

        for u_id in unique_uuids:
            nicknames_cache[u_id] = get_name_from_uuid(u_id) # Mojang API call
            # Fetch avatar (simplified, assumes api_avatar logic or direct Minotar)
            avatar_url = f"https://minotar.net/helm/{u_id}/32.png" # Smaller avatar for map
            try:
                avatar_resp = requests.get(avatar_url, timeout=2)
                if avatar_resp.status_code == 200:
                    b64_avatar = base64.b64encode(avatar_resp.content).decode('ascii')
                    avatars_cache[u_id] = f"data:image/png;base64,{b64_avatar}"
                else:
                    avatars_cache[u_id] = None # Or a default placeholder avatar
            except requests.RequestException:
                avatars_cache[u_id] = None

        for loc in locations_data:
            # Use client_timestamp if available and valid, otherwise fall back to created_at
            timestamp_to_use = loc.get('client_timestamp') or loc.get('created_at')
            # Ensure timestamp is in ISO format string for JSON serialization
            if isinstance(timestamp_to_use, datetime):
                iso_timestamp = timestamp_to_use.isoformat()
            elif isinstance(timestamp_to_use, str):
                iso_timestamp = timestamp_to_use
            else:
                iso_timestamp = datetime.utcnow().isoformat()
            player_uuid = loc.get('uuid')
            results.append({
                "uuid": player_uuid,
                "nickname": nicknames_cache.get(player_uuid, "Unknown"),
                "avatar_base64": avatars_cache.get(player_uuid),
                "x": loc.get("x"),
                "y": loc.get("y"),
                "z": loc.get("z"),
                "timestamp": iso_timestamp 
            })

        # Filter results to only include those from the last hour
        now_dt = datetime.utcnow().replace(tzinfo=None) # Naive datetime for comparison
        one_hour_ago = now_dt - timedelta(hours=1)
        final_results = []
        for r in results:
            ts_str = r.get("timestamp")
            if ts_str:
                try:
                    dt_obj = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    if dt_obj.tzinfo:
                        dt_obj = dt_obj.astimezone(timezone.utc).replace(tzinfo=None)
                    if dt_obj > one_hour_ago:
                        final_results.append(r)
                except ValueError as e:
                    app.logger.warning(f"Could not parse timestamp '{ts_str}' for location: {e}")
        return jsonify(final_results)
    except Exception as e:
        app.logger.error(f"Unexpected error in /api/locations/view: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred.", "message": str(e)}), 500


@app.route("/api/player-details/<player_uuid>", methods=["GET"])
def api_player_details(player_uuid):
    """
    Возвращает JSON с никнеймом и аватаркой игрока в Base64 по UUID.
    Ответ:
      200: { "uuid": "...", "nickname": "...", "avatar_base64": "data:image/png;base64,..." }
      404: { "error": "Player details not found or UUID invalid" }
      500: { "error": "Internal error fetching player details" }
    """
    if not player_uuid or len(player_uuid.replace('-', '')) != 32:
        return jsonify(error="Invalid UUID format"), 400

    nickname = get_name_from_uuid(player_uuid)
    # Avatar fetching logic (similar to /api/avatar/)
    avatar_base64 = None
    avatar_url = f"https://minotar.net/helm/{player_uuid}/32.png" # Using 32px for map consistency
    try:
        resp = requests.get(avatar_url, timeout=3) # Short timeout for combined endpoint
        if resp.status_code == 200:
            b64 = base64.b64encode(resp.content).decode('ascii')
            avatar_base64 = f"data:image/png;base64,{b64}"
        # Not found (404) for avatar is acceptable, nickname might still exist
    except requests.RequestException as e:
        app.logger.warning(f"Error fetching avatar for {player_uuid} in player-details: {e}")
        # Continue without avatar if it fails, nickname is more critical here

    if not nickname and not avatar_base64:
        return jsonify(error="Player details not found or UUID invalid"), 404

    return jsonify({
        "uuid": player_uuid,
        "nickname": nickname, # Will be null if not found
        "avatar_base64": avatar_base64 # Will be null if not found or error
    }), 200

@app.route("/api/avatar/<user_uuid>", methods=["GET"])
def api_avatar(user_uuid):
    """
    JSON API: возвращает PNG‑аватарку игрока в Base64.
    Ответ:
      200: { "uuid": "...", "avatar_base64": "data:image/png;base64,..." }
      404: { "error": "Avatar not found" }
      500: { "error": "Internal error fetching avatar" }
    """
    # Запрашиваем PNG с Minotar
    url = f"https://minotar.net/helm/{user_uuid}/100.png"
    try:
        resp = requests.get(url, timeout=5)
    except requests.RequestException as e:
        app.logger.error(f"Error fetching avatar for {user_uuid}: {e}")
        return jsonify(error="Internal error fetching avatar"), 500

    if resp.status_code == 200:
        # Кодируем бинарный контент в Base64
        b64 = base64.b64encode(resp.content).decode('ascii')
        data_uri = f"data:image/png;base64,{b64}"
        return jsonify(uuid=user_uuid, avatar_base64=data_uri), 200
    elif resp.status_code == 404:
        return jsonify(error="Avatar not found"), 404
    else:
        app.logger.warning(f"Unexpected status {resp.status_code} for avatar {user_uuid}")
        return jsonify(error="Error fetching avatar"), resp.status_code

@csrf.exempt
@app.route("/api/locations/report", methods=["GET","POST"])
def api_locations_report():
    if request.method == "GET":
        return jsonify(message="POST JSON {uuid, x, y, z, client_timestamp (optional, ISO format)} to me"), 200

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON"}), 400

    player_uuid = data.get("uuid") # Renamed to avoid conflict with uuid module
    x = data.get("x")
    y = data.get("y")
    z = data.get("z")
    client_timestamp_str = data.get("client_timestamp") # Optional client-provided timestamp

    if not all([player_uuid, isinstance(x, int), isinstance(y, int), isinstance(z, int)]):
        return jsonify({"error": "Fields uuid (string), x (int), y (int), z (int) are required and must be correct types."}), 400

    client_timestamp = None
    if client_timestamp_str:
        try:
            client_timestamp = datetime.fromisoformat(client_timestamp_str.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({"error": "Invalid client_timestamp format. Please use ISO 8601 format."}), 400
    
    try:
        # Insert into Supabase
        record = {
            'uuid': player_uuid,
            'x': x,
            'y': y,
            'z': z
        }
        if client_timestamp:
            record['client_timestamp'] = client_timestamp.isoformat()
        else:
            pass 
            
        response = db.client.table('player_locations').insert(record).execute()

        if response.data:
            app.logger.info(f"Reported location for {player_uuid}: X:{x} Y:{y} Z:{z} TS:{client_timestamp_str}")
            return jsonify({"success": True, "message": "Location reported successfully."}), 200
        else:
            app.logger.error(f"Failed to report location to Supabase: {response.error.message if response.error else 'Unknown error'}")
            return jsonify({"error": "Failed to store location", "details": response.error.message if response.error else 'Unknown error'}), 500

    except Exception as e:
        app.logger.error(f"Error in /api/locations/report: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500
    
@app.after_request
def set_security_headers(response):
    csp = (
        "default-src 'self'; "
        "frame-src 'self' https://*; "
        "connect-src 'self' https://*.supabase.co wss://*.supabase.co "
        "https://api.mojang.com https://api.namemc.com https://minotar.net https://api.minecraftservices.com; "
        "img-src 'self' data: https://minotar.net https://avatars.githubusercontent.com https://static.cloudflareinsights.com; "
        "media-src 'self' data: blob: https://minotar.net; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://static.cloudflareinsights.com; "
        "script-src-elem 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://static.cloudflareinsights.com; "
        "worker-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "font-src 'self' data: https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "upgrade-insecure-requests;"
    )

    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    # Кэширование по типу запроса
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    else:
        response.headers['Cache-Control'] = 'public, max-age=3600'

    return response

# Add Jinja filter for formatting datetimes in templates
def format_datetime_filter(value, format='%Y-%m-%d %H:%M:%S'):
    """Format a datetime object or an ISO string to a more readable string."""
    if isinstance(value, str):
        try:
            # Attempt to parse ISO format, including those with 'Z' or timezone offset
            if 'Z' in value:
                value = value.replace('Z', '+00:00')
            dt_obj = datetime.fromisoformat(value)
        except ValueError:
            return value # Return original string if parsing fails
    elif isinstance(value, datetime):
        dt_obj = value
    else:
        return value # Return as is if not a string or datetime
    # If it has timezone info, convert to naive UTC
    if dt_obj.tzinfo:
        dt_obj = dt_obj.astimezone(timezone.utc).replace(tzinfo=None)
    return dt_obj.strftime(format)

app.jinja_env.filters['format_datetime'] = format_datetime_filter

@app.route('/api/config')
def get_api_config():
    """Return API configuration securely from environment variables"""
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        return jsonify({'error': 'Configuration not found'}), 500
        
    return jsonify({
        'supabaseUrl': supabase_url,
        'supabaseKey': supabase_key
    })

@app.template_filter('datetime')
def format_datetime_filter(value, format='%Y-%m-%d %H:%M:%S'):
    """Format a datetime object or an ISO string to a more readable string."""
    if isinstance(value, str):
        try:
            # Attempt to parse ISO format, including those with 'Z' or timezone offset
            if 'Z' in value:
                value = value.replace('Z', '+00:00')
            dt_obj = datetime.fromisoformat(value)
        except ValueError:
            return value # Return original string if parsing fails
    elif isinstance(value, datetime):
        dt_obj = value
    else:
        return value # Return as is if not a string or datetime
    # If it has timezone info, convert to naive UTC
    if dt_obj.tzinfo:
        dt_obj = dt_obj.astimezone(timezone.utc).replace(tzinfo=None)
    return dt_obj.strftime(format)

@app.route("/admin/logs")
@role_required("owner", "admin")
def admin_logs():
    """View system logs with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        level = request.args.get('level')
        logger_name = request.args.get('logger')
        search = request.args.get('search')

        # Build query
        query = db.admin_client.table('system_logs').select('*', count='exact')

        # Apply filters
        if level:
            query = query.eq('level', level)
        if logger_name:
            query = query.eq('logger_name', logger_name)
        if search:
            query = query.or_(f'message.ilike.%{search}%,extra_data.ilike.%{search}%')

        # Get unique logger names for filter dropdown
        logger_names_result = db.admin_client.table('system_logs').select('logger_name').execute()
        logger_names = sorted(set(log['logger_name'] for log in logger_names_result.data))

        # Pagination
        start = (page - 1) * per_page
        query = query.order('timestamp', desc=True).range(start, start + per_page - 1)
        
        result = query.execute()
        logs = result.data
        total = result.count if hasattr(result, 'count') and result.count is not None else 0

        # Create pagination object
        class Pagination:
            def __init__(self, page, per_page, total):
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = (total + per_page - 1) // per_page
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1
                self.next_num = page + 1

            def iter_pages(self):
                left_edge = 2
                left_current = 2
                right_current = 2
                right_edge = 2

                last = 0
                for num in range(1, self.pages + 1):
                    if (
                        num <= left_edge
                        or num > self.pages - right_edge
                        or (
                            num >= self.page - left_current
                            and num <= self.page + right_current
                        )
                    ):
                        if last + 1 != num:
                            yield None
                        yield num
                        last = num

        pagination = Pagination(page, per_page, total)

        return render_template(
            'admin_logs.html',
            logs=logs,
            pagination=pagination,
            logger_names=logger_names
        )
    except Exception as e:
        logger.exception("Error viewing system logs", e)
        flash('Ошибка при загрузке логов', 'error')
        return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    app.run(debug=False)
