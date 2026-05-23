"""WSGI entry for gunicorn: `gunicorn -w 4 -b 0.0.0.0:5001 wsgi:app`."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.web.app import create_app

app = create_app()
