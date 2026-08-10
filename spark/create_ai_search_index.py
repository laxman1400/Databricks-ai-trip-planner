# Databricks notebook source
# MAGIC %md
# MAGIC # Create the Databricks AI Search index
# MAGIC
# MAGIC Recommended for the capstone:
# MAGIC - Source table: `main.trip_planner.attraction_documents`
# MAGIC - Primary key: `document_id`
# MAGIC - Text/embedding source column: `content`
# MAGIC - Endpoint: Standard
# MAGIC - Sync: Triggered for the demo, or Continuous if preferred
# MAGIC - Search type: Hybrid if available in your workspace
# MAGIC
# MAGIC The simplest and least error-prone setup is through Catalog Explorer:
# MAGIC 1. Open `main.trip_planner.attraction_documents`.
# MAGIC 2. Create an AI Search index.
# MAGIC 3. Select `document_id` as the primary key.
# MAGIC 4. Let Databricks compute embeddings from `content`.
# MAGIC 5. Keep `destination`, `title`, `source_url`, `latitude`, and `longitude`
# MAGIC    as metadata columns.
# MAGIC 6. Attach the created index to the Databricks App using resource key
# MAGIC    `vector-search-index`.
# MAGIC
# MAGIC This notebook intentionally keeps index creation in the UI so it works
# MAGIC across workspaces where available embedding endpoints/models differ.

print("Source table: main.trip_planner.attraction_documents")
print("Create the AI Search index in Catalog Explorer, then attach it to the app.")
