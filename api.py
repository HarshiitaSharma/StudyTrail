import csv
import io
import re
from datetime import date, timedelta

from flask import Blueprint, Response, current_app, g, jsonify, request

from . import stats
from .db import get_db
from .security import api_error, login_required

bp = Blueprint("api", __name__, url_prefix="/api")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SUBJECTS = 50


def today():
    fn = current_app.config.get("TODAY_FN")
    return fn() if fn else date.today()


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


# ------------------------------------------------------------------ subjects
@bp.get("/subjects")
@login_required
def list_subjects():
    rows = get_db().execute("SELECT id, name, color FROM subjects WHERE user_id = ? ORDER BY name", (g.user["id"],))
    return jsonify([dict(r) for r in rows])


@bp.post("/subjects")
@login_required
def create_subject():
    d, db = body(), get_db()
    name = str(d.get("name", "")).strip()
    color = d.get("color", "#2F7D6B")
    if not 1 <= len(name) <= 40:
        return api_error(400, "Subject name must be 1 to 40 characters")
    if not isinstance(color, str) or not COLOR_RE.match(color):
        return api_error(400, "Color must look like #A1B2C3")
    if db.execute("SELECT COUNT(*) FROM subjects WHERE user_id = ?", (g.user["id"],)).fetchone()[0] >= MAX_SUBJECTS:
        return api_error(400, f"You can have at most {MAX_SUBJECTS} subjects")
    if db.execute("SELECT 1 FROM subjects WHERE user_id = ? AND name = ?", (g.user["id"], name)).fetchone():
        return api_error(409, "You already have a subject with that name")
    cur = db.execute("INSERT INTO subjects (user_id, name, color) VALUES (?, ?, ?)", (g.user["id"], name, color))
    db.commit()
    return jsonify({"id": cur.lastrowid, "name": name, "color": color}), 201


def _own_subject(sid):
    return get_db().execute("SELECT id, name, color FROM subjects WHERE id = ? AND user_id = ?",
                            (sid, g.user["id"])).fetchone()


@bp.patch("/subjects/<int:sid>")
@login_required
def update_subject(sid):
    row = _own_subject(sid)
    if row is None:
        return api_error(404, "Subject not found")
    d = body()
    name = str(d.get("name", row["name"])).strip()
    color = d.get("color", row["color"])
    if not 1 <= len(name) <= 40:
        return api_error(400, "Subject name must be 1 to 40 characters")
    if not isinstance(color, str) or not COLOR_RE.match(color):
        return api_error(400, "Color must look like #A1B2C3")
    db = get_db()
    if db.execute("SELECT 1 FROM subjects WHERE user_id = ? AND name = ? AND id != ?", (g.user["id"], name, sid)).fetchone():
        return api_error(409, "You already have a subject with that name")
    db.execute("UPDATE subjects SET name = ?, color = ? WHERE id = ? AND user_id = ?", (name, color, sid, g.user["id"]))
    db.commit()
    return jsonify({"id": sid, "name": name, "color": color})


@bp.delete("/subjects/<int:sid>")
@login_required
def delete_subject(sid):
    if _own_subject(sid) is None:
        return api_error(404, "Subject not found")
    db = get_db()
    db.execute("DELETE FROM subjects WHERE id = ? AND user_id = ?", (sid, g.user["id"]))   # sessions cascade
    db.commit()
    return "", 204


# ------------------------------------------------------------------ sessions
@bp.get("/sessions")
@login_required
def list_sessions():
    q, args = ["s.user_id = ?"], [g.user["id"]]
    for param, op in (("from", ">="), ("to", "<=")):
        if request.args.get(param):
            if stats.parse_day(request.args[param]) is None:
                return api_error(400, f"'{param}' must be a date like 2026-03-10")
            q.append(f"s.day {op} ?")
            args.append(request.args[param])
    if request.args.get("subject_id"):
        if not request.args["subject_id"].isdigit():
            return api_error(400, "subject_id must be a number")
        q.append("s.subject_id = ?")
        args.append(int(request.args["subject_id"]))
    limit = min(int(request.args.get("limit", 100)) if request.args.get("limit", "100").isdigit() else 100, 500)
    rows = get_db().execute(
        "SELECT s.id, s.subject_id, sub.name AS subject, sub.color, s.minutes, s.day, s.note "
        "FROM sessions s JOIN subjects sub ON sub.id = s.subject_id "
        f"WHERE {' AND '.join(q)} ORDER BY s.day DESC, s.id DESC LIMIT ?", (*args, limit))
    return jsonify([dict(r) for r in rows])


