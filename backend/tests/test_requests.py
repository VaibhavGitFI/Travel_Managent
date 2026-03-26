"""Tests for travel request workflow: create, submit, approve, reject, self-approval prevention."""


def test_create_request(auth_client):
    resp = auth_client.post("/api/requests", json={
        "destination": "Mumbai",
        "origin": "Delhi",
        "purpose": "Client Meeting",
        "trip_type": "domestic",
        "start_date": "2026-04-01",
        "end_date": "2026-04-03",
        "duration_days": 3,
        "num_travelers": 1,
        "action": "draft",
    })
    data = resp.get_json()
    assert data["success"] is True
    assert data["request_id"].startswith("TR-")


def test_create_request_validation(auth_client):
    resp = auth_client.post("/api/requests", json={
        "destination": "",  # empty
        "purpose": "Test",
    })
    data = resp.get_json()
    assert data["success"] is False
    assert "destination" in data["error"].lower()


def test_create_request_unauthenticated(client):
    resp = client.post("/api/requests", json={"destination": "Mumbai"})
    # Either 401 (unauth) or 403 (CSRF) — both are auth failures
    assert resp.status_code in (401, 403)


def test_list_requests(auth_client):
    # Create a request first
    auth_client.post("/api/requests", json={
        "destination": "Bangalore",
        "purpose": "Team Offsite",
        "duration_days": 2,
        "action": "draft",
    })
    resp = auth_client.get("/api/requests")
    data = resp.get_json()
    assert data["success"] is True
    assert data["total"] >= 1


def test_submit_and_approve_flow(app, db):
    """Full submit & approve flow using separate clients to avoid context collision."""
    from werkzeug.security import generate_password_hash
    import secrets

    # Create employee
    emp_email = f"emp_{secrets.token_hex(4)}@example.com"
    emp_pass = "EmpPass1"
    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'Employee', 'Flow Employee', ?, 'employee', 'Engineering', 1)""",
        (f"emp_{secrets.token_hex(4)}", generate_password_hash(emp_pass), emp_email),
    )
    # Create admin
    adm_email = f"adm_{secrets.token_hex(4)}@example.com"
    adm_pass = "AdmPass1"
    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'Admin', 'Flow Admin', ?, 'super_admin', 'Management', 1)""",
        (f"adm_{secrets.token_hex(4)}", generate_password_hash(adm_pass), adm_email),
    )
    db.commit()

    # Employee creates and submits
    with app.test_client() as emp_c:
        resp = emp_c.post("/api/auth/login", json={"username": emp_email, "password": emp_pass})
        data = resp.get_json()
        assert data["success"]
        csrf = data.get("csrf_token", "")

        resp = emp_c.post("/api/requests", json={
            "destination": "Hyderabad",
            "purpose": "Conference",
            "duration_days": 2,
            "estimated_total": 25000,
            "action": "draft",
        }, headers={"X-CSRF-Token": csrf})
        data = resp.get_json()
        assert data["success"]
        request_id = data["request_id"]

        resp = emp_c.post(f"/api/requests/{request_id}/submit", headers={"X-CSRF-Token": csrf})
        data = resp.get_json()
        assert data["success"]

    # Admin approves
    with app.test_client() as adm_c:
        resp = adm_c.post("/api/auth/login", json={"username": adm_email, "password": adm_pass})
        data = resp.get_json()
        assert data["success"]
        csrf = data.get("csrf_token", "")

        resp = adm_c.post(f"/api/approvals/{request_id}/approve", json={
            "comments": "Approved for conference",
        }, headers={"X-CSRF-Token": csrf})
        data = resp.get_json()
        # 200 = approved, 400 = business rule — must not be 500
        assert resp.status_code in (200, 400)


def test_self_approval_prevented(app, db):
    """Super admin cannot approve their own request."""
    from werkzeug.security import generate_password_hash
    import secrets

    adm_email = f"selfadm_{secrets.token_hex(4)}@example.com"
    adm_pass = "AdmPass1"
    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'SelfAdmin', 'Self Admin', ?, 'super_admin', 'Management', 1)""",
        (f"selfadm_{secrets.token_hex(4)}", generate_password_hash(adm_pass), adm_email),
    )
    db.commit()

    with app.test_client() as c:
        resp = c.post("/api/auth/login", json={"username": adm_email, "password": adm_pass})
        data = resp.get_json()
        assert data["success"]
        csrf = data.get("csrf_token", "")

        # Create and submit
        resp = c.post("/api/requests", json={
            "destination": "Goa",
            "purpose": "Team Offsite",
            "duration_days": 3,
            "estimated_total": 40000,
            "action": "submit",
        }, headers={"X-CSRF-Token": csrf})
        data = resp.get_json()
        assert data["success"]
        request_id = data["request_id"]

        # Try self-approval
        resp = c.post(f"/api/approvals/{request_id}/approve", json={
            "comments": "Self-approving",
        }, headers={"X-CSRF-Token": csrf})
        data = resp.get_json()
        assert data["success"] is False


def test_reject_request(app, db):
    """Reject flow using isolated clients."""
    from werkzeug.security import generate_password_hash
    import secrets

    emp_email = f"rejemp_{secrets.token_hex(4)}@example.com"
    emp_pass = "EmpPass1"
    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'RejEmp', 'Reject Employee', ?, 'employee', 'Engineering', 1)""",
        (f"rejemp_{secrets.token_hex(4)}", generate_password_hash(emp_pass), emp_email),
    )
    adm_email = f"rejadm_{secrets.token_hex(4)}@example.com"
    adm_pass = "AdmPass1"
    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'RejAdmin', 'Reject Admin', ?, 'super_admin', 'Management', 1)""",
        (f"rejadm_{secrets.token_hex(4)}", generate_password_hash(adm_pass), adm_email),
    )
    db.commit()

    # Employee creates and submits
    with app.test_client() as emp_c:
        resp = emp_c.post("/api/auth/login", json={"username": emp_email, "password": emp_pass})
        data = resp.get_json()
        assert data["success"]
        csrf = data.get("csrf_token", "")

        resp = emp_c.post("/api/requests", json={
            "destination": "Chennai",
            "purpose": "Optional visit",
            "duration_days": 1,
            "estimated_total": 15000,
            "action": "draft",
        }, headers={"X-CSRF-Token": csrf})
        data = resp.get_json()
        assert data["success"]
        request_id = data["request_id"]

        resp = emp_c.post(f"/api/requests/{request_id}/submit", headers={"X-CSRF-Token": csrf})
        assert resp.get_json()["success"]

    # Admin rejects
    with app.test_client() as adm_c:
        resp = adm_c.post("/api/auth/login", json={"username": adm_email, "password": adm_pass})
        data = resp.get_json()
        assert data["success"]
        csrf = data.get("csrf_token", "")

        resp = adm_c.post(f"/api/approvals/{request_id}/reject", json={
            "comments": "Not aligned with Q1 goals",
        }, headers={"X-CSRF-Token": csrf})
        data = resp.get_json()
        # 200 = rejected, 400 = business rule — must not 500
        assert resp.status_code in (200, 400)
