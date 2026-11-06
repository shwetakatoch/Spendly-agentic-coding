# Spec: Date Filter for Profile Page

## Overview
Add a date-range filter to the profile page so a signed-in user can narrow the summary stats, category breakdown and recent-expenses list to a chosen period. By default the page shows the **previous calendar month's** expenses. The user can switch to the current month, other presets or a custom From/To range using the date filter. The filter is driven by query-string parameters on `GET /profile`, so filtered views are bookmarkable and need no JavaScript.

## Depends on
- Step 01 — Database setup (`expenses` table with `date` column)
- Step 03 — Login (session `user_id`)
- Profile page (existing `/profile` route and `templates/profile.html`)

## Routes
- `GET /profile` — extended (not new) to accept optional query params `preset` (`last_month`, `month`, `30d`, `year`, `all`), `start` and `end` (`YYYY-MM-DD`) — logged-in

No new routes.

## Database changes
No database changes. The existing `idx_expenses_user_date` index covers the `user_id` + `date` filtering.

## Templates
- **Create:** none
- **Modify:**
  - `templates/profile.html`
    - Add a filter bar (GET form) with preset links (Last month, This month, Last 30 days, This year, All time) and `start` / `end` date inputs plus Apply and Reset actions. Build all links with `url_for('profile', ...)`.
    - Show the active range label (e.g. "1 Oct 2026 – 31 Oct 2026" or "All time") near the stats.
    - Show an empty-state message when no expenses fall in the range.
    - Show an inline error when the custom range is invalid.

## Files to change
- `app.py` — parse and validate filter params in `profile()`, default to the previous calendar month, apply a parameterised date clause to the totals, category and recent-expense queries, pass the active range and error to the template
- `templates/profile.html` — filter bar, range label, empty state
- `static/css/style.css` — styles for the filter bar (reuse existing CSS variables)

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never interpolate `start`/`end` into SQL strings
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for(...)` for all links; preserve CRLF line endings
- Validate `start`/`end` with `date.fromisoformat`; ignore unknown `preset` values
- Default (no params, or unknown preset) = previous calendar month: first to last day of the month before today's month (handle January -> December of the prior year)
- If `start` > `end` or a date is malformed, show an error and fall back to the default (previous month) view rather than returning an error status
- Either bound may be given alone (open-ended range)
- Custom `start`/`end` take precedence over `preset`
- Replace the fixed "This month" stat card with a period total for the active range, so the cards always match the filter
- Filters apply only to the logged-in user's expenses (`WHERE user_id = ?` stays)
- Redirect to `login` when not signed in (unchanged)

## Definition of done
- [ ] `/profile` with no params shows only the previous calendar month's expenses, labelled with that month's date range
- [ ] Clicking "This month" shows only expenses from the current calendar month; totals, count, category bars and recent list all update
- [ ] "Last month", "Last 30 days", "This year" and "All time" presets each filter correctly
- [ ] Custom `start` and `end` inputs filter inclusively on both ends (e.g. `?start=2026-11-02&end=2026-11-02` shows only that day)
- [ ] Only `start` or only `end` supplied works as an open-ended range
- [ ] `?start=2026-11-10&end=2026-11-01` shows an error message and the previous-month view
- [ ] `?start=garbage` does not crash; it shows an error and the previous-month view
- [ ] A range with no expenses shows an empty-state message and zero totals
- [ ] The active preset/range is visibly highlighted and the inputs are pre-filled after applying
- [ ] "Reset" returns to the default previous-month `/profile`
- [ ] Another user's expenses never appear in the results
- [ ] Signed out, `/profile` still redirects to `/login`
