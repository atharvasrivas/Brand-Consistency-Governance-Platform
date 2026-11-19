# Vercel entrypoint (Flask is detected from this file). Locally use wsgi.py.
from app import create_app

app = create_app()
