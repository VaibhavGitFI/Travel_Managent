"""Tests for authentication: register, login, JWT, CSRF, roles."""


def test_register_success(client):
    resp = client.post("/api/auth/register", json={
        "full_name": "Alice Smith",
        "email": "alice@test.com",
        "password": "AlicePass1",
        "department": "Sales",
    })
    data = resp.get_json()
    assert data["success"] is True
    assert data.get("needs_verification") is True


def test_register_weak_password(client):
    resp = client.post("/api/auth/register", json={
        "full_name": "Bob", "email": "bob@test.com", "password": "weak",
    })
    data = resp.get_json()
    assert data["success"] is False
    assert "8 characters" in data["error"]


def test_register_no_uppercase(client):
    resp = client.post("/api/auth/register", json={
        "full_name": "Bob", "email": "bob2@test.com", "password": "lowercase1",
    })
    data = resp.get_json()
    assert data["success"] is False
    assert "uppercase" in data["error"]


def test_register_duplicate_email(client):
    payload = {"full_name": "Dup1", "email": "dup@test.com", "password": "DupPass1"}
    client.post("/api/auth/register", json=payload)
    # Verify first user
    from database import get_db
    db = get_db()
    db.execute("UPDATE users SET email_verified = 1 WHERE email = 'dup@test.com'")
    db.commit()
    db.close()
    # Try again
    resp = client.post("/api/auth/register", json=payload)
    data = resp.get_json()
    assert resp.status_code == 409
    assert "already exists" in data["error"]


def test_login_success(client, registered_user):
    resp = client.post("/api/auth/login", json={
        "username": registered_user["email"],
        "password": registered_user["password"],
    })
    data = resp.get_json()
    assert data["success"] is True
    assert "access_token" in data
    assert "refresh_token" in data
    assert "csrf_token" in data
    assert data["user"]["email"] == registered_user["email"]
    assert data["user"]["role"] == "employee"


def test_login_wrong_password(client, registered_user):
    resp = client.post("/api/auth/login", json={
        "username": registered_user["email"],
        "password": "WrongPass1",
    })
    data = resp.get_json()
    assert data["success"] is False
    assert resp.status_code == 401


def test_login_unverified_blocked(client):
    client.post("/api/auth/register", json={
        "full_name": "Unverified", "email": "unverified@test.com", "password": "TestPass1",
    })
    resp = client.post("/api/auth/login", json={
        "username": "unverified@test.com", "password": "TestPass1",
    })
    data = resp.get_json()
    assert data["success"] is False
    assert data.get("needs_verification") is True


def test_me_endpoint(auth_client):
    resp = auth_client.get("/api/auth/me")
    data = resp.get_json()
    assert data["success"] is True
    assert "password_hash" not in data["user"]


def test_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_jwt_auth(client, registered_user):
    # Login to get token
    resp = client.post("/api/auth/login", json={
        "username": registered_user["email"],
        "password": registered_user["password"],
    })
    token = resp.get_json()["access_token"]

    # Use token for auth
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    data = resp.get_json()
    assert data["success"] is True


def test_jwt_revocation_on_logout(client, registered_user):
    # Login
    resp = client.post("/api/auth/login", json={
        "username": registered_user["email"],
        "password": registered_user["password"],
    })
    data = resp.get_json()
    token = data["access_token"]
    csrf = data["csrf_token"]

    # Logout with token
    client.post("/api/auth/logout", json={"access_token": token},
                headers={"X-CSRF-Token": csrf})

    # Token should now be revoked
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_csrf_required_on_post(client, registered_user):
    # Login
    resp = client.post("/api/auth/login", json={
        "username": registered_user["email"],
        "password": registered_user["password"],
    })
    data = resp.get_json()
    assert data["success"]

    # POST without CSRF should fail (session-based auth)
    resp = client.post("/api/requests", json={"destination": "Mumbai"})
    assert resp.status_code == 403
    assert "CSRF" in resp.get_json()["error"]


def test_csrf_exempt_for_jwt(client, registered_user):
    # Login to get JWT
    resp = client.post("/api/auth/login", json={
        "username": registered_user["email"],
        "password": registered_user["password"],
    })
    token = resp.get_json()["access_token"]

    # POST with JWT but no CSRF should work (JWT is CSRF-exempt)
    resp = client.post("/api/requests", json={"destination": "Mumbai"},
                       headers={"Authorization": f"Bearer {token}"})
    # May fail for other reasons, but NOT 403 CSRF
    assert resp.status_code != 403


def test_super_admin_required(auth_client):
    # Regular user shouldn't access user management
    resp = auth_client.get("/api/users")
    assert resp.status_code == 403


def test_super_admin_access(super_admin_client):
    resp = super_admin_client.get("/api/users")
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data["users"], list)
