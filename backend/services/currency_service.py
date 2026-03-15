"""
TravelSync Pro — Currency Exchange Service
Live rates via Open Exchange Rates API (free: 1000 req/month).
Configure OPEN_EXCHANGE_APP_ID for live data.
https://openexchangerates.org
"""
import os
import logging
import requests
from datetime import datetime
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class CurrencyService:
    OXR_URL = "https://openexchangerates.org/api/latest.json"
    OXR_HIST_URL = "https://openexchangerates.org/api/historical/{date}.json"

    def __init__(self):
        self.app_id = os.getenv("OPEN_EXCHANGE_APP_ID")
        self.configured = bool(self.app_id)
        self._cache = TTLCache(maxsize=10, ttl=3600)  # 1-hr cache

    def get_rates(self) -> dict:
        """Fetch latest exchange rates (USD base)."""
        if "rates" in self._cache:
            return self._cache["rates"]

        if self.configured:
            try:
                resp = requests.get(
                    self.OXR_URL,
                    params={"app_id": self.app_id, "base": "USD"},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = {
                        "rates": data.get("rates", {}),
                        "base": "USD",
                        "timestamp": data.get("timestamp"),
                        "updated": datetime.fromtimestamp(data.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M UTC"),
                        "source": "openexchangerates",
                    }
                    self._cache["rates"] = result
                    return result
            except Exception as e:
                logger.warning("[Currency] Rates fetch error: %s", e)

        return self._fallback_rates()

    def convert(self, amount: float, from_currency: str, to_currency: str) -> dict:
        """Convert between any two currencies via USD pivot."""
        rates_data = self.get_rates()
        rates = rates_data.get("rates", {})

        if not rates:
            return {"error": "Rates unavailable", "amount": amount}

        try:
            from_rate = rates.get(from_currency.upper(), 1)
            to_rate = rates.get(to_currency.upper(), 1)
            # Convert to USD then to target
            usd_amount = amount / from_rate
            converted = usd_amount * to_rate
            return {
                "amount": amount,
                "from": from_currency.upper(),
                "to": to_currency.upper(),
                "converted": round(converted, 2),
                "rate": round(to_rate / from_rate, 6),
                "updated": rates_data.get("updated", "N/A"),
                "source": rates_data.get("source", "fallback"),
            }
        except ZeroDivisionError:
            return {"error": "Invalid currency code"}

    def get_travel_currencies(self, destination: str) -> dict:
        """Return currency info + live INR conversion for a destination country."""
        DESTINATION_CURRENCY_MAP = {
            # India
            "india": "INR",
            # USA & Americas
            "usa": "USD", "united states": "USD", "us": "USD",
            "canada": "CAD", "mexico": "MXN", "brazil": "BRL",
            # Europe
            "uk": "GBP", "united kingdom": "GBP", "britain": "GBP",
            "france": "EUR", "germany": "EUR", "italy": "EUR",
            "spain": "EUR", "netherlands": "EUR", "switzerland": "CHF",
            "europe": "EUR",
            # Asia
            "japan": "JPY", "china": "CNY", "singapore": "SGD",
            "thailand": "THB", "malaysia": "MYR", "indonesia": "IDR",
            "south korea": "KRW", "hong kong": "HKD", "taiwan": "TWD",
            "vietnam": "VND", "philippines": "PHP", "myanmar": "MMK",
            # Middle East
            "uae": "AED", "dubai": "AED", "saudi arabia": "SAR",
            "qatar": "QAR", "kuwait": "KWD", "bahrain": "BHD",
            "oman": "OMR", "jordan": "JOD", "israel": "ILS",
            # Africa
            "south africa": "ZAR", "kenya": "KES", "nigeria": "NGN",
            "egypt": "EGP",
            # Oceania
            "australia": "AUD", "new zealand": "NZD",
        }

        CURRENCY_INFO = {
            "INR": {"symbol": "₹", "name": "Indian Rupee"},
            "USD": {"symbol": "$", "name": "US Dollar"},
            "EUR": {"symbol": "€", "name": "Euro"},
            "GBP": {"symbol": "£", "name": "British Pound"},
            "JPY": {"symbol": "¥", "name": "Japanese Yen"},
            "SGD": {"symbol": "S$", "name": "Singapore Dollar"},
            "AED": {"symbol": "د.إ", "name": "UAE Dirham"},
            "THB": {"symbol": "฿", "name": "Thai Baht"},
            "CAD": {"symbol": "C$", "name": "Canadian Dollar"},
            "AUD": {"symbol": "A$", "name": "Australian Dollar"},
            "CHF": {"symbol": "CHF", "name": "Swiss Franc"},
            "CNY": {"symbol": "¥", "name": "Chinese Yuan"},
            "SAR": {"symbol": "﷼", "name": "Saudi Riyal"},
            "KWD": {"symbol": "KD", "name": "Kuwaiti Dinar"},
            "QAR": {"symbol": "QR", "name": "Qatari Riyal"},
            "MYR": {"symbol": "RM", "name": "Malaysian Ringgit"},
            "HKD": {"symbol": "HK$", "name": "Hong Kong Dollar"},
        }

        dest_lower = destination.lower().strip()
        currency_code = DESTINATION_CURRENCY_MAP.get(dest_lower, "USD")
        info = CURRENCY_INFO.get(currency_code, {"symbol": currency_code, "name": currency_code})

        # Live INR → local currency conversion
        inr_conversion = self.convert(1, "INR", currency_code)
        inr_to_local = inr_conversion.get("converted", 0)

        return {
            "destination": destination,
            "currency_code": currency_code,
            "symbol": info["symbol"],
            "name": info["name"],
            "inr_to_local": inr_to_local,
            "local_to_inr": round(1 / inr_to_local, 4) if inr_to_local else 0,
            "common_amounts": {
                "100 INR": f"{info['symbol']} {round(100 * inr_to_local, 2)}",
                "1000 INR": f"{info['symbol']} {round(1000 * inr_to_local, 2)}",
                "5000 INR": f"{info['symbol']} {round(5000 * inr_to_local, 2)}",
                "10000 INR": f"{info['symbol']} {round(10000 * inr_to_local, 2)}",
            },
            "source": inr_conversion.get("source", "fallback"),
        }

    def format_inr(self, amount: float) -> str:
        """Format amount in Indian number system (lakhs, crores)."""
        amount = round(amount, 2)
        if amount >= 10_000_000:
            return f"₹{amount/10_000_000:.2f} Cr"
        elif amount >= 100_000:
            return f"₹{amount/100_000:.2f} L"
        elif amount >= 1000:
            # Indian comma format: 1,23,456
            int_part = int(amount)
            dec_part = amount - int_part
            s = str(int_part)
            if len(s) > 3:
                s = s[:-3] + "," + s[-3:]
            if len(s) > 6:
                s = s[:-6] + "," + s[-6:]
            return f"₹{s}{f'.{int(dec_part*100):02d}' if dec_part else ''}"
        return f"₹{amount:.2f}"

    def _fallback_rates(self) -> dict:
        """Approximate rates relative to USD (updated periodically)."""
        return {
            "rates": {
                "INR": 83.5, "USD": 1.0, "EUR": 0.92, "GBP": 0.79,
                "JPY": 149.5, "SGD": 1.34, "AED": 3.67, "THB": 35.2,
                "CAD": 1.36, "AUD": 1.53, "CHF": 0.90, "CNY": 7.24,
                "SAR": 3.75, "KWD": 0.31, "QAR": 3.64, "MYR": 4.73,
                "HKD": 7.82, "KRW": 1340, "TWD": 31.5,
            },
            "base": "USD",
            "updated": "Approximate rates",
            "source": "fallback",
            "note": "Set OPEN_EXCHANGE_APP_ID for live rates",
        }


currency = CurrencyService()
