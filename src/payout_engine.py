import pandas as pd
from geopy.distance import geodesic
import numpy as np

def calculate_distance_miles(lat1, lon1, lat2, lon2):
    try:
        return geodesic((lat1, lon1), (lat2, lon2)).miles
    except ValueError:
        return float('inf')

def interpolate_segment(p1, p2, location):
    """
    Finds the closest point on the segment p1-p2 to location, 
    and checks if it is within radius. Returns interpolated intensity if triggered.
    p1, p2: dict with 'LAT', 'LON', 'USA_WIND', 'USA_PRES', 'ISO_TIME'
    location: dict with 'lat', 'lon', 'radius_miles'
    """
    # Vector implementation for projection would be faster, but keeping it readable with geopy/numpy
    # Approximate projection using flat earth for short segments (valid for 6-hr hurricane segments)
    
    lat1, lon1 = p1['LAT'], p1['LON']
    lat2, lon2 = p2['LAT'], p2['LON']
    lat_p, lon_p = location['lat'], location['lon']
    
    # Convert to simple cartesian for proportion t (valid for small areas)
    # Dx, Dy relative to p1
    dx = lat2 - lat1
    dy = lon2 - lon1
    
    if dx == 0 and dy == 0:
        return None
        
    # Project point P onto line segment
    # t = ((Px - x1)(x2 - x1) + (Py - y1)(y2 - y1)) / (len^2)
    t = ((lat_p - lat1) * dx + (lon_p - lon1) * dy) / (dx*dx + dy*dy)
    
    # Clamp t to segment [0, 1]
    t = max(0, min(1, t))
    
    # Closest point coords
    lat_c = lat1 + t * dx
    lon_c = lon1 + t * dy
    
    dist = calculate_distance_miles(lat_p, lon_p, lat_c, lon_c)
    
    if dist <= location['radius_miles']:
        # Interpolate intensity
        # Handle missings
        w1 = p1.get('USA_WIND', 0) if pd.notna(p1.get('USA_WIND')) else 0
        w2 = p2.get('USA_WIND', 0) if pd.notna(p2.get('USA_WIND')) else 0
        p_pres1 = p1.get('USA_PRES', 1013) if pd.notna(p1.get('USA_PRES')) else 1013
        p_pres2 = p2.get('USA_PRES', 1013) if pd.notna(p2.get('USA_PRES')) else 1013
        
        wind_c = w1 + t * (w2 - w1)
        pres_c = p_pres1 + t * (p_pres2 - p_pres1)
        
        return {
            'LAT': lat_c,
            'LON': lon_c,
            'USA_WIND': wind_c,
            'USA_PRES': pres_c,
            'dist': dist
        }
    return None

def determine_category(wind, pressure, payout_table):
    """
    Determines category based on Wind OR Pressure (Max of the two).
    payout_table: DataFrame with columns [Category, Min_Wind, Max_Pressure]
    """
    # Default to 0
    cat_wind = 0
    cat_pres = 0
    
    # Check Wind
    # We assume table is sorted by Category ascending (1, 2, 3, 4, 5)
    # We want the highest category where Wind >= Min_Wind
    if pd.notna(wind):
        for _, row in payout_table.iterrows():
            if wind >= row['Min_Wind']:
                cat_wind = max(cat_wind, row['Category'])
                
    # Check Pressure
    # We want the highest category where Pressure <= Max_Pressure (Lower is stronger)
    # Logic: if P <= 1000 (Cat 1 threshold), it is at least Cat 1.
    # If P <= 920 (Cat 5 threshold), it is Cat 5.
    if pd.notna(pressure) and pressure > 0:
        for _, row in payout_table.iterrows():
            # If threshold is NaN/None, ignore pressure for that cat
            if pd.notna(row['Max_Pressure']) and pressure <= row['Max_Pressure']:
                cat_pres = max(cat_pres, row['Category'])
                
    return max(cat_wind, cat_pres)

