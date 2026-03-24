"""
TravelSync Pro — Analytics Agent
Schema-tolerant analytics for dashboard, spend, and compliance views.
"""
import json
from datetime import datetime, timedelta
from database import get_db
from services.currency_service import currency


def _table_columns(db, table: str) -> set[str]:
    try:
        rows = db.execute(f"PRAGMA table_info({table})").fetchall()
        if rows:
            return {r[1] if not isinstance(r, dict) else r.get("name", "") for r in rows}
    except Exception:
        try:
            db.commit()
        except Exception:
            pass
    try:
        rows = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)).fetchall()
        return {r["column_name"] if isinstance(r, dict) else r[0] for r in rows}
    except Exception:
        try:
            db.commit()
        except Exception:
            pass
    return {"id", "user_id", "request_id", "trip_id", "category", "description",
            "invoice_amount", "date", "verification_status", "status", "stage",
            "destination", "origin", "start_date", "end_date", "estimated_total",
            "budget_inr", "purpose", "created_at"}


def _expense_amount_expr(cols: set[str], prefix: str = "") -> str:
    p = f"{prefix}." if prefix else ""
    candidates = []
    for col in ("verified_amount", "invoice_amount", "amount", "payment_amount"):
        if col in cols:
            candidates.append(f"{p}{col}")
    if not candidates:
        return "0"
    return f"COALESCE({', '.join(candidates)}, 0)"


def _format_amount(amount: float, currency_code: str = "INR") -> str:
    if currency_code == "INR":
        return currency.format_inr(amount)
    formatter = getattr(currency, "format_amount", None)
    if callable(formatter):
        return formatter(amount, currency_code)
    return f"{currency_code} {amount:,.2f}"


def _compliance_counts(db, request_cols: set[str], user_id: int = None) -> dict:
    counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "unknown": 0}
    where = []
    params = []
    if user_id and "user_id" in request_cols:
        where.append("user_id = ?")
        params.append(user_id)
    where_clause = (" WHERE " + " AND ".join(where)) if where else ""

    if "policy_compliance" in request_cols:
        rows = db.execute(
            f"SELECT policy_compliance, COUNT(*) FROM travel_requests{where_clause} GROUP BY policy_compliance",
            tuple(params),
        ).fetchall()
        for status, cnt in rows:
            key = (status or "unknown").lower()
            if key in counts:
                counts[key] += int(cnt)
            else:
                counts["unknown"] += int(cnt)
        return counts

    if "policy_compliance_json" in request_cols:
        rows = db.execute(
            f"SELECT policy_compliance_json FROM travel_requests{where_clause}",
            tuple(params),
        ).fetchall()
        for r in rows:
            raw = r[0] if not isinstance(r, dict) else r.get("policy_compliance_json")
            if not raw:
                counts["unknown"] += 1
                continue
            try:
                parsed = json.loads(raw)
                key = (parsed.get("overall_status") or "unknown").lower()
                if key in counts:
                    counts[key] += 1
                else:
                    counts["unknown"] += 1
            except (TypeError, json.JSONDecodeError):
                counts["unknown"] += 1
        return counts

    total = db.execute(
        f"SELECT COUNT(*) FROM travel_requests{where_clause}",
        tuple(params),
    ).fetchone()[0]
    counts["unknown"] = int(total or 0)
    return counts


