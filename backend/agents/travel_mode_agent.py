"""
TravelSync Pro — Travel Mode Agent
- Real flight search via AviationStack API (falls back to curated data)
- Distance-based mode recommendation (cab/bus/train/flight)
- Team arrival synchronization for multi-origin groups
- IRCTC, RedBus, Ola, Uber deep links
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from services.maps_service import maps
from services.gemini_service import gemini
from services.flights_service import flights as flights_svc, get_airport_code


def recommend_travel_mode(trip_details: dict, model=None) -> dict:
    """
    Recommend optimal travel mode(s) based on distance and preferences.
    Returns flight options (live from Amadeus), train/bus/cab links.
    """
    destination = trip_details.get("destination", "")
    travelers = trip_details.get("travelers", [])
    origin = trip_details.get("origin", travelers[0]["origin"] if travelers else "")
    travel_dates = trip_details.get("travel_dates", "")
    num_travelers = trip_details.get("num_travelers", len(travelers) or 1)
    purpose = trip_details.get("purpose", "business")

    # Parse travel date
    departure_date = _parse_date(travel_dates)

    # Calculate distance
    distance_km = maps.get_distance_km(origin, destination) if origin and destination else 0
    region = _detect_region(origin, destination)

    # Determine recommended mode
    mode = _select_mode(distance_km, num_travelers, purpose)

    # Build response
    result = {
        "recommended_mode": mode["primary"],
        "reason": mode["reason"],
        "distance_km": round(distance_km, 1),
        "region": region,
        "modes": {},
        "ai_tip": "",
        "data_source": "live",
    }

    # ── Flights ──────────────────────────────────────────────
    if distance_km > 300 or mode["primary"] == "flight":
        origin_code = get_airport_code(origin)
        dest_code = get_airport_code(destination)
        flight_data = flights_svc.search_flights(
            origin_code, dest_code, departure_date,
            adults=num_travelers, max_results=6
        )
        flight_options = flight_data.get("flights", [])
        # Only show flights if the route actually has them
        if flight_options:
            search_q = f"{origin}+to+{destination}+flights".replace(' ', '+')
            result["modes"]["flight"] = {
                "available": True,
                "options": flight_options,
                "booking_platforms": [
                    {"name": "Google Flights", "url": f"https://www.google.com/search?q={search_q}"},
                ],
                "source": flight_data.get("source", "curated"),
            }
        else:
            reason = flight_data.get("reason", "No flights available on this route")
            result["modes"]["flight"] = {"available": False, "reason": reason, "options": []}

    # ── Trains ───────────────────────────────────────────────
    if 100 < distance_km < 1500:
        from_station = _city_to_station_code(origin)
        to_station = _city_to_station_code(destination)
        result["modes"]["train"] = {
            "available": True,
            "station_from": from_station,
            "station_to": to_station,
            "platforms": _train_platforms(region, from_station, to_station, departure_date),
            "estimated_duration": _estimate_train_duration(distance_km),
            "popular_trains": _suggest_trains(origin, destination),
            "note": "Check live availability directly on rail operators",
        }

    # ── Bus ──────────────────────────────────────────────────
    if 50 < distance_km < 600:
        result["modes"]["bus"] = {
            "available": True,
            "platforms": _bus_platforms(region, origin, destination),
            "estimated_duration": _estimate_bus_duration(distance_km),
            "note": "Compare coach class, refund policy, and terminal location before booking",
        }

    # ── Cab / Self-Drive ─────────────────────────────────────
    if distance_km < 300:
        fare = _estimate_cab_fare(distance_km, region)
        result["modes"]["cab"] = {
            "available": True,
            "platforms": _cab_platforms(region),
            "self_drive": [
                {"name": "Zoomcar", "url": f"https://www.zoomcar.com/in/{destination.lower().replace(' ', '-')}/cars"},
                {"name": "Myles", "url": "https://www.mylescars.com"},
                {"name": "Revv", "url": "https://www.revv.co.in"},
            ],
            "estimated_duration": _estimate_cab_duration(distance_km),
            "estimated_fare": fare,
        }

    # AI tip
    if gemini.is_available:
        prompt = (f"In one sentence, give the best travel advice for a business trip from "
                  f"{origin} to {destination} ({distance_km:.0f}km, {num_travelers} traveler(s), "
                  f"purpose: {purpose}). Mention the recommended mode.")
        result["ai_tip"] = gemini.generate(prompt) or ""

    return result


def synchronize_team_arrivals(data: dict) -> dict:
    """
    Plan coordinated arrivals for a multi-origin team.
    Each traveler gets a personalized departure plan to arrive by meeting time.
    """
    destination = data.get("destination", "")
    travelers = data.get("travelers", [])
    meeting_time_str = data.get("meeting_time", "10:00 AM")
    meeting_date = data.get("meeting_date", datetime.now().strftime("%Y-%m-%d"))

    if not travelers:
        return {"success": False, "error": "No travelers provided"}

    # Parse meeting time
    try:
        mt = datetime.strptime(f"{meeting_date} {meeting_time_str}", "%Y-%m-%d %I:%M %p")
    except ValueError:
        try:
            mt = datetime.strptime(f"{meeting_date} {meeting_time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            mt = datetime.now().replace(hour=10, minute=0)

    plans = []
    for traveler in travelers:
        origin = traveler.get("origin", "")
        name = traveler.get("name", "Traveler")
        if not origin:
            continue

        distance_km = maps.get_distance_km(origin, destination)
        mode = _select_mode(distance_km, 1, "business")["primary"]
        travel_hours = _estimate_travel_hours(distance_km, mode)

        # Buffer: 1.5 hours for airport/station + check-in
        buffer_hours = 2.0 if mode == "flight" else 0.5
        depart_by = mt - timedelta(hours=travel_hours + buffer_hours)

        plans.append({
            "traveler": name,
            "origin": origin,
            "destination": destination,
            "distance_km": round(distance_km, 1),
            "recommended_mode": mode,
            "estimated_travel_time": f"{travel_hours:.1f} hrs",
            "depart_by": depart_by.strftime("%Y-%m-%d %H:%M"),
            "arrive_by": mt.strftime("%Y-%m-%d %H:%M"),
            "buffer_time": f"{buffer_hours:.0f} hr buffer for {mode} check-in/boarding",
            "booking_tip": _booking_tip(mode, origin, destination, meeting_date),
        })

    # Determine earliest departure
    sorted_plans = sorted(plans, key=lambda x: x.get("depart_by", ""))

    return {
        "success": True,
        "destination": destination,
        "meeting_time": meeting_time_str,
        "meeting_date": meeting_date,
        "team_plans": plans,
        "sync_summary": {
            "total_travelers": len(plans),
            "first_departure": sorted_plans[0]["depart_by"] if sorted_plans else "",
            "all_modes": list(set(p["recommended_mode"] for p in plans)),
        },
    }


# ── Helpers ─────────────────────────────────────────────────────────

def _select_mode(distance_km: float, num_travelers: int, purpose: str) -> dict:
    """Determine the best travel mode based on distance."""
    if distance_km == 0:
        return {"primary": "cab", "reason": "Intra-city travel"}
    if distance_km < 80:
        return {"primary": "cab", "reason": f"{distance_km:.0f}km — cab/auto is quickest"}
    if distance_km < 200:
        return {"primary": "cab", "reason": f"{distance_km:.0f}km — cab or bus recommended"}
    if distance_km < 400:
        return {"primary": "train", "reason": f"{distance_km:.0f}km — train is comfortable and cost-effective"}
    if distance_km < 700:
        return {"primary": "train", "reason": f"{distance_km:.0f}km — Rajdhani/Shatabdi or flight"}
    return {"primary": "flight", "reason": f"{distance_km:.0f}km — flight saves significant time"}


def _parse_date(date_str: str) -> str:
    """Extract or default departure date."""
    if not date_str:
        return (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y"]:
        try:
            return datetime.strptime(date_str.split(" to ")[0].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")


def _estimate_train_duration(distance_km: float) -> str:
    hours = distance_km / 80  # avg ~80km/h for express trains
    return f"{hours:.1f} hrs"


def _estimate_bus_duration(distance_km: float) -> str:
    hours = distance_km / 55  # avg ~55km/h for highway buses
    return f"{hours:.1f} hrs"


def _estimate_cab_duration(distance_km: float) -> str:
    hours = distance_km / 60
    return f"{hours:.1f} hrs"


def _estimate_travel_hours(distance_km: float, mode: str) -> float:
    speeds = {"flight": 700, "train": 80, "bus": 55, "cab": 60}
    base = distance_km / speeds.get(mode, 60)
    return round(base, 1)


def _city_to_station_code(city: str) -> str:
    STATION_CODES = {
        "mumbai": "CSTM", "delhi": "NDLS", "new delhi": "NDLS",
        "bangalore": "SBC", "bengaluru": "SBC", "hyderabad": "HYB",
        "chennai": "MAS", "kolkata": "KOAA", "pune": "PUNE",
        "ahmedabad": "ADI", "jaipur": "JP", "lucknow": "LKO",
        "varanasi": "BSB", "bhopal": "BPL", "nagpur": "NGP",
        "surat": "ST", "coimbatore": "CBE", "kochi": "ERS",
        "goa": "MAO", "chandigarh": "CDG", "amritsar": "ASR",
        "london": "KGX", "paris": "GDN", "berlin": "BER",
        "frankfurt": "FFM", "amsterdam": "AMS", "madrid": "MAD",
        "rome": "ROM", "vienna": "VIE", "prague": "PRG",
        "tokyo": "TYO", "osaka": "OSA", "seoul": "SEL",
        "beijing": "BJP", "shanghai": "SHA", "bangkok": "BKK",
        "singapore": "SGP", "new york": "NYP", "chicago": "CHI",
        "toronto": "YYZ", "sydney": "SYD",
    }
    return STATION_CODES.get(city.lower(), city.upper()[:3])


def _suggest_trains(origin: str, destination: str) -> list:
    """Known popular trains for common routes."""
    POPULAR_TRAINS = {
        ("mumbai", "delhi"): ["Rajdhani Express (12951)", "Duronto Express (12263)"],
        ("delhi", "mumbai"): ["Rajdhani Express (12952)", "Duronto Express (12264)"],
        ("mumbai", "bangalore"): ["Udyan Express (11301)", "Rajdhani Express (22691)"],
        ("delhi", "kolkata"): ["Rajdhani Express (12301)", "Duronto (12273)"],
        ("mumbai", "hyderabad"): ["Konark Express (11020)", "Hussainsagar Express (12701)"],
        ("delhi", "jaipur"): ["Shatabdi Express (12015)", "Ajmer Shatabdi (12015)"],
        ("delhi", "agra"): ["Gatimaan Express (12049)", "Shatabdi (12002)"],
        ("london", "paris"): ["Eurostar (London St Pancras → Paris Gare du Nord)"],
        ("paris", "berlin"): ["TGV/ICE high-speed (with transfer in Frankfurt)"],
        ("tokyo", "osaka"): ["Shinkansen Nozomi", "Shinkansen Hikari"],
        ("madrid", "barcelona"): ["AVE High Speed"],
        ("new york", "washington"): ["Amtrak Acela", "Amtrak Northeast Regional"],
    }
    key = (origin.lower().split(",")[0].strip(), destination.lower().split(",")[0].strip())
    return POPULAR_TRAINS.get(key, POPULAR_TRAINS.get((key[1], key[0]), []))


def _detect_region(origin: str, destination: str) -> str:
    text = f"{origin} {destination}".lower()
    india = {"mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "pune", "kolkata", "jaipur", "kochi"}
    europe = {"london", "paris", "berlin", "frankfurt", "madrid", "barcelona", "rome", "amsterdam", "vienna", "prague", "zurich"}
    asia = {"tokyo", "osaka", "seoul", "beijing", "shanghai", "bangkok", "singapore", "jakarta", "manila", "dubai"}
    americas = {"new york", "los angeles", "chicago", "toronto", "vancouver", "mexico city"}
    oceania = {"sydney", "melbourne", "auckland"}

    if any(c in text for c in india):
        return "india"
    if any(c in text for c in europe):
        return "europe"
    if any(c in text for c in asia):
        return "asia"
    if any(c in text for c in americas):
        return "americas"
    if any(c in text for c in oceania):
        return "oceania"
    return "global"


def _train_platforms(region: str, from_station: str, to_station: str, departure_date: str) -> list:
    if region == "india":
        return [
            {"name": "IRCTC", "url": "https://www.irctc.co.in/nget/train-search"},
            {"name": "Confirmtkt", "url": f"https://confirmtkt.com/train/{from_station}-{to_station}"},
            {"name": "RailYatri", "url": "https://www.railyatri.in/trains"},
        ]
    if region == "europe":
        return [
            {"name": "Eurail", "url": "https://www.eurail.com"},
            {"name": "Trainline", "url": "https://www.thetrainline.com"},
            {"name": "Deutsche Bahn", "url": "https://www.bahn.com"},
            {"name": "SNCF Connect", "url": "https://www.sncf-connect.com"},
        ]
    if region == "asia":
        return [
            {"name": "JR East", "url": "https://www.jreast.co.jp/e/"},
            {"name": "KTX Korail", "url": "https://www.letskorail.com"},
            {"name": "12Go", "url": "https://12go.asia"},
        ]
    if region == "americas":
        return [
            {"name": "Amtrak", "url": "https://www.amtrak.com"},
            {"name": "Via Rail", "url": "https://www.viarail.ca"},
        ]
    return [
        {"name": "Omio", "url": "https://www.omio.com"},
        {"name": "Rome2Rio", "url": "https://www.rome2rio.com"},
    ]


def _bus_platforms(region: str, origin: str, destination: str) -> list:
    from_slug = origin.lower().replace(" ", "-")
    to_slug = destination.lower().replace(" ", "-")
    if region == "india":
        return [
            {"name": "RedBus", "url": f"https://www.redbus.in/bus-tickets/{from_slug}-to-{to_slug}"},
            {"name": "AbhiBus", "url": f"https://www.abhibus.com/bus-tickets/{from_slug}-to-{to_slug}"},
            {"name": "MakeMyTrip Bus", "url": "https://www.makemytrip.com/bus-tickets/"},
        ]
    if region == "europe":
        return [
            {"name": "FlixBus", "url": "https://www.flixbus.com"},
            {"name": "BlaBlaCar Bus", "url": "https://www.blablacar.com/bus"},
        ]
    if region in ("americas", "global"):
        return [
            {"name": "Greyhound", "url": "https://www.greyhound.com"},
            {"name": "Busbud", "url": "https://www.busbud.com"},
        ]
    return [
        {"name": "12Go", "url": "https://12go.asia"},
        {"name": "Busbud", "url": "https://www.busbud.com"},
    ]


def _cab_platforms(region: str) -> list:
    if region == "india":
        return [
            {"name": "Ola", "url": "https://www.olacabs.com"},
            {"name": "Uber", "url": "https://www.uber.com/in/en/"},
            {"name": "InDrive", "url": "https://indrive.com/in/en"},
        ]
    return [
        {"name": "Uber", "url": "https://www.uber.com"},
        {"name": "Lyft", "url": "https://www.lyft.com"},
        {"name": "Bolt", "url": "https://bolt.eu"},
    ]


def _estimate_cab_fare(distance_km: float, region: str) -> str:
    if region == "india":
        return f"₹{int(distance_km * 12)}-₹{int(distance_km * 18)}"
    if region == "europe":
        return f"€{int(distance_km * 1.2)}-€{int(distance_km * 2.0)}"
    if region == "americas":
        return f"${int(distance_km * 1.1)}-${int(distance_km * 1.8)}"
    return f"${int(distance_km * 1.0)}-${int(distance_km * 1.6)}"


# ── Carbon Footprint Calculations ─────────────────────────────────────────────

# kg CO₂ per km per passenger — based on DEFRA/ICAO 2023 emission factors
_CO2_FACTORS = {
    "flight_short":  0.255,   # <1500 km (includes radiative forcing)
    "flight_long":   0.195,   # >=1500 km
    "train":         0.041,
    "bus":           0.089,
    "cab":           0.170,   # petrol / CNG average
    "ev_cab":        0.068,   # electric cab estimate
}

# Greener alternatives map
_GREENER_ALTS = {
    "flight_short": "train",
    "flight_long": None,       # no practical alternative for >1500 km intercontinental
    "cab":  "bus",
    "bus":  "train",
}


def calculate_carbon(distance_km: float, mode: str, num_travelers: int = 1) -> dict:
    """
    Calculate CO₂ emissions for a trip segment.

    Returns:
        {
          co2_kg: float,        # total CO₂ for all travelers
          co2_per_person: float,
          mode: str,
          distance_km: float,
          greener_alt: str | None,  # suggested greener mode
          greener_saving_kg: float | None,
        }
    """
    n = max(1, int(num_travelers))
    d = max(0.0, float(distance_km))

    if mode == "flight":
        factor_key = "flight_long" if d >= 1500 else "flight_short"
    elif mode in _CO2_FACTORS:
        factor_key = mode
    else:
        factor_key = "cab"

    factor = _CO2_FACTORS[factor_key]
    co2_per_person = round(d * factor, 2)
    co2_total = round(co2_per_person * n, 2)

    # Greener alternative savings
    alt_mode = _GREENER_ALTS.get(factor_key)
    greener_saving = None
    if alt_mode and alt_mode in _CO2_FACTORS:
        alt_co2 = round(d * _CO2_FACTORS[alt_mode] * n, 2)
        greener_saving = round(co2_total - alt_co2, 2)

    return {
        "co2_kg": co2_total,
        "co2_per_person": co2_per_person,
        "mode": mode,
        "distance_km": round(d, 1),
        "factor_used": factor,
        "num_travelers": n,
        "greener_alt": alt_mode,
        "greener_saving_kg": greener_saving,
        "trees_equivalent": round(co2_total / 21.77, 2),  # avg tree absorbs 21.77 kg CO₂/year
    }


def _booking_tip(mode: str, origin: str, dest: str, date: str) -> str:
    region = _detect_region(origin, dest)
    tips = {
        "flight": f"Book on MakeMyTrip or directly with IndiGo/Air India for {date}",
        "train": (
            f"Book on IRCTC — Tatkal opens 1 day before for {origin}→{dest}"
            if region == "india"
            else f"Compare rail operators and flexible fares for {origin}→{dest}"
        ),
        "bus": f"Compare coach class and terminal locations for {origin}→{dest}",
        "cab": f"Use app-based ride-hailing and confirm pickup zone for {origin} → {dest}",
    }
    return tips.get(mode, "Book in advance for best rates")
