import os
import json
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, abort, flash, session, jsonify
from datetime import datetime
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, LoginManager, UserMixin, current_user
import requests

load_dotenv()  # Загружаем переменные окружения из .env

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise ValueError("Не задан SECRET_KEY в переменных окружения!")

db_uri = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

# Определение моделей
class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role', backref=db.backref('users', lazy=True))


class Blacklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    uuid = db.Column(db.String(255), nullable=False)
    reason = db.Column(db.Text)
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('blacklisted_users', lazy=True))
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

def get_uuid_for_username(username):
    """
    Получает UUID игрока по его никнейму через Mojang API.
    Возвращает UUID (без дефисов) при успешном запросе или None, если произошла ошибка.
    """
    url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        # Значение 'id' содержит UUID без дефисов.
        return data.get('id')
    else:
        return None

# Маршрут для входа (login)
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Если пользователь уже вошел в систему, перенаправить его, например, в админ-панель:
    if current_user.is_authenticated:
        return redirect(url_for('admin_panel_main'))

    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Вы успешно вошли в систему.', 'success')
            next_page = request.args.get('next') or url_for('admin_panel_main')
            return redirect(next_page)
        else:
            flash('Неверное имя пользователя или пароль.', 'danger')
    return render_template('login.html')


# Маршрут для выхода (logout)
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

# Функция загрузки пользователя по ID
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception as e:
        return None

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    nickname = ""
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        if not nickname:
            flash("Введите никнейм для проверки.", "warning")
        else:
            normalized = nickname.lower()
            # Пытаемся найти запись в таблице Blacklist по имени (без учета регистра)
            entry = Blacklist.query.filter(func.lower(Blacklist.name) == normalized).first()
            if entry:
                result = {
                    "message": f"{nickname}, поздравляем – вы в ЧС!",
                    "color": "red",
                    "reason": entry.reason  # Добавляем причину из базы
                }
            else:
                result = {
                    "message": f"{nickname}, вы не в ЧС! Возможно, вы сменили ник?",
                    "color": "green"
                }
    return render_template("index.html", result=result, nickname=nickname)

@app.route("/fullist")
def fullist():
    # Получаем все записи из базы данных, сортируя по имени (игнорируя регистр)
    entries = Blacklist.query.order_by(func.lower(Blacklist.name)).all()
    return render_template("fullist.html", players=entries)

@app.route("/contacts")
def contacts():
    return render_template("contacts.html")

# Декоратор для проверки ролей
def roles_required(allowed_roles):
    def wrapper(fn):
        @wraps(fn)
        def wrapped_view(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role.name not in allowed_roles:
                flash("У вас нет прав для доступа к этой странице.", "danger")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        return wrapped_view
    return wrapper

# Маршрут главной админ-панели
@app.route("/admin", endpoint="admin_panel_main")
@roles_required(['admin', 'owner','moderator'])
def admin_panel():
    if not current_user.is_authenticated or current_user.role.name not in ['admin', 'owner']:
        flash("У вас нет прав для доступа к этой странице.", "danger")
        return redirect(url_for("index"))
    return render_template("admin_panel.html")

# Маршрут для управления черным списком
@app.route("/admin/blacklist", methods=["GET", "POST"])
@roles_required(['admin', 'owner','moderator'])
def admin_blacklist():
    if not current_user.is_authenticated or current_user.role.name not in ['owner', 'admin', 'moderator']:
        abort(403)  # Доступ запрещён

    if request.method == 'POST':
        nickname = request.form.get("nickname", "").strip()
        reason = request.form.get("reason", "").strip()

        if not nickname:
            flash("Введите никнейм для добавления в чёрный список.", "warning")
        elif not reason:
            flash("Укажите причину для добавления в чёрный список.", "warning")
        else:
            # Получаем UUID по никнейму через Mojang API
            uuid = get_uuid_for_username(nickname)
            if uuid is None:
                flash(f"Не удалось получить UUID для {nickname}. Проверьте правильность написания.", "danger")
            else:
                # Проверяем наличие записи по UUID в базе
                existing_entry = Blacklist.query.filter_by(uuid=uuid).first()
                if existing_entry:
                    # Если запись уже есть, обновляем имя и причину (на случай, если пользователь сменил ник)
                    existing_entry.name = nickname
                    existing_entry.reason = reason
                    db.session.commit()
                    flash(f"Запись для {nickname} успешно обновлена!", "success")
                else:
                    # Если записи ещё нет, создаём новую запись
                    new_entry = Blacklist(
                        name=nickname,
                        uuid=uuid,
                        reason=reason,
                        added_by=current_user.id
                    )
                    db.session.add(new_entry)
                    db.session.commit()
                    flash(f"{nickname} успешно добавлен в чёрный список!", "success")

    # Получаем все записи чёрного списка для отображения
    blacklist = Blacklist.query.order_by(func.lower(Blacklist.name)).all()
    return render_template('admin_blacklist.html', blacklist=blacklist)

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
def page_not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(error):
    return render_template("500.html"), 500

@app.route("/offline")
def offline():
    return render_template("offline.html")

@app.context_processor
def inject_current_year():
    return {'current_year': lambda: datetime.now().year}

if __name__ == '__main__':
    app.run(debug=os.environ.get("FLASK_DEBUG", "True"))
