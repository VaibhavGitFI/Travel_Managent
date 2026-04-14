"""
TravelSync Pro — Hotel & Accommodation Agent
- Real hotels via Google Places API
- PG / Serviced Apartments for stays >= 5 days via Google Places
- Google Maps proximity filtering for rural client sites
- Gemini AI for personalized recommendations
"""
import sys
import os
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from services.maps_service import maps
from services.gemini_service import gemini


# ── Curated fallback data (used only when Google Maps API key not set) ────────

_FALLBACK_HOTELS = [
    {"name": "Taj Hotels", "rating": 4.7, "price_per_night": 12000, "amenities": ["WiFi", "Pool", "Spa", "Restaurant", "AC"]},
    {"name": "Oberoi Hotels", "rating": 4.8, "price_per_night": 15000, "amenities": ["WiFi", "Pool", "Gym", "Restaurant", "AC"]},
    {"name": "ITC Hotels", "rating": 4.6, "price_per_night": 10000, "amenities": ["WiFi", "Restaurant", "Gym", "AC"]},
    {"name": "Marriott Hotel", "rating": 4.5, "price_per_night": 9000, "amenities": ["WiFi", "Pool", "Restaurant", "AC", "Room Service"]},
    {"name": "Hyatt Regency", "rating": 4.5, "price_per_night": 8500, "amenities": ["WiFi", "Pool", "Gym", "Restaurant", "AC"]},
    {"name": "Novotel", "rating": 4.3, "price_per_night": 7000, "amenities": ["WiFi", "Restaurant", "Gym", "AC"]},
    {"name": "Lemon Tree Hotel", "rating": 4.1, "price_per_night": 4500, "amenities": ["WiFi", "Restaurant", "AC"]},
    {"name": "Ibis Hotel", "rating": 4.0, "price_per_night": 3500, "amenities": ["WiFi", "Restaurant", "AC"]},
    {"name": "OYO Rooms Premium", "rating": 3.8, "price_per_night": 2000, "amenities": ["WiFi", "AC"]},
]

_FALLBACK_PG = [
    {"name": "Stanza Living", "type": "Coliving", "monthly_rent": 18000, "amenities": ["WiFi", "Meals", "AC", "Laundry", "Security"]},
    {"name": "NestAway Homes", "type": "Managed PG", "monthly_rent": 14000, "amenities": ["WiFi", "AC", "Security"]},
    {"name": "OYO Life", "type": "Managed PG", "monthly_rent": 12000, "amenities": ["WiFi", "AC", "Meals"]},
    {"name": "CoHo Coliving", "type": "Coliving", "monthly_rent": 20000, "amenities": ["WiFi", "Meals", "AC", "Gym", "Community"]},
    {"name": "Colive Spaces", "type": "Coliving", "monthly_rent": 16000, "amenities": ["WiFi", "AC", "Laundry", "Security"]},
    {"name": "Zolo Stays", "type": "Managed PG", "monthly_rent": 11000, "amenities": ["WiFi", "AC", "Meals"]},
]

_PG_BOOKING_URLS = {
    "Stanza Living": "https://www.stanzaliving.com",
    "NestAway Homes": "https://www.nestaway.com",
    "OYO Life": "https://www.oyorooms.com/long-term-stays",
    "CoHo Coliving": "https://www.coho.in",
    "Colive Spaces": "https://www.colive.com",
    "Zolo Stays": "https://www.zolostays.com",
}


