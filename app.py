import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, abort, flash, session, jsonify
from datetime import datetime
from functools import wraps
from sqlalchemy import func
from blacklist import BLACKLIST_DATA, BLACKLIST

load_dotenv()  # Загружаем переменные окружения из .env

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise ValueError("Не задан SECRET_KEY в переменных окружения!")

# Конфигурация подключения к базе данных
db_user = os.environ.get("MYSQL_USER")
db_password = os.environ.get("MYSQL_PASSWORD")
db_host = os.environ.get("MYSQL_HOST")
db_name = os.environ.get("MYSQL_DB")

if not all([db_user, db_password, db_host, db_name]):
    raise ValueError("Не все параметры для подключения к базе данных заданы!")

app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
                # Here you might add additional celebration logic
            else:
                result = {
                    "message": f"{nickname}, вы не в ЧС! Возможно, вы сменили ник?",
                    "color": "green"
                }
    return render_template("index.html", result=result, nickname=nickname)


@app.route("/fullist")
def fullist():
    # Sort the blacklist alphabetically by player name (using the full data)
    sorted_list = sorted(BLACKLIST_DATA, key=lambda x: x["name"].lower())
    return render_template("fullist.html", players=sorted_list)


@app.route("/contacts")
def contacts():
    return render_template("contacts.html")


# Error Handlers
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

# Optionally a route for offline (if your service worker uses it)
@app.route("/offline")
def offline():
    return render_template("offline.html")

@app.context_processor
def inject_current_year():
    return {'current_year': lambda: datetime.now().year}


if __name__ == '__main__':
    app.run(debug=True)