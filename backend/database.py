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
from dotenv import load_dotenv

# Ensure .env is loaded before checking DATABASE_URL
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path, override=False)

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


def _sqlite_fmt_to_pg(fmt: str) -> str:
    """Convert SQLite strftime format to PostgreSQL TO_CHAR format."""
    return (fmt
            .replace("%Y", "YYYY")
            .replace("%m", "MM")
            .replace("%d", "DD")
            .replace("%H", "HH24")
            .replace("%M", "MI")
            .replace("%S", "SS"))


class _PGCursor:
    """sqlite3-compatible cursor wrapper around psycopg2 cursor."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql: str, params=()):
        # Convert SQLite strftime to PostgreSQL TO_CHAR
        pg_sql = re.sub(
            r"strftime\(\s*'([^']+)'\s*,\s*(\w+)\s*\)",
            lambda m: f"TO_CHAR({m.group(2)}, '{_sqlite_fmt_to_pg(m.group(1))}')",
            sql,
        )
        pg_sql = re.sub(r"\?", "%s", pg_sql)
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

    def __exit__(self, exc_type, *args):
        if exc_type:
            self._conn.rollback()
        self.close()


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


def table_columns(db, table: str) -> set:
    """Return set of column names for a table. Works for both SQLite and PostgreSQL (Supabase)."""
    if isinstance(db, _PGAdapter):
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table,),
        ).fetchall()
        return {r["column_name"] for r in rows}
    # SQLite
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def get_db():
    """Return a database connection. Uses Supabase PostgreSQL when DATABASE_URL is set.
    Falls back to SQLite only when no DATABASE_URL is configured (local dev without Supabase).
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        pool = _get_pg_pool()
        if pool:
            try:
                conn = pool.getconn()
                conn.autocommit = False
                return _PGPoolAdapter(conn, pool)
            except Exception as exc:
                logger.error("[DB] Supabase pool getconn failed: %s", exc)
                raise RuntimeError(f"Supabase PostgreSQL connection failed: {exc}") from exc
        # Pool creation failed — try direct connection as last resort
        try:
            import psycopg2
            conn = psycopg2.connect(database_url)
            conn.autocommit = False
            logger.warning("[DB] Using direct Supabase connection (pool unavailable)")
            return _PGAdapter(conn)
        except Exception as exc:
            logger.error("[DB] Direct Supabase connection also failed: %s", exc)
            raise RuntimeError(f"Cannot connect to Supabase: {exc}") from exc

    # No DATABASE_URL — local dev only
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

    # ── Multi-tenancy: Organizations ──────────────────────────────────────────
    c.execute(f"""
    CREATE TABLE IF NOT EXISTS organizations (
        id               {pk},
        name             TEXT NOT NULL,
        slug             TEXT UNIQUE NOT NULL,
        logo_url         TEXT,
        plan             TEXT DEFAULT 'free',
        status           TEXT DEFAULT 'active',
        settings_json    TEXT DEFAULT '{{}}',
        billing_email    TEXT,
        max_members      INTEGER DEFAULT 50,
        features_json    TEXT DEFAULT '{{}}',
        notes            TEXT,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS org_members (
        id               {pk},
        org_id           INTEGER NOT NULL REFERENCES organizations(id),
        user_id          INTEGER NOT NULL REFERENCES users(id),
        org_role         TEXT DEFAULT 'member',
        department       TEXT DEFAULT 'General',
        invited_by       INTEGER,
        joined_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS travel_policies (
        id                      {pk},
        org_id                  INTEGER REFERENCES organizations(id),
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
        org_id                  INTEGER REFERENCES organizations(id),
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
        org_id       INTEGER REFERENCES organizations(id),
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
        org_id               INTEGER REFERENCES organizations(id),
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
        org_id         INTEGER REFERENCES organizations(id),
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
        org_id         INTEGER REFERENCES organizations(id),
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
        org_id      INTEGER REFERENCES organizations(id),
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
        org_id     INTEGER REFERENCES organizations(id),
        user_id    INTEGER REFERENCES users(id),
        type       TEXT DEFAULT 'info',
        title      TEXT NOT NULL,
        message    TEXT,
        read       INTEGER DEFAULT 0,
        link       TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id           {pk},
        org_id       INTEGER,
        actor_id     INTEGER,
        actor_email  TEXT,
        action       TEXT NOT NULL,
        entity       TEXT NOT NULL,
        entity_id    TEXT,
        diff_json    TEXT,
        ip_address   TEXT,
        user_agent   TEXT,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS webhook_subscriptions (
        id              {pk},
        org_id          INTEGER REFERENCES organizations(id),
        event_type      TEXT NOT NULL,
        target_url      TEXT NOT NULL,
        secret          TEXT NOT NULL,
        headers_json    TEXT DEFAULT '{{}}',
        active          INTEGER DEFAULT 1,
        last_triggered  TIMESTAMP,
        last_status     INTEGER,
        failure_count   INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── Indexes for query performance ─────────────────────────────────────────
    _create_indexes(c, use_pg)


# ── Indexes ───────────────────────────────────────────────────────────────────

def _create_indexes(c, pg=False):
    """Create indexes on foreign keys and frequently-queried columns.
    Uses CREATE INDEX IF NOT EXISTS (safe to run on every startup).
    """
    indexes = [
        # organizations & org_members
        ("idx_org_members_org_id",            "org_members", "org_id"),
        ("idx_org_members_user_id",           "org_members", "user_id"),
        ("idx_organizations_slug",            "organizations", "slug"),
        # travel_requests
        ("idx_travel_requests_org_id",        "travel_requests", "org_id"),
        ("idx_travel_requests_user_id",       "travel_requests", "user_id"),
        ("idx_travel_requests_status",        "travel_requests", "status"),
        ("idx_travel_requests_request_id",    "travel_requests", "request_id"),
        ("idx_travel_requests_start_date",    "travel_requests", "start_date"),
        # approvals
        ("idx_approvals_org_id",              "approvals", "org_id"),
        ("idx_approvals_request_id",          "approvals", "request_id"),
        ("idx_approvals_approver_id",         "approvals", "approver_id"),
        ("idx_approvals_status",              "approvals", "status"),
        # expenses_db
        ("idx_expenses_org_id",               "expenses_db", "org_id"),
        ("idx_expenses_user_id",              "expenses_db", "user_id"),
        ("idx_expenses_request_id",           "expenses_db", "request_id"),
        ("idx_expenses_approval_status",      "expenses_db", "approval_status"),
        # client_meetings
        ("idx_meetings_org_id",               "client_meetings", "org_id"),
        ("idx_meetings_user_id",              "client_meetings", "user_id"),
        ("idx_meetings_meeting_date",         "client_meetings", "meeting_date"),
        # chat_messages
        ("idx_chat_messages_user_id",         "chat_messages", "user_id"),
        ("idx_chat_messages_session_id",      "chat_messages", "session_id"),
        # chat_sessions
        ("idx_chat_sessions_org_id",          "chat_sessions", "org_id"),
        ("idx_chat_sessions_user_id",         "chat_sessions", "user_id"),
        # notifications
        ("idx_notifications_org_id",          "notifications", "org_id"),
        ("idx_notifications_user_id",         "notifications", "user_id"),
        ("idx_notifications_read",            "notifications", "read"),
        # sos_events
        ("idx_sos_events_org_id",             "sos_events", "org_id"),
        ("idx_sos_events_user_id",            "sos_events", "user_id"),
        # travel_policies
        ("idx_travel_policies_org_id",        "travel_policies", "org_id"),
        # audit_logs
        ("idx_audit_logs_org_id",             "audit_logs", "org_id"),
        ("idx_audit_logs_actor_id",           "audit_logs", "actor_id"),
        ("idx_audit_logs_entity",             "audit_logs", "entity"),
        ("idx_audit_logs_created_at",         "audit_logs", "created_at"),
        # webhook_subscriptions
        ("idx_webhooks_org_event",            "webhook_subscriptions", "org_id"),
    ]
    for idx_name, table, column in indexes:
        try:
            c.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
        except Exception as e:
            logger.debug("[DB] Index %s skipped: %s", idx_name, e)


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

    # users — profile + role hierarchy
    _add_col("users", "profile_picture", "TEXT")
    _add_col("users", "sub_role", "TEXT")

    # expenses_db — approval workflow
    _add_col("expenses_db", "approval_status", "TEXT DEFAULT 'draft'")
    _add_col("expenses_db", "approver_id", "INTEGER")
    _add_col("expenses_db", "approval_comments", "TEXT")
    _add_col("expenses_db", "submitted_at", "TIMESTAMP")
    _add_col("expenses_db", "approved_at", "TIMESTAMP")

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

    # Multi-tenancy: org_id columns on all data tables
    _add_col("travel_policies",  "org_id", "INTEGER")
    _add_col("travel_requests",  "org_id", "INTEGER")
    _add_col("approvals",        "org_id", "INTEGER")
    _add_col("expenses_db",      "org_id", "INTEGER")
    _add_col("client_meetings",  "org_id", "INTEGER")
    _add_col("sos_events",       "org_id", "INTEGER")
    _add_col("chat_sessions",    "org_id", "INTEGER")
    _add_col("notifications",    "org_id", "INTEGER")

    # Organizations: status + features columns
    _add_col("organizations", "status",        "TEXT DEFAULT 'active'")
    _add_col("organizations", "features_json", "TEXT DEFAULT '{}'")
    _add_col("organizations", "notes",         "TEXT")

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

    # users — profile + role hierarchy
    _add_col("users", "profile_picture", "TEXT")
    _add_col("users", "sub_role", "TEXT")

    # expenses_db — approval workflow
    _add_col("expenses_db", "approval_status", "TEXT DEFAULT 'draft'")
    _add_col("expenses_db", "approver_id", "INTEGER")
    _add_col("expenses_db", "approval_comments", "TEXT")
    _add_col("expenses_db", "submitted_at", "TIMESTAMP")
    _add_col("expenses_db", "approved_at", "TIMESTAMP")

    # Multi-tenancy: org_id columns on all data tables
    _add_col("travel_policies",  "org_id", "INTEGER")
    _add_col("travel_requests",  "org_id", "INTEGER")
    _add_col("approvals",        "org_id", "INTEGER")
    _add_col("expenses_db",      "org_id", "INTEGER")
    _add_col("client_meetings",  "org_id", "INTEGER")
    _add_col("sos_events",       "org_id", "INTEGER")
    _add_col("chat_sessions",    "org_id", "INTEGER")
    _add_col("notifications",    "org_id", "INTEGER")

    # Organizations: status + features columns
    _add_col("organizations", "status",        "TEXT DEFAULT 'active'")
    _add_col("organizations", "features_json", "TEXT DEFAULT '{}'")
    _add_col("organizations", "notes",         "TEXT")

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
    """No-op — demo requests removed. Requests are created through the app."""
    pass


def _seed_meetings(c, db):
    """No-op — demo meetings removed. Meetings are created through the app."""
    pass


def _seed_expenses(c, db):
    """No-op — demo expenses removed. Expenses are created through the app."""
    pass
