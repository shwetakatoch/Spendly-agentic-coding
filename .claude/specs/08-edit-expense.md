# Spec: Edit Expense

## Overview
Replace the `/expenses/<id>/edit` stub with a working form so a signed-in user can change the amount, category, date or description of an expense they previously recorded. The form is pre-filled with the current values and reuses the same validation as Step 7. On success the user is sent back to the profile page. This is Step 8 of the Spendly roadmap; it builds directly on the add-expense feature and precedes Step 9 (delete).

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db()`, `CATEGORIES`)
- Step 03 — Login (session `user_id`)
- Step 06 — Profile page with recent-expenses list (where the edit link lives)
- Step 07 — Add expense (`validate_expense()`, form template and styles)

## Routes
- `GET /expenses/<int:id>/edit` — show the form pre-filled with the expense — logged-in, owner only
- `POST /expenses/<int:id>/edit` — validate and update the expense, flash success, redirect to `profile` — logged-in, owner only

The existing `edit_expense` route is extended (now `methods=["GET", "POST"]` and `@login_required`), not renamed, so `url_for('edit_expense', id=...)` keeps working. If the expense does not exist or belongs to another user, respond with 404 (do not reveal that it exists).

## Database changes
No database changes. The existing `expenses` table already has every column needed; the update only touches `amount`, `category`, `description` and `date`. `created_at` and `user_id` are never modified.

## Templates
- **Create:** none. Generalise `templates/add_expense.html` so one form template serves both add and edit (see below).
- **Modify:**
  - `templates/add_expense.html` — accept form heading, submit label and form action from the route (e.g. `form_title`, `submit_label`, `action_url`) so edit mode shows "Edit expense" / "Save changes" and posts to the edit URL; Cancel still links to `url_for('profile')`. Keep the add page's behaviour identical.
  - `templates/profile.html` — add an "Edit" link on each row of the recent-expenses list using `url_for('edit_expense', id=e['id'])`

## Files to change
- `app.py` — implement GET/POST `edit_expense()`; add `id` to the SELECT of the `recent` query in `profile()`; pass the heading/label/action variables from `add_expense()` too
- `templates/add_expense.html` — shared add/edit form
- `templates/profile.html` — Edit link per recent expense
- `static/css/style.css` — small style for the edit link, reusing existing CSS variables

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never interpolate form values or the `id` into SQL
- Passwords hashed with werkzeug (unchanged; no password handling in this feature)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for(...)` for all links; preserve CRLF line endings in edited files
- Reuse `validate_expense()` — do not duplicate validation logic
- Always take `user_id` from the session; load and update with `WHERE id = ? AND user_id = ?` so users can never touch each other's rows
- Missing or foreign expense → `abort(404)` on both GET and POST
- GET pre-fills the form from the DB row (amount, category, date, description; blank description shows as empty)
- On validation failure re-render the form (status 200) with an error and the entered values preserved — never a 500
- On success: `UPDATE`, commit, `flash("Expense updated.", "success")`, redirect to `url_for('profile')`
- Always close the DB connection in a `finally` block, matching the existing route style
- CSRF token must be included in the form (already handled by the shared template)
- Leave the `delete_expense` stub untouched

## Definition of done
- [ ] Signed out, `GET` and `POST /expenses/1/edit` redirect to `/login`
- [ ] Each row in the profile's recent list has an "Edit" link that opens `/expenses/<id>/edit`
- [ ] The edit page shows the heading "Edit expense" and fields pre-filled with the expense's current amount, category, date and description
- [ ] Changing values and submitting redirects to `/profile` with an "Expense updated." flash, and the new values appear in the recent list, totals and category breakdown
- [ ] The `expenses` row is updated in place (same `id`, same `user_id`, same `created_at`) with amount rounded to 2 decimals and ISO date
- [ ] Clearing the description saves successfully and stores no description
- [ ] Empty, zero, negative, non-numeric, `nan` and `inf` amounts show an error and leave the row unchanged
- [ ] A tampered category, a malformed date or a future date shows an error and leaves the row unchanged
- [ ] A description over 200 characters shows an error and leaves the row unchanged
- [ ] After a validation error the form keeps the values the user entered
- [ ] `/expenses/99999/edit` (nonexistent) returns 404
- [ ] Signed in as user A, opening or posting to the edit URL of user B's expense returns 404 and does not change B's data
- [ ] Cancel returns to `/profile` without saving
- [ ] The add-expense page at `/expenses/add` still works exactly as before
- [ ] A description such as `'); DROP TABLE expenses;--` is stored as plain text and does not alter the database
