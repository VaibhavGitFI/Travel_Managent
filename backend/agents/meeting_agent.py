"""
TravelSync Pro — Client Meeting Agent
NOT a CRM — meetings can come from ANY source:
manual entry, email, WhatsApp, phone call, calendar import.
Provides AI-powered scheduling optimization and venue suggestions.
"""
import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db
from services.gemini_service import gemini
from services.maps_service import maps

logger = logging.getLogger(__name__)


SOURCE_LABELS = {
    "manual": {"label": "Manual Entry", "color": "#6366f1"},
    "email": {"label": "Email", "color": "#2563eb"},
    "whatsapp": {"label": "WhatsApp", "color": "#25d366"},
    "phone": {"label": "Phone Call", "color": "#f59e0b"},
    "calendar": {"label": "Calendar", "color": "#10b981"},
    "linkedin": {"label": "LinkedIn", "color": "#0077b5"},
    "other": {"label": "Other", "color": "#6b7280"},
}


def add_meeting(data: dict, user_id: int) -> dict:
    """Add a client meeting from any source."""
    required = ["client_name"]
    for field in required:
        if not data.get(field):
            return {"success": False, "error": f"'{field}' is required"}

    db = get_db()
    try:
        venue = data.get("venue") or data.get("location") or ""
        contact_number = data.get("contact_number") or data.get("contact_info") or ""
        email = data.get("email", "")
        if "@" in contact_number and not email:
            email = contact_number
            contact_number = ""

        db.execute(
            """INSERT INTO client_meetings
               (user_id, destination, client_name, company, contact_number, email,
                meeting_date, meeting_time, venue, agenda, notes, source_type, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                data.get("destination", ""),
                data["client_name"],
                data.get("company", ""),
                contact_number,
                email,
                data.get("meeting_date", ""),
                data.get("meeting_time", ""),
                venue,
                data.get("agenda", ""),
                data.get("notes", ""),
                data.get("source_type", "manual"),
                data.get("status", "scheduled"),
            )
        )
        db.commit()
        meeting_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.close()
        return {"success": True, "meeting_id": meeting_id,
                "message": f"Meeting with {data['client_name']} scheduled"}
    except Exception as e:
        db.close()
        return {"success": False, "error": str(e)}


def get_all_meetings(user_id: int, destination: str = None,
                     meeting_date: str = None) -> list:
    """Fetch meetings with optional filters."""
    db = get_db()
    try:
        query = "SELECT * FROM client_meetings WHERE user_id=?"
        params = [user_id]
        if destination:
            query += " AND LOWER(destination) LIKE ?"
            params.append(f"%{destination.lower()}%")
        if meeting_date:
            query += " AND meeting_date=?"
            params.append(meeting_date)
        query += " ORDER BY meeting_date, meeting_time"
        rows = db.execute(query, params).fetchall()
        meetings = []
        for row in rows:
            m = dict(zip(
                ["id", "user_id", "destination", "client_name", "company",
                 "contact_number", "email", "meeting_date", "meeting_time",
                 "venue", "agenda", "notes", "source_type", "status", "created_at", "updated_at"],
                row
            ))
            m["location"] = m.get("venue", "")
            m["duration_minutes"] = 60
            m["contact_info"] = m.get("contact_number") or m.get("email") or ""
            m["source_info"] = SOURCE_LABELS.get(m.get("source_type", "manual"),
                                                  SOURCE_LABELS["other"])
            meetings.append(m)
        db.close()
        return meetings
    except Exception as e:
        db.close()
        logger.warning("[Meeting] Get error: %s", e)
        return []


def get_meetings_for_destination(destination: str, user_id: int,
                                  travel_dates: str = "") -> dict:
    """Get meetings + AI-generated schedule optimization for a destination."""
    meetings = get_all_meetings(user_id, destination=destination)

    # AI-optimize schedule if Gemini available
    schedule_suggestion = None
    if meetings and gemini.is_available:
        schedule_suggestion = optimize_meeting_schedule(meetings, destination)

    return {
        "success": True,
        "destination": destination,
        "meetings": meetings,
        "total": len(meetings),
        "schedule_suggestion": schedule_suggestion,
        "source_breakdown": _get_source_breakdown(meetings),
    }


def update_meeting(meeting_id: int, data: dict, user_id: int) -> dict:
    """Update an existing meeting."""
    allowed = ["client_name", "company", "contact_number", "email", "meeting_date",
               "meeting_time", "venue", "agenda", "notes", "source_type", "status", "location", "contact_info"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return {"success": False, "error": "No valid fields to update"}

    if "location" in updates:
        if "venue" not in updates:
            updates["venue"] = updates["location"]
        updates.pop("location", None)
    if "contact_info" in updates:
        contact_info = updates.pop("contact_info")
        if "@" in str(contact_info):
            updates["email"] = contact_info
        else:
            updates["contact_number"] = contact_info

    db = get_db()
    try:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        set_clause += ", updated_at=CURRENT_TIMESTAMP"
        values = list(updates.values()) + [meeting_id, user_id]
        db.execute(f"UPDATE client_meetings SET {set_clause} WHERE id=? AND user_id=?", values)
        db.commit()
        db.close()
        return {"success": True, "message": "Meeting updated"}
    except Exception as e:
        db.close()
        return {"success": False, "error": str(e)}


def delete_meeting(meeting_id: int, user_id: int) -> dict:
    """Delete a meeting."""
    db = get_db()
    try:
        db.execute("DELETE FROM client_meetings WHERE id=? AND user_id=?",
                   (meeting_id, user_id))
        db.commit()
        db.close()
        return {"success": True, "message": "Meeting deleted"}
    except Exception as e:
        db.close()
        return {"success": False, "error": str(e)}


def suggest_nearby_venues(destination: str, client_locations: list) -> dict:
    """
    Suggest meeting venues near client offices using Google Maps.
    Finds hotels with conference facilities, coworking spaces, cafes.
    """
    venues = {"hotels_conference": [], "coworking": [], "cafes": []}

    if not client_locations:
        coord = maps.geocode(destination)
    else:
        coord = maps.geocode(client_locations[0])

    location = {"lat": coord["lat"], "lng": coord["lng"]}

    # Search for different venue types
    hotel_venues = maps.nearby_places(location, "lodging", radius=3000, keyword="conference")
    coworking = maps.nearby_places(location, "establishment", radius=2000, keyword="coworking space")
    cafes = maps.nearby_places(location, "cafe", radius=1000)

    if hotel_venues:
        venues["hotels_conference"] = [
            {"name": p["name"], "vicinity": p.get("vicinity"),
             "rating": p.get("rating"), "source": "google_maps"}
            for p in hotel_venues[:5]
        ]
    if coworking:
        venues["coworking"] = [
            {"name": p["name"], "vicinity": p.get("vicinity"),
             "rating": p.get("rating"), "source": "google_maps"}
            for p in coworking[:5]
        ]
    if cafes:
        venues["cafes"] = [
            {"name": p["name"], "vicinity": p.get("vicinity"),
             "rating": p.get("rating"), "source": "google_maps"}
            for p in cafes[:5]
        ]

    # Fallback note if Maps not configured
    if not maps.configured:
        venues["note"] = "Set GOOGLE_MAPS_API_KEY for live venue suggestions near client offices"

    return {"success": True, "destination": destination, "venues": venues}


def optimize_meeting_schedule(meetings: list, destination: str) -> dict:
    """Use Gemini to create an optimized day-by-day meeting schedule."""
    if not gemini.is_available or not meetings:
        return None

    meetings_text = "\n".join([
        f"- {m.get('client_name')} at {m.get('company', 'N/A')}, "
        f"Venue: {m.get('venue', 'TBD')}, Date: {m.get('meeting_date', 'TBD')}, "
        f"Time: {m.get('meeting_time', 'TBD')}"
        for m in meetings
    ])

    prompt = f"""
You are a corporate travel scheduler. Optimize this meeting schedule in {destination}:

{meetings_text}

Create a day-by-day schedule minimizing travel time between venues.
Return JSON:
{{
  "optimized_schedule": [
    {{
      "day": 1,
      "date": "YYYY-MM-DD or Day 1",
      "meetings": [
        {{
          "time": "HH:MM",
          "client": "Name",
          "company": "Company",
          "venue": "Venue",
          "estimated_duration": "1 hour",
          "travel_from_previous": "15 mins",
          "notes": "tip"
        }}
      ],
      "day_summary": "brief summary"
    }}
  ],
  "total_travel_time": "X hours",
  "efficiency_tips": ["tip1", "tip2"]
}}
"""
    return gemini.generate_json(prompt)


def _get_source_breakdown(meetings: list) -> dict:
    """Count meetings by source type."""
    breakdown = {}
    for m in meetings:
        source = m.get("source_type", "manual")
        breakdown[source] = breakdown.get(source, 0) + 1
    return breakdown
