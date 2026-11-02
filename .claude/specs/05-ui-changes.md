# Spec: UI Changes

## Overview
On `templates/landing.html` (hero section and bottom CTA section), hide every "Create free account" button/section when the user is already signed in.

## Depends on
- Step 04 — Logout (provides the `current_user` template variable)

## Routes
No new routes.

## Database changes
No database changes.

## Templates
- **Create:** none
- **Modify:**
  - `templates/landing.html`
    - Hero section: wrap the "Create free account" link in `{% if not current_user %}...{% endif %}`.
    - Bottom CTA section (`<section class="cta-section">`): wrap the whole section in `{% if not current_user %}...{% endif %}`.

## Files to change
- `templates/landing.html`

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `current_user` for the check; the elements must not render at all (no CSS hiding)

## Definition of done
- [ ] Signed out: "Create free account" shows in the hero and in the bottom CTA section
- [ ] Signed in: no "Create free account" element appears anywhere on `/`
