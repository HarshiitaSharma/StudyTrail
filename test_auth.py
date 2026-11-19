import sqlite3

from conftest import Client


def test_register_logs_in_and_returns_csrf(client):
    r = client.register()
    assert r.status_code == 201
    j = r.get_json()
    assert j["user"]["email"] == "a@example.com" and "password" not in str(j) and j["csrf"]
    assert client.get("/api/me").status_code == 200


def test_register_validation(client):
    bad = [{"name": "", "email": "a@example.com", "password": "longenough"},
           {"name": "A", "email": "not-an-email", "password": "longenough"},
           {"name": "A", "email": "a@example.com", "password": "short"},
           {"name": "A", "email": "a@example.com", "password": 12345678},
           {"name": "A" * 41, "email": "a@example.com", "password": "longenough"}]
    for b in bad:
        assert client.post("/api/register", b).status_code == 400, b


def test_duplicate_email_is_rejected_case_insensitively(client, app):
    client.register("Asha@Example.com")
    assert Client(app).register("asha@example.com").status_code == 409


def test_password_is_stored_hashed(app, user):
    row = sqlite3.connect(app.config["DATABASE"]).execute("SELECT password_hash FROM users").fetchone()
    assert "correct horse" not in row[0] and row[0].startswith("pbkdf2:")


def test_login_logout_cycle(app, user):
    user.post("/api/logout")
    assert user.get("/api/me").status_code == 401
    c2 = Client(app)
    assert c2.login(password="wrong password").status_code == 401
    assert c2.login("nobody@example.com").status_code == 401       # same generic error
    assert c2.login().status_code == 200
    assert c2.get("/api/me").status_code == 200


def test_logout_requires_csrf_token(user):
    assert user.post("/api/logout", csrf=False).status_code == 403
    assert user.get("/api/me").status_code == 200                    # still logged in


def test_wrong_csrf_token_rejected(user):
    r = user.post("/api/subjects", {"name": "X"}, csrf=False, headers={"X-CSRF-Token": "nope"})
    assert r.status_code == 403


def test_writes_must_be_json(client):
    r = client.c.post("/api/register", data="name=a&email=b", content_type="application/x-www-form-urlencoded")
    assert r.status_code == 415


def test_login_is_rate_limited(app):
    c = Client(app)
    c.register()
    c.post("/api/logout")
    for _ in range(5):
        assert c.login(password="bad bad bad").status_code == 401
    assert c.login(password="correct horse").status_code == 429       # locked even with the right password


def test_change_password(app, user):
    assert user.post("/api/password", {"current": "wrong!!!!", "new": "brand new pass"}).status_code == 403
    assert user.post("/api/password", {"current": "correct horse", "new": "short"}).status_code == 400
    assert user.post("/api/password", {"current": "correct horse", "new": "brand new pass"}).status_code == 200
    c2 = Client(app)
    assert c2.login(password="correct horse").status_code == 401
    assert c2.login(password="brand new pass").status_code == 200


def test_delete_account_removes_everything(app, user):
    from conftest import make_subject
    sid = make_subject(user)
    user.post("/api/sessions", {"subject_id": sid, "minutes": 30})
    assert user.delete("/api/account", {"password": "nope nope"}).status_code == 403
    assert user.delete("/api/account", {"password": "correct horse"}).status_code == 204
    db = sqlite3.connect(app.config["DATABASE"])
    assert [db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("users", "subjects", "sessions")] == [0, 0, 0]
    assert user.get("/api/me").status_code == 401


def test_deleted_users_old_cookie_stops_working(app, user):
    cookie_client = user.c
    con = sqlite3.connect(app.config["DATABASE"]); con.execute("DELETE FROM users"); con.commit()
    assert cookie_client.get("/api/me").status_code == 401
