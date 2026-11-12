"""CSRF protection and add-expense hardening (review follow-ups for step 07)."""
import re

import pytest

from database import db


@pytest.fixture
def csrf_client(app, user):
    """A client with CSRF enforcement on (it is skipped while TESTING is True)."""
    app.config["TESTING"] = False
    yield app.test_client()
    app.config["TESTING"] = True


def token_from(client, path):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)


def sign_in(client, user):
    token = token_from(client, "/login")
    return client.post(
        "/login",
        data={"email": user["email"], "password": user["password"], "csrf_token": token},
    )


def expense_count():
    conn = db.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


VALID = {"amount": "10", "category": "Food", "date": "2020-01-01", "description": ""}


def test_post_without_token_is_rejected(csrf_client, user):
    assert csrf_client.post(
        "/login", data={"email": user["email"], "password": user["password"]}
    ).status_code == 400


def test_post_with_wrong_token_is_rejected(csrf_client, user):
    token_from(csrf_client, "/login")
    assert csrf_client.post(
        "/login",
        data={"email": user["email"], "password": user["password"], "csrf_token": "nope"},
    ).status_code == 400


def test_login_works_with_valid_token(csrf_client, user):
    assert sign_in(csrf_client, user).status_code == 302


def test_add_expense_without_token_saves_nothing(csrf_client, user):
    sign_in(csrf_client, user)
    assert csrf_client.post("/expenses/add", data=VALID).status_code == 400
    assert expense_count() == 0


def test_add_expense_with_token_saves(csrf_client, user):
    sign_in(csrf_client, user)
    token = token_from(csrf_client, "/expenses/add")
    resp = csrf_client.post("/expenses/add", data={**VALID, "csrf_token": token})
    assert resp.status_code == 302
    assert expense_count() == 1


def test_logout_requires_token(csrf_client, user):
    sign_in(csrf_client, user)
    assert csrf_client.post("/logout").status_code == 400


def test_token_is_not_the_same_across_sessions(app, user):
    app.config["TESTING"] = False
    try:
        a = token_from(app.test_client(), "/login")
        b = token_from(app.test_client(), "/login")
    finally:
        app.config["TESTING"] = True
    assert a != b


@pytest.mark.parametrize("amount", ["10000000.01", "1e308", "99999999999"])
def test_amount_above_cap_rejected(client, user, amount):
    client.post("/login", data={"email": user["email"], "password": user["password"]})
    resp = client.post("/expenses/add", data={**VALID, "amount": amount})
    assert resp.status_code == 200
    assert expense_count() == 0


def test_amount_at_cap_accepted(client, user):
    client.post("/login", data={"email": user["email"], "password": user["password"]})
    resp = client.post("/expenses/add", data={**VALID, "amount": "10000000"})
    assert resp.status_code == 302
    assert expense_count() == 1


def test_deleted_user_session_redirects_to_login_not_500(client, user):
    client.post("/login", data={"email": user["email"], "password": user["password"]})
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM users")
        conn.commit()
    finally:
        conn.close()
    resp = client.post("/expenses/add", data=VALID)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert expense_count() == 0
