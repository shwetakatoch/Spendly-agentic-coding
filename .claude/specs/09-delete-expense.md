# Spec: Delete Expense

## Overview
Replace the `/expenses/<id>/delete` stub with a working delete action so a signed-in user can permanently remove an expense they previously recorded. Because deletion is destructive and must not be triggered by a plain link (prefetching, crawlers, CSRF), it is a POST-only action protected by the existing CSRF token and guarded by a browser confirmation prompt. On success the user returns to the profile page with a flash message. This is Step 9 of the Spendly roadmap and completes the add / edit / delete expense CRUD set.

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db()`)
- Step 03 — Login (session `user_id`, `login_required`)
- Step 06 — Profile page with recent-expenses list (where the delete control lives)
- Step 07 — Add expense (CSRF handling in forms)
- Step 08 — Edit expense (owner-scoped `WHERE id = ? AND user_id = ?` pattern, Edit link in the list)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense, flash success, redirect to `profile` — logged-in, owner only

The existing `delete_expense` stub is changed to `methods=["POST"]` and `@login_required`, not renamed, so `url_for('delete_expense', id=...)` works. `GET` is no longer allowed (Flask returns 405). If the expense does not exist or belongs to another user, respond with 404 (do not reveal that it exists).

## Database changes
No database changes. Rows are removed with a plain `DELETE FROM expenses`; no other table references `expenses`.

## Templates
- **Create:** none.
- **Modify:**
  - `templates/profile.html` — next to the existing "Edit" link on each recent-expense row, add a small inline `<form method="POST" action="{{ url_for('delete_expense', id=e['id']) }}">` containing the hidden `csrf_token` input and a "Delete" button. The form has an `onsubmit="return confirm('Delete this expense?')"` guard (or equivalent in `static/js/main.js`).

## Files to change
- `app.py` — implement `delete_expense()`
- `templates/profile.html` — Delete button/form per recent expense
- `static/css/style.css` — style the delete button (looks like the edit link, danger tone), reusing existing CSS variables

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never interpolate the `id` into SQL
- Passwords hashed with werkzeug (unchanged; no password handling in this feature)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for(...)` for all links and form actions; preserve CRLF line endings in edited files
- POST only — never delete on GET
- Always take `user_id` from the session; delete with `WHERE id = ? AND user_id = ?` so users can never remove each other's rows
- Check `cursor.rowcount`: if 0 rows were deleted, `abort(404)`
- On success: `DELETE`, commit, `flash("Expense deleted.", "success")`, redirect to `url_for('profile')`
- Always close the DB connection in a `finally` block, matching the existing route style
- CSRF token must be included in the delete form (checked by the existing `check_csrf` before_request)
- Do not touch `add_expense`, `edit_expense` or `validate_expense`

## Definition of done
- [ ] Signed out, `POST /expenses/1/delete` redirects to `/login` and deletes nothing
- [ ] Each row in the profile's recent list shows a "Delete" button beside "Edit"
- [ ] Clicking Delete shows a confirmation prompt; cancelling it leaves the expense in place
- [ ] Confirming deletes the row, redirects to `/profile` with an "Expense deleted." flash, and the expense disappears from the recent list, totals and category breakdown
- [ ] `GET /expenses/<id>/delete` returns 405 and does not delete anything
- [ ] A POST without a valid CSRF token returns 400 and does not delete anything
- [ ] `/expenses/99999/delete` (nonexistent) returns 404 on POST
- [ ] Signed in as user A, POSTing to the delete URL of user B's expense returns 404 and B's expense still exists
- [ ] Deleting an expense does not affect any other expense or the user's account
- [ ] Deleting the same expense twice (e.g. a second tab) returns 404 the second time, not a 500
- [ ] The add and edit expense pages still work exactly as before
