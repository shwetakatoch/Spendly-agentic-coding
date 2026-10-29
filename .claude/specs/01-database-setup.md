# 01 - Database Setup Specification

## 1. Overview
Replace the stub in `database/db.py` with a working SQLite implementation. This step establishes the data layer foundation for the **Spendly** application. All future features (authentication, profile, expense tracking) depend on this being correctly implemented.

## 2. Depends On
* Nothing — this is the first step.

## 3. Routes
* No new routes.
* Existing placeholder routes in `app.py` remain unchanged.

## 4. Database Schema

### A. `users` Table
| Column | Type | Constraints |
| :--- | :--- | :--- |
| `id` | `INTEGER` | Primary key, autoincrement |
| `name` | `TEXT` | Not null |
| `email` | `TEXT` | Unique, not null |
| `password_hash` | `TEXT` | Not null |
| `created_at` | `TEXT` | Default `datetime('now')` |

### B. `expenses` Table
| Column | Type | Constraints |
| :--- | :--- | :--- |
| `id` | `INTEGER` | Primary key, autoincrement |
| `user_id` | `INTEGER` | Foreign key $\rightarrow$ `users.id`, not null |
| `amount` | `REAL` | Not null |
| `category` | `TEXT` | Not null |
| `date` | `TEXT` | Not null (`YYYY-MM-DD` format) |
| `description` | `TEXT` | Nullable |
| `created_at` | `TEXT` | Default `datetime('now')` |

## 5. Functions to Implement (`database/db.py`)

### A. `get_db()`
* Opens connection to `spendly.db` (or `expense_tracker.db`) in the project root.
* Configures connection:
  * Sets `row_factory = sqlite3.Row`
  * Executes `PRAGMA foreign_keys = ON`
* Returns the connection object.

### B. `init_db()`
* Creates both tables using `CREATE TABLE IF NOT EXISTS`.
* Safe to call multiple times (idempotent).
* Ensures schema is ready before application usage.

### C. `seed_db()`
* Checks if the `users` table already contains data:
  * If yes $\rightarrow$ return early (prevent duplication).
* Inserts one demo user:
  * **Name:** `Demo User`
  * **Email:** `demo@spendly.com`
  * **Password:** `demo123` (hashed using `werkzeug.security`)
* Inserts 8 sample expenses:
  * All linked to the demo user's `id`.
  * Cover multiple categories (at least one expense per fixed category).
  * Dates spread across the current month in `YYYY-MM-DD` format.

## 6. Changes to `app.py`
* Import `get_db`, `init_db`, and `seed_db` from `database.db`.
* Call `init_db()` and `seed_db()` inside `with app.app_context():` on startup.
* Ensure the database is initialized and seeded before any routes are handled.

## 7. Files to Change
* `database/db.py` $\rightarrow$ Implement all database connection, initialization, and seeding functions.
* `app.py` $\rightarrow$ Add imports and startup initialization calls.

## 8. Files to Create
* None (aside from the auto-generated `.db` SQLite file on startup).

## 9. Dependencies
* No new `pip` packages required.
* Standard & existing libraries used:
  * `sqlite3` (Python standard library)
  * `werkzeug.security` (already installed with Flask)

## 10. Categories (Fixed List)
Use **exactly** these values for expense categories:
* `Food`
* `Transport`
* `Bills`
* `Health`
* `Entertainment`
* `Shopping`
* `Other`

## 11. Rules for Implementation
* **No ORMs:** Do not use SQLAlchemy or any other ORM.
* **Parameterized Queries Only:** Use `?` placeholders for all SQL parameters. Never use Python string formatting (`f""`, `%`, `.format()`) in SQL queries.
* **Foreign Keys:** Enable `PRAGMA foreign_keys = ON` on every database connection.
* **Data Types:** Store `amount` as `REAL` (float), not `INTEGER`.
* **Password Hashing:** Hash passwords using:
  ```python
  from werkzeug.security import generate_password_hash
  ```
* **Idempotent Seeding:** `seed_db()` must prevent duplicate inserts on restarts.
* **Date Formatting:** Dates must consistently follow the `YYYY-MM-DD` format.

## 12. Expected Behavior
* `get_db()` returns a working SQLite connection with dictionary-like row access (`sqlite3.Row`) and foreign key enforcement enabled.
* `init_db()` creates tables safely and does not fail on repeated runs.
* `seed_db()` inserts demo data only once and does not duplicate records on multiple runs.
* The database strictly enforces the `UNIQUE` email constraint and valid foreign key relationships.

## 13. Error Handling Expectations
* Inserting a duplicate email $\rightarrow$ Fails with `sqlite3.IntegrityError` (`UNIQUE` constraint).
* Inserting an expense with an invalid `user_id` $\rightarrow$ Fails with `sqlite3.IntegrityError` (`FOREIGN KEY` constraint).
* Invalid queries $\rightarrow$ Raise clear `sqlite3` exceptions for debugging.

## 14. Definition of Done
- [ ] Database file is created on app startup
- [ ] Both tables exist with correct schema and constraints
- [ ] Demo user exists with hashed password
- [ ] 8 sample expenses exist across all 7 categories
- [ ] No duplicate seed data on repeated runs
- [ ] App starts without errors
- [ ] Foreign key enforcement works
- [ ] All queries use parameterized SQL