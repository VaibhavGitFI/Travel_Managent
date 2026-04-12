"""
TravelSync Pro — Google Custom Search Service
Provides real-time web search to enrich AI chat responses.

Setup:
  1. Enable "Custom Search JSON API" in Google Cloud Console (same project as Maps)
  2. Create a search engine at https://programmablesearchengine.google.com/
     - Set to "Search the entire web"
  3. Add GOOGLE_SEARCH_CX=<your-cx-id> to backend/.env
     (GOOGLE_MAPS_API_KEY is reused as the API key)
"""
import os
import logging
from cachetools import TTLCache
from services.http_client import http as requests

logger = logging.getLogger(__name__)


class SearchService:
    CSE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_VISION_API_KEY")
        self.cx = os.getenv("GOOGLE_SEARCH_CX")
        self.configured = bool(self.api_key and self.cx)
        self._cache = TTLCache(maxsize=128, ttl=600)  # 10-min cache

    def search(self, query: str, num: int = 5) -> list:
        """
        Search the web. Returns list of {title, snippet, link}.
        Returns [] if not configured or request fails.
        """
        if not self.configured:
            return []

        cache_key = f"cse_{query[:80]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            resp = requests.get(
                self.CSE_URL,
                params={"key": self.api_key, "cx": self.cx, "q": query, "num": num},
                timeout=8,
            )
            if resp.status_code != 200:
                logger.warning("[Search] CSE returned %s", resp.status_code)
                return []

            items = resp.json().get("items", [])
            results = [
                {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": item.get("link", ""),
                }
                for item in items
            ]
            self._cache[cache_key] = results
            return results
        except Exception as e:
            logger.warning("[Search] CSE error: %s", e)
            return []

    def search_flights(self, origin: str, destination: str, date: str) -> list:
        """Search for current flight info for a route."""
        q = f"cheap flights {origin} to {destination} {date} price book"
        return self.search(q, num=4)

    def search_hotels(self, city: str, budget: str = "") -> list:
        """Search for hotels in a city."""
        q = f"best hotels in {city} {budget} book online"
        return self.search(q, num=4)

    def search_travel(self, query: str) -> list:
        """General travel search."""
        return self.search(f"travel {query}", num=5)

    def format_for_prompt(self, results: list) -> str:
        """Format search results as context text for AI prompts."""
        if not results:
            return ""
        lines = ["[Real-time web search results:]"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
            if r.get("link"):
                lines.append(f"   Source: {r['link']}")
        return "\n".join(lines)


search = SearchService()
