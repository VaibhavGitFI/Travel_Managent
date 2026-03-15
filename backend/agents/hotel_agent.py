"""
TravelSync Pro — Hotel & Accommodation Agent
- Real hotels via Amadeus API (falls back to curated data)
- PG / Serviced Apartments for stays ≥ 5 days
- Google Maps proximity filtering for rural client sites
- Gemini AI for personalized recommendations
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from services.amadeus_service import amadeus
from services.maps_service import maps
from services.gemini_service import gemini


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

    city_code = amadeus.get_airport_code(destination)
    hotels = amadeus.search_hotels(city_code, check_in_str, check_out_str,
                                    adults=num_travelers, budget_max=budget_max)

    # Proximity filter for rural trips
    if is_rural and client_address and maps.configured:
        hotels = _filter_by_proximity(hotels, client_address, max_km=2.0)
    elif is_rural and client_address:
        for h in hotels:
            h["rural_note"] = ("Hotels near client site preferred (2km radius). "
                               "Configure GOOGLE_MAPS_API_KEY for precise filtering.")

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

    # PG / long-stay options for 5+ days
    pg_options = []
    if duration_days >= 5:
        pg_options = search_pg_options({
            "destination": destination,
            "city_code": city_code,
            "duration_days": duration_days,
            "budget": budget,
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
    """Search PG / serviced apartment options for long stays."""
    city_code = data.get("city_code") or amadeus.get_airport_code(data.get("destination", ""))
    duration_days = int(data.get("duration_days", 7))

    budget = data.get("budget", "moderate")
    MONTHLY_BUDGET_CAPS = {"budget": 15000, "moderate": 30000, "premium": 60000, "luxury": None}
    budget_monthly = MONTHLY_BUDGET_CAPS.get(budget)

    options = amadeus.search_pg_options(city_code, duration_days, budget_monthly)

    for opt in options:
        opt["type_label"] = _pg_type_label(opt.get("type", ""))
        opt["booking_url"] = _pg_booking_url(opt.get("platform", ""), data.get("destination", ""))

    return options


def _filter_by_proximity(hotels: list, client_address: str, max_km: float = 2.0) -> list:
    """Filter hotels to those within max_km of client address."""
    client_coords = maps.geocode(client_address)
    if client_coords.get("source") == "fallback":
        return hotels

    filtered = []
    for hotel in hotels:
        hotel_loc = f"{hotel.get('name', '')}, {hotel.get('city', client_address)}"
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
              f"Top options: {hotel_names}. Give a 2-sentence recommendation.")
    return gemini.generate(prompt) or ""


def _build_booking_link(hotel_name: str, destination: str,
                         check_in: str, check_out: str) -> str:
    name_enc = hotel_name.replace(" ", "+")
    dest_enc = destination.replace(" ", "+")
    return (f"https://www.makemytrip.com/hotels/hotel-listing/?checkin={check_in}"
            f"&checkout={check_out}&city={dest_enc}&keyword={name_enc}")


def _pg_type_label(pg_type: str) -> str:
    labels = {
        "Managed PG": "🏠 Managed PG",
        "Serviced Apartment": "🏢 Serviced Apartment",
        "Coliving": "👥 Co-living Space",
        "Guest House": "🏡 Guest House",
    }
    return labels.get(pg_type, pg_type)


def _pg_booking_url(platform: str, destination: str) -> str:
    dest_enc = destination.replace(" ", "-").lower()
    urls = {
        "Stanza Living": f"https://www.stanzaliving.com/{dest_enc}",
        "NestAway": "https://www.nestaway.com",
        "OYO Life": f"https://www.oyorooms.com/long-term-stays/{dest_enc}/",
        "CoHo": "https://www.coho.in",
        "Colive": "https://www.colive.com",
    }
    return urls.get(platform, "https://www.nestaway.com")
