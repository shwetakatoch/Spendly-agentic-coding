"""Tests for the Spendly "Delete Expense" feature (spec 09-delete-expense.md).

Written from the spec only. The real DB is never touched: DB_PATH is
redirected to a throwaway file before app.py is imported and then
monkeypatched to a per-test temp DB.
"""

import os
import re
import sqlite3
import tempfile
from datetime import date, timedelta

import pytest

import database.db as dbmod

_IMPORT_TMP_DIR = tempfile.mkdtemp(prefix="spendly_import_")
dbmod.DB_PATH = os.path.join(_IMPORT_TMP_DIR, "import_time.db")

import app as app_module  # noqa: E402
from database.db import CATEGORIES  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

RECENT = (date.today() - timedelta(days=1)).isoformat()
# /profile defaults to last month, which would hide yesterday's expenses.
PROFILE_ALL = "/profile?preset=all"


def delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


# ------------------------------------------------------------------ #
# Fixtures / helpers                                                  #
# ------------------------------------------------------------------ #


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test_spendly.db")
    monkeypatch.setattr(dbmod, "DB_PATH", path)
    dbmod.init_db()
    return path


@pytest.fixture
def app(db_path):
    app_module.app.config.update({"TESTING": True, "SECRET_KEY": "test-secret"})
    yield app_module.app
    app_module.app.config.update({"TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(db_path, email, name="Test User"):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash("Passw0rd!x")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _make_expense(
    db_path, user_id, amount=25.00, category=None, description="Original desc"
):
    category = category or CATEGORIES[0]
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, RECENT, description),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _rows(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _exists(db_path, expense_id):
    return bool(_rows(db_path, "SELECT 1 FROM expenses WHERE id = ?", (expense_id,)))


def _count(db_path):
    return _rows(db_path, "SELECT COUNT(*) AS n FROM expenses")[0]["n"]


@pytest.fixture
def user_id(db_path):
    return _make_user(db_path, "tester@example.com")


@pytest.fixture
def other_user_id(db_path):
    return _make_user(db_path, "other@example.com", name="Other User")


@pytest.fixture
def auth_client(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


@pytest.fixture
def expense_id(db_path, user_id):
    return _make_expense(db_path, user_id, amount=777.77, description="Deleteme-unique")


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #


class TestAuthGuard:
    def test_signed_out_post_redirects_to_login(self, client, db_path, user_id):
        eid = _make_expense(db_path, user_id)
        resp = client.post(delete_url(eid))
        assert resp.status_code == 302, "Expected redirect for signed-out user"
        assert "/login" in resp.headers["Location"]

    def test_signed_out_post_deletes_nothing(self, client, db_path, user_id):
        eid = _make_expense(db_path, user_id)
        client.post(delete_url(eid))
        assert _exists(db_path, eid), "Signed-out POST must not delete"

    def test_signed_out_post_nonexistent_id_redirects_to_login(self, client):
        resp = client.post(delete_url(99999))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# Profile page UI                                                     #
# ------------------------------------------------------------------ #


class TestProfileDeleteControl:
    def test_profile_has_delete_form_for_expense(self, auth_client, expense_id):
        html = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        assert f'action="{delete_url(expense_id)}"' in html
        assert "Delete" in html

    def test_delete_form_uses_post(self, auth_client, expense_id):
        html = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        pattern = (
            r'<form[^>]*method="POST"[^>]*action="'
            + re.escape(delete_url(expense_id))
            + r'"|<form[^>]*action="'
            + re.escape(delete_url(expense_id))
            + r'"[^>]*method="POST"'
        )
        assert re.search(pattern, html, re.IGNORECASE), "Delete form must POST"

    def test_delete_form_has_csrf_token_and_confirm_modal(self, auth_client, expense_id):
        html = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        start = html.index(f'action="{delete_url(expense_id)}"')
        end = html.index("</form>", start)
        form = html[start:end]
        assert 'name="csrf_token"' in form, "Delete form needs csrf_token input"
        assert "data-confirm-delete" in form, "Form should open the confirm popup"
        assert 'id="delete-modal"' in html, "Expected a confirmation popup"
        assert "Delete this expense?" in html

    def test_each_recent_expense_has_its_own_delete_form(
        self, auth_client, db_path, user_id
    ):
        ids = [_make_expense(db_path, user_id, description=f"row{i}") for i in range(3)]
        html = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        for eid in ids:
            assert f'action="{delete_url(eid)}"' in html, f"Missing form for {eid}"

    def test_delete_form_not_shown_for_other_users_expense(
        self, auth_client, db_path, other_user_id
    ):
        other_eid = _make_expense(db_path, other_user_id)
        html = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        assert delete_url(other_eid) not in html


# ------------------------------------------------------------------ #
# Happy path                                                          #
# ------------------------------------------------------------------ #


class TestSuccessfulDelete:
    def test_post_redirects_to_profile(self, auth_client, expense_id):
        resp = auth_client.post(delete_url(expense_id))
        assert resp.status_code == 302
        assert resp.headers["Location"].rstrip("/").endswith("/profile")

    def test_post_removes_row_from_db(self, auth_client, db_path, expense_id):
        auth_client.post(delete_url(expense_id))
        assert not _exists(db_path, expense_id), "Row should be gone"

    def test_post_flashes_expense_deleted(self, auth_client, expense_id):
        resp = auth_client.post(delete_url(expense_id), follow_redirects=True)
        assert resp.status_code == 200
        assert b"Expense deleted." in resp.data

    def test_expense_disappears_from_recent_list(self, auth_client, expense_id):
        before = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        assert "Deleteme-unique" in before
        auth_client.post(delete_url(expense_id))
        after = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        assert "Deleteme-unique" not in after

    def test_expense_disappears_from_totals(self, auth_client, expense_id):
        before = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        assert "777.77" in before
        auth_client.post(delete_url(expense_id))
        after = auth_client.get(PROFILE_ALL).get_data(as_text=True)
        assert "777.77" not in after

    def test_category_removed_from_breakdown_when_only_expense(
        self, auth_client, db_path, user_id
    ):
        eid = _make_expense(db_path, user_id, amount=13.00, category=CATEGORIES[1])
        auth_client.post(delete_url(eid))
        remaining = _rows(
            db_path, "SELECT 1 FROM expenses WHERE category = ?", (CATEGORIES[1],)
        )
        assert remaining == []

    def test_flash_not_shown_again_on_next_load(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        auth_client.get("/profile")
        again = auth_client.get("/profile")
        assert b"Expense deleted." not in again.data


# ------------------------------------------------------------------ #
# HTTP semantics                                                      #
# ------------------------------------------------------------------ #


class TestMethods:
    def test_get_returns_405(self, auth_client, expense_id):
        assert auth_client.get(delete_url(expense_id)).status_code == 405

    def test_get_does_not_delete(self, auth_client, db_path, expense_id):
        auth_client.get(delete_url(expense_id))
        assert _exists(db_path, expense_id)

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_other_methods_not_allowed(self, auth_client, db_path, expense_id, method):
        resp = getattr(auth_client, method)(delete_url(expense_id))
        assert resp.status_code == 405
        assert _exists(db_path, expense_id)


# ------------------------------------------------------------------ #
# 404 handling and ownership                                          #
# ------------------------------------------------------------------ #


class TestNotFoundAndOwnership:
    def test_nonexistent_id_returns_404(self, auth_client):
        assert auth_client.post(delete_url(99999)).status_code == 404

    def test_nonexistent_id_changes_nothing(self, auth_client, db_path, expense_id):
        auth_client.post(delete_url(99999))
        assert _exists(db_path, expense_id)

    @pytest.mark.parametrize("bad_id", ["abc", "1.5", "-1x"])
    def test_non_integer_id_returns_404(self, auth_client, bad_id):
        assert auth_client.post(f"/expenses/{bad_id}/delete").status_code == 404

    def test_other_users_expense_returns_404(self, auth_client, db_path, other_user_id):
        other_eid = _make_expense(db_path, other_user_id)
        assert auth_client.post(delete_url(other_eid)).status_code == 404

    def test_other_users_expense_remains_intact(
        self, auth_client, db_path, other_user_id
    ):
        other_eid = _make_expense(
            db_path, other_user_id, amount=55.50, description="theirs"
        )
        auth_client.post(delete_url(other_eid))
        rows = _rows(db_path, "SELECT * FROM expenses WHERE id = ?", (other_eid,))
        assert len(rows) == 1
        assert rows[0]["description"] == "theirs"
        assert rows[0]["amount"] == 55.50
        assert rows[0]["user_id"] == other_user_id

    def test_other_users_expense_response_matches_nonexistent(
        self, auth_client, db_path, other_user_id
    ):
        """Must not reveal existence: same status for foreign and missing ids."""
        other_eid = _make_expense(db_path, other_user_id)
        foreign = auth_client.post(delete_url(other_eid))
        missing = auth_client.post(delete_url(99999))
        assert foreign.status_code == missing.status_code == 404

    def test_no_success_flash_on_404(self, auth_client, db_path, other_user_id):
        other_eid = _make_expense(db_path, other_user_id)
        auth_client.post(delete_url(other_eid))
        resp = auth_client.get("/profile")
        assert b"Expense deleted." not in resp.data

    def test_deleting_twice_second_is_404_not_500(self, auth_client, expense_id):
        first = auth_client.post(delete_url(expense_id))
        second = auth_client.post(delete_url(expense_id))
        assert first.status_code == 302
        assert second.status_code == 404


# ------------------------------------------------------------------ #
# Isolation: other data unaffected                                    #
# ------------------------------------------------------------------ #


class TestSideEffects:
    def test_other_expenses_of_same_user_unaffected(
        self, auth_client, db_path, user_id, expense_id
    ):
        keep1 = _make_expense(db_path, user_id, amount=1.00, description="keep1")
        keep2 = _make_expense(db_path, user_id, amount=2.00, description="keep2")
        auth_client.post(delete_url(expense_id))
        assert _exists(db_path, keep1) and _exists(db_path, keep2)
        assert _count(db_path) == 2

    def test_other_users_expenses_unaffected(
        self, auth_client, db_path, other_user_id, expense_id
    ):
        theirs = _make_expense(db_path, other_user_id, description="theirs")
        auth_client.post(delete_url(expense_id))
        assert _exists(db_path, theirs)

    def test_user_account_unaffected(self, auth_client, db_path, user_id, expense_id):
        auth_client.post(delete_url(expense_id))
        users = _rows(db_path, "SELECT * FROM users WHERE id = ?", (user_id,))
        assert len(users) == 1
        assert users[0]["email"] == "tester@example.com"

    def test_user_still_signed_in_after_delete(self, auth_client, expense_id):
        auth_client.post(delete_url(expense_id))
        assert auth_client.get("/profile").status_code == 200

    def test_exactly_one_row_deleted(self, auth_client, db_path, user_id, expense_id):
        _make_expense(db_path, user_id)
        before = _count(db_path)
        auth_client.post(delete_url(expense_id))
        assert _count(db_path) == before - 1

    def test_expenses_table_survives_after_delete(
        self, auth_client, db_path, expense_id
    ):
        auth_client.post(delete_url(expense_id))
        tables = _rows(
            db_path, "SELECT name FROM sqlite_master WHERE name = 'expenses'"
        )
        assert tables, "expenses table must still exist"


# ------------------------------------------------------------------ #
# CSRF (enforced only when TESTING is off)                            #
# ------------------------------------------------------------------ #


def _token_from(client, path):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)


@pytest.fixture
def csrf_client(app, auth_client):
    app.config["TESTING"] = False
    yield auth_client
    app.config["TESTING"] = True


class TestCsrf:
    def test_post_without_token_returns_400(self, csrf_client, expense_id):
        assert csrf_client.post(delete_url(expense_id)).status_code == 400

    def test_post_without_token_deletes_nothing(self, csrf_client, db_path, expense_id):
        csrf_client.post(delete_url(expense_id))
        assert _exists(db_path, expense_id)

    def test_post_with_wrong_token_returns_400_and_keeps_row(
        self, csrf_client, db_path, expense_id
    ):
        _token_from(csrf_client, "/profile")  # establish a session token
        resp = csrf_client.post(delete_url(expense_id), data={"csrf_token": "nope"})
        assert resp.status_code == 400
        assert _exists(db_path, expense_id)

    def test_post_with_valid_token_deletes(self, csrf_client, db_path, expense_id):
        token = _token_from(csrf_client, "/profile")
        resp = csrf_client.post(delete_url(expense_id), data={"csrf_token": token})
        assert resp.status_code == 302
        assert not _exists(db_path, expense_id)

    def test_token_from_profile_form_works(self, csrf_client, db_path, expense_id):
        html = csrf_client.get(PROFILE_ALL).get_data(as_text=True)
        start = html.index(f'action="{delete_url(expense_id)}"')
        form = html[start : html.index("</form>", start)]
        token = re.search(r'name="csrf_token" value="([0-9a-f]+)"', form).group(1)
        resp = csrf_client.post(delete_url(expense_id), data={"csrf_token": token})
        assert resp.status_code == 302
        assert not _exists(db_path, expense_id)


# ------------------------------------------------------------------ #
# Security / regression                                               #
# ------------------------------------------------------------------ #


class TestRegression:
    def test_sql_injection_in_id_does_not_delete(
        self, auth_client, db_path, expense_id
    ):
        resp = auth_client.post("/expenses/1%20OR%201=1/delete")
        assert resp.status_code == 404
        assert _exists(db_path, expense_id)

    def test_add_expense_page_still_works(self, auth_client):
        assert auth_client.get("/expenses/add").status_code == 200

    def test_edit_expense_page_still_works(self, auth_client, expense_id):
        assert auth_client.get(f"/expenses/{expense_id}/edit").status_code == 200
