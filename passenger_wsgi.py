import sys
import os

# Укажите путь к нужному интерпретатору (например, из виртуального окружения)
INTERP = os.path.expanduser("/var/www/u3085459/data/flaskenv/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Добавляем текущую рабочую директорию в PYTHONPATH
sys.path.append(os.getcwd())

from app import app as application
