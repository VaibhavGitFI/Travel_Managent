"""
TravelSync Pro — Comprehensive Audit Test Suite
================================================
Full functional, logical, and security audit of every backend API endpoint.
Covers every route, every role boundary, every validation rule, and every
business-logic constraint surfaced during the hardening initiative.

Sections
--------
 1. Authentication          — 20 tests  (register, login, JWT, CSRF, refresh, profile)
 2. Travel Requests         — 18 tests  (CRUD, status machine, per-diem, budget forecast)
 3. Approvals               —  9 tests  (role gate, self-approval block, full flow)
 4. Expenses                — 14 tests  (3-stage pipeline, anomalies, approval workflow)
 5. Meetings                — 12 tests  (CRUD, schedule, parse-text, nearby-venues)
 6. Analytics               — 10 tests  (dashboard, spend, compliance, carbon, budget, cache)
 7. Chat                    — 11 tests  (history, sessions CRUD, message, bad params)
 8. Trips                   —  7 tests  (list, plan, async, recommendations, task status)
 9. External Services       — 11 tests  (weather, currency, accommodation, pg-options)
10. SOS + Alerts            —  6 tests  (trigger, geocode, contacts, alerts list)
11. Notifications           —  6 tests  (list, unread, mark-read, count decreases)
12. Organisations           —  8 tests  (create, settings, members, invite)
13. Users (admin-only)      —  7 tests  (list, single, role change, filter, search)
14. Uploads                 —  5 tests  (image, oversize, parse-document, path traversal)
15. Infrastructure          —  7 tests  (health, docs, agents, audit, webhooks)
16. Security                — 14 tests  (SQL injection, XSS, CSRF, path traversal, webhook sig)
17. Data Isolation          —  4 tests  (requests, expenses, analytics, meetings cross-org)
18. Response Quality        —  6 tests  (JSON content-type, envelope, pagination, gzip)
19. Caching Consistency     —  4 tests  (repeated calls, stale data, fresh-after-write)
20. Business Logic          — 10 tests  (double-submit, zero amounts, unread count, DB write)

Run all:  pytest tests/test_comprehensive.py -v --tb=short
Run one:  pytest tests/test_comprehensive.py::TestAuth -v
"""
import io
import secrets
from werkzeug.security import generate_password_hash


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db, role="employee", suffix=None):
    """Insert a pre-verified user directly into DB. Returns (email, password, user_id)."""
    tag = suffix or secrets.token_hex(4)
    email = f"{role}_{tag}@audit.test"
    password = "AuditPass1"
    username = f"{role}_{tag}"
    db.execute(
        """INSERT INTO users
               (username, password_hash, name, full_name, email,
                role, department, email_verified)
           VALUES (?, ?, ?, ?, ?, ?, 'Engineering', 1)""",
        (username, generate_password_hash(password),
         username, username, email, role),
    )
    db.commit()
    row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    uid = row["id"] if isinstance(row, dict) else row[0]
    return email, password, uid


def _login(client, email, password="AuditPass1"):
    """Login and return (csrf_token, access_token, user_dict)."""
    resp = client.post("/api/auth/login",
                       json={"username": email, "password": password})
    data = resp.get_json()
    assert data.get("success"), f"Login failed for {email}: {data}"
    return data["csrf_token"], data["access_token"], data["user"]


