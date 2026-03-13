# place_info_search.py
import os
import requests
from langchain_tavily import TavilySearch

class FoursquarePlaceSearchTool:
    """
    Uses Foursquare Places API (v3) to search for places.
    Expects FOURSQUARE_API_KEY in environment.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("FOURSQUARE_API_KEY")
        if not self.api_key:
            raise ValueError("FOURSQUARE_API_KEY not found in environment")
        self.base_url = "https://api.foursquare.com/v3/places"

        # Default headers for Foursquare v3
        self.headers = {
            "Accept": "application/json",
            "Authorization": self.api_key
        }

    def _search(self, query: str = None, near: str = None, ll: str = None, limit: int = 10, categories: str = None):
        """
        Generic search wrapper.
        - query: text query
        - near: city or human-readable location (e.g., "Hyderabad")
        - ll: "lat,lon" (overrides near)
        - categories: comma-separated category ids (optional)
        """
        params = {"limit": limit}
        if query:
            params["query"] = query
        if near and not ll:
            params["near"] = near
        if ll:
            params["ll"] = ll
        if categories:
            params["categories"] = categories

        url = f"{self.base_url}/search"
        resp = requests.get(url, headers=self.headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def search_restaurants(self, place: str, limit: int = 10):
        """Search restaurants in a place (query-based)."""
        # Query "restaurant" generally returns restaurants. You can tune categories if needed.
        return self._search(query="restaurant", near=place, limit=limit)

    def search_attractions(self, place: str, limit: int = 10):
        """Search tourist attractions / points of interest."""
        return self._search(query="attraction|tourist attraction|sightseeing", near=place, limit=limit)

    def search_activities(self, place: str, limit: int = 10):
        """Search activities (tours, outdoor activities, experiences)."""
        return self._search(query="activities|things to do|tours", near=place, limit=limit)

    def search_transportation(self, place: str, limit: int = 10):
        """Search for transport-related POIs (train stations, bus stations, airports)."""
        return self._search(query="airport|train station|bus station|metro", near=place, limit=limit)


class LocationIQTool:
    """
    Use LocationIQ for geocoding and simple directions.
    Expects LOCATIONIQ_API_KEY in environment.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("LOCATIONIQ_API_KEY")
        if not self.api_key:
            raise ValueError("LOCATIONIQ_API_KEY not found in environment")
        # Use the us1 endpoint pattern used by LocationIQ docs; adjust region if needed
        self.geocode_url = "https://us1.locationiq.com/v1"
        self.directions_base = "https://us1.locationiq.com/v1/directions"

    def forward_geocode(self, query: str, limit: int = 5):
        """Return forward geocoding results for `query`."""
        url = f"{self.geocode_url}/search.php"
        params = {"key": self.api_key, "q": query, "format": "json", "limit": limit}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def reverse_geocode(self, lat: float, lon: float):
        """Reverse geocode lat/lon to address."""
        url = f"{self.geocode_url}/reverse.php"
        params = {"key": self.api_key, "lat": lat, "lon": lon, "format": "json"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_directions(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float, profile: str = "driving"):
        """
        Get directions from A -> B.
        Uses LocationIQ Directions API endpoint pattern:
        /v1/directions/{profile}/{coordinates}?key=...
        coordinates format: lon,lat;lon,lat
        """
        coords = f"{start_lon},{start_lat};{end_lon},{end_lat}"
        url = f"{self.directions_base}/{profile}/{coords}"
        params = {"key": self.api_key, "overview": "false", "steps": "true"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()


class TavilyPlaceSearchTool:
    """Fallback search tool using Tavily (like your original)."""

    def __init__(self):
        pass

    def tavily_search_attractions(self, place: str) -> dict:
        tavily_tool = TavilySearch(topic="general", include_answer="advanced")
        result = tavily_tool.invoke({"query": f"top attractive places in and around {place}"})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return result

    def tavily_search_restaurants(self, place: str) -> dict:
        tavily_tool = TavilySearch(topic="general", include_answer="advanced")
        result = tavily_tool.invoke({"query": f"what are the top 10 restaurants and eateries in and around {place}."})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return result

    def tavily_search_activity(self, place: str) -> dict:
        tavily_tool = TavilySearch(topic="general", include_answer="advanced")
        result = tavily_tool.invoke({"query": f"activities in and around {place}"})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return result

    def tavily_search_transportation(self, place: str) -> dict:
        tavily_tool = TavilySearch(topic="general", include_answer="advanced")
        result = tavily_tool.invoke({"query": f"What are the different modes of transportations available in {place}"})
        if isinstance(result, dict) and result.get("answer"):
            return result["answer"]
        return result
