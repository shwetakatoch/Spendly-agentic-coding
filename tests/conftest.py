import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from database import db

PASSWORD = "Passw0rd!x"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    app_module.app.config.update(TESTING=True)
    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Asha Rao", "asha@example.com", generate_password_hash(PASSWORD)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"email": "asha@example.com", "password": PASSWORD}
