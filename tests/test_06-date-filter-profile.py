"""Tests for the profile date filter, written from
.claude/specs/06-date-filter-profile.md.

Expenses are inserted with dates relative to date.today() and each carries a
unique description token so presence in the page can be asserted.
"""
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from database import db

PASSWORD = "Passw0rd!x"
ERROR_MARKERS = ("error", "invalid", "must be", "yyyy-mm-dd", "before")
EMPTY_MARKERS = ("no expense", "nothing", "no transactions", "no spending", "no results")


# ---------- helpers ----------

def prev_month_bounds(today):
    last = today.replace(day=1) - timedelta(days=1)  # handles January wrap
    return last.replace(day=1), last


def insert_expense(user_id, amount, d, token, category="Food"):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, token, d.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_id(email):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()["id"]
    finally:
        conn.close()


def login(client, email, password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def has_any(body, markers):
    low = body.lower()
    return any(m in low for m in markers)


def present(body, token):
    return token in body


@pytest.fixture
def today():
    return date.today()


@pytest.fixture
def uid(user):
    return get_user_id(user["email"])


@pytest.fixture
def seeded(uid, today):
    """Expenses at boundary dates. Returns {token: date}."""
    pm_start, pm_end = prev_month_bounds(today)
    two_months_ago_end = pm_start - timedelta(days=1)
    year_start = today.replace(month=1, day=1)
    data = {
        "TOKTWOMONTHS": two_months_ago_end,
        "TOKPMSTART": pm_start,
        "TOKPMEND": pm_end,
        "TOKTODAY": today,
        "TOKMONTHSTART": today.replace(day=1),
        "TOK29": today - timedelta(days=29),
        "TOK30": today - timedelta(days=30),
        "TOKYEARSTART": year_start,
        "TOKPREVYEAR": year_start - timedelta(days=1),
        "TOKOLD": date(2000, 1, 15),
    }
    for i, (token, d) in enumerate(data.items()):
        insert_expense(uid, 10 + i, d, token)
    return data


@pytest.fixture
def auth_client(client, user):
    login(client, user["email"])
    return client


def expected_tokens(seeded, start=None, end=None):
    return {
        t for t, d in seeded.items()
        if (start is None or d >= start) and (end is None or d <= end)
    }


def assert_tokens(body, seeded, expected):
    # The recent-expenses list is a short list, so presence is only required
    # for the newest few expected rows; absence is required for every
    # out-of-range row.
    newest = sorted(expected, key=lambda t: seeded[t], reverse=True)[:3]
    for token in seeded:
        if token in expected:
            if token in newest:
                assert present(body, token), f"{token} should be shown"
        else:
            assert not present(body, token), f"{token} should NOT be shown"


def get_body(client, **params):
    r = client.get("/profile", query_string=params)
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ---------- auth guard ----------

class TestAuthGuard:
    def test_signed_out_profile_redirects_to_login(self, client):
        r = client.get("/profile")
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]

    def test_signed_out_profile_with_filter_params_redirects_to_login(self, client):
        r = client.get("/profile?preset=all&start=2020-01-01")
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]


# ---------- default view ----------

class TestDefaultView:
    def test_no_params_shows_only_previous_month(self, auth_client, seeded, today):
        s, e = prev_month_bounds(today)
        body = get_body(auth_client)
        assert_tokens(body, seeded, expected_tokens(seeded, s, e))

    def test_no_params_label_shows_previous_month_range(self, auth_client, today):
        s, e = prev_month_bounds(today)
        body = get_body(auth_client)
        assert f"{s.day} {s.strftime('%b %Y')}" in body
        assert f"{e.day} {e.strftime('%b %Y')}" in body

    def test_unknown_preset_falls_back_to_previous_month(self, auth_client, seeded, today):
        s, e = prev_month_bounds(today)
        body = get_body(auth_client, preset="bogus")
        assert_tokens(body, seeded, expected_tokens(seeded, s, e))

    def test_unknown_preset_does_not_error(self, auth_client):
        body = get_body(auth_client, preset="'; DROP TABLE expenses;--")
        assert not has_any(body, ("traceback",))

    def test_january_wrap_helper_gives_december(self):
        s, e = prev_month_bounds(date(2027, 1, 15))
        assert (s, e) == (date(2026, 12, 1), date(2026, 12, 31))

    def test_default_period_total_matches_previous_month(self, auth_client, uid, today):
        s, _ = prev_month_bounds(today)
        insert_expense(uid, 1234.50, s, "TOKTOTAL")
        body = get_body(auth_client)
        assert "1,234.50" in body or "1234.50" in body, "period total missing"


# ---------- presets ----------

