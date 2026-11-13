import math
import os
import re
import secrets
import sqlite3
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask, abort, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import CATEGORIES, get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

RESET_CODE_TTL = timedelta(minutes=10)
RESET_MAX_ATTEMPTS = 5
MAX_DESCRIPTION_LENGTH = 200
MAX_AMOUNT = 10_000_000

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def password_error(password, confirm):
    """Return a message if the password is weak or doesn't match, else None."""
    if password != confirm:
        return "Passwords do not match."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must contain an uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must contain a lowercase letter."
    if not re.search(r"[0-9]", password):
        return "Password must contain a number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must contain a special character."
    return None


def already_signed_in():
    return session.get("user_id") is not None


def login_required(view):
    """Redirect to the login page unless a user is signed in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not already_signed_in():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    """Return this session's CSRF token, creating it on first use."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.before_request
def check_csrf():
    """Reject POSTs whose form token doesn't match the session's token."""
    # Skipped under TESTING so existing tests can post bare forms.
    if request.method != "POST" or app.config.get("TESTING"):
        return
    sent = request.form.get("csrf_token", "").encode()
    expected = session.get("csrf_token", "").encode()
    if not expected or not secrets.compare_digest(sent, expected):
        abort(400)


def find_user(conn, email):
    return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


@app.context_processor
def inject_current_user():
    """Expose the signed-in user (or None) to every template."""
    user_id = session.get("user_id")
    if user_id is None:
        return {"current_user": None}
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        session.clear()
        return {"current_user": None}
    return {"current_user": {"id": row["id"], "name": row["name"]}}


@app.after_request
def no_store(response):
    """Stop browsers caching pages, so Back after sign-out re-checks the session."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if already_signed_in():
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    def fail(message):
        return render_template("register.html", error=message, name=name, email=email)

    if not name or not email or not password or not confirm:
        return fail("All fields are required.")
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        return fail("Please enter a valid email address.")
    message = password_error(password, confirm)
    if message:
        return fail(message)

    duplicate = "An account with this email already exists."
    conn = get_db()
    try:
        if find_user(conn, email):
            return fail(duplicate)
        try:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return fail(duplicate)
    finally:
        conn.close()

    return render_template("register.html", success_redirect=url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if already_signed_in():
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    conn = get_db()
    try:
        user = find_user(conn, email)
    finally:
        conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.", email=email)

    session.clear()
    session["user_id"] = user["id"]
    flash(f"Welcome back, {user['name']}!", "success")
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Forgot password                                                     #
# ------------------------------------------------------------------ #

def send_reset_code(user):
    """Store a hashed 6-digit code for the user and "send" it.

    Delivery is console-only for now: the code is printed to the server log.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (datetime.now(timezone.utc) + RESET_CODE_TTL).isoformat()
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO password_resets "
            "(user_id, code_hash, expires_at, attempts) VALUES (?, ?, ?, 0)",
            (user["id"], generate_password_hash(code), expires),
        )
        conn.commit()
    finally:
        conn.close()
    print(f"[Spendly] Password reset code for {user['email']}: {code}", flush=True)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    email = request.form.get("email", "").strip().lower()
    method = request.form.get("method", "password")
    password = request.form.get("password", "")

    if not email:
        return render_template("forgot_password.html", error="Please enter your email address.")

    conn = get_db()
    try:
        user = find_user(conn, email)
    finally:
        conn.close()

    if method == "email":
        # Same response whether or not the account exists.
        if user:
            send_reset_code(user)
        session.pop("reset_user_id", None)
        session["reset_email"] = email
        flash("If an account exists for that email, we've sent a verification code.", "info")
        return redirect(url_for("verify_code"))

    if user and password and check_password_hash(user["password_hash"], password):
        session.pop("reset_email", None)
        session["reset_user_id"] = user["id"]
        return redirect(url_for("reset_password"))

    return render_template(
        "forgot_password.html",
        error="That password doesn't match. Try again, or choose \"Try another way\".",
        email=email,
    )


