# TrailWise AI — Databricks AI Trip & Outdoor Activity Planner

TrailWise AI is a capstone project that combines:

- a Spark ingestion pipeline,
- Open-Meteo weather/geocoding/air-quality APIs,
- Wikimedia unstructured destination content,
- Lakebase PostgreSQL transactional state,
- Databricks AI Search for semantic retrieval/RAG,
- a tool-calling AI agent,
- and a Streamlit frontend deployed as a Databricks App.

## 1. Rubric mapping

| Requirement | Implementation |
|---|---|
| Spark pipeline | `spark/ingest_attractions.py` and `spark/ingest_weather.py` |
| Third-party API | Open-Meteo + Wikimedia |
| Unstructured data | Wikipedia attraction/destination descriptions |
| Databricks App | Streamlit `app.py` |
| Lakebase | Trips, destinations, activities, itinerary, weather snapshots, packing |
| Embeddings/RAG | AI Search index over `attraction_documents.content` |
| Agent reads | itinerary, weather, semantic attraction search |
| Agent writes | add/move/remove itinerary items; add packing items |
| Observable agent actions | `agent_action_log` |

## 2. Architecture

```text
Open-Meteo ─┐
             ├─> Spark ingestion ─> Delta tables ─> Databricks AI Search
Wikimedia ───┘                                      │
                                                   RAG
                                                    │
User ─> Databricks App / Streamlit ─> AI Agent ─────┼─> Lakebase reads
                                      │             └─> Lakebase writes
                                      └─> Open-Meteo live weather tools
```

Lakebase is used for mutable application state. Delta + AI Search is used for the
unstructured retrieval corpus.

## 3. Repository

```text
app.py
app.yaml
requirements.txt
config.py
db.py
lakebase.py
api_clients/
  open_meteo.py
  wikimedia.py
agent/
  planner_agent.py
  tools.py
rag/
  search.py
spark/
  ingest_attractions.py
  ingest_weather.py
  create_ai_search_index.py
sql/
  schema.sql
```

## 4. Step 1 — Create the Databricks App

Create a custom Databricks App or start from the Streamlit template.

Sync this repository into the app source directory.

The app expects three resources:

1. Lakebase Autoscaling database
   - resource key: `postgres`
   - permission: **Can connect and create**

2. AI Search index
   - resource key: `vector-search-index`
   - permission: **Can select**

3. Model Serving endpoint
   - resource key: `serving-endpoint`
   - permission: **Can query**
   - choose a model endpoint that supports function/tool calling

`app.yaml` maps these resources to runtime environment variables.

## 5. Step 2 — Lakebase

Create a Lakebase Autoscaling project/database.

When you attach it to the app as the `postgres` resource, Databricks supplies the
Postgres connection environment variables for the first database resource.

This project uses OAuth database credentials generated at connection time by the
Databricks Python SDK. The token becomes the temporary Postgres password.

The app automatically executes `sql/schema.sql` on startup.

Tables:

- `users`
- `trips`
- `destinations`
- `activities`
- `itinerary_items`
- `weather_snapshots`
- `packing_items`
- `agent_action_log`

## 6. Step 3 — Run the Spark pipelines

Run `spark/ingest_attractions.py` on Databricks compute.

Before running, change these values if needed:

```python
CATALOG = "main"
SCHEMA = "trip_planner"
DESTINATIONS = ["Seattle", "Denver", "Chicago"]
```

The job:

1. calls Open-Meteo Geocoding,
2. calls Wikimedia Geosearch + page extracts,
3. creates a Spark DataFrame,
4. cleans and deduplicates unstructured text,
5. writes `main.trip_planner.attraction_documents`,
6. enables Delta Change Data Feed.

Run `spark/ingest_weather.py` to create an additional structured forecast table.

## 7. Step 4 — Build AI Search / RAG

After `attraction_documents` exists:

1. Open the table in Catalog Explorer.
2. Create an AI Search index.
3. Use `document_id` as the primary key.
4. Configure Databricks-managed embeddings from the `content` column.
5. Keep these metadata fields:
   - `destination`
   - `title`
   - `source_url`
   - `latitude`
   - `longitude`
6. For a small capstone dataset, a Standard endpoint is sufficient.
7. Trigger index sync.
8. Attach the index to your app using resource key `vector-search-index`.

`rag/search.py` queries the attached index using the app service principal.

## 8. Step 5 — Agent

`agent/planner_agent.py` calls the model endpoint with tools.

Read/RAG tools:

- `search_activities`
- `get_weather`
- `get_itinerary`

Write/action tools:

- `add_itinerary_item`
- `move_itinerary_item`
- `remove_itinerary_item`
- `add_packing_item`

The important capstone behavior is that the agent does not merely generate text.
When the user asks it to save or modify a plan, it performs an actual Lakebase
transaction.

## 9. Step 6 — Deploy

Deploy the app after the three resources are attached.

Example CLI flow:

```bash
databricks sync . /Workspace/Users/<your-email>/trailwise-ai
databricks apps deploy <your-app-name> \
  --source-code-path /Workspace/Users/<your-email>/trailwise-ai
```

## 10. Demo flow

### Demo A — Build and save an itinerary

Prompt:

> I like scenic views, easy hikes, coffee, and photography. Build a three-day
> itinerary for this trip. Check the weather and save the itinerary.

Expected behavior:

1. agent searches AI Search,
2. agent checks weather,
3. agent chooses activities,
4. agent calls `add_itinerary_item` repeatedly,
5. the saved rows appear immediately in the UI.

### Demo B — Weather-driven change

Prompt:

> Check the forecast again. If any outdoor activity is on the worst-weather day,
> move it to a better day and explain the change.

Expected behavior:

1. `get_itinerary`
2. `get_weather`
3. `move_itinerary_item`
4. explanation to the user
5. persistent change in Lakebase

### Demo C — Packing

Prompt:

> Build a packing list for this itinerary and current forecast.

Expected behavior:

1. agent reads itinerary/weather,
2. generates practical items,
3. calls `add_packing_item`,
4. packing tab displays persisted rows.

## 11. Suggested evaluator talking points

- "Lakebase is my OLTP layer because itinerary edits are transactional and must
  persist across app sessions."
- "The unstructured corpus is stored in Delta because Spark prepares it and AI
  Search indexes it for RAG."
- "The agent has explicit read and write tools, so it can take actions rather
  than only answer questions."
- "Weather is fetched live for user actions, while the Spark forecast pipeline
  demonstrates repeatable ingestion and analytics."
- "Agent changes are auditable in `agent_action_log`."

## 12. Known limitations / next improvements

- Wikipedia is useful for an educational project but not a complete travel
  inventory.
- Forecast-driven replanning only works when the trip is inside the forecast
  window.
- A production system should add operating hours, travel time, reservation
  availability, budgets, and stronger itinerary constraint solving.
- Add MLflow tracing/evaluation to score RAG retrieval and agent tool behavior.
- Add a Lakeflow Job to refresh destination/weather data on a schedule.
