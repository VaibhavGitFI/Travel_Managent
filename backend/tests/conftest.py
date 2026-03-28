"""
Shared pytest fixtures for TravelSync Pro tests.
Uses in-memory SQLite so tests never touch production data.
"""
import os
import sys
import pytest

# Ensure backend/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force SQLite (no Supabase) for tests — MUST be set before any imports
os.environ.pop("DATABASE_URL", None)
os.environ["DATABASE_URL"] = ""  # Explicitly empty to prevent Supabase
os.environ["DEBUG"] = "True"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-not-for-prod"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key"

# Reset any cached PG pool from prior runs
import database as _db_mod
_db_mod._pg_pool = None


class _AuthClient:
    """Wrapper that injects CSRF tokens on state-changing requests."""

    def __init__(self, flask_client, csrf_token, user):
        self._client = flask_client
        self.csrf_token = csrf_token
        self.user = user

    def get(self, *args, **kwargs):
        return self._client.get(*args, **kwargs)

    def post(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["X-CSRF-Token"] = self.csrf_token
        return self._client.post(url, headers=headers, **kwargs)

    def put(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["X-CSRF-Token"] = self.csrf_token
        return self._client.put(url, headers=headers, **kwargs)

    def delete(self, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["X-CSRF-Token"] = self.csrf_token
        return self._client.delete(url, headers=headers, **kwargs)


@pytest.fixture(scope="session")
def app():
    """Create a Flask app with fresh SQLite DB for test isolation."""
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    # Disable rate limiting during tests
    from extensions import limiter
    limiter.enabled = False

    # config.py uses load_dotenv(override=True) which may have loaded the real DATABASE_URL
    # from backend/.env, overriding the empty value set above.
    # Force SQLite for all tests by clearing DATABASE_URL and closing any live Supabase pool.
    import os
    import database as _db_mod
    os.environ["DATABASE_URL"] = ""
    if _db_mod._pg_pool is not None:
        try:
            _db_mod._pg_pool.closeall()
        except Exception:
            pass
        _db_mod._pg_pool = None

    # Re-initialize tables on the local SQLite file now that DATABASE_URL is cleared.
    # (create_app() may have run init_db() against Supabase; this ensures SQLite is ready.)
    with application.app_context():
        from database import init_db
        init_db()

    yield application


@pytest.fixture
def client(app):
    """Flask test client — auto-handles cookies/sessions."""
    with app.test_client() as c:
        yield c


@pytest.fixture
def db(app):
    """Direct DB connection for test assertions."""
    from database import get_db
    conn = get_db()
    yield conn
    conn.close()


@pytest.fixture
def registered_user(client):
    """Register and verify a test user. Returns user dict + password."""
    import secrets
    email = f"test_{secrets.token_hex(4)}@example.com"
    password = "TestPass1"
    # Register
    resp = client.post("/api/auth/register", json={
        "full_name": "Test User",
        "email": email,
        "password": password,
        "department": "Engineering",
    })
    assert resp.status_code in (200, 201), f"Register failed: {resp.get_json()}"

    # Force-verify in DB (skip email)
    from database import get_db
    db = get_db()
    db.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (email,))
    db.commit()
    db.close()

    return {"email": email, "password": password, "full_name": "Test User"}


@pytest.fixture
def auth_client(client, registered_user):
    """Authenticated test client (logged-in employee)."""
    resp = client.post("/api/auth/login", json={
        "username": registered_user["email"],
        "password": registered_user["password"],
    })
    data = resp.get_json()
    assert data.get("success"), f"Login failed: {data}"

    csrf = data.get("csrf_token", "")
    user = data.get("user", {})
    return _AuthClient(client, csrf, user)


@pytest.fixture
def super_admin_client(app, db):
    """Authenticated super_admin — uses a SEPARATE test client to avoid session collision."""
    from werkzeug.security import generate_password_hash
    import secrets

    email = f"admin_{secrets.token_hex(4)}@example.com"
    password = "AdminPass1"
    username = f"admin_{secrets.token_hex(4)}"

    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'Super Admin', 'Super Admin', ?, 'super_admin', 'Management', 1)""",
        (username, generate_password_hash(password), email),
    )
    db.commit()

    # Use a separate test client so we don't overwrite the employee session
    with app.test_client() as admin_c:
        resp = admin_c.post("/api/auth/login", json={"username": email, "password": password})
        data = resp.get_json()
        assert data.get("success"), f"Admin login failed: {data}"

        csrf = data.get("csrf_token", "")
        user = data.get("user", {})
        yield _AuthClient(admin_c, csrf, user)


@pytest.fixture
def manager_client(app, db):
    """Authenticated manager — separate test client."""
    from werkzeug.security import generate_password_hash
    import secrets

    email = f"mgr_{secrets.token_hex(4)}@example.com"
    password = "MgrPass1"
    username = f"mgr_{secrets.token_hex(4)}"

    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'Test Manager', 'Test Manager', ?, 'manager', 'Operations', 1)""",
        (username, generate_password_hash(password), email),
    )
    db.commit()

    with app.test_client() as mgr_c:
        resp = mgr_c.post("/api/auth/login", json={"username": email, "password": password})
        data = resp.get_json()
        assert data.get("success"), f"Manager login failed: {data}"

        csrf = data.get("csrf_token", "")
        user = data.get("user", {})
        yield _AuthClient(mgr_c, csrf, user)
