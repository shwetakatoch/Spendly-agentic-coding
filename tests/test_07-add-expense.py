"""Tests for the Spendly "Add Expense" feature (spec 07-add-expense.md).

The real expense_tracker.db is never touched: DB_PATH is redirected to a
throwaway temp file BEFORE app.py is imported (app.py seeds the DB on import).
"""
import os
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

ADD_URL = "/expenses/add"
TODAY = date.today()


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
    return app_module.app


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


@pytest.fixture
def user_id(db_path):
    return _make_user(db_path, "tester@example.com")


@pytest.fixture
def auth_client(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _rows(db_path, sql="SELECT * FROM expenses ORDER BY id"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _valid(**overrides):
    data = {
        "amount": "12.50",
        "category": CATEGORIES[0],
        "date": TODAY.isoformat(),
        "description": "Lunch",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_signed_out_redirects_to_login(self, client):
        resp = client.get(ADD_URL)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_signed_out_redirects_to_login_and_saves_nothing(self, client, db_path):
        resp = client.post(ADD_URL, data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert _rows(db_path) == [], "Signed-out POST must not insert"


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #

class TestAddForm:
    def test_get_signed_in_renders_form_fields(self, auth_client):
        resp = auth_client.get(ADD_URL)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        for field in ("amount", "category", "date", "description"):
            assert f'name="{field}"' in html, f"Missing field {field}"

    def test_get_date_defaults_to_today(self, auth_client):
        html = auth_client.get(ADD_URL).get_data(as_text=True)
        assert TODAY.isoformat() in html, "Date should default to today"

    def test_category_dropdown_lists_exactly_categories(self, auth_client):
        html = auth_client.get(ADD_URL).get_data(as_text=True)
        start = html.index("<select")
        end = html.index("</select>", start)
        select_html = html[start:end]
        assert select_html.count("<option") >= len(CATEGORIES)
        for cat in CATEGORIES:
            assert f">{cat}<" in select_html or f'value="{cat}"' in select_html, cat

    def test_get_has_cancel_link_to_profile(self, auth_client):
        html = auth_client.get(ADD_URL).get_data(as_text=True)
        assert 'href="/profile"' in html, "Cancel link should point to profile"

    def test_cancel_target_returns_to_profile_without_saving(self, auth_client, db_path):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
        assert _rows(db_path) == []


# ------------------------------------------------------------------ #
# Happy path                                                          #
# ------------------------------------------------------------------ #

class TestAddExpenseSuccess:
    def test_valid_post_redirects_to_profile(self, auth_client):
        resp = auth_client.post(ADD_URL, data=_valid())
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_post_flashes_success_message(self, auth_client):
        resp = auth_client.post(ADD_URL, data=_valid(), follow_redirects=True)
        assert resp.status_code == 200
        assert b"Expense added." in resp.data

    def test_valid_post_inserts_row_with_session_user_id(self, auth_client, db_path, user_id):
        auth_client.post(ADD_URL, data=_valid())
        rows = _rows(db_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == user_id
        assert row["amount"] == pytest.approx(12.50)
        assert row["category"] == CATEGORIES[0]
        assert row["date"] == TODAY.isoformat()
        assert row["description"] == "Lunch"

    def test_user_id_in_form_is_ignored(self, auth_client, db_path, user_id):
        other = _make_user(db_path, "other@example.com")
        auth_client.post(ADD_URL, data=_valid(user_id=str(other)))
        rows = _rows(db_path)
        assert len(rows) == 1
        assert rows[0]["user_id"] == user_id, "user_id must come from session"

    @pytest.mark.parametrize(
        "raw,expected",
        [("10.456", 10.46), ("10.994", 10.99), ("5", 5.0), ("0.01", 0.01), ("7.5", 7.5)],
    )
    def test_amount_rounded_to_two_decimals(self, auth_client, db_path, raw, expected):
        auth_client.post(ADD_URL, data=_valid(amount=raw))
        rows = _rows(db_path)
        assert len(rows) == 1
        assert rows[0]["amount"] == pytest.approx(expected, abs=1e-9)

    def test_date_stored_as_iso(self, auth_client, db_path):
        past = (TODAY - timedelta(days=10)).isoformat()
        auth_client.post(ADD_URL, data=_valid(date=past))
        assert _rows(db_path)[0]["date"] == past

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_listed_category_accepted(self, auth_client, db_path, category):
        auth_client.post(ADD_URL, data=_valid(category=category))
        rows = _rows(db_path)
        assert len(rows) == 1 and rows[0]["category"] == category

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_description_saves_fine(self, auth_client, db_path, blank):
        resp = auth_client.post(ADD_URL, data=_valid(description=blank))
        assert resp.status_code == 302
        rows = _rows(db_path)
        assert len(rows) == 1
        assert not rows[0]["description"], "Blank description stored as NULL/empty"

    def test_missing_description_field_saves_fine(self, auth_client, db_path):
        data = _valid()
        del data["description"]
        resp = auth_client.post(ADD_URL, data=data)
        assert resp.status_code == 302
        assert len(_rows(db_path)) == 1

    def test_description_is_stripped(self, auth_client, db_path):
        auth_client.post(ADD_URL, data=_valid(description="  Coffee  "))
        assert _rows(db_path)[0]["description"] == "Coffee"

    def test_description_of_exactly_200_chars_accepted(self, auth_client, db_path):
        auth_client.post(ADD_URL, data=_valid(description="a" * 200))
        rows = _rows(db_path)
        assert len(rows) == 1 and len(rows[0]["description"]) == 200

    def test_new_expense_appears_on_profile_all_time(self, auth_client):
        auth_client.post(
            ADD_URL, data=_valid(amount="321.45", description="UniqueMarkerXyz")
        )
        resp = auth_client.get("/profile?preset=all")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "UniqueMarkerXyz" in html, "Should be in recent list"
        assert "321.45" in html, "Should be in totals/breakdown"
        assert CATEGORIES[0] in html

    def test_expense_not_visible_to_other_user(self, auth_client, db_path, client):
        auth_client.post(ADD_URL, data=_valid(description="PrivateMarkerQ"))
        other = _make_user(db_path, "other2@example.com")
        with client.session_transaction() as sess:
            sess["user_id"] = other
        html = client.get("/profile?preset=all").get_data(as_text=True)
        assert "PrivateMarkerQ" not in html


# ------------------------------------------------------------------ #
# Validation errors                                                   #
# ------------------------------------------------------------------ #

class TestValidation:
    @pytest.mark.parametrize(
        "amount",
        ["", "   ", "0", "0.00", "-5", "-0.01", "abc", "12abc", "nan", "NaN",
         "inf", "-inf", "Infinity", "0.001", "0.004"],
    )
    def test_invalid_amount_shows_error_and_saves_nothing(self, auth_client, db_path, amount):
        resp = auth_client.post(ADD_URL, data=_valid(amount=amount))
        assert resp.status_code == 200, f"Amount {amount!r} must re-render, not 500/redirect"
        assert b'name="amount"' in resp.data, "Form should be re-rendered"
        assert _rows(db_path) == [], f"Amount {amount!r} must not be saved"

    def test_missing_amount_field_shows_error(self, auth_client, db_path):
        data = _valid()
        del data["amount"]
        resp = auth_client.post(ADD_URL, data=data)
        assert resp.status_code == 200
        assert _rows(db_path) == []

    @pytest.mark.parametrize(
        "category", ["", "Groceries", "food", "Food ", "'; DROP TABLE expenses;--", "999"]
    )
    def test_invalid_category_rejected(self, auth_client, db_path, category):
        resp = auth_client.post(ADD_URL, data=_valid(category=category))
        assert resp.status_code == 200
        assert _rows(db_path) == []

    def test_missing_category_field_rejected(self, auth_client, db_path):
        data = _valid()
        del data["category"]
        resp = auth_client.post(ADD_URL, data=data)
        assert resp.status_code == 200
        assert _rows(db_path) == []

    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "2024-13-01", "2024-02-30", "31/12/2024", "2024/01/01", "'; --"],
    )
    def test_malformed_date_rejected(self, auth_client, db_path, bad_date):
        resp = auth_client.post(ADD_URL, data=_valid(date=bad_date))
        assert resp.status_code == 200, f"Date {bad_date!r} must re-render"
        assert _rows(db_path) == []

    def test_missing_date_field_rejected(self, auth_client, db_path):
        data = _valid()
        del data["date"]
        resp = auth_client.post(ADD_URL, data=data)
        assert resp.status_code == 200
        assert _rows(db_path) == []

    @pytest.mark.parametrize("days_ahead", [1, 30, 3650])
    def test_future_date_rejected(self, auth_client, db_path, days_ahead):
        future = (TODAY + timedelta(days=days_ahead)).isoformat()
        resp = auth_client.post(ADD_URL, data=_valid(date=future))
        assert resp.status_code == 200
        assert _rows(db_path) == []

    def test_today_date_is_accepted(self, auth_client, db_path):
        resp = auth_client.post(ADD_URL, data=_valid(date=TODAY.isoformat()))
        assert resp.status_code == 302
        assert len(_rows(db_path)) == 1

    @pytest.mark.parametrize("length", [201, 500, 5000])
    def test_description_over_200_chars_rejected(self, auth_client, db_path, length):
        resp = auth_client.post(ADD_URL, data=_valid(description="x" * length))
        assert resp.status_code == 200
        assert _rows(db_path) == []

    def test_error_message_is_displayed(self, auth_client):
        resp = auth_client.post(ADD_URL, data=_valid(amount="-1"))
        html = resp.get_data(as_text=True).lower()
        assert "error" in html or "amount" in html, "Inline error area expected"
        assert resp.status_code == 200

    def test_no_success_flash_on_validation_error(self, auth_client):
        resp = auth_client.post(ADD_URL, data=_valid(amount="0"))
        assert b"Expense added." not in resp.data


# ------------------------------------------------------------------ #
# Value preservation after error                                      #
# ------------------------------------------------------------------ #

class TestValuePreservation:
    def test_entered_values_kept_after_error(self, auth_client):
        past = (TODAY - timedelta(days=3)).isoformat()
        resp = auth_client.post(
            ADD_URL,
            data={
                "amount": "-42",
                "category": CATEGORIES[2],
                "date": past,
                "description": "KeepMeDescription",
            },
        )
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "-42" in html, "Amount should be preserved"
        assert past in html, "Date should be preserved"
        assert "KeepMeDescription" in html, "Description should be preserved"
        # selected category preserved
        idx = html.index(f'value="{CATEGORIES[2]}"')
        option_tag_end = html.index(">", idx)
        assert "selected" in html[idx:option_tag_end + 1], "Category should stay selected"

    def test_preserved_description_is_html_escaped(self, auth_client):
        resp = auth_client.post(
            ADD_URL, data=_valid(amount="0", description='<script>alert(1)</script>')
        )
        html = resp.get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html, "Must be escaped"


# ------------------------------------------------------------------ #
# SQL injection / literal storage                                     #
# ------------------------------------------------------------------ #

class TestSqlSafety:
    PAYLOAD = "'); DROP TABLE expenses;--"

    def test_sql_in_description_stored_literally(self, auth_client, db_path):
        resp = auth_client.post(ADD_URL, data=_valid(description=self.PAYLOAD))
        assert resp.status_code == 302
        rows = _rows(db_path)
        assert len(rows) == 1
        assert rows[0]["description"] == self.PAYLOAD

    def test_sql_in_description_does_not_alter_database(self, auth_client, db_path):
        auth_client.post(ADD_URL, data=_valid(description=self.PAYLOAD))
        tables = {r["name"] for r in _rows(db_path, "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "expenses" in tables and "users" in tables
        # table still usable for a second insert
        auth_client.post(ADD_URL, data=_valid(description="second"))
        assert len(_rows(db_path)) == 2

    def test_sql_description_renders_on_profile(self, auth_client):
        auth_client.post(ADD_URL, data=_valid(description=self.PAYLOAD))
        resp = auth_client.get("/profile?preset=all")
        assert resp.status_code == 200


# ------------------------------------------------------------------ #
# Navigation links                                                    #
# ------------------------------------------------------------------ #

class TestNavLinks:
    def test_navbar_has_add_expense_link_when_signed_in(self, auth_client):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert f'href="{ADD_URL}"' in html

    def test_profile_has_add_expense_link(self, auth_client):
        html = auth_client.get("/profile?preset=all").get_data(as_text=True)
        assert html.count(f'href="{ADD_URL}"') >= 2, "Expected navbar and profile links"

    def test_navbar_hides_add_expense_link_when_signed_out(self, client):
        html = client.get("/").get_data(as_text=True)
        assert f'href="{ADD_URL}"' not in html

    def test_add_expense_url_for_resolves(self, app):
        with app.test_request_context():
            from flask import url_for
            assert url_for("add_expense") == ADD_URL
