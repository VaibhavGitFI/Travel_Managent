"""
TravelSync Pro — Smart Trip Recommendation Agent
Analyzes past trips + travel policy to suggest optimal hotel/flight combos
before the user searches. Uses historical data + Gemini for insights.
"""
import logging
from database import get_db
from services.gemini_service import gemini

logger = logging.getLogger(__name__)


def get_recommendations(user_id: int, destination: str, duration_days: int = 3) -> dict:
    """
    Generate smart trip recommendations based on past trips and policy.
    Returns {success, recommendations: {hotels, flights, budget_tip, packing, ai_insight}}
    """
    try:
        db = get_db()
        dest_lower = destination.lower().strip()

        # 1. Past trips to same destination
        past_trips = []
        try:
            cols = {r[1] for r in db.execute("PRAGMA table_info(travel_requests)").fetchall()}
            if "destination" in cols:
                rows = db.execute(
                    "SELECT * FROM travel_requests WHERE LOWER(destination) = ? ORDER BY created_at DESC LIMIT 5",
                    (dest_lower,),
                ).fetchall()
                past_trips = [dict(r) for r in rows]
        except Exception as e:
            logger.debug("[Recommendations] Past trips query: %s", e)

        # 2. Past expenses for this destination
        past_expenses = {}
        try:
            ecols = {r[1] for r in db.execute("PRAGMA table_info(expenses_db)").fetchall()}
            # Find trip_ids/request_ids for this destination
            trip_ids = [str(t.get("request_id", "")) for t in past_trips if t.get("request_id")]
            if trip_ids and "category" in ecols:
                id_col = "request_id" if "request_id" in ecols else "trip_id" if "trip_id" in ecols else None
                if id_col:
                    placeholders = ",".join("?" for _ in trip_ids)
                    amount_col = "amount" if "amount" in ecols else "invoice_amount"
                    rows = db.execute(
                        f"SELECT category, SUM({amount_col}) as total, COUNT(*) as cnt FROM expenses_db WHERE {id_col} IN ({placeholders}) GROUP BY category",
                        tuple(trip_ids),
                    ).fetchall()
                    past_expenses = {dict(r)["category"]: {"total": dict(r)["total"], "count": dict(r)["cnt"]} for r in rows}
        except Exception as e:
            logger.debug("[Recommendations] Past expenses query: %s", e)

        # 3. Travel policy
        policy = {}
        try:
            row = db.execute("SELECT * FROM travel_policies LIMIT 1").fetchone()
            if row:
                policy = dict(row)
        except Exception:
            pass

        # 4. Average spend from past trips
        avg_budget = 0
        if past_trips:
            budgets = [float(t.get("estimated_total", 0) or 0) for t in past_trips if t.get("estimated_total")]
            avg_budget = sum(budgets) / len(budgets) if budgets else 0

        db.close()

        # Build recommendations
        recs = {
            "destination": destination,
            "past_trip_count": len(past_trips),
            "avg_historical_budget": round(avg_budget),
        }

        # Hotel recommendation based on policy
        hotel_budget = policy.get("hotel_budget_per_night", 5000)
        recs["hotels"] = {
            "budget_per_night": hotel_budget,
            "total_hotel_budget": hotel_budget * duration_days,
            "tip": f"Policy allows ₹{hotel_budget:,}/night. For {duration_days} days = ₹{hotel_budget * duration_days:,} total."
                   + (" Consider PG/serviced apartment for long stays." if duration_days >= 5 else ""),
        }

        # Flight recommendation
        flight_class = policy.get("flight_class", "economy")
        recs["flights"] = {
            "preferred_class": flight_class,
            "tip": f"Company policy: {flight_class} class."
                   + (" Book 7+ days ahead for best fares." if duration_days <= 5 else ""),
        }

        # Budget tip from historical data
        if avg_budget > 0:
            recs["budget_tip"] = f"Past trips to {destination} averaged ₹{avg_budget:,.0f}. Plan accordingly."
        else:
            recs["budget_tip"] = f"No historical data for {destination}. Use budget forecast for estimates."

        # Expense breakdown from history
        if past_expenses:
            recs["expense_breakdown"] = {
                cat: {"avg": round(info["total"] / info["count"]), "typical_count": info["count"]}
                for cat, info in past_expenses.items()
            }

        # Gemini AI insight
        if gemini.is_available:
            try:
                context = (
                    f"Destination: {destination}, Duration: {duration_days} days, "
                    f"Past trips: {len(past_trips)}, Avg budget: ₹{avg_budget:,.0f}, "
                    f"Hotel budget/night: ₹{hotel_budget:,}, Flight class: {flight_class}"
                )
                if past_expenses:
                    context += f", Past expense categories: {', '.join(past_expenses.keys())}"

                ai_response = gemini.generate(
                    f"Given this corporate travel context: {context}\n\n"
                    "Give 3 short, actionable tips for optimizing this trip (cost, logistics, productivity). "
                    "Be specific to the destination. Each tip should be 1 sentence. Use bullet points.",
                    system_instruction="You are a corporate travel optimization assistant. Be concise and practical."
                )
                if ai_response:
                    recs["ai_insight"] = ai_response
                    recs["ai_powered"] = True
            except Exception as e:
                logger.debug("[Recommendations] Gemini insight failed: %s", e)

        recs["success"] = True
        return recs

    except Exception as e:
        logger.exception("Recommendation generation failed")
        return {"success": False, "error": str(e), "recommendations": {}}
