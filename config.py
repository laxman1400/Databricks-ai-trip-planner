import os

APP_NAME = "TrailWise AI"
MODEL_ENDPOINT = os.getenv("DATABRICKS_MODEL_ENDPOINT", "")
AI_SEARCH_INDEX = os.getenv("AI_SEARCH_INDEX", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

PGHOST = os.getenv("PGHOST", "")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("PGDATABASE", "databricks_postgres")
PGUSER = os.getenv("PGUSER", "")
PGSSLMODE = os.getenv("PGSSLMODE", "require")
ENDPOINT_NAME = os.getenv("ENDPOINT_NAME", "")

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WIKIMEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