def search_hotels(data: dict) -> dict:
    """
    Main hotel search entry point.
    Returns hotels + PG options (if stay >= 5 days) + Gemini recommendation.
    """
    destination = data.get("destination", "")
    duration_days = int(data.get("duration_days", 3))
    budget = data.get("budget", "moderate")
    is_rural = data.get("is_rural", False)
    require_veg = data.get("require_veg", False)
    client_address = data.get("client_address", "")
    client_place_id = data.get("client_place_id", "")
    num_travelers = int(data.get("num_travelers", 1))

    # Resolve dates
    start_date = data.get("start_date") or datetime.now().strftime("%Y-%m-%d")
    try:
        check_in = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        check_in = datetime.now()
    check_out = check_in + timedelta(days=duration_days)
    check_in_str = check_in.strftime("%Y-%m-%d")
    check_out_str = check_out.strftime("%Y-%m-%d")

    # Budget caps per night (INR)
    BUDGET_CAPS = {"budget": 4000, "moderate": 10000, "premium": 25000, "luxury": None}
    budget_max = BUDGET_CAPS.get(budget)

    # --- Resolve meeting location coordinates early ---
    # When the user picks a specific meeting spot we anchor the hotel search
    # to that location so the Places radius captures hotels near there, not
    # just near the city center.
    meeting_coords = None
    if client_address and maps.configured:
        if client_place_id:
            meeting_coords = maps.geocode_by_place_id(client_place_id)
        else:
            meeting_coords = maps.geocode(
                client_address,
                components=f"locality:{destination}" if destination else None,
            )
        # If resolution failed (fallback), discard so we don't bias the search wrongly
        if meeting_coords and meeting_coords.get("source") == "fallback":
            meeting_coords = None

    # Use Google Places for live hotel data; fall back to curated list.
    # Pass meeting_coords so the Places search is anchored to the meeting area.
    if maps.configured:
        hotels = maps.search_hotels(
            destination, budget_max=budget_max, limit=8,
            coords=meeting_coords,
        )
    else:
        hotels = []

    if not hotels:
        hotels = _fallback_hotels(destination, budget_max, limit=8)

    # Sort by proximity — meeting location is always within the destination city.
    # Prefer place_id-based geocoding for the most precise pin.
    # For rural sites use a strict 2 km radius filter instead.
    if meeting_coords:
        if is_rural:
            hotels = _filter_by_proximity(hotels, client_address, max_km=2.0)
        else:
            # Coords already resolved — pass them directly so _soft_sort doesn't re-geocode
            hotels = _soft_sort_by_coords(hotels, meeting_coords, destination)
    elif client_address and maps.configured:
        if is_rural:
            hotels = _filter_by_proximity(hotels, client_address, max_km=2.0)
        else:
            hotels = _soft_sort_by_proximity(
                hotels, client_address, destination, client_place_id=client_place_id)
    elif is_rural and client_address:
        for h in hotels:
            h["rural_note"] = ("Hotels near client site preferred (2 km radius). "
                               "Set GOOGLE_MAPS_API_KEY for precise filtering.")

    # Vegetarian filter
    if require_veg:
        hotels = _mark_veg_friendly(hotels, destination)

    # Add booking links, total cost
    for hotel in hotels:
        hotel["total_cost"] = round(hotel.get("price_per_night", 0) * duration_days * num_travelers)
        hotel["stay_duration"] = duration_days
        if not hotel.get("booking_link"):
            hotel["booking_link"] = _build_booking_link(
                hotel.get("name", ""), destination, check_in_str, check_out_str)

    # PG / long-stay options for 5+ days — pass meeting coords so PGs
    # are also anchored near the meeting location, not just city centre.
    pg_options = []
    if duration_days >= 5:
        pg_options = search_pg_options({
            "destination": destination,
            "duration_days": duration_days,
            "budget": budget,
            "meeting_coords": meeting_coords,   # None when no meeting pin set
        })

    # AI recommendation
    recommendation = _get_ai_recommendation(
        destination, budget, duration_days, hotels[:3], require_veg)

    return {
        "success": True,
        "destination": destination,
        "check_in": check_in_str,
        "check_out": check_out_str,
        "duration_days": duration_days,
        "hotels": hotels[:8],
        "pg_options": pg_options,
        "show_pg_options": duration_days >= 5,
        "veg_filter_applied": require_veg,
        "is_rural": is_rural,
        "recommendation": recommendation,
        "data_source": hotels[0].get("source", "fallback") if hotels else "fallback",
    }


