"""
TravelSync Pro — Database Layer
SQLite for development. Set DATABASE_URL for Cloud SQL PostgreSQL in production.

Schema versioning via _apply_migrations() — safely adds new columns to existing DBs.
"""
import os
import json
import logging
import sqlite3
import datetime as dt

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "travelsync.db")
logger = logging.getLogger(__name__)


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def init_db(app=None):
    """Initialize all tables, apply migrations, and seed demo data."""
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    _create_tables(c)
    db.commit()
    _apply_migrations(db, c)
    _seed_users(c, db)
    _seed_policy(c, db)
    _seed_requests(c, db)
    _seed_meetings(c, db)
    _seed_expenses(c, db)
    db.close()
    logger.info("[DB] Database initialized")


# ── Table Creation ─────────────────────────────────────────────────────────────

def _create_tables(c):
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        username         TEXT UNIQUE NOT NULL,
        password_hash    TEXT NOT NULL,
        name             TEXT NOT NULL,
        full_name        TEXT,
        email            TEXT,
        role             TEXT DEFAULT 'employee',
        department       TEXT DEFAULT 'General',
        manager_id       INTEGER,
        avatar_initials  TEXT,
        phone            TEXT,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS travel_policies (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        name                    TEXT NOT NULL,
        flight_class            TEXT DEFAULT 'economy',
        hotel_budget_per_night  INTEGER DEFAULT 5000,
        max_trip_duration_days  INTEGER DEFAULT 30,
        advance_booking_days    INTEGER DEFAULT 3,
        per_diem_inr            INTEGER DEFAULT 2000,
        monthly_budget_inr      INTEGER DEFAULT 500000,
        auto_approve_threshold  INTEGER DEFAULT 10000,
        require_receipts        INTEGER DEFAULT 1,
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS travel_requests (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id              TEXT UNIQUE,
        user_id                 INTEGER REFERENCES users(id),
        destination             TEXT NOT NULL,
        origin                  TEXT,
        purpose                 TEXT,
        trip_type               TEXT DEFAULT 'domestic',
        travel_dates            TEXT,
        start_date              TEXT,
        end_date                TEXT,
        duration_days           INTEGER DEFAULT 1,
        num_travelers           INTEGER DEFAULT 1,
        travelers_json          TEXT DEFAULT '[]',
        flight_class            TEXT DEFAULT 'economy',
        hotel_budget_per_night  REAL DEFAULT 5000,
        estimated_total         REAL DEFAULT 0,
        budget_inr              REAL DEFAULT 0,
        status                  TEXT DEFAULT 'draft',
        policy_compliance       TEXT DEFAULT 'pending',
        policy_compliance_json  TEXT DEFAULT '{}',
        compliance_details      TEXT,
        trip_plan               TEXT,
        notes                   TEXT,
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id   TEXT REFERENCES travel_requests(request_id),
        approver_id  INTEGER REFERENCES users(id),
        status       TEXT DEFAULT 'pending',
        comments     TEXT,
        decided_at   TIMESTAMP,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses_db (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id           TEXT,
        trip_id              TEXT,
        user_id              INTEGER REFERENCES users(id),
        category             TEXT DEFAULT 'miscellaneous',
        description          TEXT,
        invoice_amount       REAL DEFAULT 0,
        invoice_file         TEXT,
        payment_amount       REAL,
        payment_file         TEXT,
        verified_amount      REAL,
        verification_status  TEXT DEFAULT 'pending',
        stage                INTEGER DEFAULT 1,
        date                 TEXT,
        currency_code        TEXT DEFAULT 'INR',
        ocr_extracted_amount REAL,
        ocr_confidence       REAL,
        ocr_raw_text         TEXT,
        created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS client_meetings (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER,
        destination    TEXT,
        client_name    TEXT NOT NULL,
        company        TEXT,
        contact_number TEXT,
        email          TEXT,
        meeting_date   TEXT,
        meeting_time   TEXT,
        venue          TEXT,
        agenda         TEXT,
        notes          TEXT,
        source_type    TEXT DEFAULT 'manual',
        status         TEXT DEFAULT 'scheduled',
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS sos_events (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER,
        destination    TEXT,
        location       TEXT,
        emergency_type TEXT DEFAULT 'general',
        message        TEXT,
        resolved       INTEGER DEFAULT 0,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id          INTEGER,
        role             TEXT NOT NULL,
        content          TEXT NOT NULL,
        intent           TEXT,
        action_card_json TEXT,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER REFERENCES users(id),
        type       TEXT DEFAULT 'info',
        title      TEXT NOT NULL,
        message    TEXT,
        read       INTEGER DEFAULT 0,
        link       TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")


# ── Migrations: safely add columns to existing databases ───────────────────────

def _apply_migrations(db, c):
    """ALTER TABLE to add any columns that were added in later schema versions."""
    def _add_col(table, col, definition):
        existing = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in existing:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
                db.commit()
                logger.info("[DB] Migration: added %s.%s", table, col)
            except Exception as e:
                logger.warning("[DB] Migration skipped %s.%s: %s", table, col, e)

    # users — add computed/new columns
    _add_col("users", "full_name",       "TEXT")
    _add_col("users", "avatar_initials", "TEXT")
    _add_col("users", "phone",           "TEXT")

    # travel_requests — add all columns that request_agent.py writes
    _add_col("travel_requests", "request_id",             "TEXT UNIQUE")
    _add_col("travel_requests", "trip_type",              "TEXT DEFAULT 'domestic'")
    _add_col("travel_requests", "start_date",             "TEXT")
    _add_col("travel_requests", "end_date",               "TEXT")
    _add_col("travel_requests", "num_travelers",          "INTEGER DEFAULT 1")
    _add_col("travel_requests", "travelers_json",         "TEXT DEFAULT '[]'")
    _add_col("travel_requests", "flight_class",           "TEXT DEFAULT 'economy'")
    _add_col("travel_requests", "hotel_budget_per_night", "REAL DEFAULT 5000")
    _add_col("travel_requests", "estimated_total",        "REAL DEFAULT 0")
    _add_col("travel_requests", "policy_compliance_json", "TEXT DEFAULT '{}'")
    _add_col("travel_requests", "notes",                  "TEXT")

    # approvals — rename approved_at → decided_at if needed
    _add_col("approvals", "decided_at", "TIMESTAMP")

    # expenses_db — add request_id linkage
    _add_col("expenses_db", "request_id", "TEXT")

    # chat_messages — add action_card_json
    _add_col("chat_messages", "action_card_json", "TEXT")

    # Sync full_name from name for existing users
    c.execute("""
        UPDATE users SET full_name = name
        WHERE full_name IS NULL OR full_name = ''
    """)
    # Compute avatar_initials for existing users
    rows = c.execute("SELECT id, name FROM users WHERE avatar_initials IS NULL OR avatar_initials = ''").fetchall()
    for row in rows:
        initials = "".join(w[0].upper() for w in str(row[1]).split()[:2])
        c.execute("UPDATE users SET avatar_initials = ? WHERE id = ?", (initials, row[0]))
    db.commit()


# ── Seed Data ──────────────────────────────────────────────────────────────────

def _seed_users(c, db):
    from werkzeug.security import generate_password_hash
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return
    users = [
        ("vaibhav",   generate_password_hash("admin123"), "Vaibhav Sharma",  "Vaibhav Sharma",  "vaibhav@company.com",   "admin",    "Operations", "VS"),
        ("rohit",     generate_password_hash("admin123"), "Rohit Mehta",     "Rohit Mehta",     "rohit@company.com",     "admin",    "Finance",    "RM"),
        ("employee1", generate_password_hash("emp123"),   "Priya Patel",     "Priya Patel",     "priya@company.com",     "employee", "Sales",      "PP"),
        ("employee2", generate_password_hash("emp123"),   "Arjun Kumar",     "Arjun Kumar",     "arjun@company.com",     "employee", "Engineering","AK"),
        ("manager1",  generate_password_hash("mgr123"),   "Sunita Rao",      "Sunita Rao",      "sunita@company.com",    "manager",  "Sales",      "SR"),
    ]
    c.executemany(
        """INSERT INTO users
           (username, password_hash, name, full_name, email, role, department, avatar_initials)
           VALUES (?,?,?,?,?,?,?,?)""",
        users
    )
    db.commit()


def _seed_policy(c, db):
    if c.execute("SELECT COUNT(*) FROM travel_policies").fetchone()[0] > 0:
        return
    c.execute(
        """INSERT INTO travel_policies
           (name, flight_class, hotel_budget_per_night, max_trip_duration_days,
            advance_booking_days, per_diem_inr, monthly_budget_inr, auto_approve_threshold)
           VALUES (?,?,?,?,?,?,?,?)""",
        ("Standard Corporate Policy", "economy", 8000, 30, 3, 2500, 500000, 15000)
    )
    db.commit()


def _seed_requests(c, db):
    if c.execute("SELECT COUNT(*) FROM travel_requests").fetchone()[0] > 0:
        return
    now = dt.datetime.now()
    rows = [
        (
            "TR-2026-0310001",   # request_id
            3,                   # user_id (Priya)
            "Bangalore", "Mumbai",
            "Client Meeting", "domestic",
            f"{now.strftime('%Y-%m-%d')} to {(now + dt.timedelta(days=3)).strftime('%Y-%m-%d')}",
            now.strftime("%Y-%m-%d"),
            (now + dt.timedelta(days=3)).strftime("%Y-%m-%d"),
            3, 1, "economy", 7000, 25000, 25000,
            "approved", "compliant",
            json.dumps({"status": "compliant", "checks": []}),
            "Q4 client review",
        ),
        (
            "TR-2026-0311002",
            4,  # Arjun
            "Hyderabad", "Delhi",
            "Conference", "domestic",
            f"{now.strftime('%Y-%m-%d')} to {(now + dt.timedelta(days=2)).strftime('%Y-%m-%d')}",
            now.strftime("%Y-%m-%d"),
            (now + dt.timedelta(days=2)).strftime("%Y-%m-%d"),
            2, 1, "economy", 6000, 18000, 18000,
            "pending_approval", "compliant",
            json.dumps({"status": "compliant", "checks": []}),
            "AWS re:Invent India",
        ),
        (
            "TR-2026-0312003",
            3,  # Priya
            "Goa", "Pune",
            "Team Offsite", "domestic",
            f"{now.strftime('%Y-%m-%d')} to {(now + dt.timedelta(days=4)).strftime('%Y-%m-%d')}",
            now.strftime("%Y-%m-%d"),
            (now + dt.timedelta(days=4)).strftime("%Y-%m-%d"),
            4, 5, "economy", 5000, 30000, 30000,
            "draft", "partial",
            json.dumps({"status": "partial", "checks": []}),
            "Annual team offsite",
        ),
    ]
    c.executemany(
        """INSERT INTO travel_requests
           (request_id, user_id, destination, origin, purpose, trip_type,
            travel_dates, start_date, end_date, duration_days, num_travelers,
            flight_class, hotel_budget_per_night, estimated_total, budget_inr,
            status, policy_compliance, policy_compliance_json, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    # Create pending approval for the second request
    c.execute(
        "INSERT INTO approvals (request_id, approver_id, status) VALUES (?,?,?)",
        ("TR-2026-0311002", 1, "pending")
    )
    db.commit()


def _seed_meetings(c, db):
    if c.execute("SELECT COUNT(*) FROM client_meetings").fetchone()[0] > 0:
        return
    now = dt.datetime.now()
    rows = [
        (3, "Bangalore", "Ravi Kumar",   "TCS Innovation Labs", "+91-9876543210",
         "ravi@tcs.com",    (now + dt.timedelta(days=2)).strftime("%Y-%m-%d"),
         "10:00 AM", "TCS Whitefield",         "Q4 Partnership Discussion",  "Via email",              "email",    "scheduled"),
        (3, "Hyderabad", "Meena Reddy",  "Infosys",             "+91-8765432109",
         "meena@infosys.com",(now + dt.timedelta(days=5)).strftime("%Y-%m-%d"),
         "2:00 PM",  "Infosys Hitech City",    "Annual Review",              "Called Monday",          "phone",    "scheduled"),
        (4, "Mumbai",    "Aryan Shah",   "Wipro Digital",       "+91-7654321098",
         "aryan@wipro.com", (now + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
         "11:30 AM", "Wipro BKC",              "Product Demo",               "Meeting invite via WA",  "whatsapp", "scheduled"),
        (5, "Chennai",   "Deepa Nair",   "HCL Technologies",    "+91-6543210987",
         "deepa@hcl.com",  (now + dt.timedelta(days=7)).strftime("%Y-%m-%d"),
         "3:00 PM",  "HCL Sholinganallur",     "Proposal Presentation",      "LinkedIn message",       "linkedin", "scheduled"),
    ]
    c.executemany(
        """INSERT INTO client_meetings
           (user_id, destination, client_name, company, contact_number, email,
            meeting_date, meeting_time, venue, agenda, notes, source_type, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    db.commit()


def _seed_expenses(c, db):
    if c.execute("SELECT COUNT(*) FROM expenses_db").fetchone()[0] > 0:
        return
    now = dt.datetime.now()
    rows = [
        ("TR-2026-0310001", 3, "flight",    "IndiGo BOM-BLR",    18500, None, 18500, "verified",  3,
         now.strftime("%Y-%m-%d"), "INR", 18500, 0.92),
        ("TR-2026-0310001", 3, "hotel",     "Marriott Whitefield",7500,  None, 7500,  "verified",  3,
         now.strftime("%Y-%m-%d"), "INR", 7500,  0.88),
        ("TR-2026-0310001", 3, "meals",     "Client lunch",        2800,  None, 2800,  "verified",  3,
         now.strftime("%Y-%m-%d"), "INR", 2800,  0.75),
        ("TR-2026-0311002", 4, "flight",    "Air India DEL-HYD",  12000, None, None,  "pending",   1,
         now.strftime("%Y-%m-%d"), "INR", None,  None),
    ]
    c.executemany(
        """INSERT INTO expenses_db
           (request_id, user_id, category, description,
            invoice_amount, payment_amount, verified_amount,
            verification_status, stage, date, currency_code,
            ocr_extracted_amount, ocr_confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    db.commit()
