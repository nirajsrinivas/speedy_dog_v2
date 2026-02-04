import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from data_loader import load_data
from payout_engine import evaluate_portfolio_complex
import numpy as np

# Page Config
st.set_page_config(page_title="Hurricane Parametric Insurance", layout="wide")
st.title("Hurricane Parametric Insurance Structuring")

# --- Initialize Session State for Payout Profiles ---
if 'payout_profiles' not in st.session_state:
    # Default Profile
    default_df = pd.DataFrame({
        "Category": [1, 2, 3, 4, 5],
        "Min_Wind (kts)": [64, 83, 96, 113, 137],
        "Max_Pressure (mb)": [980, 965, 945, 920, 900], # Indicative thresholds
        "Payout_Pct": [0.10, 0.25, 0.50, 0.80, 1.00]
    })
    st.session_state['payout_profiles'] = {"Standard": default_df}
    
if 'profile_names' not in st.session_state:
    st.session_state['profile_names'] = ["Standard"]

# --- Sidebar Inputs ---

# 1. Trigger Methodology
st.sidebar.header("Methodology")
trigger_method_ui = st.sidebar.radio(
    "Trigger Calculation",
    ["Max Outcome (6-hr points)", "Interpolated Track"],
    index=1,
    help="'Interpolated' calculates intensity along the track path between points."
)
trigger_method = "interpolated" if "Interpolated" in trigger_method_ui else "max_outcome"

# 2. Payout Profiles Editor
st.sidebar.subheader("Payout Profiles")
selected_profile = st.sidebar.selectbox("Select Profile to Edit", st.session_state['profile_names'])

# Generic Editor for the selected profile table
# We want to allow user to add profiles too.
col_p1, col_p2 = st.sidebar.columns([2,1])
with col_p1:
    new_profile_name = st.text_input("New Profile Name")
with col_p2:
    if st.button("Add"):
        if new_profile_name and new_profile_name not in st.session_state['payout_profiles']:
            st.session_state['payout_profiles'][new_profile_name] = st.session_state['payout_profiles']["Standard"].copy()
            st.session_state['profile_names'].append(new_profile_name)
            st.rerun()

current_table = st.session_state['payout_profiles'][selected_profile]
edited_table = st.sidebar.data_editor(
    current_table,
    num_rows="dynamic",
    width="stretch",
    hide_index=True,
    key=f"editor_{selected_profile}"
)
# Update session state
st.session_state['payout_profiles'][selected_profile] = edited_table

# 3. Locations Input
st.sidebar.subheader("Locations")

# Default Data
default_locs = pd.DataFrame([
    {"Name": "Miami HQ", "Lat": 25.7617, "Lon": -80.1918, "Radius (mi)": 50.0, "Sublimit ($)": 1_000_000, "Profile": "Standard"},
    {"Name": "New Orleans Hub", "Lat": 29.9511, "Lon": -90.0715, "Radius (mi)": 50.0, "Sublimit ($)": 500_000, "Profile": "Standard"},
])

column_config = {
    "Name": st.column_config.TextColumn("Name", required=True),
    "Lat": st.column_config.NumberColumn("Lat", format="%.4f"),
    "Lon": st.column_config.NumberColumn("Lon", format="%.4f"),
    "Radius (mi)": st.column_config.NumberColumn("Radius", format="%.1f"),
    "Sublimit ($)": st.column_config.NumberColumn("Limit", format="$%d"),
    "Profile": st.column_config.SelectboxColumn("Profile", options=st.session_state['profile_names'], required=True)
}

locations_df = st.sidebar.data_editor(
    default_locs, 
    column_config=column_config,
    num_rows="dynamic",
    width="stretch",
    hide_index=True
)

aggregate_limit = st.sidebar.number_input("Aggregate Limit ($)", value=5_000_000, step=100_000)

# 4. Filters
st.sidebar.subheader("Filter Historical Data")
year_range = st.sidebar.slider("Year Range", 1900, 2026, (1980, 2026))

# --- Data Loading ---
@st.cache_data
def get_data():
    return load_data()

try:
    with st.spinner("Loading IBTrACS Data..."):
        df = get_data()
    st.sidebar.success(f"Source: {len(df):,} points")
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.stop()

# --- Logic Helper ---
def prep_payout_table(df_table):
    # Normalize column names for engine
    # Expected: Category, Min_Wind, Max_Pressure, Payout_Pct
    return df_table.rename(columns={
        "Min_Wind (kts)": "Min_Wind",
        "Max_Pressure (mb)": "Max_Pressure",
        "Payout_Pct": "Payout_Pct"
    })

# --- Analysis ---
if 'analysis_results' not in st.session_state:
    st.session_state['analysis_results'] = None

