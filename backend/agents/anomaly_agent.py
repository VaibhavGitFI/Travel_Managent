"""
TravelSync Pro — Expense Anomaly Detection Agent
Flags suspicious expenses: duplicates, weekend submissions, category outliers,
rapid-fire submissions, and unusually round amounts.
"""
import logging
from datetime import datetime
from database import get_db

logger = logging.getLogger(__name__)


def detect_anomalies(user_id: int) -> dict:
    """
    Scan a user's expenses for anomalies.
    Returns {success, anomalies: [{expense_id, type, severity, title, message}], summary}
    """
    anomalies = []

    try:
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(expenses_db)").fetchall()}

        amount_col = "amount" if "amount" in cols else "invoice_amount"
        date_col = "expense_date" if "expense_date" in cols else "date" if "date" in cols else "created_at"
        cat_col = "category" if "category" in cols else None

        # Fetch all user expenses
        query = f"SELECT id, {amount_col} as amount, {date_col} as expense_date"
        if cat_col:
            query += f", {cat_col} as category"
        if "vendor" in cols:
            query += ", vendor"
        if "description" in cols:
            query += ", description"
        if "created_at" in cols:
            query += ", created_at"
        query += f" FROM expenses_db WHERE user_id = ? ORDER BY {date_col} DESC"

        rows = db.execute(query, (user_id,)).fetchall()
        expenses = [dict(r) for r in rows]

        if not expenses:
            db.close()
            return {"success": True, "anomalies": [], "summary": {"total_checked": 0, "flags": 0}}

        # 1. Duplicate detection — same amount + same date (or within 1 day)
        seen = {}
        for exp in expenses:
            amt = _safe_float(exp.get("amount"))
            date_str = str(exp.get("expense_date", ""))[:10]
            key = f"{amt:.2f}_{date_str}"
            if key in seen and amt > 0:
                anomalies.append({
                    "expense_id": exp["id"],
                    "type": "duplicate",
                    "severity": "warning",
                    "title": "Possible duplicate",
                    "message": f"Same amount (₹{amt:,.0f}) on same date ({date_str}) as expense #{seen[key]}",
                    "related_id": seen[key],
                })
            else:
                seen[key] = exp["id"]

        # 2. Weekend submission detection
        for exp in expenses:
            date_str = str(exp.get("expense_date", ""))[:10]
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if dt.weekday() >= 5:  # Saturday=5, Sunday=6
                    anomalies.append({
                        "expense_id": exp["id"],
                        "type": "weekend",
                        "severity": "info",
                        "title": "Weekend expense",
                        "message": f"Expense on {dt.strftime('%A')} ({date_str}) — verify if business-related",
                    })
            except (ValueError, TypeError):
                pass

        # 3. Category outlier — amount exceeds 2x category average
        if cat_col:
            cat_totals = {}
            cat_counts = {}
            for exp in expenses:
                cat = exp.get("category", "miscellaneous")
                amt = _safe_float(exp.get("amount"))
                cat_totals[cat] = cat_totals.get(cat, 0) + amt
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

            cat_avg = {cat: cat_totals[cat] / cat_counts[cat] for cat in cat_totals if cat_counts[cat] > 1}

            for exp in expenses:
                cat = exp.get("category", "miscellaneous")
                amt = _safe_float(exp.get("amount"))
                avg = cat_avg.get(cat, 0)
                if avg > 0 and amt > avg * 2 and amt > 500:
                    anomalies.append({
                        "expense_id": exp["id"],
                        "type": "outlier",
                        "severity": "warning",
                        "title": f"High for {cat}",
                        "message": f"₹{amt:,.0f} is {amt/avg:.1f}x the average ₹{avg:,.0f} for {cat}",
                    })

        # 4. Unusually round amounts (exact thousands > ₹5000)
        for exp in expenses:
            amt = _safe_float(exp.get("amount"))
            if amt >= 5000 and amt % 1000 == 0:
                anomalies.append({
                    "expense_id": exp["id"],
                    "type": "round_amount",
                    "severity": "info",
                    "title": "Perfectly round amount",
                    "message": f"₹{amt:,.0f} is an exact multiple of ₹1,000 — may need receipt verification",
                })

        # 5. Rapid-fire submissions (multiple expenses within 5 minutes by created_at)
        if "created_at" in cols:
            sorted_by_created = sorted(
                [e for e in expenses if e.get("created_at")],
                key=lambda e: str(e.get("created_at", ""))
            )
            for i in range(1, len(sorted_by_created)):
                try:
                    prev_t = datetime.fromisoformat(str(sorted_by_created[i-1]["created_at"]).replace("Z", "+00:00"))
                    curr_t = datetime.fromisoformat(str(sorted_by_created[i]["created_at"]).replace("Z", "+00:00"))
                    diff = abs((curr_t - prev_t).total_seconds())
                    if diff < 300:  # within 5 minutes
                        anomalies.append({
                            "expense_id": sorted_by_created[i]["id"],
                            "type": "rapid_fire",
                            "severity": "info",
                            "title": "Rapid submission",
                            "message": f"Submitted within {int(diff)}s of previous expense — ensure not a duplicate",
                        })
                except (ValueError, TypeError):
                    pass

        db.close()

        # Deduplicate (same expense_id + type)
        seen_keys = set()
        unique = []
        for a in anomalies:
            key = f"{a['expense_id']}_{a['type']}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(a)

        return {
            "success": True,
            "anomalies": unique,
            "summary": {
                "total_checked": len(expenses),
                "flags": len(unique),
                "by_type": _count_by_key(unique, "type"),
                "by_severity": _count_by_key(unique, "severity"),
            },
        }
    except Exception as e:
        logger.exception("Anomaly detection failed")
        return {"success": False, "error": str(e), "anomalies": []}


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _count_by_key(items, key):
    counts = {}
    for item in items:
        v = item.get(key, "unknown")
        counts[v] = counts.get(v, 0) + 1
    return counts
