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
from contextlib import contextmanager
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
        # Convert SQLite last_insert_rowid() to PostgreSQL lastval()
        pg_sql = re.sub(r"last_insert_rowid\(\s*\)", "lastval()", pg_sql, flags=re.IGNORECASE)
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

    def rollback(self):
        self._conn.rollback()

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
        # Roll back any uncommitted transaction before returning to pool.
        # This prevents the "set_session cannot be used inside a transaction"
        # error on the next getconn() call and avoids leaving dirty state.
        try:
            if self._conn.closed == 0:
                import psycopg2.extensions as _ext
                if self._conn.status not in (_ext.STATUS_READY,):
                    self._conn.rollback()
        except Exception:
            pass
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def __exit__(self, exc_type, *args):
        if exc_type:
            try:
                self._conn.rollback()
            except Exception:
                pass
        self.close()


_pg_pool = None
_pg_pool_lock = __import__('threading').Lock()
_pg_pool_last_failure = 0.0

# Pool tuning — defaults raised from 1-4 to 2-10 to handle moderate production
# concurrency under eventlet (single Gunicorn worker, many green threads).
# Supabase session-mode poolers typically allow 20-60 connections per project.
_PG_MINCONN = max(1, int(os.getenv("DB_POOL_MINCONN", "2")))
_PG_MAXCONN = max(_PG_MINCONN, int(os.getenv("DB_POOL_MAXCONN", "10")))
_PG_ACQUIRE_RETRIES = 3   # retries before giving up on pool
_PG_ACQUIRE_BACKOFF = 0.1  # initial back-off seconds (doubles each retry)
_PG_POOL_FAILURE_COOLDOWN = float(os.getenv("DB_POOL_FAILURE_COOLDOWN", "15"))
# Per-connection timeouts added to the DSN to prevent runaway queries / stale conns
_PG_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))       # seconds
_PG_STATEMENT_TIMEOUT = int(os.getenv("DB_STATEMENT_TIMEOUT", "15000"))  # milliseconds


def _get_pg_pool():
    """Get or create a PostgreSQL connection pool (lazy singleton)."""
    global _pg_pool, _pg_pool_last_failure
    if _pg_pool is not None:
        return _pg_pool
    with _pg_pool_lock:
        if _pg_pool is not None:
            return _pg_pool
        import time
        if _pg_pool_last_failure and (time.time() - _pg_pool_last_failure) < _PG_POOL_FAILURE_COOLDOWN:
            return None
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return None
        try:
            from psycopg2 import pool as pg_pool
            _pg_pool = pg_pool.ThreadedConnectionPool(
                minconn=_PG_MINCONN,
                maxconn=_PG_MAXCONN,
                dsn=database_url,
                connect_timeout=_PG_CONNECT_TIMEOUT,
                options=f"-c statement_timeout={_PG_STATEMENT_TIMEOUT}",
            )
            logger.info(
                "[DB] PostgreSQL pool created (%d-%d conns, connect_timeout=%ds, statement_timeout=%dms)",
                _PG_MINCONN, _PG_MAXCONN, _PG_CONNECT_TIMEOUT, _PG_STATEMENT_TIMEOUT,
            )
            _pg_pool_last_failure = 0.0
            return _pg_pool
        except ImportError:
            logger.warning("[DB] psycopg2 not installed — falling back to SQLite")
        except Exception as exc:
            _pg_pool_last_failure = time.time()
            logger.error("[DB] PostgreSQL pool creation failed: %s — falling back to direct Supabase connection", exc)
    return None


def _ensure_clean_pg_conn(conn, pool):
    """
    Make sure a psycopg2 connection is in a usable state before handing it
    to a caller.

    * If the connection is closed, discard it (put back with close=True).
    * If the connection has a pending / errored transaction left over from a
      previous use without a proper close, roll it back.

    Returns True if the connection is healthy, False if it was discarded.
    Never executes a query (to avoid opening a new transaction prematurely).
    """
    try:
        import psycopg2.extensions as _ext
        if conn.closed != 0:
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            return False
        # Roll back any leftover transaction without opening a new one
        if conn.status not in (_ext.STATUS_READY, _ext.STATUS_IN_TRANSACTION):
            # STATUS_INTRANS_INERROR or unknown — reset to ready
            conn.rollback()
        elif conn.status == _ext.STATUS_IN_TRANSACTION:
            conn.rollback()
    except Exception:
        # If we can't even check, discard the connection
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
        return False
    return True


