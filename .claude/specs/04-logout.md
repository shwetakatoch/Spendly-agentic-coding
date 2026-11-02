# Spec: Logout

## Overview
Finish the sign-out half of authentication. A basic `/logout` already exists from Step 03 (it clears the session, flashes a message and redirects to the landing page), but nothing in the UI reaches it and the navbar ignores the session. This step makes logout a proper feature: the navbar shows a "Hello, <name>" greeting with a "Sign out" button instead of "Sign in" / "Get started", signing out sends the user to the login page, signed-in users can no longer open the login or registration pages, and logging out becomes a POST request so a third-party page or image tag cannot sign a user out.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`).
- Step 03 — Login (`session["user_id"]`, `secret_key`, flashed-message toasts in `base.html`, existing `/logout` view).

## Routes
- `POST /logout` — clear the session, flash "You have been signed out." and redirect to `/login` — logged-in (a logged-out visitor posting here is simply redirected to `/login`; no error)

The existing `GET /logout` is removed (a GET now returns 405). No other new routes.

## Database changes
No database changes.

## Templates
- **Create:** none
- **Modify:**
  - `templates/base.html` — navbar branches on `current_user`:
    - logged out: the existing "Sign in" and "Get started" links
    - logged in: a "Hello, <full name>" greeting (name escaped), and a "Sign out" button inside `<form method="POST" action="{{ url_for('logout') }}">`

## Files to change
- `app.py`
  - add a `@app.context_processor` that provides `current_user` (a dict with `id` and `name`) looked up from `session["user_id"]`; if the id no longer matches a user row, clear the session and provide `None`
  - set `SESSION_COOKIE_SAMESITE = "Lax"` (and keep `SESSION_COOKIE_HTTPONLY` at its default of `True`)
  - change `/logout` to `methods=["POST"]`
- `templates/base.html` — as above
- `static/css/style.css` — style the nav user label and make the "Sign out" button look like the other nav links (a button reset, no new colours)
- `tests/test_auth.py` — `test_logout_clears_session` must use `client.post`

## Files to create
- `tests/test_logout.py` — pytest tests for the logout behaviour and the navbar state (temporary database)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never string formatting in SQL
- Passwords hashed with werkzeug (unchanged; logout touches no passwords)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for(...)` for all links and form actions
- Logout must only be reachable by POST; never add a plain `<a href>` to it
- Use `session.clear()` so that any leftover reset-flow keys are removed too
- The context processor must open the DB with `get_db()`, close it in `try/finally`, and only query when `user_id` is in the session
- Render the user's name through Jinja autoescaping — never mark it `|safe`
- Preserve CRLF line endings in `app.py`; templates, CSS, JS and tests in this repo are LF

## Definition of done
- [ ] When logged out, the navbar shows "Sign in" and "Get started" and no "Sign out" button
- [ ] After signing in, the navbar shows "Hello, <full name>" and a "Sign out" button, and "Sign in" / "Get started" are gone
- [ ] Clicking "Sign out" lands on the login page (`/login`), shows a "You have been signed out." toast and the navbar returns to the logged-out state
- [ ] After signing out, pressing the browser Back button and reloading a page shows the logged-out navbar
- [ ] Visiting `/logout` directly in the address bar (GET) returns 405 and does not sign the user out
- [ ] Posting to `/logout` while logged out redirects to `/login` without an error
- [ ] If the logged-in user's row is deleted from the database, the next page load clears the session and shows the logged-out navbar instead of crashing
- [ ] A name containing HTML such as `<b>x</b>` is displayed as text in the navbar, not rendered
- [ ] The session cookie has the `HttpOnly` and `SameSite=Lax` attributes
- [ ] While signed in, opening `/login` or `/register` (typed in the address bar or via a link) redirects to `/` and the forms cannot be submitted
- [ ] `pytest` passes
- [ ] App starts with `python app.py` without errors
