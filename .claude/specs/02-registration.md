# Spec: Registration

## Overview
Turn the static `/register` page into a working sign-up flow. A visitor submits their name, email, password and password confirmation; the app validates the input (strength rules on both client and server), hashes the password with werkzeug and stores a new row in the `users` table. On success a toast confirms the account was created and the page then redirects automatically to the login page. This is the first half of authentication and must exist before login/logout (Step 3) can have real accounts to sign in to.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`, `init_db()`).

## Routes
- `GET /register` — render the empty registration form — public
- `POST /register` — validate the form and create the user — public
  - On failure: re-render the form (HTTP 200) with an error message.
  - On success: render the registration page (HTTP 200) with `success_redirect` set. The page shows a success toast and redirects to `/login` after about 2 seconds (JavaScript), with a `<meta http-equiv="refresh">` fallback at 3 seconds.

The existing `register()` view in `app.py` becomes a single view accepting `GET` and `POST`. No other new routes.

## Database changes
No database changes. The existing `users` table already has `name`, `email` (UNIQUE), `password_hash` and `created_at`. Duplicate emails are rejected by checking first and by catching `sqlite3.IntegrityError` as a safety net.

## Templates
- **Create:**
  - `templates/_macros.html` — shared Jinja macros: `password_field` (password input with the show/hide eye toggle) and `password_rules` (live strength checklist). Also used by Step 03.
- **Modify:**
  - `templates/register.html` — form action uses `url_for('register')`; adds a Confirm Password field; uses the `password_field` and `password_rules` macros; keeps name and email after a failed submit (never the password); has an error box (`data-form-error`) used by both server and client validation; on success loads the toast script and the meta-refresh fallback.
  - `templates/base.html` — adds the `#toast-container` element that renders flashed messages as toasts (used by Step 03).

## Files to change
- `app.py` — imports; `password_error()` helper and `find_user()` helper; `register()` handles `GET` and `POST`.
- `templates/register.html`, `templates/base.html` — as above.
- `static/js/main.js` — toast helper (`showToast`), show/hide password toggle, client-side strength validation and live checklist.
- `static/css/style.css` — styles for the password field and toggle, rules checklist and toasts, using the existing CSS variables.

## Files to create
- `templates/_macros.html`
- `tests/test_registration.py` — pytest tests for the registration flow (uses a temporary database, not `expense_tracker.db`).

## New dependencies
No new dependencies. (`pytest` and `pytest-flask` are already installed. Toasts are custom; SweetAlert is not used.)

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never string formatting in SQL
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log the plain password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for(...)` for all links and form actions, never hard-coded paths
- Use `get_db()` from `database/db.py` and always close the connection (`try/finally`)
- Server-side validation (the client-side checks are a convenience, not the guard):
  - name, email, password and confirm password are all present (name and email stripped; password not stripped)
  - email contains an `@` and a `.` after it, and is lower-cased and stripped before storing and comparing
  - password and confirm password match
  - password has at least 8 characters, one uppercase letter, one lowercase letter, one digit and one special (non-alphanumeric) character
  - email is not already registered → error "An account with this email already exists."
- The same strength rules run in JavaScript before submit and drive the live checklist. The form uses `novalidate` so the custom messages show instead of browser tooltips.
- On failure return HTTP 200 with the form re-rendered and a single clear `error` message
- On success do NOT redirect from the server; render the page with `success_redirect` so the toast can show first
- No session or auto-login on registration
- Preserve CRLF line endings in `app.py`; templates, CSS and JS in this repo are LF

## Definition of done
- [ ] `GET /register` shows name, email, password and confirm password fields and the rules checklist
- [ ] Each password field has an eye icon that toggles between showing and hiding the text
- [ ] The checklist ticks off each rule live as the password is typed
- [ ] Submitting valid details creates a row in `users`, shows a "Account created successfully" toast, then lands on `/login` automatically
- [ ] The stored `password_hash` is a werkzeug hash, not the plain password
- [ ] A password missing a length, uppercase, lowercase, digit or special-character requirement shows the matching error (client side, and server side if JavaScript is bypassed) and creates no row
- [ ] Mismatched password and confirmation shows "Passwords do not match." and creates no row
- [ ] Registering the same email again (also with different letter case) shows "An account with this email already exists." and creates no second row
- [ ] Submitting with an empty name, empty email or invalid email shows an error and creates no row
- [ ] After a failed submit the name and email fields keep their values; the password fields are empty
- [ ] The form action uses `url_for('register')` (no hard-coded `/register` in the template)
- [ ] The "Sign in" link on the page still goes to `/login`
- [ ] `pytest tests/test_registration.py` passes
- [ ] App starts with `python app.py` without errors
