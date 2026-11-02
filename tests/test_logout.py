import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from database import db

PW = "Passw0rd!x"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    conn = db.get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Asha <b>Rao</b>", "asha@example.com", generate_password_hash(PW)),
    )
    conn.commit()
    conn.close()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def sign_in(client):
    return client.post("/login", data={"email": "asha@example.com", "password": PW})


def test_navbar_logged_out(client):
    html = client.get("/").data
    assert b"Sign in" in html and b"Get started" in html
    assert b"Sign out" not in html


def test_navbar_logged_in_escapes_name(client):
    sign_in(client)
    html = client.get("/").data
    assert b"Sign out" in html
    assert b"Get started" not in html
    assert b'<span class="nav-user">Hello, Asha &lt;b&gt;Rao&lt;/b&gt;</span>' in html


def test_logout_post_redirects_with_toast(client):
    sign_in(client)
    r = client.post("/logout")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    r = client.get("/login")
    assert b"You have been signed out." in r.data
    assert b"Sign out" not in r.data and b"Sign in" in r.data


def test_logout_get_not_allowed_and_keeps_session(client):
    sign_in(client)
    assert client.get("/logout").status_code == 405
    assert b"Sign out" in client.get("/").data


def test_logout_when_logged_out(client):
    r = client.post("/logout")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_deleted_user_clears_session(client):
    sign_in(client)
    conn = db.get_db()
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    html = client.get("/").data
    assert b"Sign in" in html and b"Sign out" not in html
    with client.session_transaction() as s:
        assert "user_id" not in s


@pytest.mark.parametrize("path", ["/login", "/register"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_signed_in_user_redirected_from_auth_pages(client, path, method):
    sign_in(client)
    r = getattr(client, method)(path, data={"email": "x@example.com", "password": "x"})
    assert r.status_code == 302 and r.headers["Location"] == "/"


def test_session_cookie_flags(client):
    r = sign_in(client)
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
