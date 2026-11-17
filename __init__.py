import os

from flask import Flask, jsonify
from werkzeug.security import generate_password_hash

from . import api, auth, db, security

DEFAULT_SECRET = "dev-only-change-me"


def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", DEFAULT_SECRET),
        DATABASE=os.environ.get("DATABASE", os.path.join(app.instance_path, "studytrail.sqlite")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",   # set to 1 behind HTTPS
        MAX_CONTENT_LENGTH=64 * 1024,
        PASSWORD_HASH_METHOD="scrypt",
        LOGIN_MAX_FAILURES=5,
        LOGIN_WINDOW_SECONDS=600,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("TESTING") and app.config["SECRET_KEY"] == DEFAULT_SECRET:
        app.logger.warning("Using the default SECRET_KEY. Set SECRET_KEY before deploying.")
    app.config["DUMMY_HASH"] = generate_password_hash("not-a-real-password", method=app.config["PASSWORD_HASH_METHOD"])

    os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)
    db.init_app(app)
    app.before_request(security.guard)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        if resp.mimetype == "application/json":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    for code, msg in ((404, "Not found"), (405, "Method not allowed"), (413, "Request too large")):
        app.register_error_handler(code, lambda e, m=msg, c=code: (jsonify({"error": m}), c))
    return app
