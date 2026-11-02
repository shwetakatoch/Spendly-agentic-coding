import pytest
from werkzeug.security import check_password_hash

import app as app_module
from database import db

GOOD = "Passw0rd!x"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def users():
    conn = db.get_db()
    try:
        return conn.execute("SELECT * FROM users").fetchall()
    finally:
        conn.close()


def post(client, name="Asha Rao", email="asha@example.com", password=GOOD, confirm=None):
    return client.post("/register", data={
        "name": name, "email": email, "password": password,
        "confirm_password": password if confirm is None else confirm,
    })


def test_get_form(client):
    r = client.get("/register")
    assert r.status_code == 200
    assert b'action="/register"' in r.data
    assert b"confirm_password" in r.data
    assert b"data-toggle-password" in r.data


def test_valid_registration_shows_toast_and_redirects(client):
    r = post(client)
    assert r.status_code == 200
    assert b"Account created successfully" in r.data
    assert b'http-equiv="refresh"' in r.data
    assert b"/login" in r.data
    rows = users()
    assert len(rows) == 1
    assert rows[0]["password_hash"] != GOOD
    assert check_password_hash(rows[0]["password_hash"], GOOD)


def test_duplicate_email_case_insensitive(client):
    post(client)
    r = post(client, email="ASHA@Example.com")
    assert b"already exists" in r.data
    assert len(users()) == 1


@pytest.mark.parametrize("kwargs,msg", [
    ({"name": "  "}, b"All fields are required."),
    ({"email": "not-an-email"}, b"valid email"),
    ({"password": "Sh0rt!a"}, b"at least 8"),
    ({"password": "password1!"}, b"uppercase"),
    ({"password": "PASSWORD1!"}, b"lowercase"),
    ({"password": "Password!!"}, b"a number"),
    ({"password": "Password11"}, b"special character"),
    ({"confirm": "Different1!"}, b"do not match"),
])
def test_invalid_input(client, kwargs, msg):
    r = post(client, **kwargs)
    assert r.status_code == 200
    assert msg in r.data
    assert users() == []


def test_failed_submit_keeps_values(client):
    r = post(client, password="short", confirm="short")
    assert b'value="Asha Rao"' in r.data
    assert b'value="asha@example.com"' in r.data
    assert b'value="short"' not in r.data