@app.route("/verify-code", methods=["GET", "POST"])
def verify_code():
    email = session.get("reset_email")
    if not email:
        return redirect(url_for("forgot_password"))
    if request.method == "GET":
        return render_template("verify_code.html", email=email)

    if request.form.get("action") == "resend":
        conn = get_db()
        try:
            user = find_user(conn, email)
        finally:
            conn.close()
        if user:
            send_reset_code(user)
        flash("A new code has been sent if the account exists.", "info")
        return redirect(url_for("verify_code"))

    code = request.form.get("code", "").strip()
    invalid = "That code is invalid or has expired."
    conn = get_db()
    try:
        user = find_user(conn, email)
        row = None
        if user:
            row = conn.execute(
                "SELECT * FROM password_resets WHERE user_id = ?", (user["id"],)
            ).fetchone()
        if not row:
            return render_template("verify_code.html", email=email, error=invalid)

        expired = datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc)
        if expired or row["attempts"] >= RESET_MAX_ATTEMPTS:
            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user["id"],))
            conn.commit()
            return render_template(
                "verify_code.html", email=email,
                error="That code has expired or was tried too many times. Request a new one.",
            )

        if not check_password_hash(row["code_hash"], code):
            conn.execute(
                "UPDATE password_resets SET attempts = attempts + 1 WHERE user_id = ?",
                (user["id"],),
            )
            conn.commit()
            return render_template("verify_code.html", email=email, error=invalid)

        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user["id"],))
        conn.commit()
    finally:
        conn.close()

    session.pop("reset_email", None)
    session["reset_user_id"] = user["id"]
    return redirect(url_for("reset_password"))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("reset_user_id")
    if not user_id:
        flash("Please verify your identity first.", "error")
        return redirect(url_for("forgot_password"))
    if request.method == "GET":
        return render_template("reset_password.html")

    password = request.form.get("password", "")
    message = password_error(password, request.form.get("confirm_password", ""))
    if message:
        return render_template("reset_password.html", error=message)

    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        conn.commit()
    finally:
        conn.close()

    session.pop("reset_user_id", None)
    flash("Password updated. You can now sign in.", "success")
    return redirect(url_for("login"))


@app.route("/terms", strict_slashes=False)
@app.route("/terms-and-conditions", strict_slashes=False)
def terms():
    return render_template("terms.html")


@app.route("/privacy", strict_slashes=False)
@app.route("/privacy-policy", strict_slashes=False)
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


PROFILE_PRESETS = [
    ("last_month", "Last month"),
    ("month", "This month"),
    ("30d", "Last 30 days"),
    ("year", "This year"),
    ("all", "All time"),
]


PRESET_KEYS = {key for key, _ in PROFILE_PRESETS}

# start/end are ISO strings (or None); is_custom means start/end came from the
# user's own dates; is_default means the untouched last-month view.
RangeResult = namedtuple(
    "RangeResult", "start end preset error is_custom is_default"
)


def preset_range(preset, today):
    """Return (start, end) dates for a preset; either may be None."""
    if preset == "month":
        return today.replace(day=1), today
    if preset == "30d":
        return today - timedelta(days=29), today
    if preset == "year":
        return today.replace(month=1, day=1), today
    if preset == "all":
        return None, None
    # "last_month": the whole calendar month before today's month.
    last_day = today.replace(day=1) - timedelta(days=1)
    return last_day.replace(day=1), last_day


def _iso(d):
    return d.isoformat() if d else None


def _parse_custom_range(raw_start, raw_end):
    """Parse user-supplied dates. Returns (start, end, error)."""
    try:
        start = date.fromisoformat(raw_start) if raw_start else None
        end = date.fromisoformat(raw_end) if raw_end else None
    except ValueError:
        return None, None, "Enter dates as YYYY-MM-DD."
    if start and end and start > end:
        return None, None, "Start date must be on or before end date."
    return start, end, None


def resolve_range(args, today):
    """Work out the profile date filter from query args.

    Defaults to last month. Custom start/end win over preset; bad input
    falls back to last month along with an error message.
    """
    preset = args.get("preset", "last_month")
    if preset not in PRESET_KEYS:
        preset = "last_month"

    raw_start = args.get("start", "").strip()
    raw_end = args.get("end", "").strip()
    if raw_start or raw_end:
        start, end, error = _parse_custom_range(raw_start, raw_end)
        if error:
            start, end = preset_range("last_month", today)
            return RangeResult(_iso(start), _iso(end), "last_month", error, False, False)
        return RangeResult(_iso(start), _iso(end), None, None, True, False)

    start, end = preset_range(preset, today)
    return RangeResult(_iso(start), _iso(end), preset, None, False, preset == "last_month")


def range_label(start, end):
    """Human-readable range, e.g. "1 Oct 2026 – 31 Oct 2026"."""
    def fmt(iso):
        # Built by hand because %d would zero-pad the day.
        d = date.fromisoformat(iso)
        return f"{d.day} {d.strftime('%b %Y')}"
    if start and end:
        return f"{fmt(start)} – {fmt(end)}"
    if start:
        return f"From {fmt(start)}"
    if end:
        return f"Up to {fmt(end)}"
    return "All time"