def get_dashboard_stats(user_id: int = None) -> dict:
    """Dashboard KPI summary."""
    db = get_db()
    try:
        request_cols = _table_columns(db, "travel_requests")
        expense_cols = _table_columns(db, "expenses_db")

        req_where = []
        req_params = []
        exp_where = []
        exp_params = []

        if user_id and "user_id" in request_cols:
            req_where.append("user_id = ?")
            req_params.append(user_id)
        if user_id and "user_id" in expense_cols:
            exp_where.append("user_id = ?")
            exp_params.append(user_id)

        req_where_clause = (" WHERE " + " AND ".join(req_where)) if req_where else ""
        exp_where_clause = (" WHERE " + " AND ".join(exp_where)) if exp_where else ""

        total_trips = db.execute(
            f"SELECT COUNT(*) FROM travel_requests{req_where_clause}",
            tuple(req_params),
        ).fetchone()[0]

        pending_approvals = db.execute(
            "SELECT COUNT(*) FROM approvals WHERE status = 'pending'"
        ).fetchone()[0]

        amount_expr = _expense_amount_expr(expense_cols)
        total_expenses = float(db.execute(
            f"SELECT COALESCE(SUM({amount_expr}), 0) FROM expenses_db{exp_where_clause}",
            tuple(exp_params),
        ).fetchone()[0] or 0)

        status_col = "status" if "status" in request_cols else None
        active_requests = 0
        if status_col:
            active_statuses = ("draft", "submitted", "pending_approval", "pending", "in_progress")
            placeholders = ",".join("?" for _ in active_statuses)
            active_requests = db.execute(
                f"SELECT COUNT(*) FROM travel_requests{req_where_clause}"
                f"{' AND ' if req_where_clause else ' WHERE '}status IN ({placeholders})",
                tuple(req_params) + active_statuses,
            ).fetchone()[0]

        today = datetime.now().strftime("%Y-%m-%d")
        upcoming_trips = 0
        if "start_date" in request_cols:
            upcoming_trips = db.execute(
                f"SELECT COUNT(*) FROM travel_requests{req_where_clause}"
                f"{' AND ' if req_where_clause else ' WHERE '}start_date >= ?",
                tuple(req_params) + (today,),
            ).fetchone()[0]

        team_size = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        cities_visited = 0
        if "destination" in request_cols:
            cities_visited = db.execute(
                f"SELECT COUNT(DISTINCT destination) FROM travel_requests{req_where_clause}",
                tuple(req_params),
            ).fetchone()[0]

        compliance = _compliance_counts(db, request_cols, user_id=user_id)
        total_requests = max(sum(compliance.values()), 1)
        compliance_score = round((compliance["compliant"] / total_requests) * 100)

        payload = {
            "total_trips": int(total_trips or 0),
            "total_expenses": total_expenses,
            "pending_approvals": int(pending_approvals or 0),
            "compliance_score": int(compliance_score),
            "upcoming_trips": int(upcoming_trips or 0),
            "active_requests": int(active_requests or 0),
            "team_size": int(team_size or 0),
            "cities_visited": int(cities_visited or 0),
            "success": True,
        }
        payload["stats"] = payload.copy()
        return payload
    except Exception as e:
        return {"success": False, "error": str(e), "stats": {}}
    finally:
        db.close()


