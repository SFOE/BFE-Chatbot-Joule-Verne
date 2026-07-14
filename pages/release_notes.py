import streamlit as st
import json
import os

st.set_page_config(page_title="Release Notes", page_icon="📋")

st.title("📋 Release Notes")

RELEASE_FILE = os.path.join(os.path.dirname(__file__), "..", "release_notes.json")


@st.cache_data
def load_releases():
    """Load pre-fetched release notes from JSON file."""
    try:
        with open(RELEASE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


releases = load_releases()

if releases is None:
    st.info("Keine Release Notes verfügbar.")
elif len(releases) == 0:
    st.info("Noch keine Releases vorhanden.")
else:
    for release in releases:
        name = release.get("name", "")
        date = release.get("date", "")
        body = release.get("body", "")
        prerelease = release.get("prerelease", False)

        header = f"## {name}"
        if prerelease:
            header += " 🧪 Pre-release"

        st.markdown(header)
        if date:
            st.caption(f"Veröffentlicht am {date}")
        if body:
            st.markdown(body)
        else:
            st.markdown("*Keine Beschreibung verfügbar.*")
        st.divider()
