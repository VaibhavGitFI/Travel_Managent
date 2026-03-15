"""
TravelSync Pro — Weather Agent
Real-time weather data via OpenWeatherMap for travel planning.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.weather_service import weather


def get_travel_weather(destination: str, start_date: str = "", end_date: str = "") -> dict:
    """Get weather forecast for the travel period."""
    if start_date and end_date:
        return weather.get_travel_summary(destination, start_date, end_date)
    return {
        "city": destination,
        "current": weather.get_current(destination),
        "forecast": weather.get_forecast(destination, 5).get("forecasts", []),
        "source": "openweathermap",
    }


def get_dashboard_weather(cities: list) -> list:
    """Return current weather for a list of cities (dashboard widget)."""
    results = []
    for city in cities[:5]:  # Limit to 5 to avoid rate limit
        try:
            results.append(weather.get_current(city))
        except Exception:
            pass
    return results


def get_weather_advisory(destination: str, travel_date: str) -> dict:
    """Return a simple travel weather advisory for a specific date."""
    forecast = weather.get_forecast(destination, 7)
    forecasts = forecast.get("forecasts", [])

    target_day = next((f for f in forecasts if f.get("date") == travel_date), None)
    if not target_day:
        target_day = forecasts[0] if forecasts else {}

    rain_prob = target_day.get("rain_probability", 0)
    temp = target_day.get("temp_max", 28)

    if rain_prob > 70 or temp > 42:
        level = "caution"
        message = "Adverse weather conditions possible. Carry rain gear and stay hydrated."
    elif rain_prob > 40:
        level = "moderate"
        message = "Possible rain. Carry an umbrella."
    else:
        level = "clear"
        message = "Good weather expected for travel."

    return {
        "destination": destination,
        "date": travel_date,
        "weather": target_day,
        "advisory_level": level,
        "advisory_message": message,
        "source": forecast.get("source", "fallback"),
    }