def _pool_getconn_with_retry(pool):
    """
    Acquire a connection from the pool with exponential-backoff retries.

    On heavy load the pool may be momentarily exhausted.  Rather than
    immediately raising (and returning a 500 to the client), we wait a
    short time and retry up to _PG_ACQUIRE_RETRIES times.  If the pool
    itself is broken (e.g. Supabase restarted) we recreate it once and
    try again before giving up.
    """
    import time
    global _pg_pool

    last_exc = None
    backoff = _PG_ACQUIRE_BACKOFF

    for attempt in range(_PG_ACQUIRE_RETRIES):
        try:
            conn = pool.getconn()
            # Ensure the connection is clean (no stale transaction, not closed).
            # We check connection state without executing any SQL so we do not
            # accidentally open a transaction before the caller is ready.
            if not _ensure_clean_pg_conn(conn, pool):
                raise Exception("Stale connection discarded — retrying")
            return conn
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "[DB] Pool getconn attempt %d/%d failed: %s — retrying in %.2fs",
                attempt + 1, _PG_ACQUIRE_RETRIES, exc, backoff,
            )
            time.sleep(backoff)
            backoff *= 2  # exponential back-off: 0.1 → 0.2 → 0.4 s

            # Second-to-last attempt: try to recreate the pool in case it is broken.
            if attempt == _PG_ACQUIRE_RETRIES - 2:
                with _pg_pool_lock:
                    database_url = os.getenv("DATABASE_URL")
                    if database_url:
                        try:
                            from psycopg2 import pool as pg_pool_mod
                            try:
                                _pg_pool.closeall()
                            except Exception:
                                pass
                            _pg_pool = pg_pool_mod.ThreadedConnectionPool(
                                minconn=_PG_MINCONN,
                                maxconn=_PG_MAXCONN,
                                dsn=database_url,
                                connect_timeout=_PG_CONNECT_TIMEOUT,
                                options=f"-c statement_timeout={_PG_STATEMENT_TIMEOUT}",
                            )
                            pool = _pg_pool
                            logger.info("[DB] PostgreSQL pool recreated after failure")
                        except Exception as recreate_exc:
                            logger.error("[DB] Pool recreation failed: %s", recreate_exc)

    raise RuntimeError(
        f"Supabase PostgreSQL connection failed after {_PG_ACQUIRE_RETRIES} attempts: {last_exc}"
    ) from last_exc


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

    The pool is acquired with retry + exponential backoff so that transient
    exhaustion under heavy load does not immediately surface as a 500 error.
    If the pool is unrecoverable a direct connection is attempted as a final
    fallback before raising.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        pool = _get_pg_pool()
        if pool:
            try:
                conn = _pool_getconn_with_retry(pool)
                conn.autocommit = False
                return _PGPoolAdapter(conn, pool)
            except RuntimeError:
                raise
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

    # No DATABASE_URL — local dev / tests use SQLite
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