def evaluate_payout_complex(storm_track_df, policy_params, trigger_method='max_outcome'):
    """
    Args:
        trigger_method: 'max_outcome' (check pts) or 'interpolated' (check segments)
        policy_params: {
            'lat': ..., 'lon': ..., 'radius_miles': ...,
            'payout_table': pd.DataFrame (Category, Min_Wind, Max_Pressure, Payout_Pct)
        }
    """
    lat_p = policy_params.get('lat')
    lon_p = policy_params.get('lon')
    radius = policy_params.get('radius_miles')
    payout_table = policy_params.get('payout_table')
    
    if lat_p is None or lon_p is None or radius is None:
        raise ValueError("Missing policy parameters.")
    
    min_dist = float('inf')
    max_cat_achieved = 0
    closest_point_data = None
    
    points_to_check = []
    
    if trigger_method == 'interpolated':
        # Create interpolated points
        # Iterate pairs
        track_list = storm_track_df.to_dict('records')
        for i in range(len(track_list) - 1):
            p1 = track_list[i]
            p2 = track_list[i+1]
            
            interp = interpolate_segment(p1, p2, {'lat': lat_p, 'lon': lon_p, 'radius_miles': radius})
            if interp:
                points_to_check.append(interp)
                
            # Also always check the hard points (p1) to be safe/correct?
            # Actually interpolate_segment covers p1 if t=0, but strictly speaking
            # checking p1 explicitly is safer for min_dist calculation globally.
            
            d_p1 = calculate_distance_miles(lat_p, lon_p, p1['LAT'], p1['LON'])
            p1['dist'] = d_p1
            points_to_check.append(p1)
            
        # Add last point
        if track_list:
            last = track_list[-1]
            d_last = calculate_distance_miles(lat_p, lon_p, last['LAT'], last['LON'])
            last['dist'] = d_last
            points_to_check.append(last)
            
    elif trigger_method == 'max_outcome':
        # "Max Outcome" as requested: segment intersection check
        # Intensity = Max(Cat(P1), Cat(P2))
        
        track_list = storm_track_df.to_dict('records')
        for i in range(len(track_list) - 1):
            p1 = track_list[i]
            p2 = track_list[i+1]
            
            # Check geometric intersection using interpolate_segment logic
            # (ignore the interpolated return values, just check existence/dist)
            interp = interpolate_segment(p1, p2, {'lat': lat_p, 'lon': lon_p, 'radius_miles': radius})
            
            # Track geometric min_dist
            d1 = calculate_distance_miles(lat_p, lon_p, p1['LAT'], p1['LON'])
            if d1 < min_dist: 
                min_dist = d1
                closest_point_data = p1
            
            if interp:
                if interp['dist'] < min_dist:
                    min_dist = interp['dist']
                    closest_point_data = interp
                
                # Segment intersects radius. 
                # Determine Category of P1 and P2
                w1 = p1.get('USA_WIND', 0)
                p1_pres = p1.get('USA_PRES', 1013)
                cat1 = determine_category(w1, p1_pres, payout_table)
                
                w2 = p2.get('USA_WIND', 0)
                p2_pres = p2.get('USA_PRES', 1013)
                cat2 = determine_category(w2, p2_pres, payout_table)
                
                seg_cat = max(cat1, cat2)
                
                if seg_cat > max_cat_achieved:
                    max_cat_achieved = seg_cat
        
        # Check the last point specifically for distance min tracking (loop handles i to len-1)
        if track_list:
            last = track_list[-1]
            d_last = calculate_distance_miles(lat_p, lon_p, last['LAT'], last['LON'])
            if d_last < min_dist:
                min_dist = d_last
                closest_point_data = last
            
    # Now evaluate all candidates
    for pt in points_to_check:
        dist = pt['dist']
        if dist < min_dist:
            min_dist = dist
            closest_point_data = pt
            
        if dist <= radius:
            # Determine cat
            w = pt.get('USA_WIND', 0)
            p = pt.get('USA_PRES', 1013)
            
            cat = determine_category(w, p, payout_table)
            if cat > max_cat_achieved:
                max_cat_achieved = cat
                
    # Calculate Final Payout for Highest Cat
    payout_ratio = 0.0
    # Find payout for max_cat_achieved
    # Assuming standard structure: if you hit Cat 4, you get Cat 4 payout.
    # We look up max_cat_achieved in the table.
    
    match = payout_table[payout_table['Category'] == max_cat_achieved]
    if not match.empty:
        payout_ratio = match.iloc[0]['Payout_Pct']
    else:
        # If achieved 4 but table only has 1, 3, 5? 
        # Usually parametric is "at least". So we find max cat defined <= max_cat_achieved
        # e.g. Achieved 4. defined: 1, 3, 5. 
        # 4 >= 3, so pay 3's rate? 
        # Or simple lookup? Let's do simple lookup. If Cat 4 not in table, check Cat 3?
        # Better: iterate table. 
        # Payout is max(Payout_Pct) where Category <= max_cat_achieved
        
        valid_payouts = payout_table[payout_table['Category'] <= max_cat_achieved]['Payout_Pct']
        if not valid_payouts.empty:
            payout_ratio = valid_payouts.max()

    return {
        'triggered': payout_ratio > 0,
        'payout_ratio': payout_ratio,
        'max_category_inside_radius': max_cat_achieved,
        'triggered_category': max_cat_achieved, # Simplification
        'min_distance_miles': min_dist,
        'closest_point_data': closest_point_data
    }

def evaluate_portfolio_complex(storm_track_df, locations, aggregate_limit, payout_profiles, trigger_method):
    """
    locations: List of dicts, incl 'Profile_Name'
    payout_profiles: dict of {Name: DataFrame}
    """
    total_payout = 0.0
    details = []
    triggered_any = False
    
    for loc in locations:
        profile_name = loc.get('Profile_Name', 'Default')
        table = payout_profiles.get(profile_name)
        
        # Fallback if profile not found
        if table is None:
            # Check if there is a 'Default' profile
            if 'Default' in payout_profiles:
                table = payout_profiles['Default']
            else:
                # Use first available?
                table = list(payout_profiles.values())[0]

        policy = {
            'lat': loc['lat'],
            'lon': loc['lon'],
            'radius_miles': loc['radius_miles'],
            'payout_table': table
        }
        
        res = evaluate_payout_complex(storm_track_df, policy, trigger_method)
        
        loc_payout = 0.0
        if res['triggered']:
            loc_payout = res['payout_ratio'] * loc['sublimit']
            triggered_any = True
            
        details.append({
            'Location': loc['Name'],
            'Triggered': res['triggered'],
            'Payout': loc_payout,
            'Category': res['max_category_inside_radius'],
            'Min Dist': res['min_distance_miles']
        })
        
        total_payout += loc_payout
        
    final_payout = min(total_payout, aggregate_limit)
    
    return {
        'triggered': triggered_any,
        'total_payout': final_payout,
        'uncapped_payout': total_payout,
        'location_breakdown': details
    }
