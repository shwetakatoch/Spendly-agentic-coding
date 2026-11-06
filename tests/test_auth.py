"""Tests for /register and /login, written from .claude/specs/02-registration.md
and .claude/specs/03-login.md."""
import pytest
from werkzeug.security import check_password_hash

from database import db

GOOD = "Passw0rd!x"


def all_users():
    conn = db.get_db()
    try:
        return conn.execute("SELECT * FROM users").fetchall()
    finally:
        conn.close()


def register(client, name="Asha Rao", email="new@example.com", password=GOOD, confirm=None):
    return client.post("/register", data={
        "name": name, "email": email, "password": password,
        "confirm_password": password if confirm is None else confirm,
    })


def login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


# ---------- registration ----------

def test_register_page_renders_fields(client):
    r = client.get("/register")
    assert r.status_code == 200
    for field in (b'name="name"', b'name="email"', b'name="password"', b'name="confirm_password"'):
        assert field in r.data


def test_register_page_links_to_login(client):
    assert b'href="/login"' in client.get("/register").data


def test_register_success_creates_user_and_returns_200(client):
    r = register(client)
    assert r.status_code == 200  # no server redirect, page redirects client-side
    assert b'http-equiv="refresh"' in r.data
    rows = all_users()
    assert len(rows) == 1
    assert rows[0]["name"] == "Asha Rao"
    assert rows[0]["email"] == "new@example.com"


def test_register_stores_hashed_password(client):
    register(client)
    stored = all_users()[0]["password_hash"]
    assert stored != GOOD
    assert check_password_hash(stored, GOOD)


def test_register_does_not_log_user_in(client):
    register(client)
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_register_normalises_email(client):
    register(client, email="  MiXed@Example.COM ")
    assert all_users()[0]["email"] == "mixed@example.com"


@pytest.mark.parametrize("password,fragment", [
    ("Sh0rt!a", b"at least 8"),
    ("passw0rd!x", b"uppercase"),
    ("PASSW0RD!X", b"lowercase"),
    ("Password!x", b"number"),
    ("Passw0rdxx", b"special"),
])
def test_register_rejects_weak_password(client, password, fragment):
    r = register(client, password=password)
    assert r.status_code == 200
    assert fragment in r.data.lower() or fragment in r.data
    assert all_users() == []


def test_register_rejects_mismatched_confirmation(client):
    r = register(client, confirm="Different1!")
    assert r.status_code == 200
    assert b"Passwords do not match." in r.data
    assert all_users() == []


@pytest.mark.parametrize("email", ["new@example.com", "NEW@Example.com"])
def test_register_rejects_duplicate_email(client, email):
    register(client)
    r = register(client, email=email)
    assert r.status_code == 200
    assert b"An account with this email already exists." in r.data
    assert len(all_users()) == 1


@pytest.mark.parametrize("name,email", [
    ("", "a@example.com"),
    ("   ", "a@example.com"),
    ("Asha", ""),
    ("Asha", "no-at-sign.com"),
    ("Asha", "a@nodot"),
])
def test_register_rejects_missing_or_invalid_fields(client, name, email):
    r = register(client, name=name, email=email)
    assert r.status_code == 200
    assert all_users() == []


def test_register_rejects_empty_password(client):
    r = register(client, password="", confirm="")
    assert r.status_code == 200
    assert all_users() == []


def test_register_failure_keeps_name_and_email_not_password(client):
    r = register(client, name="Keep Me", email="keep@example.com", password="weak")
    assert b"Keep Me" in r.data
    assert b"keep@example.com" in r.data
    assert b'value="weak"' not in r.data


def test_register_redirects_signed_in_user(client, user):
    login(client, user["email"], user["password"])
    for r in (client.get("/register"), register(client)):
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/profile") or r.headers["Location"].endswith("/")


# ---------- login ----------

def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b'name="email"' in r.data and b'name="password"' in r.data


def test_login_page_has_forgot_password_link(client):
    r = client.get("/login")
    assert b"Forgot password?" in r.data
    assert b'href="/forgot-password"' in r.data


def test_login_success_redirects_to_profile_and_sets_session(client, user):
    r = login(client, user["email"], user["password"])
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/profile")
    with client.session_transaction() as s:
        assert s["user_id"] == all_users()[0]["id"]


def test_login_email_is_case_insensitive(client, user):
    r = login(client, "  ASHA@Example.com ", user["password"])
    assert r.status_code == 302


@pytest.mark.parametrize("email,password", [
    ("asha@example.com", "WrongPass1!"),
    ("nobody@example.com", GOOD),
    ("", ""),
])
def test_login_failure_shows_generic_error_and_no_session(client, user, email, password):
    r = login(client, email, password)
    assert r.status_code == 200
    assert b"Invalid email or password." in r.data
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_login_unknown_and_wrong_password_responses_match(client, user):
    a = login(client, "asha@example.com", "WrongPass1!")
    b = login(client, "ghost@example.com", "WrongPass1!")
    assert a.status_code == b.status_code
    assert b"Invalid email or password." in a.data and b"Invalid email or password." in b.data


def test_login_failure_keeps_email(client, user):
    r = login(client, "asha@example.com", "WrongPass1!")
    assert b"asha@example.com" in r.data


def test_login_redirects_signed_in_user_to_profile(client, user):
    login(client, user["email"], user["password"])
    for r in (client.get("/login"), login(client, user["email"], user["password"])):
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/profile")


def test_logout_ends_session_and_redirects_to_login(client, user):
    login(client, user["email"], user["password"])
    r = client.post("/logout")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/login")
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_registered_user_can_log_in(client):
    register(client)
    r = login(client, "new@example.com", GOOD)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/profile")
