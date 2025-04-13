# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import datetime
from blacklist import BLACKLIST, BLACKLIST_DATA

# Flask и настройка базы данных
app = Flask(__name__)
app.secret_key = "aYmi2Tfq1kbW-OlU8-r7cJO1p"
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://u3085459_default:oblOL1HlVCo9g99Q@localhost/u3085459_users'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# Модель Role
class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)

    def __repr__(self):
        return f'<Role {self.name}>'

# Модель User, расширяющая UserMixin для работы с Flask-Login
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role', backref=db.backref('users', lazy=True))

    def __repr__(self):
        return f'<User {self.username}>'

    def check_password(self, password):
        return check_password_hash(self.password, password)

# Загрузка пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Маршрут для управления черным списком (доступен только для Owner и Admin)
@app.route("/admin/manage_blacklist", methods=["GET", "POST"])
@login_required
def manage_blacklist():
    if current_user.role.name not in ['Owner', 'Admin']:
        flash("Доступ ограничен. Только Owner и Admin могут управлять черным списком.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        uuid = request.form['uuid']
        description = request.form['description']
        action = request.form['action']  # "add" или "remove"

        # Работа с файлом uuid_list.json
        try:
            with open('uuid_list.json', 'r+') as file:
                data = json.load(file)
                if action == 'add':
                    data.append({"uuid": uuid, "description": description})
                elif action == 'remove':
                    data = [item for item in data if item["uuid"] != uuid]
                file.seek(0)
                json.dump(data, file)
                file.truncate()  # обрезаем остатки старого содержимого
        except FileNotFoundError:
            # Если файла нет, создадим его
            data = [{"uuid": uuid, "description": description}] if action == 'add' else []
            with open('uuid_list.json', 'w') as file:
                json.dump(data, file)

        flash(f"UUID {uuid} успешно {action} в черный список.", "success")
        return redirect(url_for('manage_blacklist'))

    # Отображение текущих данных из uuid_list.json
    try:
        with open('uuid_list.json', 'r') as file:
            blacklist = json.load(file)
    except FileNotFoundError:
        blacklist = []

    return render_template('admin_manage_blacklist.html', blacklist=blacklist)

# Маршрут для добавления/редактирования описания (доступны Owner, Admin, Moderator)
@app.route("/admin/add_description/<uuid>", methods=["GET", "POST"])
@login_required
def add_description(uuid):
    if current_user.role.name not in ['Owner', 'Admin', 'Moderator']:
        flash("Доступ ограничен. Только Owner, Admin или Moderator могут добавлять описание.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        description = request.form['description']
        with open('uuid_list.json', 'r+') as file:
            data = json.load(file)
            for item in data:
                if item["uuid"] == uuid:
                    item["description"] = description
                    break
            file.seek(0)
            json.dump(data, file)
            file.truncate()
        flash(f"Описание для UUID {uuid} успешно добавлено.", "success")
        return redirect(url_for('manage_blacklist'))

    return render_template('admin_add_description.html', uuid=uuid)

# Основной маршрут
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
            if normalized in BLACKLIST:
                result = {
                    "message": f"{nickname}, поздравляем – вы в ЧС!",
                    "color": "red"
                }
                # Дополнительная логика (например, конфетти) может быть добавлена здесь
            else:
                result = {
                    "message": f"{nickname}, вы не в ЧС! Возможно, вы сменили ник?",
                    "color": "green"
                }
    return render_template("index.html", result=result, nickname=nickname)

@app.route("/fullist")
def fullist():
    # Сортируем полный список по имени игрока (без учёта регистра)
    sorted_list = sorted(BLACKLIST_DATA, key=lambda x: x["name"].lower())
    return render_template("fullist.html", players=sorted_list)

@app.route("/contacts")
def contacts():
    return render_template("contacts.html")

# Маршруты для авторизации в админ-панели
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Вы успешно вошли в админ-панель.", "success")
            return redirect(url_for("admin_panel"))
        else:
            flash("Неверный логин или пароль.", "danger")
    return render_template("admin_login.html")

@app.route("/admin")
@login_required
def admin_panel():
    # Доступ к админ-панели разрешен только для Owner и Admin
    if current_user.role.name not in ['Owner', 'Admin']:
        flash("У вас нет прав для доступа к админ-панели.", "warning")
        return redirect(url_for("index"))
    return render_template("admin_panel.html")

@app.route("/admin/logout")
@login_required
def admin_logout():
    logout_user()
    flash("Вы вышли из админ-панели.", "info")
    return redirect(url_for("index"))

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

# Маршрут для service worker (доступен по /sw.js)
@app.route("/sw.js")
def sw():
    return app.send_static_file("service-worker.js")

# Инжекция текущего года в шаблоны
@app.context_processor
def inject_current_year():
    return {'current_year': lambda: datetime.now().year}

# Для совместимости с WSGI-серверами
application = app

if __name__ == '__main__':
    app.run(debug=True)