if st.button("Run Analysis"):
    df['Year'] = df['ISO_TIME'].dt.year
    filtered_df = df[(df['Year'] >= year_range[0]) & (df['Year'] <= year_range[1])]
    
    locations_list = []
    for _, row in locations_df.iterrows():
        locations_list.append({
            'Name': row['Name'],
            'lat': row['Lat'],
            'lon': row['Lon'],
            'radius_miles': float(row['Radius (mi)']),
            'sublimit': float(row['Sublimit ($)']),
            'Profile_Name': row['Profile']
        })
        
    # Prepare Profile Dict for Engine
    engine_profiles = {}
    for name, table in st.session_state['payout_profiles'].items():
        engine_profiles[name] = prep_payout_table(table)

    # Optimization
    max_radius = max([l['radius_miles'] for l in locations_list])
    deg_buffer = (max_radius / 60.0) + 1.0
    min_lat = min([l['lat'] for l in locations_list]) - deg_buffer
    max_lat = max([l['lat'] for l in locations_list]) + deg_buffer
    min_lon = min([l['lon'] for l in locations_list]) - deg_buffer
    max_lon = max([l['lon'] for l in locations_list]) + deg_buffer
    
    optimize_df = filtered_df[
        (filtered_df['LAT'] >= min_lat) & 
        (filtered_df['LAT'] <= max_lat) & 
        (filtered_df['LON'] >= min_lon) & 
        (filtered_df['LON'] <= max_lon)
    ]
    
    unique_sids = optimize_df['SID'].unique()
    st.write(f"Analyzing {len(unique_sids)} potential storms...")
    
    results = []
    progress = st.progress(0)
    for i, sid in enumerate(unique_sids):
        track = filtered_df[filtered_df['SID'] == sid] # Use full data for accuracy
        if track.empty: continue
        
        res = evaluate_portfolio_complex(track, locations_list, aggregate_limit, engine_profiles, trigger_method)
        
        if res['triggered']:
            name = track.iloc[0]['NAME']
            year = track.iloc[0]['ISO_TIME'].year
            results.append({
                'SID': sid, 'Name': name, 'Year': year,
                'Total Payout': res['total_payout'],
                'Details': res['location_breakdown']
            })
        
        if i % 20 == 0: progress.progress((i+1)/len(unique_sids))
    progress.progress(1.0)
    st.session_state['analysis_results'] = results

# --- Visualization ---
results = st.session_state['analysis_results']
col1, col2 = st.columns([1, 2])

if results is not None:
    res_df = pd.DataFrame(results)
    with col1:
        st.subheader("Payout Summary")
        if not res_df.empty:
            st.metric("Total Payout", f"${res_df['Total Payout'].sum():,.0f}")
            st.dataframe(res_df[['Name', 'Year', 'Total Payout']], 
                         column_config={'Total Payout': st.column_config.NumberColumn(format="$%d")},
                         hide_index=True)
        else:
            st.info("No events.")
            
    with col2:
        st.subheader(f"Map ({len(res_df)} Events)")
        if not locations_df.empty:
            center = [locations_df['Lat'].mean(), locations_df['Lon'].mean()]
        else: center = [25, -80]
        
        m = folium.Map(location=center, zoom_start=5, tiles='CartoDB positron')
        
        # Locs
        for _, row in locations_df.iterrows():
            folium.Circle(
                [row['Lat'], row['Lon']], radius=float(row['Radius (mi)'])*1609.34,
                color="red", fill=True, fill_opacity=0.1, weight=1,
                popup=f"{row['Name']}<br>Limit: ${row['Sublimit ($)']:,}"
            ).add_to(m)
            
        # Segments
        # Function to get color based on max cat of two points
        def get_color(cat):
            colors = {5: '#FF0000', 4: '#FF8000', 3: '#FFFF00', 2: '#80FF00', 1: '#00FF00', 0: '#00FFFF'}
            return colors.get(cat, '#CCCCCC')
        
        if not res_df.empty:
            # Reconstruct global payout table to infer category for visualization?
            # Or just use Wind? 
            # Prompt says: "use the maximum category of two points as the category of the hurricane."
            # We need to calculate Category for each point using the DEFAULT profile or Standard?
            # Since map is global, let's use the 'Standard' profile for coloring visualization to be consistent.
            # Reconstruct engine_profiles if not in scope (e.g. on rerun without button click)
            engine_profiles = {}
            for name, table in st.session_state['payout_profiles'].items():
                engine_profiles[name] = prep_payout_table(table)

            std_table = engine_profiles.get("Standard")
            if std_table is None: std_table = list(engine_profiles.values())[0] # Fallback
            
            # Helper to get cat from wind/pres using the logic engine
            from payout_engine import determine_category
            
            # We can't import inside loop easily efficiently, so define logic inline or import
            
            for item in results:
                sid = item['SID']
                df_global = get_data() # cached
                track = df_global[df_global['SID'] == sid]
                
                # Iterate segments
                track_recs = track.to_dict('records')
                for k in range(len(track_recs) - 1):
                    p1 = track_recs[k]
                    p2 = track_recs[k+1]
                    
                    # Determine Cat for P1 and P2
                    # Note: p1['USA_WIND'] is float
                    cat1 = determine_category(p1['USA_WIND'], p1['USA_PRES'], std_table)
                    cat2 = determine_category(p2['USA_WIND'], p2['USA_PRES'], std_table)
                    
                    seg_cat = max(cat1, cat2)
                    color = get_color(seg_cat)
                    
                    folium.PolyLine(
                        locations=[(p1['LAT'], p1['LON']), (p2['LAT'], p2['LON'])],
                        color=color,
                        weight=3,
                        opacity=0.8,
                        tooltip=f"{p1['NAME']} - Cat {seg_cat}"
                    ).add_to(m)

        # 3. Legend
        legend_html = '''
             <div style="position: fixed; 
                         bottom: 50px; left: 50px; width: 140px; height: 160px; 
                         border:2px solid grey; z-index:9999; font-size:14px;
                         background-color:white; opacity:0.8; padding: 10px;">
                 <b>Category</b><br>
                 <i style="background:#FF0000;width:10px;height:10px;display:inline-block;"></i> Cat 5<br>
                 <i style="background:#FF8000;width:10px;height:10px;display:inline-block;"></i> Cat 4<br>
                 <i style="background:#FFFF00;width:10px;height:10px;display:inline-block;"></i> Cat 3<br>
                 <i style="background:#80FF00;width:10px;height:10px;display:inline-block;"></i> Cat 2<br>
                 <i style="background:#00FF00;width:10px;height:10px;display:inline-block;"></i> Cat 1<br>
                 <i style="background:#00FFFF;width:10px;height:10px;display:inline-block;"></i> TS/Other<br>
             </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=900, height=600, returned_objects=[])
