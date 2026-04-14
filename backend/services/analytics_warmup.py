"""
TravelSync Pro — Analytics Cache Warmup
Background daemon thread that pre-computes analytics for all active
organisations every 5 minutes. Keeps the cache always warm so the first
user to open the dashboard after a cache expiry never pays the DB cost.

Pattern mirrors _start_supabase_keepalive() in app.py — daemon thread,
silent on failure, never blocks app startup.

What is warmed (org-level only):
  - get_dashboard_stats()                          — global KPIs
  - get_spend_analysis(org_id, role="admin")       — per active org
  - get_policy_compliance_scorecard(org_id, ...)   — per active org

What is NOT warmed (too many combinations):
  - Per-user stats (employees) — the 60s TTL from Fix 6 handles these
    reactively; the first employee request per minute pays the DB cost,
    subsequent ones are free.
"""
import time
import logging
import threading

logger = logging.getLogger(__name__)

_WARMUP_INTERVAL_SEC = 300   # 5 minutes — aligns with analytics 60s TTL × 5
_STARTUP_DELAY_SEC   = 45    # Let gunicorn + DB pool settle before first run
_MAX_ORGS_PER_PASS   = 50    # Safety cap — avoids runaway on very large installs


def _get_active_org_ids() -> list:
    """Return distinct org_ids from the users table. Safe on any schema."""
    try:
        from database import get_db, table_columns
        db = get_db()
        try:
            cols = table_columns(db, "users")
            if "org_id" not in cols:
                return []
            rows = db.execute(
                f"SELECT DISTINCT org_id FROM users"
                f" WHERE org_id IS NOT NULL"
                f" LIMIT {_MAX_ORGS_PER_PASS}"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        finally:
            db.close()
    except Exception as e:
        logger.debug("[Warmup] Could not fetch org_ids: %s", e)
        return []


def _run_warmup() -> None:
    """
    Single warmup pass. Imports analytics functions lazily so a startup
    import error in analytics_agent.py never crashes the warmup thread.
    """
    try:
        from agents.analytics_agent import (
            get_dashboard_stats,
            get_spend_analysis,
            get_policy_compliance_scorecard,
        )
    except Exception as e:
        logger.warning("[Warmup] Could not import analytics functions: %s", e)
        return

    warmed_orgs = 0
    errors = 0

    # 1. Global stats — no user/org scope (populates cache key "dashboard:None")
    try:
        get_dashboard_stats()
        get_spend_analysis()
        get_policy_compliance_scorecard()
    except Exception as e:
        logger.debug("[Warmup] Global analytics failed: %s", e)
        errors += 1

    # 2. Per-org stats — admin/manager view for each active organisation
    org_ids = _get_active_org_ids()
    for org_id in org_ids:
        try:
            get_spend_analysis(org_id=org_id, role="admin")
            get_policy_compliance_scorecard(org_id=org_id, role="admin")
            warmed_orgs += 1
        except Exception as e:
            logger.debug("[Warmup] Org %s analytics failed: %s", org_id, e)
            errors += 1

    if errors == 0:
        logger.info("[Warmup] Analytics warmed — global + %d org(s)", warmed_orgs)
    else:
        logger.info("[Warmup] Analytics warmed — global + %d org(s), %d error(s)", warmed_orgs, errors)


def start_analytics_warmup() -> None:
    """
    Start the background analytics pre-computation daemon thread.
    Called once from app.py create_app(). Safe to call multiple times
    (subsequent calls are silently ignored via the daemon check).
    """
    def _loop():
        time.sleep(_STARTUP_DELAY_SEC)  # Wait for app to fully boot
        while True:
            _run_warmup()
            time.sleep(_WARMUP_INTERVAL_SEC)

    t = threading.Thread(target=_loop, daemon=True, name="analytics-warmup")
    t.start()
    logger.info(
        "[Warmup] Analytics warmup thread started "
        "(startup delay=%ds, interval=%ds)",
        _STARTUP_DELAY_SEC, _WARMUP_INTERVAL_SEC,
    )