class TestPresets:
    def test_last_month_preset(self, auth_client, seeded, today):
        s, e = prev_month_bounds(today)
        body = get_body(auth_client, preset="last_month")
        assert_tokens(body, seeded, expected_tokens(seeded, s, e))

    def test_this_month_preset(self, auth_client, seeded, today):
        body = get_body(auth_client, preset="month")
        assert_tokens(body, seeded, expected_tokens(seeded, today.replace(day=1), today))

    def test_this_month_excludes_previous_month_end(self, auth_client, seeded):
        body = get_body(auth_client, preset="month")
        assert "TOKPMEND" not in body

    def test_last_30_days_preset(self, auth_client, seeded, today):
        body = get_body(auth_client, preset="30d")
        # The exact edge day (29 vs 30 days back) is not pinned by the spec,
        # so only clearly-inside and clearly-outside rows are asserted.
        assert "TOKTODAY" in body
        assert "TOKOLD" not in body
        assert "TOKPREVYEAR" not in body or (today - seeded["TOKPREVYEAR"]).days <= 30

    def test_this_year_preset(self, auth_client, seeded, today):
        body = get_body(auth_client, preset="year")
        assert_tokens(body, seeded, expected_tokens(seeded, today.replace(month=1, day=1), today))

    def test_all_time_preset_shows_everything(self, auth_client, seeded):
        body = get_body(auth_client, preset="all")
        assert_tokens(body, seeded, set(seeded))

    def test_all_time_label(self, auth_client, seeded):
        body = get_body(auth_client, preset="all")
        assert "All time" in body

    @pytest.mark.parametrize("preset,label", [
        ("last_month", "Last month"),
        ("month", "This month"),
        ("30d", "Last 30 days"),
        ("year", "This year"),
        ("all", "All time"),
    ])
    def test_filter_bar_has_preset_link_labels(self, auth_client, preset, label):
        body = get_body(auth_client)
        assert label in body, f"Missing preset label {label}"
        assert f"preset={preset}" in body, f"Missing link for preset {preset}"

    def test_active_preset_is_highlighted(self, auth_client):
        body = get_body(auth_client, preset="year").lower()
        assert "active" in body or "aria-current" in body, "Active preset not marked"

    def test_period_total_updates_with_preset(self, auth_client, uid, today):
        insert_expense(uid, 777.25, today, "TOKTODAYAMT")
        body = get_body(auth_client, preset="month")
        assert "777.25" in body
        default_body = get_body(auth_client)
        assert "777.25" not in default_body


# ---------- custom range ----------

class TestCustomRange:
    def test_single_day_range_is_inclusive_both_ends(self, auth_client, seeded, today):
        d = seeded["TOKPMSTART"]
        body = get_body(auth_client, start=d.isoformat(), end=d.isoformat())
        assert_tokens(body, seeded, expected_tokens(seeded, d, d))
        assert "TOKPMSTART" in body

    def test_range_includes_both_boundaries(self, auth_client, seeded):
        s, e = seeded["TOKPMSTART"], seeded["TOKPMEND"]
        body = get_body(auth_client, start=s.isoformat(), end=e.isoformat())
        assert "TOKPMSTART" in body and "TOKPMEND" in body

    def test_range_excludes_day_before_and_after(self, auth_client, seeded):
        s, e = seeded["TOKPMSTART"], seeded["TOKPMEND"]
        body = get_body(auth_client, start=s.isoformat(), end=e.isoformat())
        assert_tokens(body, seeded, expected_tokens(seeded, s, e))

    def test_only_start_is_open_ended_upward(self, auth_client, seeded, today):
        s = seeded["TOKPMSTART"]
        body = get_body(auth_client, start=s.isoformat())
        assert_tokens(body, seeded, expected_tokens(seeded, start=s))

    def test_only_end_is_open_ended_downward(self, auth_client, seeded):
        e = seeded["TOKPMEND"]
        body = get_body(auth_client, end=e.isoformat())
        assert_tokens(body, seeded, expected_tokens(seeded, end=e))

    def test_custom_range_takes_precedence_over_preset(self, auth_client, seeded):
        s = e = seeded["TOKOLD"]
        body = get_body(auth_client, preset="all", start=s.isoformat(), end=e.isoformat())
        assert_tokens(body, seeded, expected_tokens(seeded, s, e))

    def test_inputs_are_prefilled_after_applying(self, auth_client):
        body = get_body(auth_client, start="2024-03-05", end="2024-04-06")
        assert "2024-03-05" in body
        assert "2024-04-06" in body

    def test_custom_range_label_shown(self, auth_client):
        body = get_body(auth_client, start="2024-03-05", end="2024-04-06")
        assert "5 Mar 2024" in body
        assert "6 Apr 2024" in body

    def test_filter_form_has_date_inputs_and_reset(self, auth_client):
        # Reset only appears on a non-default view (nothing to reset otherwise).
        body = get_body(auth_client, preset="all")
        assert 'name="start"' in body
        assert 'name="end"' in body
        assert 'type="date"' in body
        assert "Reset" in body
        assert "Apply" in body

    def test_reset_link_points_to_plain_profile(self, auth_client):
        body = get_body(auth_client, start="2024-03-05", end="2024-04-06")
        assert 'href="/profile"' in body

    def test_totals_and_categories_follow_custom_range(self, auth_client, uid):
        insert_expense(uid, 500, date(2024, 3, 10), "TOKCATA", category="Bills")
        insert_expense(uid, 321.75, date(2024, 5, 10), "TOKCATB", category="Health")
        body = get_body(auth_client, start="2024-03-01", end="2024-03-31")
        assert "TOKCATA" in body and "TOKCATB" not in body
        assert "Bills" in body
        assert "Health" not in body
        assert "321.75" not in body


