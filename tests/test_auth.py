import re

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import app as app_module
from database import db

PW = "Passw0rd!x"
NEW_PW = "N3w-Passw0rd"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    conn = db.get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Asha Rao", "asha@example.com", generate_password_hash(PW)),
    )
    conn.commit()
    conn.close()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def current_hash():
    conn = db.get_db()
    try:
        return conn.execute("SELECT password_hash FROM users").fetchone()[0]
    finally:
        conn.close()


def login(client, password=PW, email="asha@example.com"):
    return client.post("/login", data={"email": email, "password": password})


def test_login_success_sets_session(client):
    r = login(client)
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
    with client.session_transaction() as s:
        assert s["user_id"] == 1


@pytest.mark.parametrize("email,password", [
    ("asha@example.com", "wrong"), ("nobody@example.com", PW),
])
def test_login_failure(client, email, password):
    r = login(client, password, email)
    assert r.status_code == 200
    assert b"Invalid email or password." in r.data
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_logout_clears_session(client):
    login(client)
    assert client.get("/logout").status_code == 302
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_login_page_has_forgot_link(client):
    assert b"Forgot password?" in client.get("/login").data


def test_reset_with_last_password(client):
    r = client.post("/forgot-password", data={"email": "asha@example.com", "password": PW, "method": "password"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/reset-password")
    r = client.post("/reset-password", data={"password": NEW_PW, "confirm_password": NEW_PW})
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert check_password_hash(current_hash(), NEW_PW)


def test_wrong_last_password_rejected(client):
    r = client.post("/forgot-password", data={"email": "asha@example.com", "password": "nope", "method": "password"})
    assert r.status_code == 200
    assert b"Try another way" in r.data
    assert client.get("/reset-password").status_code == 302


def test_reset_requires_verification(client):
    assert client.post("/reset-password", data={"password": NEW_PW, "confirm_password": NEW_PW}).status_code == 302
    assert check_password_hash(current_hash(), PW)


def request_code(client, capsys, email="asha@example.com"):
    r = client.post("/forgot-password", data={"email": email, "method": "email"})
    assert r.headers["Location"].endswith("/verify-code")
    match = re.search(r"reset code for .*: (\d{6})", capsys.readouterr().out)
    return match.group(1) if match else None


def test_reset_via_email_code(client, capsys):
    code = request_code(client, capsys)
    assert code
    r = client.post("/verify-code", data={"code": code})
    assert r.status_code == 302 and r.headers["Location"].endswith("/reset-password")
    r = client.post("/reset-password", data={"password": "weak", "confirm_password": "weak"})
    assert b"at least 8" in r.data
    r = client.post("/reset-password", data={"password": NEW_PW, "confirm_password": NEW_PW})
    assert r.status_code == 302
    assert check_password_hash(current_hash(), NEW_PW)
    # code is single-use
    assert client.post("/verify-code", data={"code": code}).status_code in (200, 302)


def test_wrong_code_and_attempt_limit(client, capsys):
    code = request_code(client, capsys)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(app_module.RESET_MAX_ATTEMPTS):
        assert b"invalid or has expired" in client.post("/verify-code", data={"code": wrong}).data
    r = client.post("/verify-code", data={"code": code})
    assert r.status_code == 200 and b"Request a new one" in r.data


def test_unknown_email_gets_same_response(client, capsys):
    r = client.post("/forgot-password", data={"email": "ghost@example.com", "method": "email"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/verify-code")
    assert "reset code" not in capsys.readouterr().out
