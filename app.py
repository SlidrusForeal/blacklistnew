# app.py
from flask import Flask, render_template, request, redirect, url_for, abort, flash
from blacklist import BLACKLIST, BLACKLIST_DATA
from datetime import datetime

app = Flask(__name__)
app.secret_key = "aYmi2Tfq1kbW-OlU8-r7cJO1p"  # required for flashing messages

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
