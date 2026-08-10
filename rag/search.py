import os
from databricks.sdk import WorkspaceClient

import config


def semantic_search(query, destination=None, num_results=8):
    if not config.AI_SEARCH_INDEX:
        return {
            "configured": False,
            "results": [],
            "message": (
                "AI_SEARCH_INDEX is not configured. Attach your AI Search index "
                "to the app with resource key 'vector-search-index'."
            ),
        }

    w = WorkspaceClient()
    kwargs = {
        "index_name": config.AI_SEARCH_INDEX,
        "query_text": query,
        "num_results": num_results,
        "columns": [
            "document_id",
            "destination",
            "title",
            "content",
            "source_url",
            "latitude",
            "longitude",
        ],
    }

    # Standard AI Search indexes accept dict-style filters.
    if destination:
        kwargs["filters_json"] = f'{{"destination":"{destination}"}}'

    result = w.vector_search_indexes.query_index(**kwargs)
    payload = result.as_dict() if hasattr(result, "as_dict") else result

    manifest_cols = [
        c.get("name") if isinstance(c, dict) else getattr(c, "name", str(c))
        for c in payload.get("manifest", {}).get("columns", [])
    ]
    rows = payload.get("result", {}).get("data_array", [])

    parsed = []
    for row in rows:
        item = {}
        for i, value in enumerate(row):
            if i < len(manifest_cols):
                item[manifest_cols[i]] = value
            else:
                item[f"field_{i}"] = value
        parsed.append(item)

    return {"configured": True, "results": parsed}
