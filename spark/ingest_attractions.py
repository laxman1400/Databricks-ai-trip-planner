# Databricks notebook source
# MAGIC %md
# MAGIC # Spark pipeline: destination attraction context
# MAGIC Fetches destination coordinates from Open-Meteo, nearby place text from
# MAGIC Wikimedia, transforms/deduplicates with Spark, and writes a Delta table
# MAGIC used as the source for Databricks AI Search.

# COMMAND ----------

import requests
from pyspark.sql import functions as F, types as T

CATALOG = "workspace"      # change if needed
SCHEMA = "trip_planner_latest"     # change if needed
TABLE = f"{CATALOG}.{SCHEMA}.attraction_documents"

DESTINATIONS = ["Seattle", "Denver", "Chicago"]  # add your demo destinations

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WIKI_URL = "https://en.wikipedia.org/w/api.php"

# COMMAND ----------

def geocode(place):
    r = requests.get(
        GEOCODE_URL,
        params={
            "name": place,
            "count": 1,
            "language": "en",
            "format": "json",
        },
        timeout=20,
    )

    r.raise_for_status()

    data = r.json()

    if not data.get("results"):
        raise ValueError(f"No geocoding results found for {place}")

    hit = data["results"][0]

    return {
        "destination": hit["name"],
        "country": hit.get("country"),
        "latitude": hit["latitude"],
        "longitude": hit["longitude"],
        "timezone": hit.get("timezone"),
    }


def wikimedia_nearby(lat, lon, destination, radius=10000, limit=50):

    headers = {
        "User-Agent": "TrailWiseAI-EducationalCapstone/1.0"
    }

    geo = requests.get(
        WIKI_URL,
        params={
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": radius,
            "gslimit": limit,
            "format": "json",
        },
        headers=headers,
        timeout=20,
    )

    geo.raise_for_status()

    geo_data = geo.json()

    # Catch Wikimedia API errors
    if "error" in geo_data:
        raise RuntimeError(
            f"Wikimedia API error: {geo_data['error']}"
        )

    hits = geo_data.get("query", {}).get("geosearch", [])

    print(
        f"{destination}: Wikimedia returned "
        f"{len(hits)} nearby pages"
    )

    if not hits:
        return []

    ids = "|".join(
        str(x["pageid"])
        for x in hits
    )

    details = requests.get(
        WIKI_URL,
        params={
            "action": "query",
            "pageids": ids,
            "prop": "extracts|info",
            "exintro": 1,
            "explaintext": 1,
            "inprop": "url",
            "format": "json",
        },
        headers=headers,
        timeout=20,
    )

    details.raise_for_status()

    details_data = details.json()

    if "error" in details_data:
        raise RuntimeError(
            f"Wikimedia details API error: "
            f"{details_data['error']}"
        )

    by_id = {
        str(x["pageid"]): x
        for x in hits
    }

    rows = []

    for pageid, page in (
        details_data
        .get("query", {})
        .get("pages", {})
        .items()
    ):

        hit = by_id.get(str(pageid), {})

        text = (
            page.get("extract") or ""
        ).strip()

        # Ignore pages with little/no useful text
        if len(text) < 80:
            continue

        rows.append(
            {
                "document_id": f"wikimedia:{pageid}",
                "destination": destination,
                "title": page.get("title"),
                "content": text,
                "source_url": page.get("fullurl"),
                "latitude": hit.get("lat"),
                "longitude": hit.get("lon"),
                "distance_m": hit.get("dist"),
                "source_type": "wikimedia",
            }
        )

    print(
        f"{destination}: {len(rows)} usable documents "
        f"after filtering"
    )

    return rows

# COMMAND ----------

raw_rows = []
for place in DESTINATIONS:
    loc = geocode(place)
    raw_rows.extend(
        wikimedia_nearby(
            loc["latitude"],
            loc["longitude"],
            loc["destination"],
        )
    )

schema = T.StructType(
    [
        T.StructField("document_id", T.StringType(), False),
        T.StructField("destination", T.StringType(), False),
        T.StructField("title", T.StringType(), True),
        T.StructField("content", T.StringType(), True),
        T.StructField("source_url", T.StringType(), True),
        T.StructField("latitude", T.DoubleType(), True),
        T.StructField("longitude", T.DoubleType(), True),
        T.StructField("distance_m", T.DoubleType(), True),
        T.StructField("source_type", T.StringType(), True),
    ]
)

df = spark.createDataFrame(raw_rows, schema=schema)

clean = (
    df.withColumn("content", F.regexp_replace("content", r"\s+", " "))
      .withColumn("content", F.trim("content"))
      .filter(F.length("content") >= 80)
      .dropDuplicates(["document_id"])
      .withColumn("ingested_at", F.current_timestamp())
)

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

(
    clean.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(TABLE)
)

spark.sql(
    f"ALTER TABLE {TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"
)

display(clean.select("destination", "title", "content", "source_url").limit(20))