@contextmanager
def transaction():
    """Context manager for atomic multi-step database operations.

    Usage:
        with transaction() as db:
            db.execute("INSERT ...")
            db.execute("UPDATE ...")
        # Auto-commits on success, auto-rolls back on exception.

    Non-DB side effects (email, webhook) should happen AFTER the with block.
    """
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


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

    # ── OTIS Voice Agent Tables ───────────────────────────────────────────────

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS otis_sessions (
        id                  {pk},
        org_id              INTEGER REFERENCES organizations(id),
        user_id             INTEGER REFERENCES users(id),
        session_id          TEXT UNIQUE NOT NULL,
        status              TEXT DEFAULT 'active',
        wake_word_detected  INTEGER DEFAULT 0,
        total_turns         INTEGER DEFAULT 0,
        started_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at            TIMESTAMP,
        duration_seconds    INTEGER DEFAULT 0
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS otis_commands (
        id                      {pk},
        org_id                  INTEGER REFERENCES organizations(id),
        user_id                 INTEGER REFERENCES users(id),
        session_id              TEXT REFERENCES otis_sessions(session_id),

        command_text            TEXT NOT NULL,
        transcript              TEXT,
        transcript_confidence   REAL,

        intent                  TEXT,
        intent_confidence       REAL,
        entities_json           TEXT DEFAULT '{{}}',

        function_called         TEXT,
        function_params_json    TEXT DEFAULT '{{}}',
        function_result_json    TEXT DEFAULT '{{}}',

        response_text           TEXT,
        response_audio_url      TEXT,

        success                 INTEGER DEFAULT 1,
        error_message           TEXT,

        latency_ms              INTEGER,
        cost_usd                REAL,

        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS otis_conversations (
        id              {pk},
        session_id      TEXT REFERENCES otis_sessions(session_id),
        turn_number     INTEGER NOT NULL,
        role            TEXT NOT NULL,
        content         TEXT NOT NULL,
        audio_url       TEXT,
        timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS otis_settings (
        id                      {pk},
        org_id                  INTEGER UNIQUE REFERENCES organizations(id),
        user_id                 INTEGER UNIQUE REFERENCES users(id),

        enabled                 INTEGER DEFAULT 1,
        admin_only              INTEGER DEFAULT 1,

        wake_word               TEXT DEFAULT 'Hey Otis',
        voice_id                TEXT DEFAULT 'en-IN-male',
        voice_speed             REAL DEFAULT 1.0,
        voice_pitch             REAL DEFAULT 1.0,

        auto_execute_actions    INTEGER DEFAULT 0,
        require_confirmation    INTEGER DEFAULT 1,

        max_session_duration    INTEGER DEFAULT 600,
        idle_timeout_seconds    INTEGER DEFAULT 30,

        settings_json           TEXT DEFAULT '{{}}',

        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute(f"""
    CREATE TABLE IF NOT EXISTS otis_analytics (
        id                      {pk},
        org_id                  INTEGER REFERENCES organizations(id),
        date                    TEXT NOT NULL,

        total_sessions          INTEGER DEFAULT 0,
        total_commands          INTEGER DEFAULT 0,
        successful_commands     INTEGER DEFAULT 0,
        failed_commands         INTEGER DEFAULT 0,

        avg_latency_ms          REAL DEFAULT 0,
        total_cost_usd          REAL DEFAULT 0,

        most_used_function      TEXT,
        total_active_users      INTEGER DEFAULT 0,

        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── Auth Security Tables ──────────────────────────────────────────────────
    # token_blacklist: persists revoked JWT hashes across processes/instances.
    # Rows are expired by the keepalive thread every 4 minutes.
    c.execute("""
    CREATE TABLE IF NOT EXISTS token_blacklist (
        token_hash   TEXT PRIMARY KEY,
        expires_at   TIMESTAMP NOT NULL,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # auth_codes: stores one-time codes for password reset and email verification.
    # Replaces the previous in-memory _reset_tokens / _verify_tokens dicts so that
    # codes work correctly across multiple Cloud Run instances.
    c.execute(f"""
    CREATE TABLE IF NOT EXISTS auth_codes (
        id           {pk},
        code         TEXT UNIQUE NOT NULL,
        type         TEXT NOT NULL,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        email        TEXT,
        expires_at   TIMESTAMP NOT NULL,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        # OTIS voice agent
        ("idx_otis_sessions_org_id",          "otis_sessions", "org_id"),
        ("idx_otis_sessions_user_id",         "otis_sessions", "user_id"),
        ("idx_otis_sessions_session_id",      "otis_sessions", "session_id"),
        ("idx_otis_sessions_status",          "otis_sessions", "status"),
        ("idx_otis_commands_org_id",          "otis_commands", "org_id"),
        ("idx_otis_commands_user_id",         "otis_commands", "user_id"),
        ("idx_otis_commands_session_id",      "otis_commands", "session_id"),
        ("idx_otis_commands_function",        "otis_commands", "function_called"),
        ("idx_otis_conversations_session",    "otis_conversations", "session_id"),
        ("idx_otis_analytics_org_date",       "otis_analytics", "org_id"),
        # auth security tables
        ("idx_token_blacklist_expires",       "token_blacklist", "expires_at"),
        ("idx_auth_codes_user_type",          "auth_codes", "user_id"),
        ("idx_auth_codes_expires",            "auth_codes", "expires_at"),
    ]
    for idx_name, table, column in indexes:
        try:
            c.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
        except Exception as e:
            logger.debug("[DB] Index %s skipped: %s", idx_name, e)

    # ── Unique constraints (safe to run on every startup) ────────────────────
    # Prevents a user from being added to the same org multiple times.
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_org_members_org_user ON org_members (org_id, user_id)")
    except Exception as e:
        logger.debug("[DB] Unique index uq_org_members_org_user skipped: %s", e)


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

    # expenses_db — source tracking and duplicate detection
    _add_col("expenses_db", "source", "TEXT DEFAULT 'web'")  # whatsapp, cliq, web, manual
    _add_col("expenses_db", "vendor", "TEXT")  # extracted vendor name for duplicate detection

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

    # otis_settings — flexible JSON blob for custom per-user settings
    _add_col("otis_settings", "settings_json", "TEXT DEFAULT '{}'")

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

    # expenses_db — source tracking and duplicate detection
    _add_col("expenses_db", "source", "TEXT DEFAULT 'web'")  # whatsapp, cliq, web, manual
    _add_col("expenses_db", "vendor", "TEXT")  # extracted vendor name for duplicate detection

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

    # otis_settings — flexible JSON blob for custom per-user settings
    _add_col("otis_settings", "settings_json", "TEXT DEFAULT '{}'")

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
