import werkzeug.urls
werkzeug.urls.url_encode = werkzeug.urls.urlencode

import json
import os
import time
from datetime import datetime
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (
    Flask, render_template, redirect,
    url_for, session, flash, request, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length

# ─────────────── Конфигурация ───────────────
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('WTF_CSRF_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)


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
    role     = SelectField('Роль',
                choices=[('admin','Admin'),('moderator','Moderator'),('owner','Owner')],
                validators=[DataRequired()])
    submit   = SubmitField('Зарегистрировать')


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
def get_uuid_from_nickname(nickname: str) -> str | None:
    """Получить Minecraft UUID по нику через Mojang API."""
    try:
        resp = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{nickname}")
        if resp.status_code == 200:
            return resp.json().get('id')
    except Exception as e:
        app.logger.error(f"UUID lookup error: {e}")
    return None


# Декоратор для проверки входа в админ панель
def admin_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_user' not in session:
            flash("Требуется вход в админ-панель", "warning")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated


# Декоратор для ограничения доступа по ролям (разрешены любые из указанных)
def require_any_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            role = session.get('admin_role', '').lower()
            if role not in [r.lower() for r in roles]:
                flash("Недостаточно прав.", "danger")
                return redirect(url_for('admin_login'))
            return f(*args, **kwargs)

        return decorated

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
            result = {
                "message": f"{name}, вы в ЧС!",
                "reason": entry.reason,
                "color": "red"
            }
        else:
            result = {
                "message": f"{name}, вы не в ЧС!",
                "color": "green"
            }
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
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        user = AdminUser.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            session['admin_user'] = user.username
            session['admin_role'] = user.role.lower()
            flash("Вход выполнен успешно.", "success")
            return redirect(url_for('admin_panel'))
        flash("Неверный логин или пароль.", "danger")
    return render_template("admin_login.html", form=form)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Вы вышли из админ-панели.", "info")
    return redirect(url_for('admin_login'))


@app.route("/admin/register", methods=["GET", "POST"])
@admin_login_required
@require_any_role("owner")
def admin_register():
    form = AdminRegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        role     = form.role.data

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
@admin_login_required
@require_any_role("owner", "admin", "moderator")
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
@admin_login_required
@require_any_role("owner", "admin")
def update_nicknames():
    entries = BlacklistEntry.query.all()
    count = 0
    for e in entries:
        new_uuid = get_uuid_from_nickname(e.nickname)
        if new_uuid and new_uuid.lower() != e.uuid.lower():
            e.uuid = new_uuid
            count += 1
        time.sleep(1)
    db.session.commit()
    flash(f"UUID обновлены для {count} записей.", "success")
    return redirect(url_for('admin_panel'))


@app.route("/admin/update_reason/<int:entry_id>", methods=["GET", "POST"])
@admin_login_required
@require_any_role("owner", "admin", "moderator")
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
@admin_login_required
@require_any_role("owner")
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


@app.route("/sw.js")
def service_worker():
    return app.send_static_file("service-worker.js")


# Удаление записи из черного списка (доступ для owner и admin)
@app.route("/admin/delete/<int:entry_id>", methods=["POST"])
@admin_login_required
@require_any_role("owner", "admin")
def delete_entry(entry_id):
    entry = BlacklistEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash("Запись удалена из ЧС.", "success")
    return redirect(url_for('admin_panel'))


# Список пользователей (admin panel) – доступ только для owner
@app.route("/admin/users", methods=["GET"])
@admin_login_required
@require_any_role("owner")
def admin_users():
    users = AdminUser.query.order_by(AdminUser.username).all()
    return render_template("admin_users.html", users=users)


# Удаление пользователя (только для владельца)
@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@admin_login_required
@require_any_role("owner")
def delete_user(user_id):
    u = AdminUser.query.get_or_404(user_id)
    if u.username == session.get('admin_user'):
        flash("Нельзя удалить себя.", "warning")
    else:
        db.session.delete(u)
        db.session.commit()
        flash("Пользователь удалён.", "success")
    return redirect(url_for('admin_users'))


@app.after_request
def set_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self';"
        "connect-src 'self' https://api.mojang.com https://api.namemc.com;"
        "img-src 'self' https://minotar.net https://minotar.net *.minotar.net;"
        "script-src 'self' https://cdnjs.cloudflare.com;"
        "object-src 'none';"
        "base-uri 'self';"
    )
    response.headers['X-Frame-Options'] = 'DENY'
    return response

@app.before_request
def block_sensitive_paths():
    if request.path == '/.env':
        abort(403)
    if request.path.startswith('/asuka'):
        abort(403)

if __name__ == '__main__':
    app.run(debug=True)