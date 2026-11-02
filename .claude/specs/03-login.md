# Spec: Login, Logout and Forgot Password

## Overview
Make the `/login` form work and add a recovery path for users who forgot their password. A registered user signs in with email and password and gets a session; `/logout` ends it. On the login page a "Forgot password?" link starts a reset flow: the user first tries their last known password, or chooses "Try another way" to receive a 6-digit verification code for their registered email, then sets a new password that meets the same strength rules as registration. Email delivery is console-only for now: the code is printed to the server terminal.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`, `init_db()`).
- Step 02 — Registration (users exist; shared strength rules, `templates/_macros.html`, toast container in `base.html`, `showToast` in `main.js`).

## Routes
- `GET /login` — render the sign-in form with a "Forgot password?" link; a signed-in user is redirected to `/` instead (also for `POST /login`) — public
- `POST /login` — check email and password; on success start a session and redirect to the homepage (`/`); on failure re-render with "Invalid email or password." — public
- `GET /logout` — clear the session, flash a message, redirect to `/login` — public (made POST-only in Step 04)
- `GET /forgot-password` — form asking for email and last known password, with a "Try another way" button — public
- `POST /forgot-password` — public
  - `method=password`: if the password matches, allow a reset (`session["reset_user_id"]`) and redirect to `/reset-password`; otherwise re-render with an error
  - `method=email`: generate and store a code, print it to the console, set `session["reset_email"]` and redirect to `/verify-code`. Same response whether or not the account exists.
- `GET /verify-code` — form for the 6-digit code (requires `reset_email` in the session, else redirect to `/forgot-password`) — public
- `POST /verify-code` — verify the code, or resend one when `action=resend`; on success set `session["reset_user_id"]` and redirect to `/reset-password` — public
- `GET /reset-password` — new password and confirmation form; redirects to `/forgot-password` unless `reset_user_id` is in the session — public (needs a verified reset)
- `POST /reset-password` — validate with the shared strength rules, update the password hash, clear the reset state, flash a success message and redirect to `/login` — public (needs a verified reset)

## Database changes
New table, created by `init_db()` with `CREATE TABLE IF NOT EXISTS` (already added to `database/db.py`):

```
password_resets (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    code_hash  TEXT NOT NULL,
    expires_at TEXT NOT NULL,   -- ISO-8601 UTC
    attempts   INTEGER NOT NULL DEFAULT 0
)
```

One active code per user; requesting a new code replaces the old one. `users` is unchanged.

## Templates
- **Create:**
  - `templates/forgot_password.html` — email, last known password, "Continue" and "Try another way" buttons
  - `templates/verify_code.html` — 6-digit code input, "Verify code" and "Resend code" buttons
  - `templates/reset_password.html` — new password and confirmation, with the strength checklist
- **Modify:**
  - `templates/login.html` — form action via `url_for`, keeps the email after a failed attempt, password eye toggle, "Forgot password?" link

## Files to change
- `app.py` — `secret_key` (from `SECRET_KEY` env var, with a dev-only default); imports; `login()`, `logout()`; new `forgot_password()`, `verify_code()`, `reset_password()`; `send_reset_code()` helper; constants `RESET_CODE_TTL` (10 minutes) and `RESET_MAX_ATTEMPTS` (5)
- `database/db.py` — add the `password_resets` table to `init_db()`
- `templates/login.html` — as above
- `static/css/style.css` — `.btn-secondary`, `.form-aside`, `.form-hint`, `.code-input`

## Files to create
- `templates/forgot_password.html`, `templates/verify_code.html`, `templates/reset_password.html`
- `tests/test_auth.py` — pytest tests for login, logout and the reset flows (temporary database)

## New dependencies
No new dependencies. Code generation uses the standard library `secrets`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never string formatting in SQL
- Passwords hashed with werkzeug; verify with `check_password_hash`
- The reset code is stored only as a werkzeug hash, is 6 digits from `secrets.randbelow`, expires after 10 minutes, is single-use and is locked after 5 wrong attempts
- Never reveal whether an email is registered: login failure and "Try another way" responses must be identical for unknown and known emails
- Reset state lives in the session (`reset_email` before verification, `reset_user_id` after) and is cleared once the password is updated; `/reset-password` must refuse access without it
- Reuse the shared `password_error()` strength rules from Step 02; do not duplicate them
- Call `session.clear()` before setting `session["user_id"]` on login
- Flashed messages render as toasts through the container in `base.html`
- Email delivery is console-only: print `[Spendly] Password reset code for <email>: <code>`; real SMTP is out of scope
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for(...)` for all links and form actions
- Preserve CRLF line endings in `app.py` and `database/db.py`

## Definition of done
- [ ] Signing in with a registered email and password redirects to the homepage (`/`) and shows a welcome toast
- [ ] A wrong password or unknown email shows "Invalid email or password." and no session is created
- [ ] `/logout` clears the session and returns to the login page
- [ ] A signed-in user who opens `/login` is redirected to `/`
- [ ] The login page shows a "Forgot password?" link that opens `/forgot-password`
- [ ] Entering the correct last known password leads to the new-password form; a wrong one shows an error and `/reset-password` stays blocked
- [ ] "Try another way" prints a 6-digit code in the server console and opens the code page
- [ ] A correct code leads to the new-password form; a wrong code shows an error; after 5 wrong attempts or 10 minutes the code stops working
- [ ] "Resend code" issues a new code and the old one no longer works
- [ ] The new password must meet the registration strength rules and match its confirmation, with the same checklist and show/hide toggle
- [ ] After a successful reset the old password no longer works and the new one signs in
- [ ] A reset code cannot be reused once the password has been changed
- [ ] `/reset-password` and `/verify-code` redirect to `/forgot-password` when opened without the earlier steps
- [ ] `pytest tests/test_auth.py` passes
- [ ] App starts with `python app.py` without errors
