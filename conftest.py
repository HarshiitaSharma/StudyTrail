from datetime import date

import pytest

from app import create_app
from app.security import reset_rate_limits

TODAY = date(2026, 3, 10)


class Client:
    """Test client that remembers the CSRF token, like the real frontend does."""

    def __init__(self, app):
        self.c = app.test_client()
        self.csrf = None

    def req(self, method, url, json=None, csrf=True, **kw):
        headers = kw.pop("headers", {})
        if csrf and self.csrf and method != "GET":
            headers["X-CSRF-Token"] = self.csrf
        r = getattr(self.c, method.lower())(url, json=json, headers=headers, **kw)
        data = r.get_json(silent=True)
        if isinstance(data, dict) and data.get("csrf"):
            self.csrf = data["csrf"]
        return r

    def get(self, url, **kw): return self.req("GET", url, **kw)
    def post(self, url, json=None, **kw): return self.req("POST", url, json, **kw)
    def put(self, url, json=None, **kw): return self.req("PUT", url, json, **kw)
    def patch(self, url, json=None, **kw): return self.req("PATCH", url, json, **kw)
    def delete(self, url, json=None, **kw): return self.req("DELETE", url, json, **kw)

    def register(self, email="a@example.com", name="Asha", password="correct horse"):
        return self.post("/api/register", {"name": name, "email": email, "password": password})

    def login(self, email="a@example.com", password="correct horse"):
        return self.post("/api/login", {"email": email, "password": password})


@pytest.fixture
def app(tmp_path):
    reset_rate_limits()
    return create_app({
        "TESTING": True, "SECRET_KEY": "test", "DATABASE": str(tmp_path / "t.sqlite"),
        "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",       # fast hashing for tests only
        "TODAY_FN": lambda: TODAY,
    })


@pytest.fixture
def client(app):
    return Client(app)


@pytest.fixture
def user(client):
    assert client.register().status_code == 201
    return client


@pytest.fixture
def other(app):
    c = Client(app)
    assert c.register("b@example.com", "Bala").status_code == 201
    return c


def make_subject(c, name="Polity", color="#112233"):
    r = c.post("/api/subjects", {"name": name, "color": color})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]
