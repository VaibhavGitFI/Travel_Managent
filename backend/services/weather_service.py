
"""
TravelSync Pro — Weather Service
Real-time forecasts via OpenWeatherMap API.
Free tier: 1,000 calls/day — https://openweathermap.org/api
Configure OPENWEATHER_API_KEY for live data.
"""
import os
import logging
from datetime import datetime, timedelta
from cachetools import TTLCache
from services.http_client import http as requests

logger = logging.getLogger(__name__)


class WeatherService:
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    ICON_BASE = "https://openweathermap.org/img/wn"

    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.configured = bool(self.api_key)
        self._cache = TTLCache(maxsize=100, ttl=1800)  # 30-min cache

    def get_current(self, city: str) -> dict:
        """Get current weather for a city."""
        cache_key = f"current_{city.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self.configured:
            try:
                resp = requests.get(
                    f"{self.BASE_URL}/weather",
                    params={"q": city, "appid": self.api_key,
                            "units": "metric", "lang": "en"},
                    timeout=10
                )
                if resp.status_code == 200:
                    d = resp.json()
                    result = {
                        "city": d.get("name", city),
                        "country": d.get("sys", {}).get("country", "IN"),
                        "temp": round(d["main"]["temp"]),
                        "feels_like": round(d["main"]["feels_like"]),
                        "temp_min": round(d["main"]["temp_min"]),
                        "temp_max": round(d["main"]["temp_max"]),
                        "humidity": d["main"]["humidity"],
                        "pressure": d["main"]["pressure"],
                        "description": d["weather"][0]["description"].title(),
                        "icon": d["weather"][0]["icon"],
                        "icon_url": f"{self.ICON_BASE}/{d['weather'][0]['icon']}@2x.png",
                        "wind_speed": round(d["wind"]["speed"] * 3.6, 1),  # m/s → km/h
                        "wind_direction": d["wind"].get("deg", 0),
                        "visibility": round(d.get("visibility", 0) / 1000, 1),
                        "clouds": d.get("clouds", {}).get("all", 0),
                        "sunrise": datetime.fromtimestamp(d["sys"]["sunrise"]).strftime("%H:%M"),
                        "sunset": datetime.fromtimestamp(d["sys"]["sunset"]).strftime("%H:%M"),
                        "timestamp": datetime.now().isoformat(),
                        "source": "openweathermap",
                    }
                    self._cache[cache_key] = result
                    return result
                elif resp.status_code == 404:
                    # Try without country code
                    resp2 = requests.get(
                        f"{self.BASE_URL}/weather",
                        params={"q": city, "appid": self.api_key, "units": "metric"},
                        headers=outbound_headers(),
                        timeout=10
                    )
                    if resp2.status_code == 200:
                        d = resp2.json()
                        result = self._parse_current(d, city)
                        self._cache[cache_key] = result
                        return result
            except Exception as e:
                logger.warning("[Weather] Current error: %s", e)

        result = self._mock_current(city)
        self._cache[cache_key] = result
        return result

    def get_forecast(self, city: str, days: int = 5) -> dict:
        """Get multi-day weather forecast."""
        cache_key = f"forecast_{city.lower()}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self.configured:
            try:
                resp = requests.get(
                    f"{self.BASE_URL}/forecast",
                    params={"q": city, "appid": self.api_key,
                            "units": "metric", "cnt": min(days * 8, 40)},
                    timeout=10
                )
                if resp.status_code == 200:
                    result = self._parse_forecast(resp.json(), days)
                    self._cache[cache_key] = result
                    return result
            except Exception as e:
                logger.warning("[Weather] Forecast error: %s", e)

        result = self._mock_forecast(city, days)
        self._cache[cache_key] = result
        return result

    def get_travel_summary(self, city: str, start_date: str, end_date: str) -> dict:
        """Summarize weather for a travel period with packing suggestions."""
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            days = max(1, (end - start).days + 1)
        except (ValueError, TypeError):
            days = 5

        forecast = self.get_forecast(city, min(days, 5))
        current = self.get_current(city)
        forecasts = forecast.get("forecasts", [])

        # Derive packing suggestions from weather data
        avg_temp = sum(f.get("temp_max", 28) for f in forecasts) / max(len(forecasts), 1)
        max_rain_prob = max((f.get("rain_probability", 0) for f in forecasts), default=0)

        suggestions = []
        if avg_temp > 30:
            suggestions += ["Light cotton clothing", "Sunscreen SPF 50+", "Sunglasses & hat"]
        elif avg_temp < 15:
            suggestions += ["Warm jacket/sweater", "Thermal innerwear", "Gloves & muffler"]
        else:
            suggestions += ["Light layers for comfort", "Comfortable walking shoes"]

        if max_rain_prob > 40:
            suggestions += ["Umbrella / raincoat", "Waterproof bag cover", "Extra shoes"]

        advisory = "good"
        if max_rain_prob > 70:
            advisory = "caution"
        if max_rain_prob > 90 or avg_temp > 42 or avg_temp < 5:
            advisory = "adverse"

        return {
            "city": city,
            "period": {"start": start_date, "end": end_date, "days": days},
            "current": current,
            "forecast": forecasts[:days],
            "summary": {
                "avg_high": round(avg_temp, 1),
                "max_rain_chance": max_rain_prob,
                "travel_advisory": advisory,
                "advisory_text": {
                    "good": "Great weather for travel",
                    "caution": "Carry rain gear, possible showers",
                    "adverse": "Check conditions before travel",
                }.get(advisory, ""),
                "packing_suggestions": suggestions,
            },
            "source": forecast.get("source", "fallback"),
        }

    # ── Parsers ─────────────────────────────────────────────────────

    def _parse_current(self, d: dict, city: str) -> dict:
        return {
            "city": d.get("name", city),
            "temp": round(d["main"]["temp"]),
            "feels_like": round(d["main"]["feels_like"]),
            "humidity": d["main"]["humidity"],
            "description": d["weather"][0]["description"].title(),
            "icon": d["weather"][0]["icon"],
            "icon_url": f"{self.ICON_BASE}/{d['weather'][0]['icon']}@2x.png",
            "wind_speed": round(d["wind"]["speed"] * 3.6, 1),
            "source": "openweathermap",
        }

    def _parse_forecast(self, data: dict, days: int) -> dict:
        daily = {}
        for item in data.get("list", []):
            date = item["dt_txt"].split(" ")[0]
            if date not in daily:
                daily[date] = {"temps": [], "humidity": [], "rain_probs": [],
                                "descriptions": [], "icons": []}
            daily[date]["temps"].append(item["main"]["temp"])
            daily[date]["humidity"].append(item["main"]["humidity"])
            daily[date]["rain_probs"].append(item.get("pop", 0) * 100)
            daily[date]["descriptions"].append(item["weather"][0]["description"])
            daily[date]["icons"].append(item["weather"][0]["icon"])

        forecasts = []
        for date, vals in list(daily.items())[:days]:
            forecasts.append({
                "date": date,
                "temp_max": round(max(vals["temps"])),
                "temp_min": round(min(vals["temps"])),
                "humidity": round(sum(vals["humidity"]) / len(vals["humidity"])),
                "description": max(set(vals["descriptions"]), key=vals["descriptions"].count).title(),
                "icon": vals["icons"][len(vals["icons"]) // 2],
                "icon_url": f"{self.ICON_BASE}/{vals['icons'][len(vals['icons'])//2]}@2x.png",
                "rain_probability": round(max(vals["rain_probs"])),
            })

        city_info = data.get("city", {})
        return {
            "city": city_info.get("name", ""),
            "country": city_info.get("country", "IN"),
            "forecasts": forecasts,
            "source": "openweathermap",
        }

    # ── Fallbacks ────────────────────────────────────────────────────

    def _mock_current(self, city: str) -> dict:
        import random
        # Season-aware temperature ranges per region
        month = datetime.now().month
        CITY_PROFILES = {
            "mumbai": {"summer": (28, 36), "monsoon": (27, 33), "winter": (20, 32)},
            "delhi": {"summer": (30, 45), "monsoon": (25, 38), "winter": (5, 20)},
            "bangalore": {"summer": (22, 33), "monsoon": (20, 28), "winter": (15, 27)},
            "bengaluru": {"summer": (22, 33), "monsoon": (20, 28), "winter": (15, 27)},
            "chennai": {"summer": (28, 40), "monsoon": (25, 35), "winter": (22, 30)},
            "hyderabad": {"summer": (26, 42), "monsoon": (24, 32), "winter": (15, 28)},
            "kolkata": {"summer": (28, 40), "monsoon": (28, 35), "winter": (12, 25)},
            "jaipur": {"summer": (28, 45), "monsoon": (25, 38), "winter": (8, 22)},
        }
        season = "monsoon" if 6 <= month <= 9 else ("winter" if month <= 2 or month >= 11 else "summer")
        profile = CITY_PROFILES.get(city.lower(), {"summer": (22, 35), "monsoon": (22, 30), "winter": (15, 28)})
        t_range = profile[season]
        temp = random.randint(t_range[0], t_range[1])

        descriptions = ["Partly Cloudy", "Clear Sky", "Sunny", "Light Clouds", "Hazy"]
        if season == "monsoon":
            descriptions = ["Light Rain", "Moderate Rain", "Overcast", "Scattered Showers"]

        return {
            "city": city.title(),
            "temp": temp,
            "feels_like": temp + random.randint(-2, 3),
            "humidity": random.randint(40 if season != "monsoon" else 70, 85),
            "description": random.choice(descriptions),
            "icon": "10d" if season == "monsoon" else "02d",
            "wind_speed": round(random.uniform(5, 25), 1),
            "source": "fallback",
            "note": "Set OPENWEATHER_API_KEY for live weather",
        }

    def _mock_forecast(self, city: str, days: int) -> dict:
        import random
        forecasts = []
        current = self._mock_current(city)
        base_temp = current["temp"]
        season_rain = current.get("description", "").lower() in ["light rain", "moderate rain"]

        for i in range(days):
            date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            variation = random.randint(-3, 3)
            forecasts.append({
                "date": date,
                "temp_max": base_temp + abs(variation) + 2,
                "temp_min": base_temp - abs(variation) - 3,
                "humidity": random.randint(50, 85),
                "description": current["description"],
                "icon": current["icon"],
                "rain_probability": random.randint(60, 90) if season_rain else random.randint(5, 35),
            })
        return {"city": city.title(), "forecasts": forecasts, "source": "fallback"}


weather = WeatherService()
