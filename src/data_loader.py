import os
import requests
import pandas as pd
import numpy as np

# URL for North Atlantic IBTrACS v04
DATA_URL = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04/access/csv/ibtracs.NA.list.v04r01.csv"
LOCAL_PATH = os.path.join("data", "ibtracs.csv")

def download_data():
    """Downloads the IBTrACS data if it doesn't exist locally."""
    if not os.path.exists("data"):
        os.makedirs("data")
    
    if os.path.exists(LOCAL_PATH):
        print(f"Data already exists at {LOCAL_PATH}")
        return

    print(f"Downloading data from {DATA_URL}...")
    try:
        response = requests.get(DATA_URL, stream=True)
        response.raise_for_status()
        with open(LOCAL_PATH, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download complete.")
    except Exception as e:
        print(f"Error downloading data: {e}")
        print(f"Please manually download the file from: {DATA_URL}")
        print(f"Or visit https://www.ncei.noaa.gov/products/international-best-track-archive?name=ibtracs-data-access to find the CSV.")
        print(f"Save the file to: {os.path.abspath(LOCAL_PATH)}")
        # Clean up partial file if it exists
        if os.path.exists(LOCAL_PATH):
            os.remove(LOCAL_PATH)
        raise

def load_data():
    """Loads and cleans the IBTrACS data."""
    if not os.path.exists(LOCAL_PATH):
        download_data()
    
    # Skips the second row which contains units usually in IBTrACS CSVs? 
    # Actually IBTrACS often has units in the second row. Let's check.
    # We will read the first few lines to be safe or just use 'header=0' and then drop the unit row if it exists.
    # Official IBTrACS CSVs have the header on line 1, and units on line 2.
    
    df = pd.read_csv(LOCAL_PATH, low_memory=False, dtype=str) # Read as string initially to avoid type inference issues on ' ' or Mixed
    
    # Check if row 0 (index 0) is the units row (e.g. mb, kts)
    # Typical columns: SID, SEASON, NUMBER, BASIN, SUBBASIN, NAME, ISO_TIME, NATURE, LAT, LON, WMO_WIND, WMO_PRES, ...
    # If df.iloc[0]['SID'] is not a storm ID, it's likely units.
    if not df.empty and not df.iloc[0]['SID'].replace(':','').isalnum(): # SID is usually like 2020255N12345
        # It's likely units like 'Year' or 'kt', but let's just drop the first row if it looks like units
        # safer: clean based on known numeric columns failing conversion?
        pass

    # Actually, usually simpler to just drop index 0 if we know the format.
    # In v04r00 CSVs, row 2 (index 1) is usually units.
    # Let's inspect it after loading in a separate script or just account for it.
    # I'll optimistically drop the first row if the 'ISO_TIME' column has 'ISO_TIME' or generic text in it.
    
    if df.iloc[0]['ISO_TIME'] == 'ISO_TIME' or ' ' in str(df.iloc[0]['LAT']): 
         df = df.iloc[1:].reset_index(drop=True)

    # Convert columns
    # We need: SID, NAME, ISO_TIME, LAT, LON, USA_SSHS, USA_WIND, USA_PRES
    cols_to_keep = ['SID', 'NAME', 'ISO_TIME', 'LAT', 'LON', 'USA_SSHS', 'USA_WIND', 'USA_PRES']
    
    # Filter only columns that exist
    available_cols = [c for c in cols_to_keep if c in df.columns]
    df = df[available_cols].copy()
    
    # Type conversion
    df['LAT'] = pd.to_numeric(df['LAT'], errors='coerce')
    df['LON'] = pd.to_numeric(df['LON'], errors='coerce')
    df['USA_WIND'] = pd.to_numeric(df['USA_WIND'], errors='coerce')
    df['USA_PRES'] = pd.to_numeric(df['USA_PRES'], errors='coerce')
    df['USA_SSHS'] = pd.to_numeric(df['USA_SSHS'], errors='coerce')
    
    # Parse dates
    # IBTrACS ISO_TIME is typically YYYY-MM-DD HH:mm:ss
    df['ISO_TIME'] = pd.to_datetime(df['ISO_TIME'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    
    # Drop rows without valid lat/lon/time
    df = df.dropna(subset=['LAT', 'LON', 'ISO_TIME'])
    
    # Fill SSHS with -1 or 0 if missing, but better to keep as NaN or handle explicitly
    # Parametric often relies on clean categories.
    # USA_SSHS: Saffir Simpson Hurricane Scale.
    
    return df

if __name__ == "__main__":
    df = load_data()
    print(f"Loaded {len(df)} records.")
    print(df.head())
