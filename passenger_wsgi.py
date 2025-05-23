import os
import sys

# Add the application directory to the Python path
INTERP = os.path.expanduser("/var/www/u3085459/data/flaskenv/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Add the application directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import and create the application
from app import app as application
