import pandas as pd
from src.payout_engine import evaluate_payout

# Mock track: A storm passing close with high wind
track_data = {
    'LAT': [25.0, 25.5, 26.0], 
    'LON': [-80.0, -80.2, -80.4],
    'USA_SSHS': [3, 4, 3], # Categories
    'USA_WIND': [100, 115, 100]
}
df = pd.DataFrame(track_data)

# Policy: Miami
policy = {
    'lat': 25.7617,
    'lon': -80.1918,
    'radius_miles': 50.0,
    'payout_structure': {1: 0.1, 3: 0.5, 5: 1.0}
}

print("Testing Payout Engine...")
try:
    result = evaluate_payout(df, policy)
    print("Result:", result)
    if result['triggered'] and result['payout_ratio'] == 0.5:
        print("SUCCESS: Payout logic verified.")
    else:
        print("FAILURE: Incorrect payout logic.")
except Exception as e:
    print(f"ERROR: {e}")
