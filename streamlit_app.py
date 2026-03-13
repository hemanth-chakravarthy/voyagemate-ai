# streamlit_app.py (minimal, clean)
import streamlit as st
import requests
import datetime
import os

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="VoyageMate AI", layout="centered")
st.title("🌍 VoyageMate AI")

st.markdown("Enter where you'd like to go (e.g., 'Plan a trip to Gokarna for 5 days').")

if "history" not in st.session_state:
    st.session_state.history = []

with st.form("plan_form", clear_on_submit=True):
    q = st.text_input("Plan request", placeholder="e.g. Goa, 5 days")
    submit = st.form_submit_button("Generate Plan")

if submit and q.strip():
    st.session_state.history.append({"q": q, "time": datetime.datetime.now().isoformat()})
    with st.spinner("Generating itinerary..."):
        try:
            resp = requests.post(f"{BASE_URL}/query", json={"question": q}, timeout=60)
            if resp.status_code != 200:
                st.error(f"Backend error ({resp.status_code}): {resp.text}")
            else:
                data = resp.json()

                st.header("Itinerary")
                st.write(f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
                st.write(f"**Query:** {q}")
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

        except Exception as e:
            st.error(f"Failed to get plan: {e}")

# simple recent history UI
if st.session_state.history:
    st.markdown("---")
    st.subheader("Recent requests")
    for item in reversed(st.session_state.history[-6:]):
        st.write(f"- {item['q']} ({item['time']})")
