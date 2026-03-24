"""
TravelSync Pro — Database Layer
SQLite for development. Set DATABASE_URL for Cloud SQL PostgreSQL in production.

Schema versioning via _apply_migrations() — safely adds new columns to existing DBs.

get_db() returns a unified interface that works identically for both SQLite and PostgreSQL:
  - Rows support both dict access (row["key"]) and attribute access
  - SQL uses '?' placeholders (auto-converted to '%s' for PostgreSQL)
  - .execute(), .fetchone(), .fetchall(), .commit(), .close() all work the same
"""
import os
import re
import json
import logging
import sqlite3
import datetime as dt

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "travelsync.db")
logger = logging.getLogger(__name__)


class _PGRow(dict):
    """Dict-like row wrapper that also supports attribute access (like sqlite3.Row)."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().get(key, default)

    def keys(self):
        return super().keys()


class _PGCursor:
    """sqlite3-compatible cursor wrapper around psycopg2 cursor."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql: str, params=()):
        pg_sql = re.sub(r"\?", "%s", sql)
        self._cur.execute(pg_sql, params or ())
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return _PGRow(row) if row else None

    def fetchall(self):
        return [_PGRow(r) for r in self._cur.fetchall()]

    def __iter__(self):
        return (_PGRow(r) for r in self._cur)


class _PGAdapter:
    """sqlite3-compatible wrapper around psycopg2 connection."""

    def __init__(self, conn):
        self._conn = conn
        import psycopg2.extras
        self._cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.row_factory = None  # compatibility attribute

    def execute(self, sql: str, params=()):
        cursor = _PGCursor(self._cur)
        cursor.execute(sql, params)
        return cursor

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self


class _PGPoolAdapter(_PGAdapter):
    """Pooled version — returns connection to pool on close instead of destroying it."""

    def __init__(self, conn, pool):
        super().__init__(conn)
        self._pool = pool

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def __exit__(self, exc_type, *args):
        if exc_type:
            self._conn.rollback()
        self.close()


_pg_pool = None
_pg_pool_lock = __import__('threading').Lock()


def _get_pg_pool():
    """Get or create a PostgreSQL connection pool (lazy singleton)."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    with _pg_pool_lock:
        if _pg_pool is not None:
            return _pg_pool
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return None
        try:
            from psycopg2 import pool as pg_pool
            _pg_pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=database_url,
            )
            logger.info("[DB] PostgreSQL connection pool created (2-10 connections)")
            return _pg_pool
        except ImportError:
            logger.warning("[DB] psycopg2 not installed — falling back to SQLite")
        except Exception as exc:
            logger.error("[DB] PostgreSQL pool creation failed: %s — falling back to SQLite", exc)
    return None


def get_db():
    """Return a database connection. Uses pooled PostgreSQL if available, else SQLite."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        pool = _get_pg_pool()
        if pool:
            try:
                conn = pool.getconn()
                conn.autocommit = False
                return _PGPoolAdapter(conn, pool)
            except Exception as exc:
                logger.error("[DB] Pool getconn failed: %s — falling back to SQLite", exc)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def _is_pg():
    """Check if PostgreSQL is configured."""
    return bool(os.getenv("DATABASE_URL"))


def init_db(app=None):
    """Initialize all tables, apply migrations, and seed demo data."""
    # Try PostgreSQL first; if connection fails, get_db() falls back to SQLite
    db = get_db()
    using_pg = isinstance(db, _PGAdapter)

    if using_pg:
        _create_tables(db, pg=True)
        db.commit()
        _apply_migrations_pg(db)
        _seed_users(db, db)
        _seed_policy(db, db)
        _seed_requests(db, db)
        _seed_meetings(db, db)
        _seed_expenses(db, db)
        db.close()
    else:
        db.close()
        db = sqlite3.connect(DB_PATH)
        c = db.cursor()
        _create_tables(c, pg=False)
        db.commit()
        _apply_migrations(db, c)
        _seed_users(c, db)
        _seed_policy(c, db)
        _seed_requests(c, db)
        _seed_meetings(c, db)
        _seed_expenses(c, db)
        db.close()
    logger.info("[DB] Database initialized (%s)", "PostgreSQL" if using_pg else "SQLite")


