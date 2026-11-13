# Spec: Add Expense

## Overview
Replace the `/expenses/add` stub with a working form so a signed-in user can record a new expense (amount, category, date, optional description). On success the expense is stored against the user and they are sent back to the profile page, where it shows up in the totals, category breakdown and recent list. This is Step 7 of the Spendly roadmap and is the first feature that writes to the `expenses` table from the UI; Steps 8 (edit) and 9 (delete) build on it.

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db()`, `CATEGORIES` in `database/db.py`)
- Step 03 — Login (session `user_id`)
- Step 04 — Logout / base navbar
- Profile page (`/profile`, where new expenses are visible)

## Routes
- `GET /expenses/add` — show the add-expense form — logged-in (redirect to `login` otherwise)
- `POST /expenses/add` — validate and insert the expense, flash success, redirect to `profile` — logged-in

The existing `add_expense` route is extended (now `methods=["GET", "POST"]`), not renamed, so `url_for('add_expense')` keeps working.

## Database changes
No database changes. The existing `expenses` table (`user_id`, `amount REAL NOT NULL`, `category TEXT NOT NULL`, `description TEXT`, `date TEXT NOT NULL`, `created_at`) and `idx_expenses_user_date` already cover this. `CATEGORIES` in `database/db.py` is the single source of allowed categories.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`; form with:
  - Amount (`type="number"`, `step="0.01"`, `min="0.01"`, required)
  - Category (`<select>` populated from `CATEGORIES`, required)
  - Date (`type="date"`, required, defaults to today, `max` = today) 
  - Description (text, optional, max 200 chars)
  - Submit button and a Cancel link back to `url_for('profile')`
  - Inline error message area; on error, re-render with the user's previously entered values
- **Modify:**
  - `templates/profile.html` — add an "Add expense" button/link using `url_for('add_expense')`
  - `templates/base.html` — add an "Add expense" navbar link (signed-in only) using `url_for('add_expense')`

## Files to change
- `app.py` — import `CATEGORIES` from `database.db`; implement GET/POST `add_expense()` with validation and insert
- `templates/profile.html` — "Add expense" link
- `templates/base.html` — navbar link for signed-in users
- `static/css/style.css` — form styles, reusing the existing auth-form styles and CSS variables where possible

## Files to create
- `templates/add_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never interpolate form values into SQL
- Passwords hashed with werkzeug (unchanged; no password handling in this feature)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for(...)` for all links; preserve CRLF line endings in edited files
- Redirect to `login` when `session["user_id"]` is missing (GET and POST)
- Always take `user_id` from the session, never from the form
- Server-side validation (do not rely on HTML attributes):
  - amount must parse as a number, be finite (reject `nan`/`inf`), and be > 0; round to 2 decimals
  - category must be one of `CATEGORIES`
  - date must parse with `date.fromisoformat` and must not be in the future; store as ISO `YYYY-MM-DD`
  - description is stripped, optional, max 200 characters; store `NULL`/empty if blank
- On validation failure re-render the form (status 200) with an error message and the entered values preserved — never a 500
- On success: insert, commit, `flash("Expense added.", "success")`, redirect to `url_for('profile')`
- Always close the DB connection in a `finally` block, matching the existing route style
- Leave the `edit_expense` and `delete_expense` stubs untouched

## Definition of done
- [ ] Signed out, `GET /expenses/add` and `POST /expenses/add` redirect to `/login`
- [ ] Signed in, `/expenses/add` renders the form with amount, category, date (defaulting to today) and description fields
- [ ] The category dropdown lists exactly the categories in `CATEGORIES`
- [ ] Submitting valid data redirects to `/profile` with a "Expense added." flash message
- [ ] The new expense appears in the profile's recent list and is included in totals/category breakdown (using the "All time" or matching date filter)
- [ ] The row in `expenses` has the logged-in user's `user_id`, the amount rounded to 2 decimals and the ISO date
- [ ] Empty, zero, negative, non-numeric, `nan` and `inf` amounts show an error and save nothing
- [ ] A category not in `CATEGORIES` (e.g. via a tampered request) shows an error and saves nothing
- [ ] A malformed or future date shows an error and saves nothing
- [ ] A description over 200 characters shows an error (or is rejected) and saves nothing; a blank description saves fine
- [ ] After a validation error the form keeps the values the user entered
- [ ] The navbar and profile page both have working "Add expense" links when signed in, and the navbar link is hidden when signed out
- [ ] Cancel returns to `/profile` without saving
- [ ] A form value containing SQL such as `'); DROP TABLE expenses;--` in the description is stored as plain text and does not alter the database
