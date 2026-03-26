"""
Comprehensive endpoint tests — every API route must not 500.
Tests multi-user handling, auth boundaries, and error resilience.
"""
import json


# ── Health & Docs ─────────────────────────────────────────────────────────────

def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] in ("ok", "degraded")


def test_docs_json(client):
    resp = client.get("/api/docs/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "endpoints" in data


# ── Auth Flow ─────────────────────────────────────────────────────────────────

def test_auth_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_auth_login_bad_credentials(client):
    resp = client.post("/api/auth/login", json={
        "username": "nonexistent@example.com",
        "password": "WrongPass1",
    })
    data = resp.get_json()
    assert resp.status_code == 401
    assert data["success"] is False


def test_auth_register_missing_fields(client):
    resp = client.post("/api/auth/register", json={})
    data = resp.get_json()
    assert data["success"] is False


def test_auth_me_authenticated(auth_client):
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "user" in data


# ── Notifications ─────────────────────────────────────────────────────────────

def test_notifications_unauthenticated(client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 401


def test_notifications_list(auth_client):
    resp = auth_client.get("/api/notifications")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "notifications" in data


def test_notifications_bad_limit_param(auth_client):
    """Non-numeric limit param must not 500."""
    resp = auth_client.get("/api/notifications?limit=abc")
    assert resp.status_code == 200


def test_notifications_mark_all_read(auth_client):
    resp = auth_client.post("/api/notifications/read-all")
    assert resp.status_code == 200


# ── Analytics ─────────────────────────────────────────────────────────────────

def test_analytics_dashboard(auth_client):
    resp = auth_client.get("/api/analytics/dashboard")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_analytics_spend(auth_client):
    resp = auth_client.get("/api/analytics/spend")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "success" in data  # May be False on empty DB — must not crash


def test_analytics_compliance(auth_client):
    resp = auth_client.get("/api/analytics/compliance")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "success" in data


# ── Trips ─────────────────────────────────────────────────────────────────────

def test_trips_list_unauthenticated(client):
    resp = client.get("/api/trips")
    assert resp.status_code == 401


def test_trips_list(auth_client):
    resp = auth_client.get("/api/trips")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "trips" in data


# ── Requests ──────────────────────────────────────────────────────────────────

def test_requests_list(auth_client):
    resp = auth_client.get("/api/requests")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_requests_bad_pagination(auth_client):
    """Non-numeric page/per_page must not 500."""
    resp = auth_client.get("/api/requests?page=abc&per_page=xyz")
    assert resp.status_code == 200


def test_create_request_draft(auth_client):
    resp = auth_client.post("/api/requests", json={
        "destination": "Pune",
        "origin": "Mumbai",
        "purpose": "Team Sync",
        "trip_type": "domestic",
        "start_date": "2026-05-01",
        "end_date": "2026-05-02",
        "duration_days": 2,
        "num_travelers": 1,
        "estimated_total": 12000,
        "action": "draft",
    })
    data = resp.get_json()
    assert data["success"] is True
    assert data["request_id"].startswith("TR-")


def test_create_request_validation_empty_destination(auth_client):
    resp = auth_client.post("/api/requests", json={
        "destination": "",
        "purpose": "Test",
    })
    data = resp.get_json()
    assert data["success"] is False


# ── Approvals ─────────────────────────────────────────────────────────────────

def test_approvals_employee_view(auth_client):
    resp = auth_client.get("/api/approvals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["view"] == "employee"


def test_approvals_manager_view(super_admin_client):
    resp = super_admin_client.get("/api/approvals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["view"] == "manager"


def test_approve_nonexistent_request(super_admin_client):
    resp = super_admin_client.post("/api/approvals/FAKE-ID/approve", json={})
    data = resp.get_json()
    assert data["success"] is False


# ── Expenses ──────────────────────────────────────────────────────────────────

def test_expenses_list(auth_client):
    resp = auth_client.get("/api/expenses")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "expenses" in data


def test_expenses_bad_pagination(auth_client):
    resp = auth_client.get("/api/expenses?page=abc&per_page=xyz")
    assert resp.status_code == 200


# ── Meetings ──────────────────────────────────────────────────────────────────

def test_meetings_list(auth_client):
    resp = auth_client.get("/api/meetings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_meetings_create(auth_client):
    resp = auth_client.post("/api/meetings", json={
        "destination": "Delhi",
        "client_name": "John Doe",
        "company": "Acme Corp",
        "meeting_date": "2026-05-10",
        "meeting_time": "10:00 AM",
        "venue": "Acme HQ",
        "agenda": "Q2 Planning",
        "contact_number": "+91-9876543210",
        "email": "john@acme.com",
    })
    data = resp.get_json()
    # 200 or 201 = created, 400 = validation — neither should be 500
    assert resp.status_code in (200, 201, 400)
    assert "success" in data


# ── Chat ──────────────────────────────────────────────────────────────────────

def test_chat_history_unauthenticated(client):
    resp = client.get("/api/chat/history")
    assert resp.status_code == 401


def test_chat_history(auth_client):
    resp = auth_client.get("/api/chat/history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_chat_history_bad_limit(auth_client):
    resp = auth_client.get("/api/chat/history?limit=abc")
    assert resp.status_code == 200


# ── Alerts ────────────────────────────────────────────────────────────────────

def test_alerts(auth_client):
    resp = auth_client.get("/api/alerts")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "alerts" in data


# ── Weather ───────────────────────────────────────────────────────────────────

def test_weather_current(auth_client):
    resp = auth_client.get("/api/weather/current?city=Mumbai")
    # May be 200 (live) or 200 (fallback) — either is fine
    assert resp.status_code == 200


# ── Currency ──────────────────────────────────────────────────────────────────

def test_currency_convert(auth_client):
    resp = auth_client.post("/api/currency/convert", json={
        "from_currency": "USD",
        "to_currency": "INR",
        "amount": 100,
    })
    assert resp.status_code == 200


# ── Users (admin-only) ───────────────────────────────────────────────────────

def test_users_list_unauthorized(auth_client):
    """Regular employee cannot access user management."""
    resp = auth_client.get("/api/users")
    assert resp.status_code == 403


def test_users_list_as_admin(super_admin_client):
    resp = super_admin_client.get("/api/users")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["total"] >= 1


# ── Agents ────────────────────────────────────────────────────────────────────

def test_agents_list(auth_client):
    resp = auth_client.get("/api/agents")
    assert resp.status_code == 200


def test_agents_health(auth_client):
    resp = auth_client.get("/api/agents/health")
    assert resp.status_code == 200


# ── Audit ─────────────────────────────────────────────────────────────────────

def test_audit_logs(super_admin_client):
    resp = super_admin_client.get("/api/audit")
    assert resp.status_code == 200


# ── Webhooks ──────────────────────────────────────────────────────────────────

def test_webhook_events(auth_client):
    resp = auth_client.get("/api/webhooks/events")
    assert resp.status_code == 200


# ── Multi-User Tests ──────────────────────────────────────────────────────────
# These tests use separate fixtures that each get their own test_client,
# so they don't mix auth_client and super_admin_client in the same test.

def test_employee_cannot_approve(auth_client):
    """Regular employee cannot approve requests."""
    resp = auth_client.post("/api/approvals/FAKE-ID/approve", json={})
    assert resp.status_code == 403


def test_admin_sees_all_requests(super_admin_client):
    """Admin can list all requests system-wide."""
    resp = super_admin_client.get("/api/requests")
    data = resp.get_json()
    assert data["success"] is True
    assert "requests" in data


def test_admin_full_approval_flow(super_admin_client, app, db):
    """Full flow with separate users using sequential session switching."""
    from werkzeug.security import generate_password_hash
    import secrets

    # Create an employee user directly in DB
    emp_email = f"emp_{secrets.token_hex(4)}@example.com"
    emp_pass = "EmpPass1"
    emp_user = f"emp_{secrets.token_hex(4)}"
    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'Employee', 'Test Employee', ?, 'employee', 'Engineering', 1)""",
        (emp_user, generate_password_hash(emp_pass), emp_email),
    )
    db.commit()

    # Use a separate client for the employee
    with app.test_client() as emp_c:
        # Employee logs in
        resp = emp_c.post("/api/auth/login", json={"username": emp_email, "password": emp_pass})
        data = resp.get_json()
        assert data.get("success"), f"Employee login failed: {data}"
        emp_csrf = data.get("csrf_token", "")

        # Employee creates a draft request
        resp = emp_c.post("/api/requests", json={
            "destination": "Jaipur",
            "origin": "Delhi",
            "purpose": "Sales Meeting",
            "duration_days": 2,
            "estimated_total": 20000,
            "action": "draft",
        }, headers={"X-CSRF-Token": emp_csrf})
        data = resp.get_json()
        assert data["success"] is True
        req_id = data["request_id"]

        # Employee submits
        resp = emp_c.post(f"/api/requests/{req_id}/submit", headers={"X-CSRF-Token": emp_csrf})
        data = resp.get_json()
        assert data["success"] is True

    # Admin approves (using super_admin_client fixture)
    resp = super_admin_client.post(f"/api/approvals/{req_id}/approve", json={
        "comments": "Approved for Q2 sales",
    })
    data = resp.get_json()
    # 200 = approved, 400 = business rule (e.g., different approver assigned)
    # Neither should be 500
    assert resp.status_code in (200, 400)
    assert "success" in data


# ── Error Resilience ──────────────────────────────────────────────────────────

def test_404_api_endpoint(client):
    resp = client.get("/api/nonexistent")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["success"] is False


def test_405_wrong_method(client):
    resp = client.delete("/api/health")
    assert resp.status_code == 405
    data = resp.get_json()
    assert data["success"] is False


def test_invalid_json_body(auth_client):
    resp = auth_client.post("/api/requests",
                            data="not json",
                            content_type="application/json")
    # Should not crash — returns 400 or handles gracefully
    assert resp.status_code in (200, 400, 422)


def test_empty_json_body(auth_client):
    resp = auth_client.post("/api/requests", json={})
    data = resp.get_json()
    assert data["success"] is False
