import json
from databricks.sdk import WorkspaceClient

import config
from agent.tools import TOOL_DEFINITIONS, ToolRegistry


SYSTEM_PROMPT = """
You are TrailWise AI, a weather-aware trip-planning agent.

Your responsibilities:
1. Use semantic search to discover attractions and activities instead of inventing places.
2. Check weather before scheduling outdoor activities when the trip is within forecast range.
3. Use database write tools when the user asks you to create, change, move, remove, or save something.
4. Explain weather-driven changes clearly.
5. Avoid destructive changes unless the user requested them.
6. Stay within the trip's start and end dates.
7. If forecast data is unavailable because the trip is too far in the future, say so and build a provisional plan.
8. When building an itinerary, first read the existing itinerary to avoid accidental duplicates.
9. Include concise source-aware explanations for recommendations returned by search.
"""


def _json_safe(value):
    return json.loads(json.dumps(value, default=str))


class TripPlannerAgent:
    def __init__(self, trip_id):
        if not config.MODEL_ENDPOINT:
            raise RuntimeError(
                "DATABRICKS_MODEL_ENDPOINT is missing. Attach a tool-capable "
                "Model Serving endpoint to the app."
            )
        self.trip_id = int(trip_id)
        self.registry = ToolRegistry(trip_id)
        w = WorkspaceClient()
        self.client = w.serving_endpoints.get_open_ai_client()

    def run(self, user_message, conversation=None, max_tool_rounds=8):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation:
            messages.extend(conversation[-12:])
        messages.append({"role": "user", "content": user_message})

        for _ in range(max_tool_rounds):
            response = self.client.chat.completions.create(
                model=config.MODEL_ENDPOINT,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.2,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []

            if not tool_calls:
                return {
                    "answer": message.content or "",
                    "messages": messages
                    + [{"role": "assistant", "content": message.content or ""}],
                }

            assistant_tool_message = {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_tool_message)

            for tool_call in tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                    result = self.registry.execute(tool_call.function.name, args)
                    payload = {"ok": True, "result": _json_safe(result)}
                except Exception as exc:
                    payload = {"ok": False, "error": str(exc)}

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(payload, default=str),
                    }
                )

        return {
            "answer": (
                "I reached the tool-call safety limit before completing the request. "
                "Please ask me to continue with the current trip."
            ),
            "messages": messages,
        }
