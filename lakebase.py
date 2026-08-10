import json
from db import execute, fetch_all, fetch_one


def ensure_user(email, display_name=None):
    row = execute(
        """
        INSERT INTO users(email, display_name)
        VALUES (%s, %s)
        ON CONFLICT(email)
        DO UPDATE SET display_name = COALESCE(EXCLUDED.display_name, users.display_name)
        RETURNING id, email, display_name
        """,
        (email, display_name),
        returning=True,
    )
    return row


def create_trip(user_id, name, start_date, end_date, destination):
    trip = execute(
        """
        INSERT INTO trips(user_id, name, start_date, end_date)
        VALUES (%s, %s, %s, %s)
        RETURNING id, user_id, name, start_date, end_date, status
        """,
        (user_id, name, start_date, end_date),
        returning=True,
    )
    execute(
        """
        INSERT INTO destinations(
            trip_id, name, country, latitude, longitude, timezone, description
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            trip["id"],
            destination["name"],
            destination.get("country"),
            destination["latitude"],
            destination["longitude"],
            destination.get("timezone"),
            destination.get("description"),
        ),
    )
    return get_trip(trip["id"])


def list_trips(user_id):
    return fetch_all(
        """
        SELECT t.*, d.name AS destination_name, d.country,
               d.latitude, d.longitude, d.timezone
        FROM trips t
        JOIN destinations d ON d.trip_id = t.id
        WHERE t.user_id = %s
        ORDER BY t.start_date DESC, t.id DESC
        """,
        (user_id,),
    )


def get_trip(trip_id):
    return fetch_one(
        """
        SELECT t.*, d.id AS destination_id, d.name AS destination_name,
               d.country, d.latitude, d.longitude, d.timezone,
               d.description AS destination_description
        FROM trips t
        JOIN destinations d ON d.trip_id = t.id
        WHERE t.id = %s
        """,
        (trip_id,),
    )


def save_activities(destination_id, activities):
    saved = 0
    for a in activities:
        execute(
            """
            INSERT INTO activities(
                destination_id, external_id, title, source_type, source_url,
                description, latitude, longitude, metadata_json
            )
            VALUES (%s, %s, %s, 'wikimedia', %s, %s, %s, %s, %s)
            ON CONFLICT(destination_id, source_type, external_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                source_url = EXCLUDED.source_url,
                description = EXCLUDED.description,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                destination_id,
                a.get("external_id"),
                a.get("title"),
                a.get("source_url"),
                a.get("description"),
                a.get("latitude"),
                a.get("longitude"),
                json.dumps(
                    {
                        "distance_m": a.get("distance_m"),
                        "image_url": a.get("image_url"),
                    }
                ),
            ),
        )
        saved += 1
    return saved


def list_activities(destination_id, limit=50):
    return fetch_all(
        """
        SELECT id, title, source_url, description, latitude, longitude, metadata_json
        FROM activities
        WHERE destination_id = %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (destination_id, limit),
    )


def get_itinerary(trip_id):
    return fetch_all(
        """
        SELECT id, item_date, start_time, end_time, title, location,
               notes, source, sort_order
        FROM itinerary_items
        WHERE trip_id = %s
        ORDER BY item_date, sort_order, start_time NULLS LAST, id
        """,
        (trip_id,),
    )


def add_itinerary_item(
    trip_id,
    item_date,
    title,
    start_time=None,
    end_time=None,
    location=None,
    notes=None,
    source="agent",
    sort_order=0,
):
    row = execute(
        """
        INSERT INTO itinerary_items(
            trip_id, item_date, start_time, end_time, title, location,
            notes, source, sort_order
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, trip_id, item_date, start_time, end_time, title,
                  location, notes, source, sort_order
        """,
        (
            trip_id,
            item_date,
            start_time,
            end_time,
            title,
            location,
            notes,
            source,
            sort_order,
        ),
        returning=True,
    )
    log_action(trip_id, "add_itinerary_item", row, f"Added {title}")
    return row


def move_itinerary_item(item_id, new_date, new_start_time=None, reason=None):
    existing = fetch_one(
        "SELECT id, trip_id, title FROM itinerary_items WHERE id = %s", (item_id,)
    )
    if not existing:
        raise ValueError(f"Itinerary item {item_id} was not found.")

    row = execute(
        """
        UPDATE itinerary_items
        SET item_date = %s,
            start_time = COALESCE(%s, start_time),
            notes = CASE
                WHEN %s IS NULL THEN notes
                WHEN notes IS NULL OR notes = '' THEN %s
                ELSE notes || E'\n' || %s
            END,
            updated_at = NOW()
        WHERE id = %s
        RETURNING id, trip_id, item_date, start_time, title, notes
        """,
        (
            new_date,
            new_start_time,
            reason,
            reason,
            reason,
            item_id,
        ),
        returning=True,
    )
    log_action(
        existing["trip_id"],
        "move_itinerary_item",
        row,
        f"Moved {existing['title']} to {new_date}",
    )
    return row


def remove_itinerary_item(item_id):
    existing = fetch_one(
        "SELECT id, trip_id, title FROM itinerary_items WHERE id = %s", (item_id,)
    )
    if not existing:
        raise ValueError(f"Itinerary item {item_id} was not found.")
    execute("DELETE FROM itinerary_items WHERE id = %s", (item_id,))
    log_action(
        existing["trip_id"],
        "remove_itinerary_item",
        {"item_id": item_id},
        f"Removed {existing['title']}",
    )
    return {"removed": True, "item_id": item_id, "title": existing["title"]}


def add_packing_item(trip_id, item, reason=None):
    row = execute(
        """
        INSERT INTO packing_items(trip_id, item, reason)
        VALUES (%s, %s, %s)
        ON CONFLICT(trip_id, item)
        DO UPDATE SET reason = COALESCE(EXCLUDED.reason, packing_items.reason)
        RETURNING id, trip_id, item, reason, packed
        """,
        (trip_id, item, reason),
        returning=True,
    )
    log_action(trip_id, "add_packing_item", row, f"Added packing item: {item}")
    return row


def list_packing_items(trip_id):
    return fetch_all(
        """
        SELECT id, item, reason, packed
        FROM packing_items
        WHERE trip_id = %s
        ORDER BY packed, item
        """,
        (trip_id,),
    )


def save_weather_snapshot(destination_id, summary):
    if not summary.get("available"):
        return None
    return execute(
        """
        INSERT INTO weather_snapshots(
            destination_id, forecast_date, min_temp_c, max_temp_c,
            precipitation_probability, weather_code, wind_speed_kmh,
            aqi, uv_index, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, destination_id, forecast_date, fetched_at
        """,
        (
            destination_id,
            summary["date"],
            summary.get("min_temp_c"),
            summary.get("max_temp_c"),
            summary.get("precipitation_probability"),
            summary.get("weather_code"),
            summary.get("wind_speed_kmh"),
            summary.get("aqi"),
            summary.get("uv_index"),
            json.dumps(summary),
        ),
        returning=True,
    )


def log_action(trip_id, action_name, payload, result_summary):
    execute(
        """
        INSERT INTO agent_action_log(
            trip_id, action_name, action_payload, result_summary
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            trip_id,
            action_name,
            json.dumps(payload, default=str),
            result_summary,
        ),
    )
