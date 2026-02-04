import streamlit as st
import geopandas as gpd
import io
import fiona
from shapely.geometry import shape, mapping
import os
import zipfile
import tempfile
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import osmnx as ox
import pandas as pd
import json

# Configure OSMnx
ox.settings.use_cache = True
ox.settings.log_console = False

st.set_page_config(page_title="Get Shapefiles", page_icon="🌍", layout="wide")

st.title("Geospatial Tools")

tab1, tab2 = st.tabs(["KML/KMZ Converter", "Interactive Tracing & Extraction"])

# --- TAB 1: KML Converter ---
with tab1:
    st.header("Convert KML/KMZ to Shapefile")
    
    uploaded_file = st.file_uploader("Upload KML or KMZ file", type=["kml", "kmz"])
    
    if uploaded_file:
        with tempfile.TemporaryDirectory() as tmpdirname:
            file_path = os.path.join(tmpdirname, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            kml_path = file_path
            if uploaded_file.name.lower().endswith('.kmz'):
                try:
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(tmpdirname)
                        for root, dirs, files in os.walk(tmpdirname):
                            for file in files:
                                if file.lower().endswith('.kml'):
                                    kml_path = os.path.join(root, file)
                                    break
                except Exception as e:
                    st.error(f"Error unzipping KMZ: {e}")
            
            try:
                fiona.drvsupport.supported_drivers['KML'] = 'rw'
                gdf = gpd.read_file(kml_path)
                
                st.success(f"Successfully loaded {len(gdf)} features.")
                st.write(gdf.head())
                
                # Cleanup columns
                for col in gdf.columns:
                    if pd.api.types.is_object_dtype(gdf[col]):
                        gdf[col] = gdf[col].astype(str)
                
                shp_buffer = io.BytesIO()
                with tempfile.TemporaryDirectory() as shp_dir:
                    out_path = os.path.join(shp_dir, "output.shp")
                    gdf.to_file(out_path)
                    
                    with zipfile.ZipFile(shp_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for filename in os.listdir(shp_dir):
                            if filename.startswith("output"):
                                zip_file.write(os.path.join(shp_dir, filename), filename)
                                
                st.download_button(
                    label="Download Shapefile (.zip)",
                    data=shp_buffer.getvalue(),
                    file_name="converted_shapefile.zip",
                    mime="application/zip"
                )
                
            except Exception as e:
                st.error(f"Error checking KML: {e}")

# --- TAB 2: OSMnx Extraction ---
with tab2:
    st.header("Trace & Extract Features")
    
    # Session State for Extraction
    if 'extracted_gdf' not in st.session_state:
        st.session_state['extracted_gdf'] = None
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        basemap_name = st.selectbox("Select Basemap", ["OpenStreetMap", "ESRI Satellite", "CartoDB Positron"])
    
    if basemap_name == "ESRI Satellite":
        tiles = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        attr = "Esri"
    elif basemap_name == "CartoDB Positron":
        tiles = "CartoDB positron"
        attr = None
    else:
        tiles = "OpenStreetMap"
        attr = None
    
    # Create Map
    # Map Center Persistence
    if 'map_center' not in st.session_state:
        st.session_state['map_center'] = [40.7128, -74.0060]
        
    m = folium.Map(location=st.session_state['map_center'], zoom_start=14, tiles=tiles, attr=attr)
    
    # Add Extracted Features if they exist
    if st.session_state['extracted_gdf'] is not None:
        folium.GeoJson(
            st.session_state['extracted_gdf'],
            name="Extracted Features",
            style_function=lambda x: {'color': 'blue', 'weight': 1, 'fillOpacity': 0.3},
            tooltip=folium.GeoJsonTooltip(fields=['unique_id'] if 'unique_id' in st.session_state['extracted_gdf'].columns else [])
        ).add_to(m)
    
    draw = Draw(
        export=False,
        filename='my_data.geojson',
        position='topleft',
        draw_options={'polyline': False, 'rectangle': True, 'circle': False, 'marker': False, 'circlemarker': False},
        edit_options={'poly': {'allowIntersection': False}}
    )
    draw.add_to(m)
    
    output = st_folium(m, width=1000, height=600)
    
    # Process Drawing
    if output and "all_drawings" in output and output["all_drawings"]:
        last_drawing = output["all_drawings"][-1]
        
        st.write("---")
        st.subheader("Extraction Settings")
        
        extract_type = st.multiselect("Features to Extract", ["Buildings", "Amenities", "Parks"], default=["Buildings"])
            
        if st.button("Extract Features"):
            try:
                poly_shape = shape(last_drawing['geometry'])
                
                tags = {}
                if "Buildings" in extract_type: tags['building'] = True
                if "Amenities" in extract_type: tags['amenity'] = True
                if "Parks" in extract_type: tags['leisure'] = 'park'
                
                # Create GDF for the Drawn Polygon
                poly_gdf = gpd.GeoDataFrame(
                    {'geometry': [poly_shape], 'type': ['Drawn Polygon'], 'name': ['Area of Interest']},
                    crs="EPSG:4326"
                )

                with st.spinner("Querying OpenStreetMap..."):
                    try:
                        gdf = ox.features_from_polygon(poly_shape, tags=tags)
                    except Exception:
                        gdf = gpd.GeoDataFrame() # Handle no result gracefully
                    
                if not gdf.empty:
                    st.success(f"Found {len(gdf)} features!")
                    gdf = gdf.reset_index()
                    # Ensure alignment for concat
                    final_gdf = pd.concat([poly_gdf, gdf], ignore_index=True)
                else:
                    st.warning("No features found in this area. Returning polygon only.")
                    final_gdf = poly_gdf
                
                # Update Map Center to Polygon Centroid
                centroid = poly_shape.centroid
                st.session_state['map_center'] = [centroid.y, centroid.x]
                
                st.session_state['extracted_gdf'] = final_gdf
                st.rerun()
                    
            except Exception as e:
                st.error(f"Error extracting features: {e}")

    # Download Section (Separate from logic to allow persistence)
    if st.session_state['extracted_gdf'] is not None:
        st.subheader("Download Data")
        download_format = st.radio("Download Format", ["Shapefile (.zip)", "GeoJSON"])
        
        gdf_out = st.session_state['extracted_gdf'].copy()
        
        # Format Prep
        # Shapefile requires string columns typically
        for col in gdf_out.columns:
            if pd.api.types.is_object_dtype(gdf_out[col]):
                gdf_out[col] = gdf_out[col].astype(str)
                
        if download_format == "Shapefile (.zip)":
            shp_buffer_o = io.BytesIO()
            with tempfile.TemporaryDirectory() as shp_dir_o:
                out_path_o = os.path.join(shp_dir_o, "features.shp")
                gdf_out.to_file(out_path_o)
                
                with zipfile.ZipFile(shp_buffer_o, "w", zipfile.ZIP_DEFLATED) as zip_file_o:
                    for filename in os.listdir(shp_dir_o):
                        if filename.startswith("features"):
                            zip_file_o.write(os.path.join(shp_dir_o, filename), filename)
            
            st.download_button(
                label="Download Extracted Shapefile",
                data=shp_buffer_o.getvalue(),
                file_name="osmnx_features.zip",
                mime="application/zip"
            )
        else:
            # GeoJSON
            geojson_str = gdf_out.to_json()
            st.download_button(
                label="Download Extracted GeoJSON",
                data=geojson_str,
                file_name="osmnx_features.geojson",
                mime="application/geo+json"
            )
