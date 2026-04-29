# streamlit_app.py (minimal, clean)
import streamlit as st
import requests
import datetime
import os
import uuid

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="VoyageMate AI", layout="centered")
st.title("🌍 VoyageMate AI")

st.markdown("Enter where you'd like to go (e.g., 'Plan a trip to Gokarna for 5 days').")

if "history" not in st.session_state:
    st.session_state.history = []
if "plan_data" not in st.session_state:
    st.session_state.plan_data = None
if "plan_meta" not in st.session_state:
    st.session_state.plan_meta = {}

with st.form("plan_form", clear_on_submit=False):
    # 1. Main Search Bar
    st.subheader("Where are you going?")
    q = st.text_input("", placeholder="e.g. Paris for 3 days, Goa for a weekend", label_visibility="collapsed")
    
    # 2. Trip Preferences (Simplified)
    with st.expander("✨ Personalize your trip", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            budget_range = st.selectbox("Budget", ["low", "mid", "high"], index=1)
            travel_style = st.selectbox("Travel style", ["backpacking", "luxury"], index=0)
        with col2:
            food_preference = st.selectbox("Food preference", ["veg", "non-veg"], index=0)
            preferred_places = st.text_input("Interests", placeholder="beach, history")
            
    # 3. Advanced Settings (Hidden by default)
    with st.expander("⚙️ Advanced Settings", expanded=False):
        col3, col4 = st.columns(2)
        with col3:
            user_id = st.text_input("User ID", value="user_123")
            fast_mode = st.checkbox("Fast mode", value=True)
            minimal_mode = st.checkbox("Minimal plan", value=True)
        with col4:
            instant_mode = st.checkbox("Instant mode", value=False)
            compact = st.checkbox("Concise output", value=True)
            use_stored_profile = st.checkbox("Use stored profile", value=True)
            show_debug = st.checkbox("Show debug details", value=False)

    submit = st.form_submit_button("Generate My Plan", use_container_width=True)


if submit and q.strip():
    st.session_state.history.append({"q": q, "time": datetime.datetime.now().isoformat()})
    with st.spinner("Generating itinerary..."):
        try:
            profile_payload = {
                "budget_range": budget_range,
                "travel_style": travel_style,
                "preferred_places": [p.strip() for p in preferred_places.split(",") if p.strip()],
                "food_preference": food_preference,
            }
            if use_stored_profile:
                profile_payload = {}
            plan_id = str(uuid.uuid4())
            resp = requests.post(
                f"{BASE_URL}/query",
                json={"question": q + ("\nPlease keep the response concise." if compact else ""), "user_id": user_id, "profile": profile_payload, "fast_mode": fast_mode, "minimal_mode": minimal_mode, "instant_mode": instant_mode},
                timeout=120,
            )
            if resp.status_code != 200:
                st.error(f"Backend error ({resp.status_code}): {resp.text}")
            else:
                data = resp.json()
                server_plan_id = data.get("plan_id") or plan_id
                st.session_state.plan_data = data
                st.session_state.plan_meta = {
                    "query": q,
                    "generated_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                    "plan_id": server_plan_id,
                    "user_id": user_id,
                }

        except Exception as e:
            st.error(f"Failed to get plan: {e}")

# Render last plan if present
if st.session_state.plan_data:
    data = st.session_state.plan_data
    meta = st.session_state.plan_meta

    st.header("Itinerary")
    st.write(f"**Generated:** {meta.get('generated_at','')}")
    st.write(f"**Query:** {meta.get('query','')}")
    if show_debug:
        st.write(f"**Plan ID:** {meta.get('plan_id','')}")
    st.markdown("---")

    # WEATHER first, as a separate block (if present)
    if data.get("weather"):
        st.subheader("Weather")
        st.markdown(data["weather"].replace("\n", "  \n"))

    # DAY-BY-DAY prioritized
    day_by_day = data.get("day_by_day", []) or []
    if day_by_day:
        st.subheader("Day-by-day itinerary")
        for d in day_by_day:
            title = d.get("day", "Day")
            with st.expander(title, expanded=False):
                st.markdown(d.get("text", "").replace("\n", "  \n") or "—")
    else:
        # fallbacks to generic/offbeat plans
        if data.get("generic_plan"):
            st.subheader("Generic Tourist Plan")
            st.markdown(data["generic_plan"].replace("\n", "  \n"))
        if data.get("offbeat_plan"):
            st.subheader("Off-Beat Plan")
            st.markdown(data["offbeat_plan"].replace("\n", "  \n"))
        if not data.get("generic_plan") and not data.get("offbeat_plan"):
            # finally show raw
            st.subheader("Full Plan (raw)")
            st.markdown(data.get("raw", "").replace("\n", "  \n"))

    # Cost summary (if available)
    costs = data.get("costs", {}) or {}
    if costs:
        st.subheader("Cost summary")
        total = costs.get("Total") or sum(v for v in costs.values())
        st.write(f"**Estimated total:** ₹{total:,}")
        with st.expander("Cost breakdown"):
            for k, v in costs.items():
                st.write(f"- {k}: ₹{v:,}")

    # Tools used (debug) collapsed
    tools = data.get("tools_used", []) or []
    if tools:
        with st.expander("Tools used (debug)", expanded=False):
            st.write(", ".join(tools))

    # raw download
    with st.expander("Full raw text", expanded=False):
        st.code(data.get("raw", ""), language="text")
    st.download_button("Download itinerary (TXT)", data=data.get("raw",""), file_name="itinerary.txt", mime="text/plain")

    st.markdown("---")
    st.subheader("Feedback")
    rating = st.slider("Rating", min_value=1, max_value=5, value=4, key="rating")
    feedback_text = st.text_area("What should be improved?", value="", key="feedback_text")
    if st.button("Submit Feedback"):
        fb_resp = requests.post(
            f"{BASE_URL}/feedback",
            json={
                "user_id": meta.get("user_id", "anonymous"),
                "plan_id": meta.get("plan_id", ""),
                "rating": rating,
                "feedback": feedback_text,
            },
            timeout=60,
        )
        if fb_resp.status_code == 200:
            st.success("Feedback saved")
        else:
            st.error(f"Feedback error ({fb_resp.status_code}): {fb_resp.text}")

# simple recent history UI
if st.session_state.history:
    st.markdown("---")
    st.subheader("Recent requests")
    for item in reversed(st.session_state.history[-6:]):
        st.write(f"- {item['q']} ({item['time']})")