@app.route("/profile")
@login_required
def profile():
    user_id = session["user_id"]

    rng = resolve_range(request.args, date.today())
    start, end = rng.start, rng.end
    # Only literal SQL fragments may be appended to `where`; every value goes
    # through `params` as a "?" placeholder. Never interpolate user input here.
    where = "user_id = ?"
    params = [user_id]
    if start:
        where += " AND date >= ?"
        params.append(start)
    if end:
        where += " AND date <= ?"
        params.append(end)

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE " + where,
            params,
        ).fetchone()
        categories = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE " + where + " GROUP BY category ORDER BY total DESC",
            params,
        ).fetchall()
        recent = conn.execute(
            "SELECT id, category, description, amount, date FROM expenses "
            "WHERE " + where + " ORDER BY date DESC, id DESC LIMIT 5",
            params,
        ).fetchall()
    finally:
        conn.close()

    top = categories[0]["total"] if categories else 0
    category_rows = [
        {
            "name": row["category"],
            "total": row["total"],
            "percent": round(row["total"] / top * 100) if top else 0,
        }
        for row in categories
    ]
    member_since = None
    if user["created_at"]:
        member_since = datetime.fromisoformat(user["created_at"]).strftime("%B %Y")

    return render_template(
        "profile.html",
        user=user,
        member_since=member_since,
        totals=totals,
        categories=category_rows,
        recent=recent,
        range_label=range_label(start, end),
        active_preset=rng.preset,
        custom_start=start if rng.is_custom else "",
        custom_end=end if rng.is_custom else "",
        filter_error=rng.error,
        is_default=rng.is_default,
        presets=PROFILE_PRESETS,
    )


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


def validate_expense(form, today):
    """Check the add-expense form.

    Returns (clean_values, None) on success or (None, error_message) on failure.
    """
    raw_amount = form.get("amount", "").strip()
    category = form.get("category", "")
    raw_date = form.get("date", "").strip()
    description = form.get("description", "").strip()

    try:
        amount = round(float(raw_amount), 2)
    except ValueError:
        return None, "Enter the amount as a number."
    if not math.isfinite(amount) or amount < 0.01:
        return None, "Amount must be at least 0.01."
    if amount > MAX_AMOUNT:
        return None, f"Amount can't be more than {MAX_AMOUNT:,}."

    if category not in CATEGORIES:
        return None, "Please choose a category from the list."

    try:
        expense_date = date.fromisoformat(raw_date)
    except ValueError:
        return None, "Enter the date as YYYY-MM-DD."
    if expense_date > today:
        return None, "Date can't be in the future."

    if len(description) > MAX_DESCRIPTION_LENGTH:
        return None, f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer."

    return {
        "amount": amount,
        "category": category,
        "date": expense_date.isoformat(),
        "description": description or None,
    }, None


EXPENSE_FORM_TEXT = {
    "add": ("Add expense", "Record what you spent", "Add expense"),
    "edit": ("Edit expense", "Update the details", "Save changes"),
}


def expense_form_context(mode, today, action_url):
    """Template variables shared by the add and edit expense forms.

    The template reads `values` with .get(), so it can be a plain dict (GET)
    or request.form (re-render after an error).
    """
    title, subtitle, submit = EXPENSE_FORM_TEXT[mode]
    return {
        "categories": CATEGORIES,
        "today": today.isoformat(),
        "max_description": MAX_DESCRIPTION_LENGTH,
        "form_title": title,
        "form_subtitle": subtitle,
        "submit_label": submit,
        "action_url": action_url,
    }


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    user_id = session["user_id"]
    today = date.today()
    form_context = expense_form_context("add", today, url_for("add_expense"))

    if request.method == "GET":
        return render_template(
            "add_expense.html", values={"date": today.isoformat()}, error=None,
            **form_context,
        )

    clean, error = validate_expense(request.form, today)
    if error:
        return render_template(
            "add_expense.html", values=request.form, error=error, **form_context
        )

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, clean["amount"], clean["category"],
             clean["description"], clean["date"]),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # The account was deleted while this session was still open.
        session.clear()
        flash("Your session has expired. Please sign in again.", "error")
        return redirect(url_for("login"))
    finally:
        conn.close()

    flash("Expense added.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    user_id = session["user_id"]
    today = date.today()
    form_context = expense_form_context(
        "edit", today, url_for("edit_expense", id=id)
    )

    conn = get_db()
    try:
        # Scoping by user_id makes other users' expenses look nonexistent.
        row = conn.execute(
            "SELECT amount, category, description, date FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (id, user_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        abort(404)

    if request.method == "GET":
        values = {
            "amount": row["amount"],
            "category": row["category"],
            "date": row["date"],
            "description": row["description"] or "",
        }
        return render_template(
            "add_expense.html", values=values, error=None, **form_context
        )

    clean, error = validate_expense(request.form, today)
    if error:
        return render_template(
            "add_expense.html", values=request.form, error=error, **form_context
        )

    # No IntegrityError handling here (unlike add): the UPDATE never changes
    # user_id, so it can't break the foreign key.
    conn = get_db()
    try:
        conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, description = ?, "
            "date = ? WHERE id = ? AND user_id = ?",
            (
                clean["amount"],
                clean["category"],
                clean["description"],
                clean["date"],
                id,
                user_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    flash("Expense updated.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
