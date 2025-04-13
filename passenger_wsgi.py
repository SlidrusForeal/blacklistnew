import sys
import os

# Укажите путь к интерпретатору виртуального окружения для вашего приложения.
INTERP = os.path.expanduser("/var/www/u3085459/data/slidrusforeal-blacklistnew/venv/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Добавляем директорию проекта в PYTHONPATH, чтобы Flask мог найти все модули.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Импортируем экземпляр приложения, который будет использоваться сервером WSGI.
from app import app as application
