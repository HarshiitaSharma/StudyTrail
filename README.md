# StudyTrail 📚

A study-time tracker with **user accounts, a REST API and a database**. Log sessions per subject,
see your streak, weekly goal progress and a 14-day chart, and export everything to CSV.
Built with Python, Flask and SQLite, with a small vanilla JavaScript frontend. It is designed to be
a clear, tested base you can extend (see `ISSUES.md`).

## Run it
```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
flask --app app run --debug                             # http://127.0.0.1:5000
python -m pytest -q                                     # 32 tests
```
With Docker:
```bash
echo "SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')" > .env
docker compose up --build                               # http://localhost:8000
```

## Features
- Register, log in and out, change password, delete account (removes all your data)
- Subjects with colors; study sessions with minutes, date and note
- Stats: today, last 7 days, weekly goal %, day streak, per-subject breakdown, 14-day chart
- CSV export of all your sessions

## API
All endpoints are under `/api`, send and receive JSON, and (except register and login) need a login.
Write requests need the header `X-CSRF-Token` (returned by login, register and `/me`).

| Method | Path | Purpose |
|---|---|---|
| POST | `/register`, `/login`, `/logout` | Accounts and sessions |
| GET | `/me` | Current user and CSRF token |
| POST | `/password` | Change password `{current, new}` |
| DELETE | `/account` | Delete account `{password}` |
| GET, POST | `/subjects` | List or create `{name, color}` |
| PATCH, DELETE | `/subjects/<id>` | Rename, recolor or delete |
| GET, POST | `/sessions` | List (`from`, `to`, `subject_id`, `limit`) or log `{subject_id, minutes, day, note}` |
| DELETE | `/sessions/<id>` | Delete a session |
| PUT | `/goal` | Weekly goal `{weekly_goal_min}` |
| GET | `/stats` | Dashboard numbers |
| GET | `/export.csv` | All sessions as CSV |

## Security design
This is the part to read before changing anything:
- **Passwords** are hashed with scrypt (werkzeug); the plain password is never stored or logged
- **Login** returns the same error for a wrong password and an unknown email, and runs a hash check either way
- **Rate limiting**: 5 failed logins per email and IP per 10 minutes returns 429 (in memory, see ISSUES.md)
- **Sessions**: signed HttpOnly SameSite=Lax cookie, rotated on login and on password change
- **CSRF**: every write needs a per-session token header, and writes must be JSON
- **Isolation**: every query is scoped by `user_id`; another user's id returns 404 (tests cover this)
- **SQL injection**: all queries are parameterized
- **XSS**: the frontend never uses `innerHTML` with user data; a Content-Security-Policy blocks inline scripts
- **CSV injection**: cells starting with `= + - @` are prefixed with `'`
- **Input limits**: field lengths, number ranges, 64 KB request cap, max 50 subjects

## Project layout
```
app/__init__.py   app factory, headers, error handlers
app/auth.py       register, login, logout, password, delete account
app/api.py        subjects, sessions, goal, stats, CSV
app/security.py   CSRF guard, login_required, rate limiter
app/stats.py      pure statistics functions (streak, series)
app/db.py  app/schema.sql
app/static/       index.html, app.js, style.css
tests/            pytest suite (auth, API, isolation, stats)
wsgi.py  Dockerfile  docker-compose.yml  .env.example
```

## Deploy notes
Set a long random `SECRET_KEY` (the production entry point `wsgi.py` refuses to start without one).
Serve over HTTPS and set `COOKIE_SECURE=1`. Use one gunicorn worker until the rate limiter moves out of process memory.
