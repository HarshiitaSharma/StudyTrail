"""CSRF protection, JSON-only writes, login rate limiting and the login_required decorator."""
import functools
import secrets
import time

from flask import current_app, g, jsonify, request, session

from .db import get_db

CSRF_EXEMPT = {"/api/register", "/api/login"}      # no session exists yet
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def api_error(status, message):
    return jsonify({"error": message}), status


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def guard():
    """Runs before every request. Cross-site forms cannot send JSON or custom headers."""
    if not request.path.startswith("/api/") or request.method not in UNSAFE:
        return None
    if request.content_length and request.mimetype != "application/json":
        return api_error(415, "Send JSON with Content-Type: application/json")
    if request.path not in CSRF_EXEMPT:
        sent = request.headers.get("X-CSRF-Token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            return api_error(403, "Missing or invalid CSRF token")
    return None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get("user_id")
        user = None
        if uid is not None:
            user = get_db().execute(
                "SELECT id, email, name, weekly_goal_min FROM users WHERE id = ?", (uid,)).fetchone()
        if user is None:
            session.clear()
            return api_error(401, "Please log in")
        g.user = user
        return view(*args, **kwargs)
    return wrapped


# ---- login rate limiting (in memory: per process, resets on restart) ----
_failures = {}


def _recent(key):
    window = current_app.config["LOGIN_WINDOW_SECONDS"]
    now = time.time()
    _failures[key] = [t for t in _failures.get(key, []) if now - t < window]
    return _failures[key]


def login_locked(key):
    return len(_recent(key)) >= current_app.config["LOGIN_MAX_FAILURES"]


def record_login_failure(key):
    _recent(key).append(time.time())


def clear_login_failures(key):
    _failures.pop(key, None)


def reset_rate_limits():
    _failures.clear()