def search_pg_options(data: dict) -> list:
    """Search PG / serviced apartment options for long stays.

    data may include:
      meeting_coords: {lat, lng} — when set, search is anchored to the meeting
                                   location pin so PGs near that area surface first.
    """
    destination = data.get("destination", "")
    duration_days = int(data.get("duration_days", 7))
    budget = data.get("budget", "moderate")
    meeting_coords = data.get("meeting_coords")   # {lat, lng} or None

    MONTHLY_BUDGET_CAPS = {"budget": 15000, "moderate": 30000, "premium": 60000, "luxury": None}
    budget_monthly = MONTHLY_BUDGET_CAPS.get(budget)

    # Try real data via Google Places first, anchored to meeting location when available
    options = []
    if maps.configured:
        options = maps.search_pg_options(
            destination,
            budget_monthly=budget_monthly,
            limit=6,
            coords=meeting_coords,
        )

    # Fall back to curated list
    if not options:
        options = _fallback_pg_options(destination, budget_monthly)

    for opt in options:
        opt["type_label"] = _pg_type_label(opt.get("type", ""))
        if not opt.get("booking_url"):
            name = opt.get("name", "")
            opt["booking_url"] = _PG_BOOKING_URLS.get(name, _pg_booking_url_by_type(opt.get("type", ""), destination))
        opt.setdefault("amenities", ["WiFi", "AC", "Security"])

    return options


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fallback_hotels(destination: str, budget_max: int, limit: int = 8) -> list:
    """Return curated hotel list for when Google Places is unavailable."""
    hotels = []
    for h in _FALLBACK_HOTELS:
        if budget_max and h["price_per_night"] > budget_max:
            continue
        hotels.append({
            **h,
            "area": destination,
            "price": h["price_per_night"],
            "currency": "INR",
            "source": "fallback",
        })
    random.shuffle(hotels)
    return hotels[:limit]


def _fallback_pg_options(destination: str, budget_monthly: int) -> list:
    """Return curated PG list for when Google Places is unavailable."""
    options = []
    for pg in _FALLBACK_PG:
        if budget_monthly and pg["monthly_rent"] > budget_monthly:
            continue
        options.append({**pg, "area": destination, "source": "fallback"})
    return options


def _soft_sort_by_coords(hotels: list, meeting_coords: dict, destination: str) -> list:
    """Sort hotels by distance from pre-resolved meeting coordinates.
    Skips geocoding since coords are already known — avoids the extra API call."""
    try:
        origin = f"{meeting_coords['lat']},{meeting_coords['lng']}"
        for h in hotels:
            if h.get("latitude") and h.get("longitude"):
                dest_str = f"{h['latitude']},{h['longitude']}"
            else:
                dest_str = f"{h.get('name', '')}, {h.get('area', destination)}, {destination}"
            try:
                dist = maps.get_distance_km(origin, dest_str)
                h["distance_from_meeting_km"] = round(dist, 1)
                h["distance_from_meeting"] = f"{dist:.1f} km from meeting location"
            except Exception:
                h["distance_from_meeting_km"] = 999
        hotels.sort(key=lambda h: h.get("distance_from_meeting_km", 999))
    except Exception:
        pass
    return hotels


def _soft_sort_by_proximity(hotels: list, client_address: str, destination: str,
                             client_place_id: str = None) -> list:
    """Sort hotels by distance from client_address (same city — best-effort).

    When client_place_id is provided (from Google Places autocomplete), we use
    geocode/json?place_id=XXX for the exact confirmed Google pin rather than
    ambiguous text geocoding.
    """
    try:
        # Prefer place_id geocoding when available — exact confirmed Google pin
        if client_place_id and maps.configured:
            client_coords = maps.geocode_by_place_id(client_place_id)
        else:
            # Component-filtered geocoding: pins the address to the destination city
            # e.g. "GTP Colony" + components="locality:Dhule" → precise Dhule result
            # This prevents matching a same-named area in another city.
            components = f"locality:{destination}" if destination else None
            client_coords = maps.geocode(client_address, components=components)

        if client_coords.get("source") == "fallback" or not client_coords.get("lat"):
            return hotels

        origin = f"{client_coords['lat']},{client_coords['lng']}"
        for h in hotels:
            # Prefer lat/lng already stored on the hotel (from Places API); fall back to name lookup
            if h.get("latitude") and h.get("longitude"):
                dest_str = f"{h['latitude']},{h['longitude']}"
            else:
                dest_str = f"{h.get('name', '')}, {h.get('area', destination)}, {destination}"
            try:
                dist = maps.get_distance_km(origin, dest_str)
                h["distance_from_meeting_km"] = round(dist, 1)
                h["distance_from_meeting"] = f"{dist:.1f} km from meeting location"
            except Exception:
                h["distance_from_meeting_km"] = 999
        hotels.sort(key=lambda h: h.get("distance_from_meeting_km", 999))
    except Exception:
        pass
    return hotels


