from datetime import date, timedelta
import streamlit as st

from api_clients.open_meteo import OpenMeteoClient
from api_clients.wikimedia import WikimediaClient
from agent.planner_agent import TripPlannerAgent
from db import init_schema
import lakebase
import config


st.set_page_config(page_title="TrailWise AI", page_icon="🧭", layout="wide")

st.title("🧭 TrailWise AI")
st.caption(
    "Databricks capstone: Spark + third-party APIs + Lakebase + AI Search/RAG + agent actions"
)

try:
    init_schema()
except Exception as exc:
    st.error(f"Lakebase initialization failed: {exc}")
    st.info(
        "Attach the Lakebase database resource before using the app. "
        "For local development, set DATABASE_URL."
    )
    st.stop()

with st.sidebar:
    st.header("Traveler")
    email = st.text_input("Email", value="demo@example.com")
    display_name = st.text_input("Name", value="Demo Traveler")
    user = lakebase.ensure_user(email, display_name)

    st.divider()
    st.header("Create trip")
    trip_name = st.text_input("Trip name", value="Weekend Adventure")
    destination_input = st.text_input("Destination", value="Seattle")
    start_date = st.date_input("Start date", value=date.today() + timedelta(days=3))
    end_date = st.date_input("End date", value=date.today() + timedelta(days=5))

    if st.button("Create trip", type="primary", use_container_width=True):
        if end_date < start_date:
            st.error("End date must be on or after start date.")
        else:
            try:
                geo = OpenMeteoClient().geocode(destination_input)
                trip = lakebase.create_trip(
                    user["id"], trip_name, start_date, end_date, geo
                )
                st.session_state["trip_id"] = trip["id"]
                st.success(f"Created trip to {geo['name']}.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

trips = lakebase.list_trips(user["id"])
if not trips:
    st.info("Create your first trip from the sidebar.")
    st.stop()

trip_options = {f"{t['name']} — {t['destination_name']} ({t['start_date']})": t["id"] for t in trips}
default_id = st.session_state.get("trip_id", trips[0]["id"])
labels = list(trip_options.keys())
default_index = next((i for i, label in enumerate(labels) if trip_options[label] == default_id), 0)
selected_label = st.selectbox("Active trip", labels, index=default_index)
trip_id = trip_options[selected_label]
st.session_state["trip_id"] = trip_id
trip = lakebase.get_trip(trip_id)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Destination", trip["destination_name"])
c2.metric("Starts", str(trip["start_date"]))
c3.metric("Ends", str(trip["end_date"]))
c4.metric("Status", trip["status"])

tab_plan, tab_discover, tab_weather, tab_packing = st.tabs(
    ["🤖 AI Planner", "🔎 Discover", "🌦️ Weather", "🎒 Packing"]
)

with tab_plan:
    st.subheader("Ask the trip agent")
    st.write(
        "Try: **Build me a day-by-day itinerary with scenic outdoor activities and coffee. "
        "Check the weather and save the plan.**"
    )

    chat_key = f"chat_{trip_id}"
    st.session_state.setdefault(chat_key, [])

    for msg in st.session_state[chat_key]:
        if msg["role"] in {"user", "assistant"}:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    prompt = st.chat_input("Plan or change this trip...")
    if prompt:
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Planning and using tools..."):
                try:
                    agent = TripPlannerAgent(trip_id)
                    history = [
                        m for m in st.session_state[chat_key][:-1]
                        if m["role"] in {"user", "assistant"}
                    ]
                    result = agent.run(prompt, conversation=history)
                    answer = result["answer"]
                    st.markdown(answer)
                    st.session_state[chat_key].append(
                        {"role": "assistant", "content": answer}
                    )
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    st.subheader("Saved itinerary")
    itinerary = lakebase.get_itinerary(trip_id)
    if itinerary:
        st.dataframe(itinerary, use_container_width=True, hide_index=True)
    else:
        st.caption("No itinerary items saved yet.")

with tab_discover:
    st.subheader("Seed destination content")
    st.write(
        "This fetches nearby Wikipedia attraction text into Lakebase for inspection. "
        "The Spark ingestion job writes the full retrieval corpus to a Delta table for AI Search."
    )
    if st.button("Fetch nearby attractions"):
        try:
            with st.spinner("Fetching Wikimedia destination context..."):
                pages = WikimediaClient().nearby_pages(
                    trip["latitude"], trip["longitude"], radius_m=15000, limit=25
                )
                count = lakebase.save_activities(trip["destination_id"], pages)
            st.success(f"Saved/updated {count} attraction records.")
        except Exception as exc:
            st.error(str(exc))

    activities = lakebase.list_activities(trip["destination_id"])
    for a in activities[:15]:
        with st.expander(a["title"]):
            st.write(a["description"])
            if a.get("source_url"):
                st.caption(a["source_url"])

with tab_weather:
    st.subheader("Weather-aware planning")
    check_date = st.date_input(
        "Forecast date",
        value=max(date.today(), trip["start_date"]),
        min_value=trip["start_date"],
        max_value=trip["end_date"],
        key=f"weather_{trip_id}",
    )
    if st.button("Check weather"):
        try:
            summary = OpenMeteoClient().daily_summary(
                trip["latitude"],
                trip["longitude"],
                check_date,
                timezone=trip["timezone"] or "auto",
            )
            lakebase.save_weather_snapshot(trip["destination_id"], summary)
            st.json(summary)
        except Exception as exc:
            st.error(str(exc))

with tab_packing:
    st.subheader("Packing list")
    packing = lakebase.list_packing_items(trip_id)
    if packing:
        st.dataframe(packing, use_container_width=True, hide_index=True)
    else:
        st.caption("No packing items yet. Ask the agent to build one.")