@bp.post("/sessions")
@login_required
def create_session():
    d = body()
    if not is_int(d.get("subject_id")) or _own_subject(d["subject_id"]) is None:
        return api_error(404, "Subject not found")
    if not is_int(d.get("minutes")) or not 1 <= d["minutes"] <= 1440:
        return api_error(400, "Minutes must be a whole number from 1 to 1440")
    day = d.get("day") or today().isoformat()
    parsed = stats.parse_day(day)
    if parsed is None:
        return api_error(400, "Day must be a date like 2026-03-10")
    if parsed > today() + timedelta(days=1):
        return api_error(400, "Day cannot be in the future")
    note = str(d.get("note", "")).strip()
    if len(note) > 200:
        return api_error(400, "Note must be 200 characters or fewer")
    db = get_db()
    cur = db.execute("INSERT INTO sessions (user_id, subject_id, minutes, day, note) VALUES (?, ?, ?, ?, ?)",
                     (g.user["id"], d["subject_id"], d["minutes"], day, note))
    db.commit()
    return jsonify({"id": cur.lastrowid, "subject_id": d["subject_id"], "minutes": d["minutes"], "day": day, "note": note}), 201


@bp.delete("/sessions/<int:sid>")
@login_required
def delete_session(sid):
    db = get_db()
    cur = db.execute("DELETE FROM sessions WHERE id = ? AND user_id = ?", (sid, g.user["id"]))
    db.commit()
    return ("", 204) if cur.rowcount else api_error(404, "Session not found")


# --------------------------------------------------------------- goal + stats
@bp.put("/goal")
@login_required
def set_goal():
    v = body().get("weekly_goal_min")
    if not is_int(v) or not 0 <= v <= 10080:
        return api_error(400, "Weekly goal must be a whole number of minutes from 0 to 10080")
    db = get_db()
    db.execute("UPDATE users SET weekly_goal_min = ? WHERE id = ?", (v, g.user["id"]))
    db.commit()
    return jsonify({"weekly_goal_min": v})


@bp.get("/stats")
@login_required
def get_stats():
    db, uid, t = get_db(), g.user["id"], today()
    since = (t - timedelta(days=13)).isoformat()
    by_day = {}
    for r in db.execute("SELECT day, SUM(minutes) AS m FROM sessions WHERE user_id = ? AND day >= ? GROUP BY day", (uid, since)):
        by_day[date.fromisoformat(r["day"])] = r["m"]
    all_days = {date.fromisoformat(r["day"]) for r in db.execute(
        "SELECT DISTINCT day FROM sessions WHERE user_id = ? AND day >= ?", (uid, (t - timedelta(days=400)).isoformat()))}
    week_start = (t - timedelta(days=6)).isoformat()
    subjects = db.execute(
        "SELECT sub.id, sub.name, sub.color, SUM(s.minutes) AS minutes FROM sessions s "
        "JOIN subjects sub ON sub.id = s.subject_id WHERE s.user_id = ? AND s.day >= ? "
        "GROUP BY sub.id ORDER BY minutes DESC", (uid, week_start)).fetchall()
    week, goal = stats.window_total(by_day, t, 7), g.user["weekly_goal_min"]
    return jsonify({
        "today": by_day.get(t, 0), "week": week, "goal": goal, "goal_pct": stats.goal_pct(week, goal),
        "streak": stats.streak(all_days, t), "daily": stats.daily_series(by_day, t, 14),
        "by_subject": [dict(r) for r in subjects],
    })


def _csv_cell(v):
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s     # block spreadsheet formula injection


@bp.get("/export.csv")
@login_required
def export_csv():
    rows = get_db().execute(
        "SELECT s.day, sub.name, s.minutes, s.note FROM sessions s JOIN subjects sub ON sub.id = s.subject_id "
        "WHERE s.user_id = ? ORDER BY s.day, s.id", (g.user["id"],))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", "subject", "minutes", "note"])
    for r in rows:
        w.writerow([r["day"], _csv_cell(r["name"]), r["minutes"], _csv_cell(r["note"])])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=studytrail-sessions.csv"})
