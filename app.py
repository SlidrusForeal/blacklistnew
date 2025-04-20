#!/usr/bin/env python3
# ─────────────── app.py ───────────────

import os
import json
import time
from datetime import datetime
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
    url_for, session, flash, request, abort,
    jsonify, Response, make_response, g
)
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt, set_access_cookies, get_jwt_identity, unset_jwt_cookies, verify_jwt_in_request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException, HTTPError
import logging.config

# ─────────────── Конфигурация Flask ───────────────
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('WTF_CSRF_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# JWT конфигурация (куки)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_ACCESS_COOKIE_PATH'] = '/'
app.config['JWT_COOKIE_CSRF_PROTECT'] = True

# ─────────────── Настройка логирования ───────────────
# Создаём папку для логов, если её нет
if not os.path.exists('logs'):
    os.mkdir('logs')

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
        'info_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/info.log',
            'when': 'midnight',
            'backupCount': 7,
            'formatter': 'default',
            'level': 'INFO'
        },
        'error_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': 'logs/error.log',
            'when': 'midnight',
            'backupCount': 30,
            'formatter': 'default',
            'level': 'ERROR'
        }
    },
    'loggers': {
        '': {
            'handlers': ['console', 'info_file', 'error_file'],
            'level': 'INFO',
            'propagate': True
        }
    }
}
logging.config.dictConfig(LOG_CONFIG)

# также направляем werkzeug (Flask’s HTTP request log) в ту же систему
logging.getLogger('werkzeug').handlers = logging.getLogger().handlers
logging.getLogger('werkzeug').setLevel(logging.INFO)
# ─────────────── Расширения ───────────────
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
jwt = JWTManager(app)

# ─────────────── Параметры rate-limiting и HTTP-клиент ───────────────
_MAX_CALLS = 600
_WINDOW_SEC = 10 * 60
_call_times = deque()
_session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500,502,503,504], raise_on_status=False)
_adapter = HTTPAdapter(max_retries=retries)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


# ─────────────── Модели ───────────────

class BlacklistEntry(db.Model):
    __tablename__ = 'blacklist_entry'
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(64), nullable=False)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    reason = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<BlacklistEntry {self.nickname} ({self.uuid})>"


class AdminUser(db.Model):
    __tablename__ = 'admin_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # owner, admin, moderator

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<AdminUser {self.username} ({self.role})>"


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

