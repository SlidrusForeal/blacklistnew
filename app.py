from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime
from functools import wraps
import requests
import time
import json  # Для работы с whitelist и JSON

app = Flask(__name__)
app.secret_key = "aYmi2Tfq1kbW-OlU8-r7cJO1p"  # Ключ для flash-сообщений и сессий

# Настройка подключения к базе PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://postgres:VcqdfYPqFanWbPDsGxJKRCjnIJxDZBpl@yamanote.proxy.rlwy.net:38858/railway"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Модель записи чёрного списка
class BlacklistEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(64), nullable=False)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    reason = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<BlacklistEntry {self.nickname} ({self.uuid})>"

# Модель администратора
class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)  # Увеличенная длина
    role = db.Column(db.String(16), nullable=False)  # "owner", "admin" или "moderator"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<AdminUser {self.username} - {self.role}>"

# Функция для получения UUID на основе никнейма (UUID v5 для стабильности)
def get_uuid_from_nickname(nickname):
    try:
        response = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{nickname}")
        if response.status_code == 200:
            data = response.json()
            uuid = data['id']
            return str(uuid)
        else:
            app.logger.error(f"Mojang API response: {response.status_code}")
            return None
    except Exception as e:
        app.logger.error(f"Ошибка получения UUID: {e}")
        return None

# Декоратор для проверки входа в админ панель
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_user' not in session:
            flash("Требуется вход в админ панель", "warning")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Декоратор для ограничения доступа по ролям (разрешены любые из указанных)
def require_any_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'admin_role' not in session or session['admin_role'].lower() not in [role.lower() for role in roles]:
                flash("Доступ запрещён: недостаточно прав.", "danger")
                return redirect(url_for('admin_login'))
            return f(*args, **kwargs)
        return decorated_function
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
    result = None
    nickname = ""
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        if not nickname:
            flash("Введите никнейм для проверки.", "warning")
        else:
            # Поиск по никнейму без учёта регистра
            entry = BlacklistEntry.query.filter(
                db.func.lower(BlacklistEntry.nickname) == nickname.lower()
            ).first()
            if entry:
                new_uuid = get_uuid_from_nickname(nickname)
                if entry.uuid.lower() != new_uuid.lower():
                    entry.uuid = new_uuid
                    if entry.nickname != nickname:
                        entry.nickname = nickname
                    db.session.commit()
                result = {
                    "message": f"{nickname}, поздравляем – вы в ЧС!",
                    "reason": entry.reason,
                    "color": "red"
                }
            else:
                result = {
                    "message": f"{nickname}, вы не в ЧС! Возможно, вы сменили ник?",
                    "color": "green"
                }
    return render_template("index.html", result=result, nickname=nickname)

@app.route("/fullist")
def fullist():
    entries = BlacklistEntry.query.order_by(BlacklistEntry.nickname.asc()).all()
    return render_template("fullist.html", players=entries)

@app.route("/contacts")
def contacts():
    return render_template("contacts.html")

@app.route("/offline")
def offline():
    return render_template("offline.html")

# Обработчики ошибок
@app.errorhandler(400)
def bad_request(error):
    return render_template("400.html"), 400

@app.errorhandler(401)
def unauthorized(error):
    return render_template("401.html"), 401

@app.errorhandler(403)
def forbidden(error):
    return render_template("403.html"), 403

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(error):
    return render_template("500.html"), 500

# Контекстный процессор для получения текущего года
@app.context_processor
def inject_current_year():
    return {'current_year': lambda: datetime.now().year}

