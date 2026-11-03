import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone

from flask import (
    Flask, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

RESET_CODE_TTL = timedelta(minutes=10)
RESET_MAX_ATTEMPTS = 5

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


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    month = date.today().strftime("%Y-%m")
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count, "
            "COALESCE(SUM(CASE WHEN strftime('%Y-%m', date) = ? THEN amount END), 0) "
            "AS month_total FROM expenses WHERE user_id = ?",
            (month, user_id),
        ).fetchone()
        categories = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
        ).fetchall()
        recent = conn.execute(
            "SELECT category, description, amount, date FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 5",
            (user_id,),
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
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
