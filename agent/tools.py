from api_clients.open_meteo import OpenMeteoClient
from rag.search import semantic_search
import lakebase


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_activities",
            "description": "Semantic RAG search for attractions and activities suitable for the trip.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather and air-quality summary for a trip date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format.",
                    }
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_itinerary",
            "description": "Read the current saved itinerary for the trip.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_itinerary_item",
            "description": "Persist a new activity to the trip itinerary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "title": {"type": "string"},
                    "start_time": {
                        "type": ["string", "null"],
                        "description": "HH:MM, or null.",
                    },
                    "location": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
                "required": ["date", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_itinerary_item",
            "description": "Move a saved itinerary item to another day/time and record the reason.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "new_date": {"type": "string"},
                    "new_start_time": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]},
                },
                "required": ["item_id", "new_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_itinerary_item",
            "description": "Delete an itinerary item from the saved trip.",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "integer"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_packing_item",
            "description": "Persist an item to the packing list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "reason": {"type": ["string", "null"]},
                },
                "required": ["item"],
            },
        },
    },
]


class ToolRegistry:
    def __init__(self, trip_id):
        self.trip_id = int(trip_id)
        self.weather = OpenMeteoClient()

    def execute(self, name, arguments):
        trip = lakebase.get_trip(self.trip_id)
        if not trip:
            raise ValueError(f"Trip {self.trip_id} not found.")

        if name == "search_activities":
            query = arguments["query"]
            # Destination is included in the semantic query because it is robust
            # across standard and storage-optimized index configurations.
            combined = f"{query}. Destination: {trip['destination_name']}."
            return semantic_search(
                combined,
                destination=None,
                num_results=arguments.get("num_results", 8),
            )

        if name == "get_weather":
            summary = self.weather.daily_summary(
                trip["latitude"],
                trip["longitude"],
                arguments["date"],
                timezone=trip.get("timezone") or "auto",
            )
            lakebase.save_weather_snapshot(trip["destination_id"], summary)
            return summary

        if name == "get_itinerary":
            return lakebase.get_itinerary(self.trip_id)

        if name == "add_itinerary_item":
            return lakebase.add_itinerary_item(
                trip_id=self.trip_id,
                item_date=arguments["date"],
                title=arguments["title"],
                start_time=arguments.get("start_time"),
                location=arguments.get("location"),
                notes=arguments.get("notes"),
            )

        if name == "move_itinerary_item":
            return lakebase.move_itinerary_item(
                item_id=arguments["item_id"],
                new_date=arguments["new_date"],
                new_start_time=arguments.get("new_start_time"),
                reason=arguments.get("reason"),
            )

        if name == "remove_itinerary_item":
            return lakebase.remove_itinerary_item(arguments["item_id"])

        if name == "add_packing_item":
            return lakebase.add_packing_item(
                self.trip_id,
                arguments["item"],
                arguments.get("reason"),
            )

        raise ValueError(f"Unknown tool: {name}")