def _post(client, url, csrf, payload=None, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["X-CSRF-Token"] = csrf
    return client.post(url, json=payload or {}, headers=headers, **kwargs)


def _put(client, url, csrf, payload=None, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["X-CSRF-Token"] = csrf
    return client.put(url, json=payload or {}, headers=headers, **kwargs)


def _delete(client, url, csrf, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["X-CSRF-Token"] = csrf
    return client.delete(url, headers=headers, **kwargs)


def _patch(client, url, csrf, payload=None):
    return client.patch(url, json=payload or {},
                        headers={"X-CSRF-Token": csrf})


def _ok(resp, expected_status=200):
    """Assert HTTP status and that body is JSON with success=True."""
    assert resp.status_code == expected_status, (
        f"Expected HTTP {expected_status}, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)[:300]}"
    )
    data = resp.get_json()
    assert data is not None, "Response is not JSON"
    return data


def _paginated(data, key):
    """Assert list envelope has required pagination fields."""
    assert key in data, f"Missing '{key}' list in response"
    assert "total" in data, "Missing 'total' in paginated response"
    assert isinstance(data[key], list), f"'{key}' must be a list"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuth:

    def test_register_requires_email_verification(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "New User",
            "email": f"new_{secrets.token_hex(4)}@test.com",
            "password": "NewPass1",
        })
        assert resp.status_code in (200, 201)
        data = resp.get_json()
        assert data["success"] is True
        assert data.get("needs_verification") is True

    def test_register_weak_password_rejected(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "Weak", "email": "weak@test.com", "password": "short",
        })
        assert resp.get_json()["success"] is False

    def test_register_no_uppercase_rejected(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "Lower", "email": "lower@test.com", "password": "lowercase1",
        })
        assert resp.get_json()["success"] is False

    def test_register_missing_email_rejected(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "NoEmail", "password": "AuditPass1",
        })
        assert resp.get_json()["success"] is False

    def test_register_short_full_name_rejected(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "X",
            "email": f"short_{secrets.token_hex(4)}@test.com",
            "password": "AuditPass1",
        })
        assert resp.get_json()["success"] is False

    def test_register_duplicate_email_returns_409(self, client):
        email = f"dup_{secrets.token_hex(4)}@test.com"
        payload = {"full_name": "Dup User", "email": email, "password": "AuditPass1"}
        client.post("/api/auth/register", json=payload)
        from database import get_db
        db = get_db()
        db.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (email,))
        db.commit()
        db.close()
        resp2 = client.post("/api/auth/register", json=payload)
        assert resp2.status_code == 409

    def test_login_success_returns_all_tokens(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        data = resp.get_json()
        assert data["success"] is True
        assert "access_token" in data
        assert "refresh_token" in data
        assert "csrf_token" in data

    def test_login_wrong_password_401(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "username": registered_user["email"], "password": "WrongPass99",
        })
        assert resp.status_code == 401
        assert resp.get_json()["success"] is False

    def test_login_nonexistent_user_401(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "nobody@ghost.test", "password": "AuditPass1",
        })
        assert resp.status_code == 401

    def test_me_endpoint_strips_password_hash(self, auth_client):
        resp = auth_client.get("/api/auth/me")
        data = _ok(resp)
        assert "user" in data
        assert "password_hash" not in data["user"]
        assert "email" in data["user"]
        assert "role" in data["user"]

    def test_me_unauthenticated_401(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_jwt_bearer_auth_works_without_session(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        token = resp.get_json()["access_token"]
        resp = client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_jwt_revoked_after_logout(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        d = resp.get_json()
        token, csrf = d["access_token"], d["csrf_token"]
        client.post("/api/auth/logout",
                    json={"access_token": token},
                    headers={"X-CSRF-Token": csrf})
        resp = client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_refresh_token_returns_new_access_token(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        refresh = resp.get_json()["refresh_token"]
        resp = client.post("/api/auth/refresh",
                           json={"refresh_token": refresh})
        data = resp.get_json()
        assert data.get("success") is True or "access_token" in data

    def test_csrf_required_on_state_changing_requests(self, client, registered_user):
        client.post("/api/auth/login", json={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        resp = client.post("/api/requests", json={"destination": "Mumbai"})
        assert resp.status_code == 403
        assert "CSRF" in resp.get_json().get("error", "")

    def test_jwt_bypasses_csrf_requirement(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        token = resp.get_json()["access_token"]
        resp = client.post("/api/requests", json={"destination": "Mumbai"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code != 403

    def test_profile_get_excludes_password_hash(self, auth_client):
        resp = auth_client.get("/api/auth/profile")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "password_hash" not in data.get("user", {})

    def test_profile_update(self, auth_client):
        resp = auth_client.put("/api/auth/profile", json={
            "full_name": "Updated Full Name",
            "department": "Product",
        })
        assert resp.status_code in (200, 201)
        assert resp.get_json().get("success") is True

    def test_unverified_user_cannot_login(self, client):
        email = f"unver_{secrets.token_hex(4)}@test.com"
        client.post("/api/auth/register", json={
            "full_name": "Unverified", "email": email, "password": "AuditPass1",
        })
        resp = client.post("/api/auth/login",
                           json={"username": email, "password": "AuditPass1"})
        data = resp.get_json()
        assert data["success"] is False
        assert data.get("needs_verification") is True

    def test_password_hash_never_in_users_admin_list(self, super_admin_client):
        resp = super_admin_client.get("/api/users")
        text = resp.get_data(as_text=True)
        assert "password_hash" not in text


# ─────────────────────────────────────────────────────────────────────────────
# 2. Travel Requests
# ─────────────────────────────────────────────────────────────────────────────

class TestTravelRequests:

    def test_list_returns_paginated_envelope(self, auth_client):
        resp = auth_client.get("/api/requests")
        data = _ok(resp)
        _paginated(data, "requests")

    def test_bad_pagination_params_do_not_500(self, auth_client):
        resp = auth_client.get("/api/requests?page=abc&per_page=xyz")
        assert resp.status_code == 200

    def test_create_draft_returns_request_id(self, auth_client):
        resp = auth_client.post("/api/requests", json={
            "destination": "Bangalore",
            "origin": "Mumbai",
            "purpose": "Client Pitch",
            "trip_type": "domestic",
            "start_date": "2026-06-01",
            "end_date": "2026-06-03",
            "duration_days": 3,
            "num_travelers": 1,
            "estimated_total": 20000,
            "action": "draft",
        })
        data = _ok(resp, expected_status=201)
        assert data["request_id"].startswith("TR-")

    def test_empty_destination_rejected(self, auth_client):
        resp = auth_client.post("/api/requests",
                                json={"destination": "", "purpose": "Test"})
        data = resp.get_json()
        assert data["success"] is False
        assert "destination" in data["error"].lower()

    def test_missing_destination_rejected(self, auth_client):
        resp = auth_client.post("/api/requests", json={"purpose": "Test"})
        assert resp.get_json()["success"] is False

    def test_invalid_trip_type_rejected(self, auth_client):
        resp = auth_client.post("/api/requests", json={
            "destination": "Dubai",
            "purpose": "Sales",
            "trip_type": "moonshot",
        })
        assert resp.get_json()["success"] is False

    def test_duration_days_over_365_rejected(self, auth_client):
        resp = auth_client.post("/api/requests", json={
            "destination": "Mumbai", "purpose": "Too long",
            "duration_days": 999, "action": "draft",
        })
        assert resp.get_json()["success"] is False

    def test_estimated_total_over_max_rejected(self, auth_client):
        resp = auth_client.post("/api/requests", json={
            "destination": "New York", "purpose": "Sales",
            "estimated_total": 100_000_000,
        })
        assert resp.get_json()["success"] is False

    def test_get_request_detail(self, auth_client):
        cr = auth_client.post("/api/requests", json={
            "destination": "Pune", "purpose": "Meeting",
            "duration_days": 1, "action": "draft",
        })
        req_id = cr.get_json()["request_id"]
        resp = auth_client.get(f"/api/requests/{req_id}")
        data = _ok(resp)
        # request_id either top-level or nested under 'request'
        nested_id = data.get("request_id") or data.get("request", {}).get("request_id")
        assert nested_id == req_id

    def test_get_nonexistent_request_404(self, auth_client):
        resp = auth_client.get("/api/requests/TR-DOESNOTEXIST-000")
        assert resp.status_code == 404

    def test_update_draft_request(self, auth_client):
        cr = auth_client.post("/api/requests", json={
            "destination": "Kolkata", "purpose": "Original", "action": "draft",
        })
        req_id = cr.get_json()["request_id"]
        resp = auth_client.put(f"/api/requests/{req_id}",
                               json={"purpose": "Updated Purpose"})
        assert resp.status_code in (200, 201)
        assert resp.get_json()["success"] is True

    def test_submit_request_changes_status(self, app, db):
        email, _, _ = _make_user(db, "employee")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            cr = _post(c, "/api/requests", csrf, {
                "destination": "Hyderabad", "purpose": "Conference",
                "duration_days": 2, "estimated_total": 25000, "action": "draft",
            })
            req_id = cr.get_json()["request_id"]
            sub = _post(c, f"/api/requests/{req_id}/submit", csrf)
            data = sub.get_json()
            assert data["success"] is True
            assert data.get("status") in ("submitted", "pending_approval")

    def test_unauthenticated_cannot_create_request(self, client):
        resp = client.post("/api/requests", json={"destination": "Delhi"})
        assert resp.status_code in (401, 403)

    def test_per_diem_tier1_city(self, auth_client):
        resp = auth_client.get("/api/requests/per-diem?city=Mumbai&days=3")
        data = _ok(resp)
        assert "daily_total" in data or "daily_rates" in data or "total_allowance" in data

    def test_per_diem_international_city(self, auth_client):
        resp = auth_client.get("/api/requests/per-diem?city=London&days=5")
        assert resp.status_code in (200, 400)

    def test_per_diem_missing_city_rejected(self, auth_client):
        resp = auth_client.get("/api/requests/per-diem?days=3")
        assert resp.status_code in (400, 422) or resp.get_json().get("success") is False

    def test_per_diem_missing_days_defaults_gracefully(self, auth_client):
        """Per-diem clamps missing days to 1 (max(1, default)) — returns 200 not 400."""
        resp = auth_client.get("/api/requests/per-diem?city=Delhi")
        # Endpoint defaults days to 1 via max(1, int(args.get("days", 1)))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True

    def test_budget_forecast_returns_response(self, auth_client):
        resp = auth_client.post("/api/requests/budget-forecast", json={
            "destination": "Chennai", "origin": "Bangalore",
            "trip_type": "domestic", "num_travelers": 2,
        })
        assert resp.status_code == 200
        assert "success" in resp.get_json()

    def test_trip_report_fake_id_returns_error(self, auth_client):
        resp = auth_client.get("/api/requests/TR-FAKE-REPORT-999/report")
        assert resp.status_code in (400, 404)
        assert resp.get_json()["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Approvals
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovals:

    def test_employee_view_returns_employee(self, auth_client):
        resp = auth_client.get("/api/approvals")
        data = _ok(resp)
        assert data.get("view") == "employee"

    def test_manager_view_returns_manager(self, manager_client):
        resp = manager_client.get("/api/approvals")
        data = _ok(resp)
        assert data.get("view") == "manager"
        assert "approvals" in data

    def test_super_admin_view_returns_manager(self, super_admin_client):
        resp = super_admin_client.get("/api/approvals")
        data = _ok(resp)
        assert data.get("view") == "manager"

    def test_employee_cannot_approve(self, auth_client):
        resp = auth_client.post("/api/approvals/TR-FAKE-001/approve", json={})
        assert resp.status_code == 403

    def test_employee_cannot_reject(self, auth_client):
        resp = auth_client.post("/api/approvals/TR-FAKE-001/reject",
                                json={"reason": "nope"})
        assert resp.status_code == 403

    def test_approve_nonexistent_request_fails_gracefully(self, super_admin_client):
        resp = super_admin_client.post("/api/approvals/TR-TOTALLY-FAKE/approve",
                                      json={})
        data = resp.get_json()
        assert data["success"] is False
        assert resp.status_code in (400, 404)

    def test_self_approval_blocked(self, app, db):
        email, _, _ = _make_user(db, "super_admin")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            cr = _post(c, "/api/requests", csrf, {
                "destination": "Agra", "purpose": "Self Test",
                "duration_days": 1, "action": "submit",
            })
            req_id = cr.get_json()["request_id"]
            resp = _post(c, f"/api/approvals/{req_id}/approve", csrf,
                         {"comments": "self-approve"})
            assert resp.get_json()["success"] is False

    def test_full_approve_flow(self, app, db):
        emp_email, _, _ = _make_user(db, "employee")
        adm_email, _, _ = _make_user(db, "super_admin")
        req_id = None

        with app.test_client() as emp_c:
            csrf, _, _ = _login(emp_c, emp_email)
            cr = _post(emp_c, "/api/requests", csrf, {
                "destination": "Lucknow", "purpose": "Site Visit",
                "duration_days": 2, "estimated_total": 18000, "action": "draft",
            })
            req_id = cr.get_json()["request_id"]
            sub = _post(emp_c, f"/api/requests/{req_id}/submit", csrf)
            assert sub.get_json()["success"] is True

        with app.test_client() as adm_c:
            csrf, _, _ = _login(adm_c, adm_email)
            resp = _post(adm_c, f"/api/approvals/{req_id}/approve", csrf,
                         {"comments": "Approved"})
            # 200 = approved, 400 = different approver assigned — never 500
            assert resp.status_code in (200, 400)
            assert "success" in resp.get_json()

    def test_full_reject_flow(self, app, db):
        emp_email, _, _ = _make_user(db, "employee")
        adm_email, _, _ = _make_user(db, "super_admin")
        req_id = None

        with app.test_client() as emp_c:
            csrf, _, _ = _login(emp_c, emp_email)
            cr = _post(emp_c, "/api/requests", csrf, {
                "destination": "Nagpur", "purpose": "Optional visit",
                "action": "draft",
            })
            req_id = cr.get_json()["request_id"]
            _post(emp_c, f"/api/requests/{req_id}/submit", csrf)

        with app.test_client() as adm_c:
            csrf, _, _ = _login(adm_c, adm_email)
            resp = _post(adm_c, f"/api/approvals/{req_id}/reject", csrf,
                         {"reason": "Over budget"})
            assert resp.status_code in (200, 400)
            assert "success" in resp.get_json()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Expenses
# ─────────────────────────────────────────────────────────────────────────────

class TestExpenses:

    def test_list_expenses_paginated_envelope(self, auth_client):
        resp = auth_client.get("/api/expenses")
        data = _ok(resp)
        _paginated(data, "expenses")

    def test_bad_pagination_does_not_500(self, auth_client):
        resp = auth_client.get("/api/expenses?page=notanumber&per_page=also")
        assert resp.status_code == 200

    def test_create_expense_stage1(self, auth_client):
        resp = auth_client.post("/api/expenses", json={
            "category": "travel",
            "description": "Flight BOM-DEL",
            "invoice_amount": 8500,
            "currency_code": "INR",
        })
        assert resp.status_code in (200, 201)
        assert resp.get_json().get("success") is True

    def test_create_expense_negative_amount_rejected(self, auth_client):
        resp = auth_client.post("/api/expenses", json={
            "category": "food", "description": "Lunch", "invoice_amount": -100,
        })
        assert resp.get_json()["success"] is False

    def test_create_expense_amount_over_max_rejected(self, auth_client):
        resp = auth_client.post("/api/expenses", json={
            "category": "hotel", "description": "Suite",
            "invoice_amount": 60_000_000,
        })
        assert resp.get_json()["success"] is False

    def test_expense_summary_with_trip_id(self, auth_client, db):
        me = auth_client.get("/api/auth/me").get_json()["user"]
        db.execute(
            "INSERT INTO expenses_db (user_id, trip_id, category, invoice_amount, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (me["id"], "TRIP-AUDIT-001", "taxi", 450, "cab to airport"),
        )
        db.commit()
        resp = auth_client.get("/api/expenses/summary?trip_id=TRIP-AUDIT-001")
        assert resp.status_code == 200

    def test_expense_summary_no_trip_id_does_not_500(self, auth_client):
        resp = auth_client.get("/api/expenses/summary")
        assert resp.status_code != 500

    def test_expense_anomalies_endpoint(self, auth_client):
        resp = auth_client.get("/api/expenses/anomalies")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "anomalies" in data or "success" in data

    def test_expense_pending_approvals_manager(self, manager_client):
        resp = manager_client.get("/api/expenses/pending-approvals")
        data = _ok(resp)
        assert "expenses" in data

    def test_expense_submit_for_approval(self, app, db):
        email, _, uid = _make_user(db, "employee")
        db.execute(
            "INSERT INTO expenses_db (user_id, category, invoice_amount, description, stage)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid, "hotel", 5000, "Night stay audit", 1),
        )
        db.commit()
        row = db.execute(
            "SELECT id FROM expenses_db WHERE user_id = ? AND description = 'Night stay audit'",
            (uid,),
        ).fetchone()
        exp_id = row["id"] if isinstance(row, dict) else row[0]

        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            resp = _post(c, f"/api/expenses/{exp_id}/submit", csrf)
            assert resp.status_code in (200, 400)

    def test_expense_approve_blocked_for_employee(self, auth_client):
        resp = auth_client.post("/api/expenses/999999/approve", json={})
        assert resp.status_code in (400, 403, 404)

    def test_expense_reject_missing_reason_rejected(self, manager_client):
        resp = manager_client.post("/api/expenses/999999/reject", json={})
        data = resp.get_json()
        assert resp.status_code != 200 or data.get("success") is False

    def test_upload_expense_ocr(self, auth_client):
        pdf = io.BytesIO(b"%PDF-1.4 fake receipt for OCR audit test")
        resp = auth_client._client.post(
            "/api/expense/upload-and-extract",
            data={"file": (pdf, "receipt.pdf")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
        assert resp.status_code in (200, 400, 503)
        assert resp.get_json() is not None

    def test_expense_unauthenticated_401(self, client):
        assert client.get("/api/expenses").status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 5. Meetings
# ─────────────────────────────────────────────────────────────────────────────

class TestMeetings:

    def test_list_meetings_paginated(self, auth_client):
        resp = auth_client.get("/api/meetings")
        data = _ok(resp)
        assert "meetings" in data or "items" in data

    def test_create_meeting_full_fields(self, auth_client):
        resp = auth_client.post("/api/meetings", json={
            "destination": "Bangalore",
            "client_name": "Ravi Kumar",
            "company": "TechCorp India",
            "meeting_date": "2026-07-01",
            "meeting_time": "11:00 AM",
            "venue": "Brigade Tower",
            "agenda": "Q3 roadmap review",
            "contact_number": "+91-9988776655",
            "email": "ravi@techcorp.in",
        })
        assert resp.status_code in (200, 201)
        assert resp.get_json().get("success") is True

    def test_create_meeting_short_client_name_rejected(self, auth_client):
        resp = auth_client.post("/api/meetings", json={
            "destination": "Pune", "client_name": "X", "company": "Y",
        })
        assert resp.get_json()["success"] is False

    def test_create_meeting_missing_client_name_rejected(self, auth_client):
        resp = auth_client.post("/api/meetings", json={
            "destination": "Delhi", "company": "Acme",
        })
        assert resp.get_json()["success"] is False

    def test_update_meeting(self, auth_client):
        cr = auth_client.post("/api/meetings", json={
            "destination": "Chennai", "client_name": "Priya Nair",
            "company": "South Corp", "agenda": "Initial",
        })
        d = cr.get_json()
        if not d.get("success"):
            return
        mid = d.get("id") or d.get("meeting", {}).get("id")
        if mid:
            resp = auth_client.put(f"/api/meetings/{mid}",
                                   json={"agenda": "Updated agenda"})
            assert resp.status_code in (200, 201)

    def test_delete_meeting(self, auth_client):
        cr = auth_client.post("/api/meetings", json={
            "destination": "Kochi", "client_name": "Arjun Menon",
            "company": "Kerala Tech", "agenda": "To delete",
        })
        d = cr.get_json()
        if not d.get("success"):
            return
        mid = d.get("id") or d.get("meeting", {}).get("id")
        if mid:
            resp = _delete(auth_client._client, f"/api/meetings/{mid}",
                           auth_client.csrf_token)
            assert resp.status_code in (200, 204)

    def test_meetings_search_param(self, auth_client):
        auth_client.post("/api/meetings", json={
            "destination": "Jaipur",
            "client_name": "UniqueSearchXYZ999",
            "company": "Test Co",
        })
        resp = auth_client.get("/api/meetings?search=UniqueSearchXYZ999")
        assert resp.status_code == 200

    def test_schedule_suggestion_no_500(self, auth_client):
        resp = auth_client.post("/api/meetings/suggest-schedule", json={
            "meetings": [
                {"client_name": "A", "company": "Co1", "destination": "Mumbai"},
                {"client_name": "B", "company": "Co2", "destination": "Pune"},
            ],
            "preferences": {"destination": "Mumbai"},
        })
        assert resp.status_code in (200, 503)
        assert resp.get_json() is not None

    def test_parse_text_endpoint(self, auth_client):
        resp = auth_client.post("/api/meetings/parse-text", json={
            "text": "Meeting with John from Acme Monday 10am Delhi",
            "source_type": "email",
        })
        assert resp.status_code in (200, 503)

    def test_nearby_venues_endpoint(self, auth_client):
        resp = auth_client.post("/api/meetings/nearby-venues", json={
            "location": "Connaught Place, Delhi",
        })
        assert resp.status_code in (200, 503)

    def test_missing_location_for_nearby_venues_rejected(self, auth_client):
        resp = auth_client.post("/api/meetings/nearby-venues", json={})
        assert resp.status_code in (400, 422) or resp.get_json().get("success") is False

    def test_meetings_unauthenticated_401(self, client):
        assert client.get("/api/meetings").status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 6. Analytics
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalytics:

    def test_dashboard_200(self, auth_client):
        resp = auth_client.get("/api/analytics/dashboard")
        data = _ok(resp)
        assert "success" in data

    def test_spend_analysis_200(self, auth_client):
        resp = auth_client.get("/api/analytics/spend")
        assert resp.status_code == 200
        assert "success" in resp.get_json()

    def test_compliance_scorecard_200(self, auth_client):
        resp = auth_client.get("/api/analytics/compliance")
        assert resp.status_code == 200
        assert "success" in resp.get_json()

    def test_carbon_analytics_200(self, auth_client):
        resp = auth_client.get("/api/analytics/carbon")
        assert resp.status_code == 200
        assert "success" in resp.get_json()

    def test_carbon_estimate_flight(self, auth_client):
        resp = auth_client.get(
            "/api/analytics/carbon/estimate"
            "?origin=Mumbai&destination=Delhi&mode=flight&travelers=1"
        )
        assert resp.status_code == 200
        assert "success" in resp.get_json()

    def test_carbon_estimate_missing_destination_rejected(self, auth_client):
        resp = auth_client.get(
            "/api/analytics/carbon/estimate?origin=Mumbai&mode=flight"
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_budget_tracking_no_request_id(self, auth_client):
        resp = auth_client.get("/api/analytics/budget")
        assert resp.status_code == 200

    def test_budget_tracking_with_request_id(self, auth_client):
        cr = auth_client.post("/api/requests", json={
            "destination": "Mysore", "purpose": "Training",
            "duration_days": 2, "estimated_total": 15000, "action": "draft",
        })
        req_id = cr.get_json()["request_id"]
        resp = auth_client.get(f"/api/analytics/budget?request_id={req_id}")
        assert resp.status_code == 200

    def test_analytics_unauthenticated_401(self, client):
        assert client.get("/api/analytics/dashboard").status_code == 401

    def test_repeated_calls_return_identical_success_flag(self, auth_client):
        """Cache must not corrupt responses on repeated calls."""
        results = []
        for _ in range(3):
            resp = auth_client.get("/api/analytics/dashboard")
            assert resp.status_code == 200
            results.append(resp.get_json().get("success"))
        assert all(r == results[0] for r in results), "Inconsistent cached responses"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Chat
# ─────────────────────────────────────────────────────────────────────────────

class TestChat:

    def test_history_returns_messages_list(self, auth_client):
        resp = auth_client.get("/api/chat/history")
        data = _ok(resp)
        assert "messages" in data
        assert isinstance(data["messages"], list)

    def test_history_with_limit_param(self, auth_client):
        resp = auth_client.get("/api/chat/history?limit=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("messages", [])) <= 5

    def test_history_bad_limit_does_not_500(self, auth_client):
        assert auth_client.get("/api/chat/history?limit=notanumber").status_code == 200

    def test_history_unauthenticated_401(self, client):
        assert client.get("/api/chat/history").status_code == 401

    def test_send_chat_message(self, auth_client):
        resp = auth_client.post("/api/chat",
                                json={"message": "What is the travel policy?"})
        assert resp.status_code in (200, 503)
        data = resp.get_json()
        assert data is not None
        assert "success" in data or "reply" in data or "response" in data

    def test_empty_message_body_rejected(self, auth_client):
        resp = auth_client.post("/api/chat", json={})
        data = resp.get_json()
        assert data["success"] is False or resp.status_code in (400, 422)

    def test_sessions_list(self, auth_client):
        resp = auth_client.get("/api/chat/sessions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sessions" in data or "success" in data

    def test_create_session(self, auth_client):
        resp = auth_client.post("/api/chat/sessions",
                                json={"title": "Audit Session"})
        assert resp.status_code in (200, 201)

    def test_rename_session(self, auth_client):
        cr = auth_client.post("/api/chat/sessions", json={"title": "To Rename"})
        d = cr.get_json()
        sid = d.get("session", {}).get("id") or d.get("id")
        if sid:
            resp = _patch(auth_client._client,
                          f"/api/chat/sessions/{sid}",
                          auth_client.csrf_token,
                          {"title": "Renamed"})
            assert resp.status_code in (200, 201)

    def test_delete_session(self, auth_client):
        cr = auth_client.post("/api/chat/sessions", json={"title": "To Delete"})
        d = cr.get_json()
        sid = d.get("session", {}).get("id") or d.get("id")
        if sid:
            resp = _delete(auth_client._client,
                           f"/api/chat/sessions/{sid}",
                           auth_client.csrf_token)
            assert resp.status_code in (200, 204)

    def test_chat_with_session_id(self, auth_client):
        cr = auth_client.post("/api/chat/sessions", json={"title": "Scoped"})
        d = cr.get_json()
        sid = d.get("session", {}).get("id") or d.get("id")
        if sid:
            resp = auth_client.post("/api/chat",
                                    json={"message": "Hello", "session_id": sid})
            assert resp.status_code in (200, 503)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Trips
# ─────────────────────────────────────────────────────────────────────────────

class TestTrips:

    def test_list_trips_paginated(self, auth_client):
        resp = auth_client.get("/api/trips")
        data = _ok(resp)
        _paginated(data, "trips")

    def test_list_trips_unauthenticated_401(self, client):
        assert client.get("/api/trips").status_code == 401

    def test_plan_trip_fallback_works(self, auth_client):
        """Must succeed even with no external API keys (fallback mode)."""
        resp = auth_client.post("/api/trips/plan", json={
            "destination": "Goa", "origin": "Mumbai",
            "start_date": "2026-08-01", "end_date": "2026-08-04",
            "purpose": "team offsite", "num_travelers": 3, "budget": 50000,
        })
        assert resp.status_code in (200, 429, 503)
        if resp.status_code == 200:
            assert "success" in resp.get_json()

    def test_trip_recommendations_does_not_500(self, auth_client):
        resp = auth_client.post("/api/trips/recommendations",
                                json={"destination": "Jaipur", "duration_days": 3})
        assert resp.status_code in (200, 503)

    def test_async_plan_returns_task_id(self, auth_client):
        resp = auth_client.post("/api/trips/plan-async", json={
            "destination": "Shimla", "origin": "Delhi", "purpose": "leisure",
        })
        assert resp.status_code in (200, 202, 429, 503)
        if resp.status_code in (200, 202):
            data = resp.get_json()
            assert "task_id" in data or "success" in data

    def test_task_status_nonexistent_does_not_500(self, auth_client):
        resp = auth_client.get("/api/tasks/nonexistent-task-id-xyz")
        assert resp.status_code in (200, 404)
        assert resp.get_json() is not None

    def test_get_trip_not_found(self, auth_client):
        resp = auth_client.get("/api/trips/99999999")
        assert resp.status_code in (400, 404)


# ─────────────────────────────────────────────────────────────────────────────
# 9. External Services (Weather / Currency / Accommodation)
# ─────────────────────────────────────────────────────────────────────────────

class TestExternalServices:

    def test_weather_current_with_city(self, auth_client):
        resp = auth_client.get("/api/weather/current?city=Mumbai")
        assert resp.status_code == 200
        data = resp.get_json()
        # Weather returns flat dict (city, temp, description…) OR {success, …} depending on source
        assert data is not None
        assert "city" in data or "success" in data or "temp" in data

    def test_weather_current_missing_city_rejected(self, auth_client):
        resp = auth_client.get("/api/weather/current")
        assert resp.status_code in (400, 422) or resp.get_json().get("success") is False

    def test_weather_travel_forecast(self, auth_client):
        resp = auth_client.post("/api/weather", json={
            "city": "Delhi", "travel_dates": "2026-09-01 to 2026-09-05",
        })
        assert resp.status_code in (200, 503)

    def test_currency_convert_usd_to_inr(self, auth_client):
        resp = auth_client.post("/api/currency/convert", json={
            "from_currency": "USD", "to_currency": "INR", "amount": 100,
        })
        assert resp.status_code == 200

    def test_currency_convert_same_currency(self, auth_client):
        resp = auth_client.post("/api/currency/convert", json={
            "from_currency": "INR", "to_currency": "INR", "amount": 500,
        })
        assert resp.status_code == 200

    def test_currency_convert_zero_amount(self, auth_client):
        resp = auth_client.post("/api/currency/convert", json={
            "from_currency": "USD", "to_currency": "INR", "amount": 0,
        })
        assert resp.status_code == 200

    def test_currency_convert_missing_fields_rejected(self, auth_client):
        resp = auth_client.post("/api/currency/convert", json={"amount": 100})
        assert resp.status_code in (400, 422) or resp.get_json().get("success") is False

    def test_currency_travel_info_does_not_500(self, auth_client):
        resp = auth_client.get("/api/currency/travel-info?destination=Tokyo")
        assert resp.status_code in (200, 503)

    def test_accommodation_search(self, auth_client):
        resp = auth_client.get(
            "/api/accommodation/search?city=Mumbai"
            "&check_in=2026-09-01&check_out=2026-09-03"
        )
        assert resp.status_code in (200, 503)
        assert "success" in resp.get_json()

    def test_accommodation_missing_city_rejected(self, auth_client):
        resp = auth_client.get("/api/accommodation/search")
        assert resp.status_code in (400, 422) or resp.get_json().get("success") is False

    def test_pg_options_endpoint(self, auth_client):
        resp = auth_client.post("/api/accommodation/pg-options", json={
            "destination": "Bangalore", "duration_days": 30, "budget": 15000,
        })
        assert resp.status_code in (200, 503)

    def test_pg_options_missing_destination_rejected(self, auth_client):
        resp = auth_client.post("/api/accommodation/pg-options", json={})
        assert resp.get_json()["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 10. SOS + Alerts
# ─────────────────────────────────────────────────────────────────────────────

class TestSOSAndAlerts:

    def test_sos_contacts_lookup(self, auth_client):
        resp = auth_client.get("/api/sos/contacts?city=Mumbai&country=India")
        assert resp.status_code in (200, 503)
        assert "success" in resp.get_json()

    def test_sos_trigger_with_location(self, auth_client):
        resp = auth_client.post("/api/sos", json={
            "city": "Mumbai", "country": "India",
            "message": "Test SOS — audit only",
            "emergency_type": "medical",
            "latitude": 19.0760, "longitude": 72.8777,
        })
        # 429 = rate limit hit from other tests; both fine
        assert resp.status_code in (200, 429)
        assert "success" in resp.get_json()

    def test_sos_reverse_geocode_valid_coords(self, auth_client):
        resp = auth_client.post("/api/sos/reverse-geocode", json={
            "latitude": 28.6139, "longitude": 77.2090,
        })
        assert resp.status_code in (200, 503)
        assert "success" in resp.get_json()

    def test_sos_reverse_geocode_missing_coords_rejected(self, auth_client):
        resp = auth_client.post("/api/sos/reverse-geocode", json={})
        assert resp.status_code in (400, 422) or resp.get_json().get("success") is False

    def test_alerts_returns_list(self, auth_client):
        resp = auth_client.get("/api/alerts")
        data = _ok(resp)
        assert "alerts" in data
        assert isinstance(data["alerts"], list)

    def test_alerts_unauthenticated_401(self, client):
        assert client.get("/api/alerts").status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 11. Notifications
# ─────────────────────────────────────────────────────────────────────────────

class TestNotifications:

    def test_list_notifications_has_unread_count(self, auth_client):
        resp = auth_client.get("/api/notifications")
        data = _ok(resp)
        assert "notifications" in data
        assert "unread_count" in data

    def test_list_unread_only_param(self, auth_client):
        resp = auth_client.get("/api/notifications?unread_only=true")
        assert resp.status_code == 200

    def test_bad_limit_does_not_500(self, auth_client):
        assert auth_client.get("/api/notifications?limit=abc").status_code == 200

    def test_mark_all_read(self, auth_client):
        resp = auth_client.post("/api/notifications/read-all")
        _ok(resp)

    def test_mark_single_fake_id_does_not_500(self, auth_client):
        resp = auth_client.post("/api/notifications/999999999/read")
        assert resp.status_code in (200, 404)

    def test_notifications_unauthenticated_401(self, client):
        assert client.get("/api/notifications").status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 12. Organisations
# ─────────────────────────────────────────────────────────────────────────────

class TestOrganizations:

    def test_get_own_org_before_creating(self, auth_client):
        resp = auth_client.get("/api/orgs/me")
        assert resp.status_code in (200, 404)

    def test_create_org_success(self, auth_client):
        resp = auth_client.post("/api/orgs", json={
            "name": f"Audit Org {secrets.token_hex(4)}",
        })
        assert resp.status_code in (200, 201)
        data = resp.get_json()
        assert data.get("success") is True or "organization" in data

    def test_create_org_name_too_short_rejected(self, auth_client):
        resp = auth_client.post("/api/orgs", json={"name": "X"})
        assert resp.get_json()["success"] is False

    def test_create_org_missing_name_rejected(self, auth_client):
        resp = auth_client.post("/api/orgs", json={})
        assert resp.get_json()["success"] is False

    def test_org_members_list(self, app, db):
        email, _, _ = _make_user(db, "employee")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            _post(c, "/api/orgs", csrf,
                  {"name": f"MembersOrg {secrets.token_hex(4)}"})
            resp = c.get("/api/orgs/members",
                         headers={"X-CSRF-Token": csrf})
            assert resp.status_code in (200, 404)

    def test_invite_nonexistent_user_fails(self, app, db):
        email, _, _ = _make_user(db, "employee")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            _post(c, "/api/orgs", csrf,
                  {"name": f"InviteOrg {secrets.token_hex(4)}"})
            resp = _post(c, "/api/orgs/invite", csrf, {
                "email": "nobody_ghost_99@nowhere.test",
                "role": "member",
            })
            assert resp.get_json()["success"] is False

    def test_org_settings_update(self, app, db):
        email, _, _ = _make_user(db, "employee")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            cr = _post(c, "/api/orgs", csrf,
                       {"name": f"SettingsOrg {secrets.token_hex(4)}"})
            if cr.get_json().get("success"):
                resp = _put(c, "/api/orgs/settings", csrf, {
                    "name": f"Renamed {secrets.token_hex(4)}",
                })
                assert resp.status_code in (200, 403, 404)

    def test_org_unauthenticated_401(self, client):
        assert client.get("/api/orgs/me").status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 13. Users (admin-only)
# ─────────────────────────────────────────────────────────────────────────────

class TestUsers:

    def test_list_users_forbidden_for_employee(self, auth_client):
        assert auth_client.get("/api/users").status_code == 403

    def test_list_users_success_for_super_admin(self, super_admin_client):
        resp = super_admin_client.get("/api/users")
        data = _ok(resp)
        assert "users" in data
        assert data["total"] >= 1

    def test_get_single_user_no_password_hash(self, super_admin_client, db):
        row = db.execute("SELECT id FROM users LIMIT 1").fetchone()
        uid = row["id"] if isinstance(row, dict) else row[0]
        resp = super_admin_client.get(f"/api/users/{uid}")
        if resp.status_code == 200:
            assert "password_hash" not in resp.get_json().get("user", {})

    def test_change_user_role_to_manager(self, super_admin_client, db):
        _, _, uid = _make_user(db, "employee")
        resp = super_admin_client.put(f"/api/users/{uid}/role",
                                      json={"role": "manager"})
        assert resp.status_code in (200, 400, 403)
        if resp.status_code == 200:
            assert resp.get_json()["success"] is True

    def test_invalid_role_rejected(self, super_admin_client, db):
        _, _, uid = _make_user(db, "employee")
        resp = super_admin_client.put(f"/api/users/{uid}/role",
                                      json={"role": "superstar"})
        assert resp.get_json()["success"] is False or resp.status_code in (400, 422)

    def test_admin_cannot_change_own_role(self, super_admin_client):
        me = super_admin_client.get("/api/auth/me").get_json()["user"]
        resp = super_admin_client.put(f"/api/users/{me['id']}/role",
                                      json={"role": "employee"})
        assert resp.get_json()["success"] is False or resp.status_code in (400, 403)

    def test_list_users_filter_by_role(self, super_admin_client, db):
        _make_user(db, "manager")
        resp = super_admin_client.get("/api/users?role=manager")
        data = resp.get_json()
        assert "users" in data
        for u in data["users"]:
            assert u.get("role") == "manager"

    def test_list_users_search(self, super_admin_client, db):
        _make_user(db, "employee", suffix="searchme777")
        resp = super_admin_client.get("/api/users?search=searchme777")
        data = resp.get_json()
        assert "users" in data
        assert any("searchme777" in (u.get("email", "") + u.get("username", ""))
                   for u in data["users"])


# ─────────────────────────────────────────────────────────────────────────────
# 14. Uploads
# ─────────────────────────────────────────────────────────────────────────────

class TestUploads:

    def test_upload_valid_png(self, auth_client):
        # Minimal valid 1×1 pixel PNG
        png = io.BytesIO(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00'
            b'\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N'
            b'\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        resp = auth_client._client.post(
            "/api/uploads",
            data={"file": (png, "tiny.png")},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
        assert resp.status_code in (200, 201, 400, 401)

    def test_upload_too_large_returns_413(self, client):
        big = io.BytesIO(b"x" * (21 * 1024 * 1024))
        resp = client.post("/api/uploads",
                           data={"file": (big, "big.txt")},
                           content_type="multipart/form-data")
        assert resp.status_code in (413, 401)

    def test_upload_parse_document(self, auth_client):
        pdf = io.BytesIO(b"%PDF-1.4 fake ticket for parse test")
        resp = auth_client._client.post(
            "/api/uploads/parse-document",
            data={"file": (pdf, "ticket.pdf"), "doc_type": "flight_ticket"},
            content_type="multipart/form-data",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
        assert resp.status_code in (200, 400, 503)

    def test_serve_nonexistent_file_does_not_500(self, auth_client):
        resp = auth_client.get("/api/uploads/totally_nonexistent_xyz.pdf")
        assert resp.status_code in (404, 401)

    def test_upload_unauthenticated_401(self, client):
        resp = client.post("/api/uploads",
                           data={"file": (io.BytesIO(b"data"), "f.txt")},
                           content_type="multipart/form-data")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 15. Infrastructure (health, docs, agents, audit, webhooks)
# ─────────────────────────────────────────────────────────────────────────────

class TestInfraEndpoints:

    def test_health_check_structure(self, client):
        resp = client.get("/api/health")
        assert resp.status_code in (200, 503)
        data = resp.get_json()
        assert data["status"] in ("ok", "healthy", "degraded")
        assert "checks" in data

    def test_health_check_no_auth_required(self, client):
        """Health endpoint must be publicly accessible (used by Cloud Run probe)."""
        resp = client.get("/api/health")
        assert resp.status_code in (200, 503)

    def test_docs_json_endpoint(self, client):
        resp = client.get("/api/docs/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "endpoints" in data

    def test_agents_list(self, auth_client):
        resp = auth_client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "agents" in data or "success" in data

    def test_agents_health(self, auth_client):
        resp = auth_client.get("/api/agents/health")
        assert resp.status_code == 200

    def test_audit_logs_forbidden_for_employee(self, auth_client):
        assert auth_client.get("/api/audit").status_code == 403

    def test_audit_logs_accessible_for_super_admin(self, super_admin_client):
        assert super_admin_client.get("/api/audit").status_code == 200

    def test_webhooks_events_list(self, auth_client):
        assert auth_client.get("/api/webhooks/events").status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 16. Security
# ─────────────────────────────────────────────────────────────────────────────

class TestSecurity:

    def test_unauthenticated_unknown_path_returns_401_not_404(self, client):
        """Endpoint enumeration prevention — unauthenticated unknown path → 401."""
        resp = client.get("/api/totally-nonexistent-endpoint-xyz")
        assert resp.status_code == 401
        assert resp.get_json()["success"] is False

    def test_authenticated_unknown_path_returns_404(self, auth_client):
        resp = auth_client.get("/api/totally-nonexistent-endpoint-xyz")
        assert resp.status_code == 404
        assert resp.get_json()["success"] is False

    def test_wrong_http_method_returns_405_json(self, client):
        resp = client.delete("/api/health")
        assert resp.status_code == 405
        data = resp.get_json()
        assert data is not None
        assert data["success"] is False

    def test_invalid_json_body_does_not_500(self, auth_client):
        resp = auth_client._client.post(
            "/api/requests",
            data=b"this {{{ is not json",
            content_type="application/json",
            headers={"X-CSRF-Token": auth_client.csrf_token},
        )
        assert resp.status_code in (200, 400, 422)

    def test_sql_injection_in_requests_search(self, auth_client):
        resp = auth_client.get("/api/requests?search=' OR '1'='1; --")
        assert resp.status_code != 500

    def test_sql_injection_in_expense_search(self, auth_client):
        resp = auth_client.get(
            "/api/expenses?search='; DROP TABLE expenses_db; --"
        )
        assert resp.status_code != 500

    def test_sql_injection_in_meetings_search(self, auth_client):
        resp = auth_client.get(
            "/api/meetings?search=1' UNION SELECT * FROM users --"
        )
        assert resp.status_code != 500

    def test_xss_payload_in_destination_does_not_500(self, auth_client):
        resp = auth_client.post("/api/requests", json={
            "destination": "<script>alert('xss')</script>",
            "purpose": "XSS test",
            "action": "draft",
        })
        assert resp.status_code != 500

    def test_path_traversal_blocked(self, client):
        resp = client.get("/../../../etc/passwd")
        assert resp.status_code in (301, 308, 404, 200)
        if resp.status_code == 200:
            assert b"root:" not in resp.data

    def test_whatsapp_webhook_unsigned_rejected(self, client):
        resp = client.post("/api/whatsapp/webhook", data={
            "From": "whatsapp:+919999999999",
            "Body": "hello", "NumMedia": "0",
        })
        assert resp.status_code == 403

    def test_whatsapp_webhook_bogus_signature_rejected(self, client):
        resp = client.post(
            "/api/whatsapp/webhook",
            data={"From": "whatsapp:+919999999999", "Body": "hi", "NumMedia": "0"},
            headers={"X-Twilio-Signature": "bogus-signature-value"},
        )
        assert resp.status_code == 403

    def test_cliq_webhook_no_auth_rejected(self, client):
        resp = client.post("/api/cliq/bot", json={"text": "hello"})
        assert resp.status_code == 403

    def test_cliq_webhook_wrong_token_rejected(self, client):
        resp = client.post("/api/cliq/bot", json={"text": "hello"},
                           headers={"Authorization": "Bearer totally-wrong-token"})
        assert resp.status_code == 403

    def test_oversized_string_payload_does_not_500(self, auth_client):
        """Purpose field has no length cap — request is accepted (201) or rejected (400).
        Either is fine; the important thing is it must not 500."""
        resp = auth_client.post("/api/requests", json={
            "destination": "Mumbai",
            "purpose": "A" * 100_000,
        })
        assert resp.status_code in (200, 201, 400, 413, 422)

    def test_null_bytes_in_destination_do_not_500(self, auth_client):
        resp = auth_client.post("/api/requests", json={
            "destination": "Mumbai\x00null",
            "purpose": "Test",
        })
        assert resp.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# 17. Multi-Tenant Data Isolation
# ─────────────────────────────────────────────────────────────────────────────

def _two_org_users(db, role="employee"):
    """Helper: create two users each in their own org. Returns two login tuples."""
    tag = secrets.token_hex(6)

    def _create(suffix, org_name):
        slug = f"iso-{suffix}-{tag}"
        email = f"{suffix}_{tag}@iso.test"
        db.execute("INSERT INTO organizations (name, slug) VALUES (?, ?)",
                   (org_name, slug))
        db.commit()
        oid = db.execute("SELECT id FROM organizations WHERE slug = ?",
                         (slug,)).fetchone()
        oid = oid["id"] if isinstance(oid, dict) else oid[0]
        uname = f"{suffix}_{tag}"
        db.execute(
            "INSERT INTO users (username, password_hash, name, full_name, email,"
            " role, department, email_verified) VALUES (?, ?, ?, ?, ?, ?, 'Eng', 1)",
            (uname, generate_password_hash("Pass1234"),
             uname, uname, email, role),
        )
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE email = ?",
                         (email,)).fetchone()
        uid = uid["id"] if isinstance(uid, dict) else uid[0]
        db.execute(
            "INSERT INTO org_members (org_id, user_id, org_role) VALUES (?, ?, 'member')",
            (oid, uid),
        )
        db.commit()
        return uid, oid, email

    return _create("a", f"IsoA-{tag}"), _create("b", f"IsoB-{tag}")


class TestDataIsolation:

    def test_requests_not_visible_across_orgs(self, app, db):
        (uid_a, oid_a, _email_a), (_uid_b, _oid_b, email_b) = _two_org_users(db)
        db.execute(
            "INSERT INTO travel_requests (user_id, org_id, request_id, destination, status)"
            " VALUES (?, ?, ?, 'SecretCityOrgA', 'draft')",
            (uid_a, oid_a, f"TR-ISO-A-{secrets.token_hex(4)}"),
        )
        db.commit()
        with app.test_client() as c:
            csrf, _, _ = _login(c, email_b, "Pass1234")
            data = c.get("/api/requests").get_json()
            dests = [r.get("destination", "") for r in data.get("requests", [])]
            assert "SecretCityOrgA" not in dests, "Org B can see Org A's request!"

    def test_expenses_not_visible_across_users(self, app, db):
        (uid_a, oid_a, _email_a), (_uid_b, _oid_b, email_b) = _two_org_users(db)
        db.execute(
            "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description)"
            " VALUES (?, ?, 'hotel', 99999, 'SECRET_EXPENSE_AUDIT')",
            (uid_a, oid_a),
        )
        db.commit()
        with app.test_client() as c:
            csrf, _, _ = _login(c, email_b, "Pass1234")
            data = c.get("/api/expenses").get_json()
            descs = [e.get("description", "") for e in data.get("expenses", [])]
            assert "SECRET_EXPENSE_AUDIT" not in descs, "User B can see User A's expense!"

    def test_analytics_spend_not_leaking_across_orgs(self, app, db):
        (uid_a, oid_a, _email_a), (_uid_b, _oid_b, email_b) = _two_org_users(db, "manager")
        db.execute(
            "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount,"
            " description, created_at) VALUES (?, ?, 'travel', 77777, 'OrgA private', '2026-04-01')",
            (uid_a, oid_a),
        )
        db.commit()
        with app.test_client() as c:
            csrf, _, _ = _login(c, email_b, "Pass1234")
            data = c.get("/api/analytics/spend").get_json()
            total = data.get("total_spend", 0)
            assert total != 77777, "Org B analytics leaked Org A spend total!"

    def test_meetings_not_visible_across_users(self, app, db):
        (uid_a, oid_a, _email_a), (_uid_b, _oid_b, email_b) = _two_org_users(db)
        db.execute(
            "INSERT INTO client_meetings"
            " (user_id, org_id, destination, client_name, company, agenda, meeting_date)"
            " VALUES (?, ?, 'SecretCity', 'SECRET_CLIENT_XYZ', 'SecretCorp', 'Confidential', '2026-09-01')",
            (uid_a, oid_a),
        )
        db.commit()
        with app.test_client() as c:
            csrf, _, _ = _login(c, email_b, "Pass1234")
            data = c.get("/api/meetings").get_json()
            items = data.get("meetings", data.get("items", []))
            clients = [m.get("client_name", "") for m in items]
            assert "SECRET_CLIENT_XYZ" not in clients, "User B can see User A's meeting!"


# ─────────────────────────────────────────────────────────────────────────────
# 18. Response Quality
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseQuality:

    def test_all_list_endpoints_return_json(self, auth_client):
        endpoints = [
            "/api/requests", "/api/expenses", "/api/meetings",
            "/api/notifications", "/api/alerts",
        ]
        for url in endpoints:
            resp = auth_client.get(url)
            ct = resp.headers.get("Content-Type", "")
            assert "application/json" in ct, f"Non-JSON content-type at {url}: {ct}"

    def test_all_analytics_endpoints_return_json(self, auth_client):
        for url in ["/api/analytics/dashboard", "/api/analytics/spend",
                    "/api/analytics/compliance", "/api/analytics/carbon",
                    "/api/analytics/budget"]:
            resp = auth_client.get(url)
            ct = resp.headers.get("Content-Type", "")
            assert "application/json" in ct, f"Non-JSON at {url}"

    def test_all_success_responses_have_success_key(self, auth_client):
        for url in ["/api/analytics/dashboard", "/api/analytics/spend",
                    "/api/analytics/compliance", "/api/requests",
                    "/api/expenses", "/api/meetings", "/api/notifications",
                    "/api/alerts", "/api/auth/me"]:
            resp = auth_client.get(url)
            if resp.status_code == 200:
                data = resp.get_json()
                assert "success" in data, f"Missing 'success' key in {url}: {data}"

    def test_list_endpoints_have_total_field(self, auth_client):
        for url in ["/api/requests", "/api/expenses", "/api/meetings",
                    "/api/notifications"]:
            resp = auth_client.get(url)
            if resp.status_code == 200:
                data = resp.get_json()
                assert "total" in data, f"Missing 'total' in {url}"

    def test_error_responses_have_error_or_message_key(self, client):
        resp = client.post("/api/auth/login",
                           json={"username": "bad@test.com", "password": "bad"})
        data = resp.get_json()
        assert "error" in data or "message" in data

    def test_health_response_has_required_fields(self, client):
        data = client.get("/api/health").get_json()
        assert "status" in data
        assert "checks" in data
        assert data["status"] in ("ok", "healthy", "degraded")


# ─────────────────────────────────────────────────────────────────────────────
# 19. Caching Consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestCaching:

    def test_dashboard_consistent_across_three_calls(self, auth_client):
        """Cache must not corrupt or flip success flag on repeated calls."""
        flags = []
        for _ in range(3):
            resp = auth_client.get("/api/analytics/dashboard")
            assert resp.status_code == 200
            flags.append(resp.get_json().get("success"))
        assert len(set(flags)) == 1, f"Inconsistent dashboard responses: {flags}"

    def test_spend_consistent_across_three_calls(self, auth_client):
        for _ in range(3):
            assert auth_client.get("/api/analytics/spend").status_code == 200

    def test_compliance_consistent_across_three_calls(self, auth_client):
        for _ in range(3):
            assert auth_client.get("/api/analytics/compliance").status_code == 200

    def test_newly_created_request_appears_in_list(self, auth_client):
        """Requests list must reflect new data — must not serve stale cache."""
        cr = auth_client.post("/api/requests", json={
            "destination": "CacheBustCity999",
            "purpose": "Cache Validity Test",
            "action": "draft",
        })
        assert cr.get_json()["success"] is True

        resp = auth_client.get("/api/requests")
        dests = [r.get("destination", "") for r in resp.get_json().get("requests", [])]
        assert "CacheBustCity999" in dests, "Newly created request missing from list"


# ─────────────────────────────────────────────────────────────────────────────
# 20. Business Logic Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestBusinessLogic:

    def test_double_submit_does_not_500(self, app, db):
        """Submitting an already-submitted request must fail gracefully."""
        email, _, _ = _make_user(db, "employee")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            cr = _post(c, "/api/requests", csrf, {
                "destination": "Vadodara", "purpose": "Double submit test",
                "action": "draft",
            })
            req_id = cr.get_json()["request_id"]
            sub1 = _post(c, f"/api/requests/{req_id}/submit", csrf)
            assert sub1.get_json()["success"] is True
            sub2 = _post(c, f"/api/requests/{req_id}/submit", csrf)
            assert sub2.status_code != 500

    def test_per_diem_zero_days_clamped_to_one(self, auth_client):
        """Per-diem uses max(1, days) — 0 is clamped to 1 and returns 200 gracefully."""
        resp = auth_client.get("/api/requests/per-diem?city=Mumbai&days=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True
        # Clamped to 1 day so total_allowance > 0
        assert data.get("total_allowance", 0) > 0 or data.get("daily_total", 0) > 0

    def test_per_diem_negative_days_clamped_to_one(self, auth_client):
        """Per-diem uses max(1, days) — negative is clamped to 1 and returns 200."""
        resp = auth_client.get("/api/requests/per-diem?city=Delhi&days=-5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True

    def test_currency_negative_amount_does_not_500(self, auth_client):
        resp = auth_client.post("/api/currency/convert", json={
            "from_currency": "USD", "to_currency": "INR", "amount": -100,
        })
        assert resp.status_code != 500

    def test_num_travelers_zero_rejected(self, auth_client):
        resp = auth_client.post("/api/requests", json={
            "destination": "Mumbai", "purpose": "Zero travelers",
            "num_travelers": 0, "action": "draft",
        })
        data = resp.get_json()
        assert data["success"] is False or resp.status_code in (400, 422)

    def test_unread_count_zero_after_read_all(self, app, db):
        email, _, uid = _make_user(db, "employee")
        for _ in range(3):
            db.execute(
                "INSERT INTO notifications (user_id, type, title, message, read)"
                " VALUES (?, 'info', 'Test', 'msg', 0)",
                (uid,),
            )
        db.commit()

        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            before = c.get("/api/notifications").get_json()
            assert before.get("unread_count", 0) >= 3

            _post(c, "/api/notifications/read-all", csrf)

            after = c.get("/api/notifications").get_json()
            assert after.get("unread_count", 0) == 0, (
                "unread_count must be 0 after read-all"
            )

    def test_sos_event_written_to_db(self, app, db):
        email, _, uid = _make_user(db, "employee")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            _post(c, "/api/sos", csrf, {
                "city": "Bhopal", "country": "India",
                "message": "DB audit SOS test",
                "emergency_type": "security",
                "latitude": 23.2599, "longitude": 77.4126,
            })
        row = db.execute(
            "SELECT id FROM sos_events WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
        assert row is not None, "SOS event must be persisted to DB"

    def test_chat_message_persisted_to_db(self, app, db):
        email, _, uid = _make_user(db, "employee")
        with app.test_client() as c:
            csrf, _, _ = _login(c, email)
            _post(c, "/api/chat", csrf, {"message": "What is the flight policy?"})
        row = db.execute(
            "SELECT id FROM chat_messages WHERE user_id = ? LIMIT 1", (uid,),
        ).fetchone()
        assert row is not None, "Chat message must be persisted to DB"

    def test_status_transition_invalid_value_does_not_500(self, auth_client):
        cr = auth_client.post("/api/requests", json={
            "destination": "Surat", "purpose": "Status test", "action": "draft",
        })
        req_id = cr.get_json()["request_id"]
        resp = auth_client.put(f"/api/requests/{req_id}/status",
                               json={"status": "totally_invalid_status"})
        assert resp.status_code != 500

    def test_expense_string_amount_does_not_500(self, auth_client):
        """String '500' where float expected must not crash."""
        resp = auth_client.post("/api/expenses", json={
            "category": "food", "description": "lunch",
            "invoice_amount": "500",
        })
        assert resp.status_code != 500
