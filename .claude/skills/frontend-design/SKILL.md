---
name: frontend-design
description: Design and build any new page, or major page section, for the Spendly Flask expense tracker so it matches the existing theme, templates, code style and project workflow. Use this skill whenever the user says "design the page", "create a ___ page", "build the ___ page", "add a page for ...", "make a dashboard/settings/history/report page", or describes what a page should contain, even if they never say "frontend" or "template". Produces the Jinja template, CSS, Flask route and optional vanilla JS (no tests), following the project's own conventions.
---

# Frontend design for Spendly

The user describes a page in words (any page: profile, expense list, add/edit form, dashboard, settings, reports, and so on). Your job is to turn that description into a working page that looks and reads like it was always part of the app. Consistency with the existing code matters more than novelty: a page with its own colours, fonts or layout patterns makes the app feel stitched together.

Nothing below is specific to one page. The examples are illustrations; build what the user actually described.

## Stack (do not introduce anything else)

- Flask + Jinja2 templates in `templates/`, all extending `base.html`
- One stylesheet, `static/css/style.css`, built on CSS variables
- Vanilla JS only (`static/js/main.js`, or the page's `{% block scripts %}`)
- SQLite through `database/db.py` (`get_db()`, raw parameterised SQL, no ORM)
- No CSS framework, no JS framework, no build step

## How this project works (follow it)

Features are built one step at a time, each with a spec in `.claude/specs/NN-name.md` (Overview, Depends on, Routes, Database changes, Templates, Files to change/create, Rules for implementation, Definition of done) on a branch `feature/<slug>`. The `/create-spec` command makes the spec and branch.

- If a spec for this page already exists, read it first and build exactly that, treating its "Definition of done" as the checklist.
- If none exists, don't create branches or commit on your own. Work on the current branch, and offer to run `/create-spec` if the user wants a spec first. Mention this in one line, not a lecture.
- Never commit or push unless the user asks.

## Workflow

1. **Understand the request.** Restate the page's purpose and the content blocks the user asked for. Ask only if something that changes the design is truly ambiguous (e.g. is a field editable, is the page public or signed-in only). Otherwise choose a sensible default and say so at the end.
2. **Re-read the code before writing.** The project evolves, so don't trust a snapshot. Read `templates/base.html`, `static/css/style.css` (the `:root` variables plus the section nearest to what you're building), one similar template (`login.html` for cards/forms, `landing.html` for richer layouts), `templates/_macros.html`, the relevant part of `app.py` and `database/db.py` for the schema.
3. **Reuse before you add.** Look for an existing class or macro that does the job (cards, `.form-group`, `.form-input`, `.btn-primary`, `.btn-ghost`, `.btn-submit`, `.btn-secondary`, `.auth-error`, toasts, `password_field`). Add new CSS only for what genuinely doesn't exist.
4. **Build** the template, CSS, route, and JS if needed, following the rules below.
5. **Verify.** Don't write new tests; this skill only builds the page. Run the existing `pytest` suite to make sure nothing broke, then start the app or use Flask's test client to confirm the page renders. Report what you ran and what you couldn't check. If anything fails, say so with the output.

## Design rules

**Theme.** Warm paper background, near-black ink, deep-green accent. Use the variables at the top of `style.css` (`--ink`, `--ink-soft`, `--ink-muted`, `--ink-faint`, `--paper`, `--paper-warm`, `--paper-card`, `--accent`, `--accent-light`, `--accent-2`, `--accent-2-light`, `--danger`, `--danger-light`, `--border`, `--border-soft`, `--font-display`, `--font-body`, `--radius-sm/md/lg`, `--max-width`). Never write raw hex colours in new rules. If a needed colour truly doesn't exist, add a variable to `:root` and say so.

**Typography.** Page titles and big numbers use `var(--font-display)`; everything else inherits DM Sans from `body`. Don't add fonts.

**Layout patterns in use.**
- Narrow centred forms: `*-section` > `*-container` > header + white card (`background: var(--paper-card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 2rem`), as in `.auth-*`.
- Wide pages: `max-width: var(--max-width); margin: 0 auto;` with about `2rem` side padding, as in `.nav-inner` and `.features-inner`.
- Use `min-height: calc(100vh - 60px - 100px)` on page sections so the footer stays low on short pages.
- Data-heavy pages (lists, stats, charts) can borrow the look of the landing page's dashboard preview (`.preview-*`). Build charts with plain HTML/CSS bars or inline SVG, not a library.

**Naming.** Prefix new classes with the page name in kebab-case (`.history-table`, `.settings-card`), matching `.auth-title` and `.legal-card`. Add them to `style.css` under a banner comment like the others:

```css
/* ------------------------------------------------------------------ */
/* <Page name>                                                         */
/* ------------------------------------------------------------------ */
```

Put the new section before the "Responsive" block, or extend that block, so breakpoints stay together (existing ones: 900px and 600px). Stack grids to one column on small screens.

**Accessibility basics.** Every input has a `<label for>`, actions are `<button>` or `<a>` as appropriate, decorative glyphs get `aria-hidden="true"`, and text stays on `--ink*` colours over paper or card backgrounds.

## Code conventions

- Templates: `{% extends "base.html" %}`, `{% block title %}Page — Spendly{% endblock %}`, markup in `{% block content %}`, page JS in `{% block scripts %}`.
- Links and form actions use `url_for(...)`, never hard-coded paths; static files use `url_for('static', filename=...)`.
- Forms use `method="POST"`. Show validation errors via an `error` template variable in an `.auth-error`-style box, re-fill submitted values, and use `flash(message, "success" | "info" | "error")` for feedback (rendered as toasts by `base.html`).
- State-changing actions (delete, logout, etc.) must be POST, never a plain link.
- Routes live in `app.py`, grouped with the existing ones. If a placeholder route for this page already exists (e.g. `/expenses/add` returns "coming in Step 7"), replace its body instead of adding a duplicate route.
- Pages for signed-in users guard access: `if not session.get("user_id"): return redirect(url_for("login"))`. Scope every query to that user.
- Database: `get_db()`, close in `try/finally`, parameterised queries (`?`) only. If the page needs schema changes, add them to `init_db()` with `CREATE TABLE IF NOT EXISTS` (or a safe migration) and mention it prominently.
- `current_user` (with `id` and `name`) is available in every template. For more fields, query them in the route and pass them in.
- Jinja autoescaping stays on; never use `|safe` on user-provided data.
- Use the file's own line endings. Check with `grep -c $'\r' <file>` before editing; the repo is currently LF throughout, even though CLAUDE.md says CRLF. Don't convert whole files.
- If the page should be reachable from the UI, add a navbar link in `base.html` (signed-in users) using `url_for`.
- Don't add dependencies. If one is truly needed, stop and ask.

## What to hand back

A short summary: files created or changed, the route and its URL, any new CSS variables or macros, assumptions you made about anything the user didn't specify, and what you verified (existing tests run, page render check). The diff speaks for itself, so don't narrate it.
