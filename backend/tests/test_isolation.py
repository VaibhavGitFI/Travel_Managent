"""
Multi-tenant data isolation tests.

These tests verify that users in different organizations cannot see each other's
data. They cover the Critical findings from the architectural audit:
  - analytics/spend must be scoped to the caller's org
  - analytics/compliance must be scoped to the caller's org
  - expenses must be scoped to the caller's user/org
  - travel requests must be scoped to the caller's user/org

Each test creates two users in two separate orgs, inserts data for both, then
verifies each user can only see their own org's data.
"""
import secrets
from werkzeug.security import generate_password_hash


def _create_org_user(db, org_name, username, role="employee"):
    """Helper: create an org, a user, and link them. Returns (user_id, org_id)."""
    slug = f"org-{secrets.token_hex(4)}"
    email = f"{username}@{slug}.test"
    password_hash = generate_password_hash("TestPass1")

    # Create org
    db.execute(
        "INSERT INTO organizations (name, slug) VALUES (?, ?)",
        (org_name, slug),
    )
    db.commit()
    org = db.execute("SELECT id FROM organizations WHERE slug = ?", (slug,)).fetchone()
    org_id = org["id"] if isinstance(org, dict) else org[0]

    # Create user
    db.execute(
        """INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, ?, ?, ?, ?, 'Engineering', 1)""",
        (username, password_hash, username, username, email, role),
    )
    db.commit()
    user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    user_id = user["id"] if isinstance(user, dict) else user[0]

    # Link user to org
    db.execute(
        "INSERT INTO org_members (org_id, user_id, org_role) VALUES (?, ?, ?)",
        (org_id, user_id, "org_admin" if role in ("admin", "manager") else "member"),
    )
    db.commit()

    return user_id, org_id, email


def _login(client, email, password="TestPass1"):
    """Login and return (csrf_token, access_token, user_dict)."""
    resp = client.post("/api/auth/login", json={"username": email, "password": password})
    data = resp.get_json()
    assert data.get("success"), f"Login failed: {data}"
    return data.get("csrf_token", ""), data.get("access_token", ""), data.get("user", {})


def _authed_get(client, url, csrf_token):
    """GET with CSRF header."""
    return client.get(url, headers={"X-CSRF-Token": csrf_token})


# ── Analytics Spend Isolation ────────────────────────────────────────────────

def test_spend_analysis_isolated_between_orgs(app, db):
    """User in Org A must not see Org B's expenses in /api/analytics/spend."""
    tag = secrets.token_hex(4)
    uid_a, oid_a, email_a = _create_org_user(db, f"OrgA-{tag}", f"alice_{tag}", role="manager")
    uid_b, oid_b, email_b = _create_org_user(db, f"OrgB-{tag}", f"bob_{tag}", role="manager")

    # Insert expenses for each org
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description, created_at) VALUES (?, ?, 'travel', 5000, 'OrgA flight', '2026-04-01')",
        (uid_a, oid_a),
    )
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description, created_at) VALUES (?, ?, 'meals', 9000, 'OrgB dinner', '2026-04-01')",
        (uid_b, oid_b),
    )
    db.commit()

    with app.test_client() as c_a:
        csrf_a, _, _ = _login(c_a, email_a)
        resp = _authed_get(c_a, "/api/analytics/spend", csrf_a)
        data = resp.get_json()
        assert data.get("success"), f"Spend failed: {data}"

        # OrgA user should see their org's 5000 but NOT OrgB's 9000
        total = data.get("total_spend", 0)
        categories = data.get("category_breakdown", [])
        cat_names = [c.get("category", "") for c in categories]

        # Must NOT contain OrgB's meals category (or if it does, the amount must
        # not include OrgB's 9000)
        for cat in categories:
            if cat.get("category") == "meals":
                assert cat.get("amount", 0) < 9000, (
                    f"OrgA user can see OrgB's expenses! meals amount={cat['amount']}"
                )


