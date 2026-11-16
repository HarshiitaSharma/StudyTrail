import re

from flask import Blueprint, current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .security import (api_error, clear_login_failures, csrf_token, login_locked, login_required,
                       record_login_failure)

bp = Blueprint("auth", __name__, url_prefix="/api")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _hash(password):
    return generate_password_hash(password, method=current_app.config["PASSWORD_HASH_METHOD"])


def _user_json(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "weekly_goal_min": row["weekly_goal_min"]}


def _start_session(user_row):
    session.clear()                      # new session on login prevents session fixation
    session["user_id"] = user_row["id"]
    return jsonify({"user": _user_json(user_row), "csrf": csrf_token()})


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.post("/register")
def register():
    d = _body()
    name = str(d.get("name", "")).strip()
    email = str(d.get("email", "")).strip().lower()
    password = d.get("password")
    if not 1 <= len(name) <= 40:
        return api_error(400, "Name must be 1 to 40 characters")
    if len(email) > 254 or not EMAIL_RE.match(email):
        return api_error(400, "Enter a valid email address")
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        return api_error(400, "Password must be 8 to 128 characters")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return api_error(409, "An account with this email already exists")
    cur = db.execute("INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                     (email, name, _hash(password)))
    db.commit()
    row = db.execute("SELECT id, email, name, weekly_goal_min FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    resp = _start_session(row)
    resp.status_code = 201
    return resp


@bp.post("/login")
def login():
    d = _body()
    email = str(d.get("email", "")).strip().lower()
    password = d.get("password")
    key = (request.remote_addr, email)
    if login_locked(key):
        return api_error(429, "Too many failed attempts. Try again in a few minutes.")
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    # Always run a hash check so response time does not reveal whether the email exists.
    stored = row["password_hash"] if row else current_app.config["DUMMY_HASH"]
    ok = isinstance(password, str) and check_password_hash(stored, password) and row is not None
    if not ok:
        record_login_failure(key)
        return api_error(401, "Wrong email or password")
    clear_login_failures(key)
    return _start_session(row)


@bp.post("/logout")
def logout():
    session.clear()
    return "", 204


@bp.get("/me")
@login_required
def me():
    return jsonify({"user": _user_json(g.user), "csrf": csrf_token()})


@bp.post("/password")
@login_required
def change_password():
    d = _body()
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if not isinstance(d.get("current"), str) or not check_password_hash(row["password_hash"], d["current"]):
        return api_error(403, "Current password is incorrect")
    new = d.get("new")
    if not isinstance(new, str) or not 8 <= len(new) <= 128:
        return api_error(400, "New password must be 8 to 128 characters")
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (_hash(new), row["id"]))
    db.commit()
    return _start_session(row)           # rotate session and CSRF token


@bp.delete("/account")
@login_required
def delete_account():
    d = _body()
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if not isinstance(d.get("password"), str) or not check_password_hash(row["password_hash"], d["password"]):
        return api_error(403, "Password is incorrect")
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (row["id"],))   # subjects and sessions cascade
    db.commit()
    session.clear()
    return "", 204