def _filter_by_proximity(hotels: list, client_address: str, max_km: float = 2.0) -> list:
    """Filter hotels to those within max_km of client address."""
    client_coords = maps.geocode(client_address)
    if client_coords.get("source") == "fallback":
        return hotels

    filtered = []
    for hotel in hotels:
        hotel_loc = f"{hotel.get('name', '')}, {hotel.get('area', client_address)}"
        try:
            dist = maps.get_distance_km(
                f"{client_coords['lat']},{client_coords['lng']}", hotel_loc)
            hotel["distance_from_client_km"] = round(dist, 1)
            hotel["distance_from_client"] = f"{dist:.1f} km from client site"
            if dist <= max_km:
                filtered.append(hotel)
        except Exception:
            filtered.append(hotel)

    return filtered if filtered else hotels


def _mark_veg_friendly(hotels: list, destination: str) -> list:
    """Mark hotels with vegetarian restaurant availability."""
    dest_lower = destination.lower()
    veg_cities = ["ahmedabad", "jaipur", "surat", "indore", "varanasi",
                  "amritsar", "rajkot", "udaipur", "jodhpur"]
    city_is_veg_friendly = any(c in dest_lower for c in veg_cities)

    for hotel in hotels:
        amenities = [a.lower() for a in hotel.get("amenities", [])]
        hotel["veg_friendly"] = (
            city_is_veg_friendly
            or "restaurant" in amenities
            or "dining" in amenities
        )
        hotel["veg_note"] = (
            "Vegetarian options widely available in this city"
            if city_is_veg_friendly
            else "Confirm vegetarian menu with hotel before booking"
        )
    return hotels


def _get_ai_recommendation(destination: str, budget: str, duration: int,
                             top_hotels: list, veg: bool) -> str:
    if not gemini.is_available or not top_hotels:
        return ""
    hotel_names = ", ".join(h.get("name", "") for h in top_hotels)
    veg_note = " Guest requires vegetarian meals." if veg else ""
    prompt = (f"Corporate travel hotel recommendation for {destination}. "
              f"Budget: {budget}. Duration: {duration} days.{veg_note} "
              f"Top options: {hotel_names}. Give a 2-sentence recommendation without emojis.")
    return gemini.generate(prompt) or ""


def _build_booking_link(hotel_name: str, destination: str,
                         check_in: str, check_out: str) -> str:
    name_enc = hotel_name.replace(" ", "+")
    dest_enc = destination.replace(" ", "+")
    return (f"https://www.makemytrip.com/hotels/hotel-listing/?checkin={check_in}"
            f"&checkout={check_out}&city={dest_enc}&keyword={name_enc}")


def _pg_type_label(pg_type: str) -> str:
    labels = {
        "Managed PG": "Managed PG",
        "Serviced Apartment": "Serviced Apartment",
        "Coliving": "Co-living Space",
        "Guest House": "Guest House",
    }
    return labels.get(pg_type, pg_type)


def _pg_booking_url_by_type(pg_type: str, destination: str) -> str:
    dest_enc = destination.replace(" ", "-").lower()
    if pg_type == "Coliving":
        return f"https://www.stanzaliving.com/{dest_enc}"
    if pg_type == "Serviced Apartment":
        return "https://www.nestaway.com"
    return f"https://www.oyorooms.com/long-term-stays/{dest_enc}/"
