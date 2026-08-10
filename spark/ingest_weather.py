# Databricks notebook source
# MAGIC %md
# MAGIC # Spark pipeline: weather forecast snapshots
# MAGIC Calls Open-Meteo, normalizes daily forecasts with Spark, and persists
# MAGIC structured forecast data to Delta for analytics/evaluation.

# COMMAND ----------

import requests
from pyspark.sql import functions as F

CATALOG = "main"
SCHEMA = "trip_planner"
TABLE = f"{CATALOG}.{SCHEMA}.weather_forecasts"
DESTINATIONS = ["Seattle", "Denver", "Chicago"]

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# COMMAND ----------

rows = []
for place in DESTINATIONS:
    geo = requests.get(
        GEOCODE_URL,
        params={"name": place, "count": 1, "format": "json"},
        timeout=20,
    ).json()["results"][0]

    payload = requests.get(
        FORECAST_URL,
        params={
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "timezone": geo.get("timezone", "auto"),
            "forecast_days": 16,
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                    "uv_index_max",
                ]
            ),
        },
        timeout=20,
    ).json()

    d = payload["daily"]
    for i, day in enumerate(d["time"]):
        rows.append(
            {
                "destination": geo["name"],
                "forecast_date": day,
                "weather_code": d["weather_code"][i],
                "max_temp_c": d["temperature_2m_max"][i],
                "min_temp_c": d["temperature_2m_min"][i],
                "precip_probability": d["precipitation_probability_max"][i],
                "max_wind_kmh": d["wind_speed_10m_max"][i],
                "max_uv_index": d["uv_index_max"][i],
            }
        )

df = spark.createDataFrame(rows)

clean = (
    df.withColumn("forecast_date", F.to_date("forecast_date"))
      .dropDuplicates(["destination", "forecast_date"])
      .withColumn("ingested_at", F.current_timestamp())
)

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

(
    clean.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(TABLE)
)

display(clean.orderBy("destination", "forecast_date"))
