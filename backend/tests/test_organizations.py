"""Tests for organization CRUD, membership, and invites."""
import secrets


def test_no_org_initially(auth_client):
    resp = auth_client.get("/api/orgs/me")
    data = resp.get_json()
    assert data["success"] is True
    assert data["organization"] is None


def test_create_and_manage_org(auth_client):
    """Test full org lifecycle: create, view, list members, update settings."""
    org_name = f"TestCorp-{secrets.token_hex(4)}"
    # Create org
    resp = auth_client.post("/api/orgs", json={"name": org_name})
    data = resp.get_json()
    assert data["success"] is True, f"Create failed: {data}"
    assert data["organization"]["name"] == org_name

    # Get my org
    resp = auth_client.get("/api/orgs/me")
    data = resp.get_json()
    assert data["success"] is True
    assert data["organization"] is not None
    assert data["organization"]["my_role"] == "org_owner"

    # List members
    resp = auth_client.get("/api/orgs/members")
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["members"]) >= 1
    roles = [m["org_role"] for m in data["members"]]
    assert "org_owner" in roles

    # Update settings
    resp = auth_client.put("/api/orgs/settings", json={
        "name": "Updated Corp",
        "billing_email": "billing@corp.com",
    })
    data = resp.get_json()
    assert data["success"] is True


def test_invite_nonexistent_user(auth_client):
    """Invite fails when target user doesn't exist."""
    # Create org first
    auth_client.post("/api/orgs", json={"name": f"InviteOrg-{secrets.token_hex(4)}"})
    resp = auth_client.post("/api/orgs/invite", json={
        "email": "nonexistent@nowhere.com",
        "role": "member",
    })
    data = resp.get_json()
    assert data["success"] is False
    assert "not found" in data["error"].lower() or "register" in data["error"].lower()


def test_org_unauthenticated(client):
    resp = client.get("/api/orgs/me")
    assert resp.status_code == 401
