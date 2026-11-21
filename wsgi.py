import os

from app import DEFAULT_SECRET, create_app

if os.environ.get("SECRET_KEY", DEFAULT_SECRET) == DEFAULT_SECRET:
    raise RuntimeError("Set the SECRET_KEY environment variable before running in production.")
app = create_app()