def test_spend_analysis_employee_sees_only_own(app, db):
    """An employee should see only their own expenses, not org-wide."""
    tag = secrets.token_hex(4)
    uid_emp, oid, email_emp = _create_org_user(db, f"OrgC-{tag}", f"emp_{tag}", role="employee")

    # Create another user in the same org
    other_username = f"other_{tag}"
    other_email = f"{other_username}@orgc.test"
    db.execute(
        "INSERT INTO users (username, password_hash, name, full_name, email, role, department, email_verified) VALUES (?, ?, ?, ?, ?, 'employee', 'Sales', 1)",
        (other_username, generate_password_hash("TestPass1"), other_username, other_username, other_email),
    )
    db.commit()
    other = db.execute("SELECT id FROM users WHERE username = ?", (other_username,)).fetchone()
    other_id = other["id"] if isinstance(other, dict) else other[0]
    db.execute("INSERT INTO org_members (org_id, user_id, org_role) VALUES (?, ?, 'member')", (oid, other_id))

    # Insert expenses for both users in the same org
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description, created_at) VALUES (?, ?, 'taxi', 500, 'my cab', '2026-04-01')",
        (uid_emp, oid),
    )
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description, created_at) VALUES (?, ?, 'hotel', 12000, 'colleague hotel', '2026-04-01')",
        (other_id, oid),
    )
    db.commit()

    with app.test_client() as c:
        csrf, _, _ = _login(c, email_emp)
        resp = _authed_get(c, "/api/analytics/spend", csrf)
        data = resp.get_json()
        assert data.get("success"), f"Spend failed: {data}"

        # Employee should NOT see the colleague's 12000 hotel expense
        total = data.get("total_spend", 0)
        assert total < 12000, (
            f"Employee can see colleague's expenses! total_spend={total}"
        )


# ── Analytics Compliance Isolation ───────────────────────────────────────────

def test_compliance_isolated_between_orgs(app, db):
    """Compliance scorecard must not include other orgs' data."""
    tag = secrets.token_hex(4)
    uid_a, oid_a, email_a = _create_org_user(db, f"CompA-{tag}", f"compa_{tag}", role="manager")
    uid_b, oid_b, email_b = _create_org_user(db, f"CompB-{tag}", f"compb_{tag}", role="manager")

    # Insert travel requests for each org
    db.execute(
        "INSERT INTO travel_requests (user_id, org_id, request_id, destination, status, policy_compliance) VALUES (?, ?, ?, 'Mumbai', 'approved', 'compliant')",
        (uid_a, oid_a, f"TR-A-{tag}"),
    )
    db.execute(
        "INSERT INTO travel_requests (user_id, org_id, request_id, destination, status, policy_compliance) VALUES (?, ?, ?, 'Delhi', 'approved', 'non_compliant')",
        (uid_b, oid_b, f"TR-B-{tag}"),
    )
    db.commit()

    with app.test_client() as c_a:
        csrf_a, _, _ = _login(c_a, email_a)
        resp = _authed_get(c_a, "/api/analytics/compliance", csrf_a)
        data = resp.get_json()
        assert data.get("success"), f"Compliance failed: {data}"

        requests_data = data.get("requests", {})
        # OrgA's manager should see only their org's compliant request,
        # NOT OrgB's non_compliant one
        assert requests_data.get("non_compliant", 0) == 0, (
            f"OrgA user can see OrgB's non-compliant requests! "
            f"non_compliant={requests_data.get('non_compliant')}"
        )


# ── Expense List Isolation ───────────────────────────────────────────────────

def test_expense_list_isolated_between_users(app, db):
    """GET /api/expenses must only return the caller's own expenses."""
    tag = secrets.token_hex(4)
    uid_a, oid_a, email_a = _create_org_user(db, f"ExpA-{tag}", f"expa_{tag}")
    uid_b, oid_b, email_b = _create_org_user(db, f"ExpB-{tag}", f"expb_{tag}")

    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description) VALUES (?, ?, 'food', 300, 'lunch A')",
        (uid_a, oid_a),
    )
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description) VALUES (?, ?, 'food', 700, 'lunch B')",
        (uid_b, oid_b),
    )
    db.commit()

    with app.test_client() as c_a:
        csrf_a, _, _ = _login(c_a, email_a)
        resp = _authed_get(c_a, "/api/expenses", csrf_a)
        data = resp.get_json()
        assert data.get("success") is not False, f"Expenses failed: {data}"

        descriptions = [e.get("description", "") for e in data.get("expenses", [])]
        assert "lunch B" not in descriptions, (
            f"User A can see User B's expenses! descriptions={descriptions}"
        )