# --- Маршруты админ панели ---
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        admin_user = AdminUser.query.filter_by(username=username).first()
        if admin_user and admin_user.check_password(password):
            session['admin_user'] = admin_user.username
            # Сохраняем роль в нижнем регистре для корректного сравнения
            session['admin_role'] = admin_user.role.lower()
            flash("Успешный вход в админ панель", "success")
            return redirect(url_for("admin_panel"))
        else:
            flash("Неверное имя пользователя или пароль", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop('admin_user', None)
    session.pop('admin_role', None)
    flash("Вы вышли из админ панели", "info")
    return redirect(url_for("admin_login"))

# Функция регистрации пользователей (только для владельца)
@app.route("/admin/register", methods=["GET", "POST"])
@admin_login_required
@require_any_role("owner")
def admin_register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip().lower()
        if not username or not password or not role:
            flash("Все поля должны быть заполнены.", "warning")
        elif role not in ["owner", "admin", "moderator"]:
            flash("Неверное значение роли.", "warning")
        else:
            if AdminUser.query.filter_by(username=username).first():
                flash("Пользователь с таким именем уже существует.", "warning")
            else:
                new_user = AdminUser(username=username, role=role)
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.commit()
                flash("Пользователь успешно зарегистрирован.", "success")
                return redirect(url_for("admin_panel"))
    return render_template("admin_register.html")

# Админ панель для добавления/удаления записей в черном списке (owner и admin)
@app.route("/admin", methods=["GET", "POST"])
@admin_login_required
@require_any_role("owner", "admin")
def admin_panel():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        reason = request.form.get("reason", "").strip()
        if not nickname or not reason:
            flash("Все поля должны быть заполнены", "warning")
        else:
            user_uuid = get_uuid_from_nickname(nickname)
            entry = BlacklistEntry.query.filter_by(uuid=user_uuid).first()
            if entry:
                flash("Элемент с данным никнеймом уже существует", "warning")
            else:
                new_entry = BlacklistEntry(nickname=nickname, uuid=user_uuid, reason=reason)
                db.session.add(new_entry)
                db.session.commit()
                flash("Запись успешно добавлена", "success")
                return redirect(url_for("admin_panel"))
    entries = BlacklistEntry.query.order_by(BlacklistEntry.nickname.asc()).all()
    return render_template("admin_panel.html", entries=entries)

# Обновление никнеймов (доступ только для владельца)
@app.route("/admin/update_nicknames", methods=["POST"])
@admin_login_required
@require_any_role("owner")
def update_nicknames():
    entries = BlacklistEntry.query.all()
    updated_count = 0
    for entry in entries:
        uuid_for_api = entry.uuid.replace("-", "")
        url = f"https://api.mojang.com/user/profile/{uuid_for_api}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()  # Объект с полями "id" и "name"
                correct_name = data.get("name", "").strip()
                app.logger.info(f"Обработка UUID '{entry.uuid}': API вернул NAME: '{correct_name}'")
                if correct_name and entry.nickname.lower() != correct_name.lower():
                    entry.nickname = correct_name
                    updated_count += 1
            else:
                app.logger.warning(f"Не удалось получить данные по UUID {entry.uuid}. Статус: {response.status_code}")
                flash(f"Не удалось обновить данные для {entry.nickname} (UUID: {entry.uuid}). Статус: {response.status_code}", "warning")
        except Exception as e:
            app.logger.error(f"Ошибка при запросе для UUID {entry.uuid}: {str(e)}")
            flash(f"Ошибка при обновлении данных для {entry.nickname}: {str(e)}", "danger")
        time.sleep(1)  # Задержка для соблюдения лимитов API
    db.session.commit()
    flash(f"Обновлено {updated_count} записей.", "success")
    return redirect(url_for("admin_panel"))

# Обновление причины занесения в ЧС (доступ для owner и moderator)
@app.route("/admin/update_reason/<int:entry_id>", methods=["GET", "POST"])
@admin_login_required
@require_any_role("owner", "admin", "moderator")
def update_reason(entry_id):
    entry = BlacklistEntry.query.get_or_404(entry_id)
    if request.method == "POST":
        new_reason = request.form.get("reason", "").strip()
        if not new_reason:
            flash("Поле 'причина' не может быть пустым.", "warning")
        else:
            if entry.reason != new_reason:
                entry.reason = new_reason
                db.session.commit()
                flash("Причина успешно обновлена.", "success")
            else:
                flash("Новая причина совпадает с текущей.", "info")
            return redirect(url_for("admin_panel"))
    return render_template("update_reason.html", entry=entry)

# Редактор whitelist (доступ только для владельца)
@app.route("/admin/whitelist", methods=["GET", "POST"])
@admin_login_required
@require_any_role("owner")
def admin_whitelist():
    if request.method == "POST":
        action = request.form.get("action")
        uuid_value = request.form.get("uuid", "").strip()
        whitelist = load_whitelist()
        if action == "add" and uuid_value:
            if uuid_value not in whitelist:
                whitelist.append(uuid_value)
                flash(f"UUID {uuid_value} добавлен в whitelist", "success")
            else:
                flash(f"UUID {uuid_value} уже существует в whitelist", "warning")
        elif action == "delete" and uuid_value:
            if uuid_value in whitelist:
                whitelist.remove(uuid_value)
                flash(f"UUID {uuid_value} удалён из whitelist", "success")
            else:
                flash(f"UUID {uuid_value} не найден в whitelist", "warning")
        save_whitelist(whitelist)
        return redirect(url_for("admin_whitelist"))
    whitelist = load_whitelist()
    return render_template("admin_whitelist.html", whitelist=whitelist)

# Маршрут для отдачи сервис-воркера
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
    flash("Запись удалена", "success")
    return redirect(url_for("admin_panel"))

# Список пользователей (admin panel) – доступ только для owner
@app.route("/admin/users", methods=["GET"])
@admin_login_required
@require_any_role("owner")
def admin_users():
    users = AdminUser.query.order_by(AdminUser.username.asc()).all()
    return render_template("admin_users.html", users=users)

# Удаление пользователя (только для владельца)
@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@admin_login_required
@require_any_role("owner")
def delete_user(user_id):
    user = AdminUser.query.get_or_404(user_id)
    # Защита: не разрешаем удалить текущего владельца (например, залогиненного)
    if user.username == session.get("admin_user"):
        flash("Нельзя удалить активного пользователя.", "warning")
        return redirect(url_for("admin_users"))
    db.session.delete(user)
    db.session.commit()
    flash("Пользователь удалён.", "success")
    return redirect(url_for("admin_users"))

if __name__ == '__main__':
    app.run(debug=True)
