from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime
from functools import wraps
import requests
import time

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
    # Изменено: увеличена длина поля password_hash до 256 символов
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # "owner" или "admin"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<AdminUser {self.username} - {self.role}>"

# Функция для получения UUID на основе никнейма (UUID v5 для стабильности)
def get_uuid_from_nickname(nickname):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, nickname.lower()))

# Декоратор для проверки входа в админ панель
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_user' not in session:
            flash("Требуется вход в админ панель", "warning")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

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
            user_uuid = get_uuid_from_nickname(nickname)
            entry = BlacklistEntry.query.filter_by(uuid=user_uuid).first()
            if entry:
                # Если ник изменился, обновляем его в БД
                if entry.nickname.lower() != nickname.lower():
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

# Страница входа в админ панель
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        admin_user = AdminUser.query.filter_by(username=username).first()
        if admin_user and admin_user.check_password(password):
            session['admin_user'] = admin_user.username
            session['admin_role'] = admin_user.role
            flash("Успешный вход в админ панель", "success")
            return redirect(url_for("admin_panel"))
        else:
            flash("Неверное имя пользователя или пароль", "danger")
    return render_template("admin_login.html")

# Выход из админ панели
@app.route("/admin/logout")
def admin_logout():
    session.pop('admin_user', None)
    session.pop('admin_role', None)
    flash("Вы вышли из админ панели", "info")
    return redirect(url_for("admin_login"))

# Админ панель (защищённый маршрут)
@app.route("/admin", methods=["GET", "POST"])
@admin_login_required
def admin_panel():
    # Обработка добавления новой записи в чёрный список
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

@app.route("/admin/update_nicknames", methods=["POST"])
@admin_login_required
def update_nicknames():
    entries = BlacklistEntry.query.all()
    updated_count = 0
    for entry in entries:
        # Формируем запрос к API Mojang для получения актуального ника по текущему значению поля nickname
        url = f"https://api.mojang.com/users/profiles/minecraft/{entry.nickname}"
        try:
            response = requests.get(url)
            # Если запрос успешен (HTTP 200), возвращаем JSON с полями "id" и "name"
            if response.status_code == 200:
                data = response.json()
                correct_uuid = data.get("id")
                correct_name = data.get("name")
                if correct_uuid and correct_name:
                    # Если сохранённые значения не совпадают с данными от Mojang, обновляем запись
                    if entry.uuid != correct_uuid or entry.nickname != correct_name:
                        entry.uuid = correct_uuid
                        entry.nickname = correct_name
                        updated_count += 1
            else:
                # Если запрос не успешен (например, 204 No Content или другой статус),
                # можно вывести уведомление для конкретного ника
                flash(f"Пользователь {entry.nickname} не найден в Mojang API.", "warning")
        except Exception as e:
            flash(f"Ошибка при запросе для {entry.nickname}: {str(e)}", "danger")
        # Задержка в 1 секунду между запросами для соблюдения лимитов API
        time.sleep(1)
    db.session.commit()
    flash(f"Обновлено {updated_count} записей.", "success")
    return redirect(url_for("admin_panel"))

@app.route("/sw.js")
def service_worker():
    return app.send_static_file("service-worker.js")

# Удаление записи из чёрного списка (админ панель)
@app.route("/admin/delete/<int:entry_id>", methods=["POST"])
@admin_login_required
def delete_entry(entry_id):
    entry = BlacklistEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash("Запись удалена", "success")
    return redirect(url_for("admin_panel"))

if __name__ == '__main__':
    app.run(debug=True)