# Функции для работы с whitelist (файл uuid_list.json)
def load_whitelist():
    try:
        with open("uuid_list.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"Ошибка загрузки whitelist: {str(e)}")
        return []


def save_whitelist(data):
    try:
        with open("uuid_list.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        app.logger.error(f"Ошибка сохранения whitelist: {str(e)}")


# --- Маршруты публичного сайта ---
@app.route("/", methods=["GET", "POST"])
def index():
    form = CheckForm()
    result = None
    if form.validate_on_submit():
        name = form.nickname.data.strip()
        entry = BlacklistEntry.query.filter(
            db.func.lower(BlacklistEntry.nickname) == name.lower()
        ).first()
        if entry:
            new_uuid = get_uuid_from_nickname(name)
            if new_uuid and new_uuid.lower() != entry.uuid.lower():
                entry.uuid = new_uuid
                entry.nickname = name
                db.session.commit()
            result = {"message": f"{name}, вы в ЧС!", "reason": entry.reason, "color": "red"}
        else:
            result = {"message": f"{name}, вы не в ЧС!", "color": "green"}
    return render_template("index.html", form=form, result=result)


@app.route("/fullist")
def fullist():
    players = BlacklistEntry.query.order_by(BlacklistEntry.nickname.asc()).all()
    return render_template("fullist.html", players=players)


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
for code in [400, 401, 403, 404, 500]:
    @app.errorhandler(code)
    def error_page(error, code=code):
        return render_template(f"{code}.html"), code


# Контекстный процессор для получения текущего года
@app.context_processor
def inject_current_year():
    return {'current_year': lambda: datetime.now().year}


# ─────────────── Админ-панель ───────────────
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        user = AdminUser.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            access_token = create_access_token(identity=user.username, additional_claims={'role': user.role})
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

        if AdminUser.query.filter_by(username=username).first():
            flash("Пользователь с таким именем уже существует.", "warning")
        else:
            new_user = AdminUser(username=username, role=role)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("Пользователь успешно зарегистрирован.", "success")
            return redirect(url_for("admin_panel"))

    # при GET-запросе или ошибках валидации подставляем form в шаблон
    return render_template("admin_register.html", form=form)


@app.route("/admin", methods=["GET", "POST"])
@role_required("owner", "admin", "moderator")
def admin_panel():
    form = BlacklistForm()
    if form.validate_on_submit():
        nick = form.nickname.data.strip()
        reason = form.reason.data.strip()
        if not get_uuid_from_nickname(nick):
            flash("Не удалось получить UUID.", "warning")
        elif BlacklistEntry.query.filter_by(uuid=get_uuid_from_nickname(nick)).first():
            flash("Уже в черном списке.", "info")
        else:
            entry = BlacklistEntry(
                nickname=nick,
                uuid=get_uuid_from_nickname(nick),
                reason=reason
            )
            db.session.add(entry)
            db.session.commit()
            flash("Запись добавлена в ЧС.", "success")
            return redirect(url_for('admin_panel'))
    entries = BlacklistEntry.query.order_by(BlacklistEntry.nickname).all()
    return render_template("admin_panel.html", form=form, entries=entries)


# Обновление никнеймов (доступ только для владельца)
@app.route("/admin/update_nicknames", methods=["POST"])
@role_required("owner", "admin")
def update_nicknames():
    entries = BlacklistEntry.query.all()
    updated_count = 0

    for entry in entries:
        # Берём UUID из поля entry.uuid
        new_name = get_name_from_uuid(entry.uuid)
        if new_name and new_name.strip().lower() != entry.nickname.strip().lower():
            entry.nickname = new_name
            updated_count += 1
        # Смягчаем нагрузку на API
        time.sleep(1)

    db.session.commit()
    flash(f"Обновлены никнеймы для {updated_count} записей.", "success")
    return redirect(url_for('admin_panel'))


@app.route("/admin/update_nickname/<int:entry_id>", methods=["POST"])
@role_required("owner", "admin")
def update_nickname(entry_id):
    entry = BlacklistEntry.query.get_or_404(entry_id)
    new_name = get_name_from_uuid(entry.uuid)
    if new_name and new_name.strip().lower() != entry.nickname.strip().lower():
        entry.nickname = new_name
        db.session.commit()
        flash(f"Запись #{entry_id}: никнейм обновлён на '{new_name}'.", "success")
    else:
        flash(f"Запись #{entry_id}: изменений не найдено.", "info")
    return redirect(url_for('admin_panel'))


@app.route("/admin/update_reason/<int:entry_id>", methods=["GET", "POST"])
@role_required("owner", "admin", "moderator")
def update_reason(entry_id):
    entry = BlacklistEntry.query.get_or_404(entry_id)
    form = UpdateReasonForm(reason=entry.reason)
    if form.validate_on_submit():
        if form.reason.data.strip() != entry.reason:
            entry.reason = form.reason.data.strip()
            db.session.commit()
            flash("Причина изменена.", "success")
        else:
            flash("Новая причина совпадает со старой.", "info")
        return redirect(url_for('admin_panel'))
    return render_template("update_reason.html", form=form, entry=entry)


@app.route("/admin/whitelist", methods=["GET", "POST"])
@role_required("owner")
def admin_whitelist():
    form = WhitelistForm()
    if form.validate_on_submit():
        wl = json.load(open("uuid_list.json", "r", encoding="utf-8"))
        u = form.uuid.data.strip()
        if form.action.data == 'add':
            if u not in wl:
                wl.append(u)
                flash("UUID добавлен в whitelist.", "success")
            else:
                flash("UUID уже в whitelist.", "info")
        else:
            if u in wl:
                wl.remove(u)
                flash("UUID удалён из whitelist.", "success")
            else:
                flash("UUID не найден в whitelist.", "warning")
        json.dump(wl, open("uuid_list.json", "w", encoding="utf-8"), indent=2)
        return redirect(url_for('admin_whitelist'))
    wl_current = json.load(open("uuid_list.json", "r", encoding="utf-8"))
    return render_template("admin_whitelist.html", form=form, whitelist=wl_current)


@app.route('/avatar/<user_uuid>.png')
def avatar(user_uuid):
    url = f"https://minotar.net/helm/{user_uuid}/100.png"
    resp = requests.get(url, timeout=5)
    if resp.status_code != 200:
        abort(resp.status_code)
    out = make_response(resp.content)
    out.headers['Content-Type'] = 'image/png'
    out.headers['Cache-Control'] = 'public, max-age=86400'
    return out


@app.route("/sw.js")
def service_worker():
    return app.send_static_file("service-worker.js")


# Удаление записи из черного списка (доступ для owner и admin)
@app.route("/admin/delete/<int:entry_id>", methods=["POST"])
@role_required("owner", "admin")
def delete_entry(entry_id):
    entry = BlacklistEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash("Запись удалена из ЧС.", "success")
    return redirect(url_for('admin_panel'))


# Список пользователей (admin panel) – доступ только для owner
@app.route("/admin/users", methods=["GET"])
@role_required("owner")
def admin_users():
    users = AdminUser.query.order_by(AdminUser.username).all()
    return render_template('admin_users.html', users=users)

# Удаление пользователя (только для владельца)
@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@role_required("owner")
def delete_user(user_id):
    current = get_jwt_identity()
    u = AdminUser.query.get_or_404(user_id)
    if u.username == current:
        flash("Нельзя удалить себя.", "warning")
    else:
        db.session.delete(u)
        db.session.commit()
        flash("Пользователь удалён.", "success")
    return redirect(url_for('admin_users'))

@app.before_request
def block_sensitive_paths():
    if request.path == '/.env':
        abort(403)
    if request.path.startswith('/asuka'):
        abort(403)
    if any(request.path.startswith(p) for p in ["/.git", "/.aws", "/wp-", "/.ht", "/config", "/settings"]):
        abort(403)


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
    r"""
    Эндпоинт: проверяет ник в черном списке.
    Возвращает реальный UTF-8 JSON без \u-эскейпов.
    """
    nickname = request.args.get('nickname', '').strip()
    if not nickname:
        payload = {'error': 'Параметр nickname обязателен и не может быть пустым'}
        text = json.dumps(payload, ensure_ascii=False)
        return Response(text, status=400, mimetype='application/json')

    entry = BlacklistEntry.query.filter(
        db.func.lower(BlacklistEntry.nickname) == nickname.lower()
    ).first()

    if entry:
        new_uuid = get_uuid_from_nickname(nickname)
        if new_uuid and new_uuid.lower() != entry.uuid.lower():
            entry.uuid = new_uuid
            entry.nickname = nickname
            db.session.commit()

        payload = {
            'in_blacklist': True,
            'nickname': entry.nickname,
            'uuid': entry.uuid,
            'reason': entry.reason,
            'created_at': entry.created_at.isoformat()
        }
    else:
        payload = {'in_blacklist': False}

    text = json.dumps(payload, ensure_ascii=False)
    return Response(text, status=200, mimetype='application/json')

@app.route("/admin/map", methods=["GET"])
@role_required("owner", "admin")
def admin_map():
    return render_template("admin_map.html")

@app.route("/api/fullist", methods=["GET"])
def api_full_blacklist():
    """
    Публичный JSON-эндпоинт, возвращает список всех записей из ЧС.
    """
    entries = BlacklistEntry.query.order_by(BlacklistEntry.created_at.desc()).all()
    payload = []

    for entry in entries:
        payload.append({
            "nickname": entry.nickname,
            "uuid": entry.uuid,
            "reason": entry.reason,
            "created_at": entry.created_at.isoformat()
        })

    return Response(json.dumps(payload, ensure_ascii=False), mimetype="application/json")


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
    app.logger.exception('Unhandled exception:')
    return render_template('500.html'), 500


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
    entries = (
        BlacklistEntry.query
        .order_by(BlacklistEntry.created_at.desc())
        .limit(limit)
        .all()
    )

    # Формируем JSON-пayload
    payload = [
        {
            "nickname": e.nickname,
            "uuid": e.uuid,
            "reason": e.reason,
            "created_at": e.created_at.isoformat()
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
    import time

    now = time.time()
    cutoff = now - 3600  # час назад
    results = []

    try:
        with open("locations.json", "r", encoding="utf-8") as f:
            locations = json.load(f)  # массив объектов
    except (FileNotFoundError, json.JSONDecodeError):
        locations = []

    for entry in locations:
        ts = entry.get("timestamp", 0)
        if ts > cutoff:
            # приводим timestamp к ISO для фронта, если нужно
            entry["timestamp"] = datetime.utcfromtimestamp(ts).isoformat()
            results.append(entry)

    return jsonify(results)


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
        return jsonify(message="POST JSON {uuid,x,y,z} to me"), 200

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON"}), 400

    uuid = data.get("uuid")
    x, y, z = data.get("x"), data.get("y"), data.get("z")
    if not all([uuid, x, y, z]):
        return jsonify({"error": "Fields uuid, x, y, z are required"}), 400

    # load existing, but guard against empty/corrupt JSON
    try:
        with open("locations.json", "r", encoding="utf-8") as f:
            locations = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        locations = []

    # append & prune
    ts_now = time.time()
    locations.append({"uuid": uuid, "x": x, "y": y, "z": z, "timestamp": ts_now})
    cutoff = ts_now - 3600
    locations = [loc for loc in locations if loc.get("timestamp", 0) > cutoff]

    with open("locations.json", "w", encoding="utf-8") as f:
        json.dump(locations, f, indent=2, ensure_ascii=False)

    return jsonify({"success": True}), 200
    
@app.after_request
def set_security_headers(response):
    csp = (
        "default-src 'self'; "
        "frame-src 'self' https://*; "
        "connect-src 'self' https://api.mojang.com https://api.namemc.com https://minotar.net; "
        "img-src 'self' data: https://minotar.net https://avatars.githubusercontent.com; "
        "media-src 'self' data: blob: https://minotar.net; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "worker-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "upgrade-insecure-requests;"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer-when-downgrade'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    return response

if __name__ == '__main__':
    app.run(debug=True)
