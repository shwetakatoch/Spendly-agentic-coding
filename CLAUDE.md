# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Spendly is a Flask expense-tracker. It is a step-by-step teaching scaffold: only the landing, auth-form, and legal pages are real so far. The rest are stubs marked "coming in Step N".

## Commands

```
python -m venv venv && venv\Scripts\activate   # a venv/ already exists in the repo dir
pip install -r requirements.txt
python app.py                                   # dev server, debug on, http://127.0.0.1:5001
pytest                                          # pytest + pytest-flask are installed; no tests exist yet
pytest path/to/test_file.py::test_name          # single test
```

There is no linter or build step.

## Architecture

- `app.py` holds all routes. Pages that exist: `/`, `/register`, `/login`, `/terms`, `/privacy`. Both `/terms` and `/privacy` have a long-form alias (`/terms-and-conditions`, `/privacy-policy`) and `strict_slashes=False`. Because the last-declared rule is the one `url_for` picks, `url_for('terms')` and `url_for('privacy')` produce the long-form URLs.
- The routes `/logout`, `/profile` and `/expenses/...` return placeholder strings. Each is meant to be implemented in a later step.
- `database/db.py` is an empty stub. Its header comment says it should define `get_db()` (SQLite connection with `row_factory` and foreign keys on), `init_db()` (`CREATE TABLE IF NOT EXISTS`) and `seed_db()`. Nothing imports it yet.
- `templates/base.html` is the shared shell (navbar, footer, `{% block content %}`, `{% block scripts %}`). All other templates extend it. Page-specific JS goes in the `scripts` block. `static/js/main.js` is an empty placeholder loaded on every page.
- `static/css/style.css` is the only stylesheet, and there is no per-page CSS. It uses CSS variables (`--ink`, `--paper`, `--accent`, `--border`, `--font-*`, `--radius-*`) defined at the top. Reuse them rather than adding raw colours. Fonts are DM Serif Display and DM Sans, loaded from Google Fonts in `base.html`.
- `landing.html` has a hero with a dashboard mock and a vanilla-JS YouTube modal. The modal sets the iframe `src` on open and clears it on close to stop playback. `VIDEO_URL` in that script is a placeholder.
- `terms.html` and `privacy.html` contain placeholder legal text, not real policy.

## Conventions

- Files use CRLF line endings (Windows). Preserve them when editing programmatically.
- Use `url_for(...)` for all links, never hard-coded paths.