def get_spend_analysis() -> dict:
    """Spend trend + category + destination breakdown."""
    db = get_db()
    try:
        expense_cols = _table_columns(db, "expenses_db")
        amount_expr = _expense_amount_expr(expense_cols)
        date_col = "created_at" if "created_at" in expense_cols else "expense_date" if "expense_date" in expense_cols else "date"

        monthly_trend = []
        for i in range(5, -1, -1):
            month_dt = datetime.now().replace(day=1) - timedelta(days=i * 30)
            month_key = month_dt.strftime("%Y-%m")
            month_label = month_dt.strftime("%b %Y")
            amount = float(db.execute(
                f"""SELECT COALESCE(SUM({amount_expr}), 0)
                    FROM expenses_db
                    WHERE strftime('%Y-%m', {date_col}) = ?""",
                (month_key,),
            ).fetchone()[0] or 0)
            monthly_trend.append({
                "month": month_key,
                "label": month_label,
                "amount": amount,
                "total": amount,
                "formatted": _format_amount(amount),
            })

        cat_col = "category" if "category" in expense_cols else None
        category_breakdown = []
        if cat_col:
            rows = db.execute(
                f"SELECT {cat_col}, COALESCE(SUM({amount_expr}), 0) FROM expenses_db GROUP BY {cat_col} ORDER BY 2 DESC"
            ).fetchall()
            for row in rows:
                name = row[0] or "miscellaneous"
                amount = float(row[1] or 0)
                category_breakdown.append({
                    "category": name,
                    "name": name,
                    "amount": amount,
                    "total": amount,
                    "formatted": _format_amount(amount),
                })

        request_cols = _table_columns(db, "travel_requests")
        top_cities = []
        if "destination" in request_cols:
            rows = db.execute(
                "SELECT destination, COUNT(*) FROM travel_requests GROUP BY destination ORDER BY 2 DESC LIMIT 8"
            ).fetchall()
            top_cities = [
                {"city": r[0], "name": r[0], "trips": int(r[1]), "count": int(r[1])}
                for r in rows if r[0]
            ]

        total_spend = float(sum(i["amount"] for i in category_breakdown))
        return {
            "success": True,
            "monthly_trend": monthly_trend,
            "category_breakdown": category_breakdown,
            "by_category": category_breakdown,
            "top_cities": top_cities,
            "total_spend": total_spend,
            "total_spend_formatted": _format_amount(total_spend),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def get_budget_tracking(request_id: str = None) -> dict:
    """Budget view for a request or overall month."""
    db = get_db()
    try:
        request_cols = _table_columns(db, "travel_requests")
        expense_cols = _table_columns(db, "expenses_db")
        amount_expr = _expense_amount_expr(expense_cols)

        if request_id:
            key_col = "request_id" if "request_id" in request_cols else "id"
            req = db.execute(
                f"SELECT * FROM travel_requests WHERE {key_col} = ?",
                (request_id,),
            ).fetchone()
            if not req:
                return {"success": False, "error": "Request not found"}
            req_dict = dict(req)
            budget = float(req_dict.get("estimated_total") or req_dict.get("budget_inr") or 0)

            filters = []
            params = []
            if "request_id" in expense_cols:
                filters.append("request_id = ?")
                params.append(request_id)
            if "trip_id" in expense_cols:
                filters.append("trip_id = ?")
                params.append(request_id)
            where = " OR ".join(filters) if filters else "1=0"
            actual = float(db.execute(
                f"SELECT COALESCE(SUM({amount_expr}), 0) FROM expenses_db WHERE {where}",
                tuple(params),
            ).fetchone()[0] or 0)

            return {
                "success": True,
                "request_id": request_id,
                "budget": budget,
                "actual": actual,
                "remaining": budget - actual,
                "utilization_pct": round((actual / budget * 100) if budget else 0),
                "budget_formatted": _format_amount(budget),
                "actual_formatted": _format_amount(actual),
                "status": "over_budget" if actual > budget else "on_track",
            }

        policy = _get_policy()
        monthly_budget = float(policy.get("monthly_budget_inr") or 500000)
        month_key = datetime.now().strftime("%Y-%m")
        date_col = "created_at" if "created_at" in expense_cols else "expense_date" if "expense_date" in expense_cols else "date"
        actual_month = float(db.execute(
            f"""SELECT COALESCE(SUM({amount_expr}), 0)
                FROM expenses_db
                WHERE strftime('%Y-%m', {date_col}) = ?""",
            (month_key,),
        ).fetchone()[0] or 0)

        return {
            "success": True,
            "monthly_budget": monthly_budget,
            "actual_month": actual_month,
            "remaining": monthly_budget - actual_month,
            "utilization_pct": round((actual_month / monthly_budget * 100) if monthly_budget else 0),
            "budget_formatted": _format_amount(monthly_budget),
            "actual_formatted": _format_amount(actual_month),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def get_policy_compliance_scorecard() -> dict:
    """Policy + expense verification scorecard."""
    db = get_db()
    try:
        request_cols = _table_columns(db, "travel_requests")
        expense_cols = _table_columns(db, "expenses_db")

        compliance = _compliance_counts(db, request_cols)
        total_requests = sum(compliance.values())
        compliance_rate = round((compliance["compliant"] / total_requests * 100) if total_requests else 0)

        if "verification_status" in expense_cols:
            total_exp = db.execute("SELECT COUNT(*) FROM expenses_db").fetchone()[0]
            verified_exp = db.execute(
                "SELECT COUNT(*) FROM expenses_db WHERE verification_status = 'verified'"
            ).fetchone()[0]
        elif "status" in expense_cols:
            total_exp = db.execute("SELECT COUNT(*) FROM expenses_db").fetchone()[0]
            verified_exp = db.execute(
                "SELECT COUNT(*) FROM expenses_db WHERE status IN ('approved', 'verified', 'reimbursed')"
            ).fetchone()[0]
        else:
            total_exp = 0
            verified_exp = 0

        expense_verification_rate = round((verified_exp / total_exp * 100) if total_exp else 0)
        overall_score = round((compliance_rate + expense_verification_rate) / 2)

        checks = [
            {"name": "Policy compliant requests >= 70%", "passed": compliance_rate >= 70},
            {"name": "Expense verification >= 80%", "passed": expense_verification_rate >= 80},
            {"name": "No non-compliant backlog spike", "passed": compliance["non_compliant"] <= max(1, compliance["compliant"])},
        ]

        return {
            "success": True,
            "overall_score": overall_score,
            "compliance_rate": compliance_rate,
            "expense_verification_rate": expense_verification_rate,
            "requests": {
                "total": total_requests,
                "compliant": compliance["compliant"],
                "partial": compliance["partial"],
                "non_compliant": compliance["non_compliant"],
                "unknown": compliance["unknown"],
            },
            "expenses": {
                "total": total_exp,
                "verified": verified_exp,
                "pending": max(total_exp - verified_exp, 0),
            },
            "checks": checks,
            "status": "excellent" if overall_score >= 80 else "good" if overall_score >= 60 else "needs_improvement",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def get_carbon_analytics(user_id: int = None, role: str = "employee") -> dict:
    """
    Compute carbon footprint analytics.
    Returns monthly CO₂ trend, department comparison, and greener-alternative suggestions.
    """
    from agents.travel_mode_agent import calculate_carbon
    from services.maps_service import maps

    db = get_db()
    try:
        # Fetch completed/in_progress trips
        if role in ("admin", "manager"):
            rows = db.execute(
                """SELECT tr.request_id, tr.origin, tr.destination, tr.trip_type,
                          tr.duration_days, tr.num_travelers, tr.start_date,
                          u.department
                   FROM travel_requests tr
                   LEFT JOIN users u ON u.id = tr.user_id
                   WHERE tr.status IN ('completed', 'in_progress', 'approved', 'booked')
                   ORDER BY tr.start_date DESC LIMIT 100"""
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT tr.request_id, tr.origin, tr.destination, tr.trip_type,
                          tr.duration_days, tr.num_travelers, tr.start_date,
                          u.department
                   FROM travel_requests tr
                   LEFT JOIN users u ON u.id = tr.user_id
                   WHERE tr.user_id = ? AND tr.status IN ('completed', 'in_progress', 'approved', 'booked')
                   ORDER BY tr.start_date DESC LIMIT 50""",
                (user_id,)
            ).fetchall()
    finally:
        db.close()

    # CO₂ per trip
    monthly: dict[str, float] = {}
    dept_totals: dict[str, float] = {}
    trip_carbon_list = []
    total_co2 = 0.0
    total_savings_possible = 0.0
    greener_suggestions = []

    for row in rows:
        r = dict(row)
        origin = r.get("origin") or ""
        dest = r.get("destination") or ""
        trip_type = r.get("trip_type") or "domestic"
        n = max(1, int(r.get("num_travelers") or 1))

        # Determine distance
        dist_km = 0.0
        if origin and dest:
            try:
                dist_km = maps.get_distance_km(origin, dest) or 0.0
            except Exception:
                pass
        if not dist_km:
            # Rough fallback: domestic ~700 km avg, international ~5000 km avg
            dist_km = 5000.0 if trip_type == "international" else 700.0

        mode = "flight" if (trip_type == "international" or dist_km > 400) else "cab"

        carbon = calculate_carbon(dist_km, mode, n)
        co2 = carbon["co2_kg"]
        total_co2 += co2

        # Monthly bucket (YYYY-MM)
        month = (r.get("start_date") or "")[:7]
        if month:
            monthly[month] = monthly.get(month, 0.0) + co2

        # Department bucket
        dept = r.get("department") or "General"
        dept_totals[dept] = dept_totals.get(dept, 0.0) + co2

        trip_carbon_list.append({
            "request_id": r.get("request_id"),
            "route": f"{origin} → {dest}",
            "co2_kg": co2,
            "mode": mode,
            "distance_km": carbon["distance_km"],
            "greener_alt": carbon.get("greener_alt"),
            "saving_kg": carbon.get("greener_saving_kg"),
        })

        if carbon.get("greener_saving_kg") and carbon["greener_saving_kg"] > 5:
            total_savings_possible += carbon["greener_saving_kg"]
            if len(greener_suggestions) < 3:
                greener_suggestions.append({
                    "route": f"{origin} → {dest}",
                    "current_mode": mode,
                    "suggested_mode": carbon["greener_alt"],
                    "saving_kg": round(carbon["greener_saving_kg"], 1),
                    "saving_pct": round(carbon["greener_saving_kg"] / co2 * 100, 0) if co2 else 0,
                })

    # Sort monthly trend
    monthly_trend = [
        {"month": m, "co2_kg": round(v, 2)}
        for m, v in sorted(monthly.items())
    ]

    # Department comparison
    dept_comparison = [
        {"department": d, "co2_kg": round(v, 2)}
        for d, v in sorted(dept_totals.items(), key=lambda x: -x[1])
    ]

    return {
        "success": True,
        "total_co2_kg": round(total_co2, 2),
        "total_trips_analyzed": len(rows),
        "trees_to_offset": round(total_co2 / 21.77, 1),
        "potential_savings_kg": round(total_savings_possible, 2),
        "monthly_trend": monthly_trend,
        "department_comparison": dept_comparison,
        "top_trips": sorted(trip_carbon_list, key=lambda x: -x["co2_kg"])[:10],
        "greener_suggestions": greener_suggestions,
    }


def _get_policy() -> dict:
    """Fetch active policy when present, else first row, else defaults."""
    db = get_db()
    try:
        cols = _table_columns(db, "travel_policies")
        if "active" in cols:
            row = db.execute("SELECT * FROM travel_policies WHERE active = 1 LIMIT 1").fetchone()
        else:
            row = db.execute("SELECT * FROM travel_policies ORDER BY id LIMIT 1").fetchone()
        if row:
            return dict(row)
    except Exception:
        return {}
    finally:
        db.close()
    return {}