# ---------- invalid input ----------

class TestInvalidRange:
    def test_start_after_end_shows_error_and_previous_month(self, auth_client, seeded, today):
        s, e = prev_month_bounds(today)
        r = auth_client.get("/profile?start=2026-11-10&end=2026-11-01")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert has_any(body, ERROR_MARKERS), "Expected inline error message"
        assert_tokens(body, seeded, expected_tokens(seeded, s, e))

    @pytest.mark.parametrize("params", [
        {"start": "garbage"},
        {"end": "garbage"},
        {"start": "2026-13-45"},
        {"start": "2026-02-30", "end": "2026-03-01"},
        {"start": "01/02/2026"},
        {"start": "2026-01-01", "end": "not-a-date"},
        {"start": "' OR 1=1 --"},
    ])
    def test_malformed_dates_do_not_crash_and_show_error(
        self, auth_client, seeded, today, params
    ):
        s, e = prev_month_bounds(today)
        r = auth_client.get("/profile", query_string=params)
        assert r.status_code == 200, "Malformed input must not produce an error status"
        body = r.get_data(as_text=True)
        assert has_any(body, ERROR_MARKERS), "Expected inline error message"
        assert_tokens(body, seeded, expected_tokens(seeded, s, e))

    def test_invalid_range_does_not_leak_all_time(self, auth_client, seeded):
        body = get_body(auth_client, start="garbage", preset="all")
        assert "TOKOLD" not in body, "Fallback should be previous month, not all time"

    def test_valid_range_shows_no_error_text_for_dates(self, auth_client):
        body = get_body(auth_client, start="2024-01-01", end="2024-01-31")
        assert "Start date must be" not in body
        assert "Enter dates as" not in body


# ---------- empty state ----------

class TestEmptyState:
    def test_range_without_expenses_shows_empty_message(self, auth_client, seeded):
        body = get_body(auth_client, start="1990-01-01", end="1990-01-31")
        assert has_any(body, EMPTY_MARKERS), "Expected an empty-state message"
        for token in seeded:
            assert token not in body

    def test_user_with_no_expenses_default_view_is_empty_state(self, auth_client):
        body = get_body(auth_client)
        assert has_any(body, EMPTY_MARKERS)

    def test_empty_range_still_renders_filter_bar(self, auth_client):
        body = get_body(auth_client, start="1990-01-01", end="1990-01-31")
        assert 'name="start"' in body
        assert "1990-01-01" in body

    def test_non_empty_range_has_no_empty_message(self, auth_client, seeded):
        body = get_body(auth_client, preset="all")
        assert not has_any(body, ("no expenses",)), "Empty state shown despite data"


# ---------- isolation between users ----------

class TestUserIsolation:
    @pytest.fixture
    def other_user_expenses(self, app, today):
        conn = db.get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Other Person", "other@example.com", generate_password_hash(PASSWORD)),
            )
            other_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        pm_start, _ = prev_month_bounds(today)
        insert_expense(other_id, 9999.99, pm_start, "OTHERPREV")
        insert_expense(other_id, 8888.88, today, "OTHERTODAY")
        insert_expense(other_id, 7777.77, date(2000, 1, 1), "OTHEROLD")
        return other_id

    @pytest.mark.parametrize("params", [
        {},
        {"preset": "last_month"},
        {"preset": "month"},
        {"preset": "30d"},
        {"preset": "year"},
        {"preset": "all"},
        {"start": "1999-01-01"},
        {"end": "2999-01-01"},
        {"start": "1999-01-01", "end": "2999-01-01"},
    ])
    def test_other_users_expenses_never_appear(
        self, auth_client, seeded, other_user_expenses, params
    ):
        body = auth_client.get("/profile", query_string=params).get_data(as_text=True)
        for token in ("OTHERPREV", "OTHERTODAY", "OTHEROLD"):
            assert token not in body, f"{token} leaked under {params}"
        for amt in ("9999.99", "8888.88", "7777.77"):
            assert amt not in body, f"other user's amount {amt} leaked under {params}"

    def test_other_users_expenses_not_in_totals(self, auth_client, uid, other_user_expenses, today):
        pm_start, _ = prev_month_bounds(today)
        insert_expense(uid, 11, pm_start, "TOKMINE")
        body = get_body(auth_client)
        assert "TOKMINE" in body
        assert "10,010.99" not in body and "10010.99" not in body
