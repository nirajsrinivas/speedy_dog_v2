import streamlit as st
from PIL import Image
import os

st.set_page_config(
    page_title="Speedy Dog To Go",
    page_icon="🐕",
    layout="centered"
)

# Load and display logo at the top
try:
    # Path relative to where streamlit is run (usually project root)
    logo_path = os.path.join("src", "assets", "logo.png")
    if os.path.exists(logo_path):
        img = Image.open(logo_path)
        st.image(img, width=225)
    else:
        st.warning("Logo not found in assets.")
except Exception as e:
    st.error(f"Error loading logo: {e}")

st.title("Welcome to Speedy Dog Insurance Tools")
st.markdown("### Advanced Parametric Structuring & Geospatial Analysis")

st.markdown("""
Select a tool from the sidebar to begin:

*   **Hurricane Parametric**: Analyze historical hurricane tracks against your asset portfolio. Define parametric triggers based on Wind Speed and Central Pressure.
*   **Get Shapefiles**: Convert KML/KMZ files to Shapefiles, map polygons, and extract building footprints using OSMnx.
""")