# ── Table Creation ─────────────────────────────────────────────────────────────

def _create_tables(c, pg=None):
    # PostgreSQL uses SERIAL instead of INTEGER PRIMARY KEY AUTOINCREMENT
    use_pg = pg if pg is not None else _is_pg()
    pk = "SERIAL PRIMARY KEY" if use_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        id               {pk},
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

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS travel_policies (
        id                      {pk},
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

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS travel_requests (
        id                      {pk},
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
        policy_compliance_json  TEXT DEFAULT '{{}}',
        compliance_details      TEXT,
        trip_plan               TEXT,
        notes                   TEXT,
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS approvals (
        id           {pk},
        request_id   TEXT REFERENCES travel_requests(request_id),
        approver_id  INTEGER REFERENCES users(id),
        status       TEXT DEFAULT 'pending',
        comments     TEXT,
        decided_at   TIMESTAMP,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS expenses_db (
        id                   {pk},
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

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS client_meetings (
        id             {pk},
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

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS sos_events (
        id             {pk},
        user_id        INTEGER,
        destination    TEXT,
        location       TEXT,
        emergency_type TEXT DEFAULT 'general',
        message        TEXT,
        resolved       INTEGER DEFAULT 0,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id          TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL,
        title       TEXT DEFAULT 'New Chat',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id               {pk},
        user_id          INTEGER,
        session_id       TEXT,
        role             TEXT NOT NULL,
        content          TEXT NOT NULL,
        intent           TEXT,
        action_card_json TEXT,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS notifications (
        id         {pk},
        user_id    INTEGER REFERENCES users(id),
        type       TEXT DEFAULT 'info',
        title      TEXT NOT NULL,
        message    TEXT,
        read       INTEGER DEFAULT 0,
        link       TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")


# ── Migrations: safely add columns to existing databases ───────────────────────

def _apply_migrations_pg(db):
    """PostgreSQL-compatible migrations using information_schema."""
    def _add_col(table, col, definition):
        try:
            existing = {r["column_name"] for r in db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (table,)
            ).fetchall()}
            if col not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
                db.commit()
                logger.info("[DB] Migration: added %s.%s", table, col)
        except Exception as e:
            logger.warning("[DB] Migration skipped %s.%s: %s", table, col, e)

    _add_col("users", "full_name",       "TEXT")
    _add_col("users", "avatar_initials", "TEXT")
    _add_col("users", "phone",           "TEXT")
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
    _add_col("approvals", "decided_at", "TIMESTAMP")
    _add_col("expenses_db", "request_id", "TEXT")
    _add_col("chat_messages", "action_card_json", "TEXT")
    _add_col("chat_messages", "session_id", "TEXT")
    _add_col("users", "email_verified", "INTEGER DEFAULT 1")

    # chat_sessions table (for existing databases)
    try:
        db.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            title       TEXT DEFAULT 'New Chat',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.commit()
    except Exception:
        pass

    # Sync full_name from name for existing users
    db.execute("UPDATE users SET full_name = name WHERE full_name IS NULL OR full_name = ''")
    rows = db.execute("SELECT id, name FROM users WHERE avatar_initials IS NULL OR avatar_initials = ''").fetchall()
    for row in rows:
        initials = "".join(w[0].upper() for w in str(row["name"]).split()[:2])
        db.execute("UPDATE users SET avatar_initials = ? WHERE id = ?", (initials, row["id"]))
    db.commit()


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

    # chat_messages — add action_card_json + session_id
    _add_col("chat_messages", "action_card_json", "TEXT")
    _add_col("chat_messages", "session_id", "TEXT")

    # chat_sessions table (for existing databases)
    try:
        c.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            title       TEXT DEFAULT 'New Chat',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.commit()
    except Exception:
        pass

    # users — email verification flag (default 1 = verified for existing users)
    _add_col("users", "email_verified", "INTEGER DEFAULT 1")

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

def _count(c, table):
    """Get row count — works with both SQLite cursor and PG adapter."""
    row = c.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
    return row["cnt"] if isinstance(row, dict) else row[0]


def _exec_many(c, sql, rows):
    """executemany for both SQLite cursor and PG adapter (which lacks executemany)."""
    if hasattr(c, "executemany"):
        c.executemany(sql, rows)
    else:
        for row in rows:
            c.execute(sql, row)


def _seed_users(c, db):
    """No-op — demo users removed. Users register through the signup flow."""
    pass


def _seed_policy(c, db):
    if _count(c, "travel_policies") > 0:
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
    if _count(c, "travel_requests") > 0:
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
    _exec_many(
        c,
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
    if _count(c, "client_meetings") > 0:
        return
    now = dt.datetime.now()
    rows = [
        (1, "Mumbai",    "Ankit Mehta",  "Reliance Industries", "+91-9812345670",
         "ankit@reliance.com", (now + dt.timedelta(days=3)).strftime("%Y-%m-%d"),
         "10:00 AM", "Reliance Corporate Park",  "Q1 Strategy Review",        "Email thread",           "email",    "scheduled"),
        (1, "Delhi",     "Sunita Gupta", "HDFC Bank",           "+91-9823456781",
         "sunita@hdfc.com",   (now + dt.timedelta(days=6)).strftime("%Y-%m-%d"),
         "2:30 PM",  "HDFC House Connaught Pl",  "Expense Reconciliation",    "LinkedIn outreach",      "linkedin", "scheduled"),
        (2, "Bangalore", "Karan Joshi",  "Infosys BPO",         "+91-9834567892",
         "karan@infosys.com", (now + dt.timedelta(days=4)).strftime("%Y-%m-%d"),
         "11:00 AM", "Infosys Electronic City",  "Budget Planning FY26",      "Calendar invite",        "calendar", "scheduled"),
        (3, "Bangalore", "Ravi Kumar",   "TCS Innovation Labs", "+91-9876543210",
         "ravi@tcs.com",    (now + dt.timedelta(days=2)).strftime("%Y-%m-%d"),
         "10:00 AM", "TCS Whitefield",           "Q4 Partnership Discussion",  "Via email",             "email",    "scheduled"),
        (3, "Hyderabad", "Meena Reddy",  "Infosys",             "+91-8765432109",
         "meena@infosys.com",(now + dt.timedelta(days=5)).strftime("%Y-%m-%d"),
         "2:00 PM",  "Infosys Hitech City",      "Annual Review",              "Called Monday",         "phone",    "scheduled"),
        (4, "Mumbai",    "Aryan Shah",   "Wipro Digital",       "+91-7654321098",
         "aryan@wipro.com", (now + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
         "11:30 AM", "Wipro BKC",                "Product Demo",               "Meeting invite via WA", "whatsapp", "scheduled"),
        (5, "Chennai",   "Deepa Nair",   "HCL Technologies",    "+91-6543210987",
         "deepa@hcl.com",  (now + dt.timedelta(days=7)).strftime("%Y-%m-%d"),
         "3:00 PM",  "HCL Sholinganallur",       "Proposal Presentation",      "LinkedIn message",      "linkedin", "scheduled"),
    ]
    _exec_many(
        c,
        """INSERT INTO client_meetings
           (user_id, destination, client_name, company, contact_number, email,
            meeting_date, meeting_time, venue, agenda, notes, source_type, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    db.commit()


def _seed_expenses(c, db):
    if _count(c, "expenses_db") > 0:
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
    _exec_many(
        c,
        """INSERT INTO expenses_db
           (request_id, user_id, category, description,
            invoice_amount, payment_amount, verified_amount,
            verification_status, stage, date, currency_code,
            ocr_extracted_amount, ocr_confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    db.commit()
