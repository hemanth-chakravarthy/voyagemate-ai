# place_search_tool.py
import os
from typing import List
from langchain.tools import tool
from dotenv import load_dotenv

# Import new wrappers
from utils.place_info_search import FoursquarePlaceSearchTool, TavilyPlaceSearchTool, LocationIQTool

load_dotenv()

class PlaceSearchTool:
    def __init__(self):
        load_dotenv()
        # Read Foursquare & LocationIQ keys from env
        self.fsq_api_key = os.environ.get("FOURSQUARE_API_KEY")
        self.locationiq_api_key = os.environ.get("LOCATIONIQ_API_KEY")

        # Initialize services, raise friendly error if missing
        if not self.fsq_api_key:
            raise ValueError("FOURSQUARE_API_KEY not found in environment")
        self.foursquare = FoursquarePlaceSearchTool(api_key=self.fsq_api_key)

        # LocationIQ is optional but recommended for geocoding/routing
        if self.locationiq_api_key:
            self.locationiq = LocationIQTool(api_key=self.locationiq_api_key)
        else:
            self.locationiq = None

        self.tavily_search = TavilyPlaceSearchTool()
        self.place_search_tool_list = self._setup_tools()

    def _setup_tools(self) -> List:
        """Expose a set of tools for LangChain or other agent usage."""

        @tool
        def search_attractions(place: str) -> str:
            """Search attractions of a place using Foursquare, fallback to Tavily."""
            try:
                res = self.foursquare.search_attractions(place)
                # Normalize response into a readable list
                items = []
                for r in res.get("results", []) if isinstance(res, dict) else (res or []):
                    name = r.get("name") or r.get("place_name") or r.get("display_name")
                    cat = ", ".join([c.get("name") for c in r.get("categories", [])]) if r.get("categories") else ""
                    location = r.get("location", {})
                    addr = location.get("formatted_address") or ", ".join(filter(None, [location.get("address"), location.get("locality")]))
                    items.append(f"{name} ({cat}) - {addr}")
                if items:
                    return f"Top attractions in {place}:\n" + "\n".join(items)
            except Exception as e:
                tavily_result = self.tavily_search.tavily_search_attractions(place)
                return f"Foursquare search failed ({e}).\nFallback results:\n{tavily_result}"
            return f"No attractions found for {place}."

        @tool
        def search_restaurants(place: str) -> str:
            """Search restaurants of a place using Foursquare, fallback to Tavily."""
            try:
                res = self.foursquare.search_restaurants(place)
                items = []
                for r in res.get("results", []) if isinstance(res, dict) else (res or []):
                    name = r.get("name")
                    cat = ", ".join([c.get("name") for c in r.get("categories", [])]) if r.get("categories") else ""
                    address = r.get("location", {}).get("formatted_address") or r.get("location", {}).get("address")
                    items.append(f"{name} ({cat}) - {address}")
                if items:
                    return f"Top restaurants in {place}:\n" + "\n".join(items)
            except Exception as e:
                tavily_result = self.tavily_search.tavily_search_restaurants(place)
                return f"Foursquare search failed ({e}).\nFallback results:\n{tavily_result}"
            return f"No restaurants found for {place}."

        @tool
        def search_activities(place: str) -> str:
            """Search activities in a place using Foursquare, fallback to Tavily."""
            try:
                res = self.foursquare.search_activities(place)
                items = []
                for r in res.get("results", []) if isinstance(res, dict) else (res or []):
                    items.append(r.get("name", "Unnamed place"))
                if items:
                    return f"Activities and experiences in {place}:\n" + "\n".join(items)
            except Exception as e:
                tavily_result = self.tavily_search.tavily_search_activity(place)
                return f"Foursquare search failed ({e}).\nFallback results:\n{tavily_result}"
            return f"No activities found for {place}."

        @tool
        def search_transportation(place: str) -> str:
            """Search transport hubs (airport, train, bus) using Foursquare, fallback to Tavily."""
            try:
                res = self.foursquare.search_transportation(place)
                items = []
                for r in res.get("results", []) if isinstance(res, dict) else (res or []):
                    items.append(r.get("name", "Unnamed transport place"))
                if items:
                    return f"Transportation options in {place}:\n" + "\n".join(items)
            except Exception as e:
                tavily_result = self.tavily_search.tavily_search_transportation(place)
                return f"Foursquare search failed ({e}).\nFallback results:\n{tavily_result}"
            return f"No transportation info found for {place}."

        # Extra helpful tools using LocationIQ
        @tool
        def geocode_address(address: str) -> str:
            """Return lat/lon for a given address using LocationIQ."""
            if not self.locationiq:
                return "LocationIQ not configured"
            try:
                res = self.locationiq.forward_geocode(address)
                if isinstance(res, list) and len(res) > 0:
                    top = res[0]
                    return f"{top.get('display_name')} -> lat: {top.get('lat')}, lon: {top.get('lon')}"
                return "No geocode result"
            except Exception as e:
                return f"Geocode failed: {e}"

        @tool
        def get_directions(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> str:
            """Get directions from A to B using LocationIQ (if configured)."""
            if not self.locationiq:
                return "LocationIQ not configured"
            try:
                res = self.locationiq.get_directions(start_lat, start_lon, end_lat, end_lon)
                # summarize route distance/duration if available
                routes = res.get("routes") or res.get("features") or res
                # try to pick distance/duration from response
                if isinstance(routes, list) and len(routes) > 0:
                    route = routes[0]
                    # LocationIQ returns 'legs' with 'summary' possibly, be defensive
                    summary = []
                    distance = route.get("distance") or route.get("properties", {}).get("distance")
                    duration = route.get("duration") or route.get("properties", {}).get("duration")
                    if distance:
                        summary.append(f"Distance: {distance}")
                    if duration:
                        summary.append(f"Duration: {duration}")
                    return " ; ".join(summary) or "Directions found (see raw response)"
                return "No route found"
            except Exception as e:
                return f"Directions failed: {e}"

        return [search_attractions, search_restaurants, search_activities, search_transportation, geocode_address, get_directions]
