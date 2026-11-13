"""Tests for the Spendly "Edit Expense" feature (spec 08-edit-expense.md).

The real expense_tracker.db is never touched: DB_PATH is redirected to a
throwaway temp file BEFORE app.py is imported (app.py seeds the DB on import),
and monkeypatched to a per-test temp DB afterwards.
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

TODAY = date.today()
ORIG_DATE = (TODAY - timedelta(days=5)).isoformat()
PAYLOAD = "'); DROP TABLE expenses;--"


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


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


def _make_expense(
    db_path,
    user_id,
    amount=25.00,
    category=None,
    expense_date=ORIG_DATE,
    description="Original desc",
):
    category = category or CATEGORIES[0]
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _rows(db_path, sql="SELECT * FROM expenses ORDER BY id", params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _row(db_path, expense_id):
    rows = _rows(db_path, "SELECT * FROM expenses WHERE id = ?", (expense_id,))
    return dict(rows[0]) if rows else None


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
    return _make_expense(db_path, user_id)


@pytest.fixture
def foreign_expense_id(db_path, other_user_id):
    return _make_expense(
        db_path,
        other_user_id,
        amount=99.99,
        category=CATEGORIES[1],
        description="Foreign secret",
    )


def _valid(**overrides):
    data = {
        "amount": "42.75",
        "category": CATEGORIES[1],
        "date": TODAY.isoformat(),
        "description": "Updated desc",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #


class TestAuthGuard:
    def test_get_signed_out_redirects_to_login(self, client, expense_id):
        resp = client.get(edit_url(expense_id))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_signed_out_redirects_to_login(self, client, expense_id):
        resp = client.post(edit_url(expense_id), data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_signed_out_does_not_change_row(self, client, db_path, expense_id):
        before = _row(db_path, expense_id)
        client.post(edit_url(expense_id), data=_valid())
        assert _row(db_path, expense_id) == before

    def test_signed_out_nonexistent_id_redirects_to_login(self, client):
        resp = client.get(edit_url(1))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# Ownership / 404                                                     #
# ------------------------------------------------------------------ #


class TestOwnership:
    def test_get_nonexistent_returns_404(self, auth_client):
        assert auth_client.get(edit_url(99999)).status_code == 404

    def test_post_nonexistent_returns_404(self, auth_client, db_path):
        resp = auth_client.post(edit_url(99999), data=_valid())
        assert resp.status_code == 404
        assert _rows(db_path) == []

    def test_get_foreign_expense_returns_404(self, auth_client, foreign_expense_id):
        resp = auth_client.get(edit_url(foreign_expense_id))
        assert resp.status_code == 404
        assert b"Foreign secret" not in resp.data, "Must not leak foreign data"

    def test_post_foreign_expense_returns_404_and_leaves_data(
        self, auth_client, db_path, foreign_expense_id
    ):
        before = _row(db_path, foreign_expense_id)
        resp = auth_client.post(edit_url(foreign_expense_id), data=_valid())
        assert resp.status_code == 404
        assert (
            _row(db_path, foreign_expense_id) == before
        ), "Foreign row must be unchanged"

    def test_foreign_404_matches_nonexistent_404(self, auth_client, foreign_expense_id):
        foreign = auth_client.get(edit_url(foreign_expense_id))
        missing = auth_client.get(edit_url(99999))
        assert foreign.status_code == missing.status_code == 404

    def test_post_with_user_id_in_form_cannot_steal_foreign_row(
        self, auth_client, db_path, user_id, foreign_expense_id, other_user_id
    ):
        resp = auth_client.post(
            edit_url(foreign_expense_id), data=_valid(user_id=str(user_id))
        )
        assert resp.status_code == 404
        assert _row(db_path, foreign_expense_id)["user_id"] == other_user_id

    def test_non_integer_id_returns_404(self, auth_client):
        assert auth_client.get("/expenses/abc/edit").status_code == 404


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #


class TestEditForm:
    def test_get_returns_200_with_heading(self, auth_client, expense_id):
        resp = auth_client.get(edit_url(expense_id))
        assert resp.status_code == 200
        assert b"Edit expense" in resp.data

    def test_get_shows_save_changes_label(self, auth_client, expense_id):
        assert b"Save changes" in auth_client.get(edit_url(expense_id)).data

    def test_get_has_all_fields(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        for field in ("amount", "category", "date", "description"):
            assert f'name="{field}"' in html, f"Missing field {field}"

    def test_get_prefills_amount_date_description(self, auth_client, db_path, user_id):
        eid = _make_expense(
            db_path,
            user_id,
            amount=37.5,
            expense_date="2024-03-15",
            description="PrefillMarker",
        )
        html = auth_client.get(edit_url(eid)).get_data(as_text=True)
        assert "37.5" in html, "Amount should be pre-filled"
        assert "2024-03-15" in html, "Date should be pre-filled"
        assert "PrefillMarker" in html, "Description should be pre-filled"

    def test_get_preselects_current_category(self, auth_client, db_path, user_id):
        eid = _make_expense(db_path, user_id, category=CATEGORIES[2])
        html = auth_client.get(edit_url(eid)).get_data(as_text=True)
        idx = html.index(f'value="{CATEGORIES[2]}"')
        tag_end = html.index(">", idx)
        assert (
            "selected" in html[idx : tag_end + 1]
        ), "Current category must be selected"

    def test_get_blank_description_shows_empty(self, auth_client, db_path, user_id):
        eid = _make_expense(db_path, user_id, description=None)
        resp = auth_client.get(edit_url(eid))
        assert resp.status_code == 200
        assert b"None" not in resp.data, "NULL description must not render as 'None'"

    def test_form_posts_to_edit_url(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        assert edit_url(expense_id) in html, "Form action should be the edit URL"

    def test_form_includes_csrf_token(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        assert 'name="csrf_token"' in html

    def test_cancel_link_points_to_profile(self, auth_client, expense_id):
        html = auth_client.get(edit_url(expense_id)).get_data(as_text=True)
        assert 'href="/profile"' in html

    def test_get_does_not_modify_row(self, auth_client, db_path, expense_id):
        before = _row(db_path, expense_id)
        auth_client.get(edit_url(expense_id))
        assert _row(db_path, expense_id) == before

    def test_description_prefill_is_html_escaped(self, auth_client, db_path, user_id):
        eid = _make_expense(db_path, user_id, description="<script>alert(1)</script>")
        html = auth_client.get(edit_url(eid)).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html


# ------------------------------------------------------------------ #
# Happy path                                                          #
# ------------------------------------------------------------------ #


class TestEditSuccess:
    def test_valid_post_redirects_to_profile(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=_valid())
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_post_flashes_success(self, auth_client, expense_id):
        resp = auth_client.post(
            edit_url(expense_id), data=_valid(), follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"Expense updated." in resp.data

    def test_row_updated_with_new_values(self, auth_client, db_path, expense_id):
        auth_client.post(edit_url(expense_id), data=_valid())
        row = _row(db_path, expense_id)
        assert row["amount"] == pytest.approx(42.75)
        assert row["category"] == CATEGORIES[1]
        assert row["date"] == TODAY.isoformat()
        assert row["description"] == "Updated desc"

    def test_row_updated_in_place_id_user_created_at_unchanged(
        self, auth_client, db_path, expense_id, user_id
    ):
        before = _row(db_path, expense_id)
        auth_client.post(edit_url(expense_id), data=_valid())
        after = _row(db_path, expense_id)
        assert after is not None
        assert after["id"] == before["id"]
        assert after["user_id"] == user_id == before["user_id"]
        assert after["created_at"] == before["created_at"]
        assert len(_rows(db_path)) == 1, "No new row should be created"

    def test_user_id_in_form_is_ignored(
        self, auth_client, db_path, expense_id, user_id, other_user_id
    ):
        auth_client.post(edit_url(expense_id), data=_valid(user_id=str(other_user_id)))
        assert _row(db_path, expense_id)["user_id"] == user_id

    def test_only_target_row_is_updated(
        self, auth_client, db_path, user_id, expense_id
    ):
        other_own = _make_expense(db_path, user_id, amount=1.11, description="Sibling")
        before = _row(db_path, other_own)
        auth_client.post(edit_url(expense_id), data=_valid())
        assert _row(db_path, other_own) == before

    def test_foreign_rows_untouched_by_own_edit(
        self, auth_client, db_path, expense_id, foreign_expense_id
    ):
        before = _row(db_path, foreign_expense_id)
        auth_client.post(edit_url(expense_id), data=_valid())
        assert _row(db_path, foreign_expense_id) == before

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("10.456", 10.46),
            ("10.994", 10.99),
            ("5", 5.0),
            ("0.01", 0.01),
            ("7.5", 7.5),
        ],
    )
    def test_amount_rounded_to_two_decimals(
        self, auth_client, db_path, expense_id, raw, expected
    ):
        auth_client.post(edit_url(expense_id), data=_valid(amount=raw))
        assert _row(db_path, expense_id)["amount"] == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_category_accepted(self, auth_client, db_path, expense_id, category):
        resp = auth_client.post(edit_url(expense_id), data=_valid(category=category))
        assert resp.status_code == 302
        assert _row(db_path, expense_id)["category"] == category

    def test_date_stored_as_iso(self, auth_client, db_path, expense_id):
        past = (TODAY - timedelta(days=40)).isoformat()
        auth_client.post(edit_url(expense_id), data=_valid(date=past))
        assert _row(db_path, expense_id)["date"] == past

    def test_today_date_accepted(self, auth_client, db_path, expense_id):
        resp = auth_client.post(
            edit_url(expense_id), data=_valid(date=TODAY.isoformat())
        )
        assert resp.status_code == 302

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_clearing_description_saves_and_stores_none(
        self, auth_client, db_path, expense_id, blank
    ):
        resp = auth_client.post(edit_url(expense_id), data=_valid(description=blank))
        assert resp.status_code == 302
        assert not _row(db_path, expense_id)[
            "description"
        ], "Description should be cleared"

    def test_missing_description_field_saves(self, auth_client, db_path, expense_id):
        data = _valid()
        del data["description"]
        resp = auth_client.post(edit_url(expense_id), data=data)
        assert resp.status_code == 302
        assert not _row(db_path, expense_id)["description"]

    def test_description_is_stripped(self, auth_client, db_path, expense_id):
        auth_client.post(edit_url(expense_id), data=_valid(description="  Coffee  "))
        assert _row(db_path, expense_id)["description"] == "Coffee"

    def test_description_exactly_200_chars_accepted(
        self, auth_client, db_path, expense_id
    ):
        resp = auth_client.post(
            edit_url(expense_id), data=_valid(description="a" * 200)
        )
        assert resp.status_code == 302
        assert len(_row(db_path, expense_id)["description"]) == 200

    def test_saving_unchanged_values_succeeds(self, auth_client, db_path, expense_id):
        before = _row(db_path, expense_id)
        resp = auth_client.post(
            edit_url(expense_id),
            data={
                "amount": str(before["amount"]),
                "category": before["category"],
                "date": before["date"],
                "description": before["description"],
            },
        )
        assert resp.status_code == 302
        assert _row(db_path, expense_id) == before

    def test_new_values_appear_on_profile(self, auth_client, expense_id):
        auth_client.post(
            edit_url(expense_id),
            data=_valid(amount="321.45", description="EditedMarkerXyz"),
        )
        resp = auth_client.get("/profile?preset=all")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "EditedMarkerXyz" in html, "New description in recent list"
        assert "321.45" in html, "New amount in totals/breakdown"
        assert CATEGORIES[1] in html
        assert "Original desc" not in html, "Old description should be gone"


# ------------------------------------------------------------------ #
# Validation errors                                                   #
# ------------------------------------------------------------------ #


class TestValidation:
    def _assert_rerendered_unchanged(self, resp, db_path, expense_id, before):
        assert resp.status_code == 200, "Validation failure must re-render with 200"
        assert b'name="amount"' in resp.data, "Form should be re-rendered"
        assert _row(db_path, expense_id) == before, "Row must be unchanged"

    @pytest.mark.parametrize(
        "amount",
        [
            "",
            "   ",
            "0",
            "0.00",
            "-5",
            "-0.01",
            "abc",
            "12abc",
            "nan",
            "NaN",
            "inf",
            "-inf",
            "Infinity",
            "0.001",
            "0.004",
        ],
    )
    def test_invalid_amount_rejected(self, auth_client, db_path, expense_id, amount):
        before = _row(db_path, expense_id)
        resp = auth_client.post(edit_url(expense_id), data=_valid(amount=amount))
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    def test_missing_amount_field_rejected(self, auth_client, db_path, expense_id):
        before = _row(db_path, expense_id)
        data = _valid()
        del data["amount"]
        resp = auth_client.post(edit_url(expense_id), data=data)
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    @pytest.mark.parametrize(
        "category",
        ["", "Groceries", "food", "Food ", PAYLOAD, "999"],
    )
    def test_invalid_category_rejected(
        self, auth_client, db_path, expense_id, category
    ):
        before = _row(db_path, expense_id)
        resp = auth_client.post(edit_url(expense_id), data=_valid(category=category))
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    def test_missing_category_field_rejected(self, auth_client, db_path, expense_id):
        before = _row(db_path, expense_id)
        data = _valid()
        del data["category"]
        resp = auth_client.post(edit_url(expense_id), data=data)
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    @pytest.mark.parametrize(
        "bad_date",
        [
            "",
            "not-a-date",
            "2024-13-01",
            "2024-02-30",
            "31/12/2024",
            "2024/01/01",
            "'; --",
        ],
    )
    def test_malformed_date_rejected(self, auth_client, db_path, expense_id, bad_date):
        before = _row(db_path, expense_id)
        resp = auth_client.post(edit_url(expense_id), data=_valid(date=bad_date))
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    def test_missing_date_field_rejected(self, auth_client, db_path, expense_id):
        before = _row(db_path, expense_id)
        data = _valid()
        del data["date"]
        resp = auth_client.post(edit_url(expense_id), data=data)
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    @pytest.mark.parametrize("days_ahead", [1, 30, 3650])
    def test_future_date_rejected(self, auth_client, db_path, expense_id, days_ahead):
        before = _row(db_path, expense_id)
        future = (TODAY + timedelta(days=days_ahead)).isoformat()
        resp = auth_client.post(edit_url(expense_id), data=_valid(date=future))
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    @pytest.mark.parametrize("length", [201, 500, 5000])
    def test_description_over_200_rejected(
        self, auth_client, db_path, expense_id, length
    ):
        before = _row(db_path, expense_id)
        resp = auth_client.post(
            edit_url(expense_id), data=_valid(description="x" * length)
        )
        self._assert_rerendered_unchanged(resp, db_path, expense_id, before)

    def test_no_success_flash_on_error(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=_valid(amount="0"))
        assert b"Expense updated." not in resp.data

    def test_error_page_still_shows_edit_heading(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=_valid(amount="-1"))
        assert b"Edit expense" in resp.data

    def test_error_message_displayed(self, auth_client, expense_id):
        resp = auth_client.post(edit_url(expense_id), data=_valid(amount="-1"))
        html = resp.get_data(as_text=True).lower()
        assert resp.status_code == 200
        assert "error" in html or "amount" in html

    def test_invalid_post_does_not_create_rows(self, auth_client, db_path, expense_id):
        auth_client.post(edit_url(expense_id), data=_valid(amount="abc"))
        assert len(_rows(db_path)) == 1


# ------------------------------------------------------------------ #
# Value preservation after error                                      #
# ------------------------------------------------------------------ #


class TestValuePreservation:
    def test_entered_values_kept_after_error(self, auth_client, expense_id):
        past = (TODAY - timedelta(days=3)).isoformat()
        resp = auth_client.post(
            edit_url(expense_id),
            data={
                "amount": "-42",
                "category": CATEGORIES[2],
                "date": past,
                "description": "KeepMeDescription",
            },
        )
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "-42" in html, "Entered amount should be preserved"
        assert past in html, "Entered date should be preserved"
        assert "KeepMeDescription" in html, "Entered description should be preserved"
        idx = html.index(f'value="{CATEGORIES[2]}"')
        tag_end = html.index(">", idx)
        assert (
            "selected" in html[idx : tag_end + 1]
        ), "Entered category should stay selected"

    def test_entered_values_shown_not_stored_values(self, auth_client, expense_id):
        resp = auth_client.post(
            edit_url(expense_id),
            data=_valid(amount="0", description="EnteredNotStored"),
        )
        html = resp.get_data(as_text=True)
        assert "EnteredNotStored" in html
        assert "Original desc" not in html

    def test_preserved_description_is_html_escaped(self, auth_client, expense_id):
        resp = auth_client.post(
            edit_url(expense_id),
            data=_valid(amount="0", description="<script>alert(1)</script>"),
        )
        assert "<script>alert(1)</script>" not in resp.get_data(as_text=True)


# ------------------------------------------------------------------ #
# SQL safety                                                          #
# ------------------------------------------------------------------ #


class TestSqlSafety:
    def test_sql_in_description_stored_literally(
        self, auth_client, db_path, expense_id
    ):
        resp = auth_client.post(edit_url(expense_id), data=_valid(description=PAYLOAD))
        assert resp.status_code == 302
        assert _row(db_path, expense_id)["description"] == PAYLOAD

    def test_sql_in_description_does_not_alter_database(
        self, auth_client, db_path, expense_id
    ):
        auth_client.post(edit_url(expense_id), data=_valid(description=PAYLOAD))
        tables = {
            r["name"]
            for r in _rows(db_path, "SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"expenses", "users"} <= tables
        assert len(_rows(db_path)) == 1

    def test_profile_renders_after_sql_description(self, auth_client, expense_id):
        auth_client.post(edit_url(expense_id), data=_valid(description=PAYLOAD))
        resp = auth_client.get("/profile?preset=all")
        assert resp.status_code == 200


# ------------------------------------------------------------------ #
# Profile link / navigation                                           #
# ------------------------------------------------------------------ #


class TestProfileEditLink:
    def test_profile_row_has_edit_link(self, auth_client, expense_id):
        html = auth_client.get("/profile?preset=all").get_data(as_text=True)
        assert f'href="{edit_url(expense_id)}"' in html
        assert "Edit" in html

    def test_each_row_has_own_edit_link(self, auth_client, db_path, user_id):
        ids = [_make_expense(db_path, user_id, description=f"Row{i}") for i in range(3)]
        html = auth_client.get("/profile?preset=all").get_data(as_text=True)
        for eid in ids:
            assert f'href="{edit_url(eid)}"' in html, f"Missing edit link for {eid}"

    def test_profile_does_not_link_foreign_expense(
        self, auth_client, expense_id, foreign_expense_id
    ):
        html = auth_client.get("/profile?preset=all").get_data(as_text=True)
        assert f'href="{edit_url(foreign_expense_id)}"' not in html

    def test_edit_link_opens_edit_page(self, auth_client, expense_id):
        resp = auth_client.get(edit_url(expense_id))
        assert resp.status_code == 200

    def test_cancel_target_profile_loads_without_saving(
        self, auth_client, db_path, expense_id
    ):
        before = _row(db_path, expense_id)
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
        assert _row(db_path, expense_id) == before

    def test_url_for_edit_expense_resolves(self, app):
        with app.test_request_context():
            from flask import url_for

            assert url_for("edit_expense", id=7) == "/expenses/7/edit"


# ------------------------------------------------------------------ #
# Add expense regression                                              #
# ------------------------------------------------------------------ #


class TestAddExpenseUnchanged:
    def test_add_page_still_renders_add_mode(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200
        assert b"Edit expense" not in resp.data
        assert b"Save changes" not in resp.data
        for field in ("amount", "category", "date", "description"):
            assert f'name="{field}"'.encode() in resp.data

    def test_add_post_still_inserts_and_flashes(self, auth_client, db_path, user_id):
        resp = auth_client.post("/expenses/add", data=_valid(), follow_redirects=True)
        assert resp.status_code == 200
        assert b"Expense added." in resp.data
        rows = _rows(db_path)
        assert len(rows) == 1 and rows[0]["user_id"] == user_id

    def test_add_form_posts_to_add_url_not_edit(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert "/edit" not in html.split("<form", 1)[1].split(">", 1)[0]


def test_post_without_csrf_token_rejected_when_not_testing(app, client):
    """Edit POSTs are CSRF-protected; the check is only skipped under TESTING."""
    conn = dbmod.get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES ('C', 'csrf@example.com', 'x')"
        )
        uid = conn.execute("SELECT id FROM users WHERE email = 'csrf@example.com'").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, 10, 'Food', ?)",
            (uid, date.today().isoformat()),
        )
        eid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    app.config["TESTING"] = False
    try:
        with client.session_transaction() as sess:
            sess["user_id"] = uid
        resp = client.post(
            f"/expenses/{eid}/edit",
            data={"amount": "99", "category": "Food", "date": date.today().isoformat()},
        )
    finally:
        app.config["TESTING"] = True
    assert resp.status_code == 400
    conn = dbmod.get_db()
    try:
        assert conn.execute("SELECT amount FROM expenses WHERE id = ?", (eid,)).fetchone()[0] == 10
    finally:
        conn.close()