# ── Search Isolation ─────────────────────────────────────────────────────────

def test_expense_search_does_not_leak_across_orgs(app, db):
    """Search on /api/expenses?search=X must not return other users' expenses."""
    tag = secrets.token_hex(4)
    uid_a, oid_a, email_a = _create_org_user(db, f"SrchA-{tag}", f"srcha_{tag}")
    uid_b, oid_b, email_b = _create_org_user(db, f"SrchB-{tag}", f"srchb_{tag}")

    # Both have an expense with "uber" in the description
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description) VALUES (?, ?, 'taxi', 200, 'uber ride to office')",
        (uid_a, oid_a),
    )
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description) VALUES (?, ?, 'taxi', 800, 'uber ride to airport')",
        (uid_b, oid_b),
    )
    db.commit()

    with app.test_client() as c_a:
        csrf_a, _, _ = _login(c_a, email_a)
        resp = _authed_get(c_a, "/api/expenses?search=uber", csrf_a)
        data = resp.get_json()

        expenses = data.get("expenses", [])
        for e in expenses:
            assert e.get("description") != "uber ride to airport", (
                f"Search leaked User B's expense to User A! expense={e}"
            )


# ── OTIS Context Isolation ──────────────────────────────────────────────────

def test_otis_context_isolated_between_orgs(app, db):
    """_build_otis_context must only return data for the caller's own user/org."""
    tag = secrets.token_hex(4)
    uid_a, oid_a, email_a = _create_org_user(db, f"OtisA-{tag}", f"otisa_{tag}", role="manager")
    uid_b, oid_b, email_b = _create_org_user(db, f"OtisB-{tag}", f"otisb_{tag}", role="manager")

    # Insert expenses for each user
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description, approval_status, created_at) "
        "VALUES (?, ?, 'flight', 15000, 'OrgA flight', 'draft', '2026-04-01')",
        (uid_a, oid_a),
    )
    db.execute(
        "INSERT INTO expenses_db (user_id, org_id, category, invoice_amount, description, approval_status, created_at) "
        "VALUES (?, ?, 'hotel', 25000, 'OrgB hotel', 'submitted', '2026-04-01')",
        (uid_b, oid_b),
    )
    # Insert travel requests
    db.execute(
        "INSERT INTO travel_requests (user_id, org_id, request_id, destination, status, created_at) "
        "VALUES (?, ?, ?, 'Mumbai', 'submitted', '2026-04-01')",
        (uid_a, oid_a, f"TR-OTISA-{tag}"),
    )
    db.execute(
        "INSERT INTO travel_requests (user_id, org_id, request_id, destination, status, created_at) "
        "VALUES (?, ?, ?, 'Delhi', 'submitted', '2026-04-01')",
        (uid_b, oid_b, f"TR-OTISB-{tag}"),
    )
    db.commit()

    # Build context for user A
    from routes.otis import _build_otis_context
    from database import get_db as _get_db
    test_db = _get_db()

    user_a = {"id": uid_a, "org_id": oid_a, "role": "manager", "name": "OtisA", "email": email_a}
    ctx_a = _build_otis_context(user_a, test_db)

    # User A's expenses must be only their own
    expense_descs = [e.get("description", "") for e in ctx_a.get("pending_expenses", [])]
    assert "OrgB hotel" not in expense_descs, f"OTIS context leaked OrgB expense to OrgA: {expense_descs}"

    # User A's trips must be only their own
    trip_dests = [t.get("destination", "") for t in ctx_a.get("recent_trips", [])]
    assert "Delhi" not in trip_dests, f"OTIS context leaked OrgB trip to OrgA: {trip_dests}"

    # User A's pending approvals must be only their org
    approval_dests = [a.get("destination", "") for a in ctx_a.get("pending_approvals", [])]
    assert "Delhi" not in approval_dests, f"OTIS context leaked OrgB approval to OrgA: {approval_dests}"

    test_db.close()
