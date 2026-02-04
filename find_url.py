import requests

base_url = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04/access/csv/"
candidates = [
    "ibtracs.NA.list.v04r00.csv",
    "ibtracs.NA.list.v04r01.csv",
    "ibtracs.NA.list.v04r02.csv",
    "ibtracs.NA.list.v04r03.csv"
]

print(f"Checking access to {base_url}...")
try:
    r = requests.get(base_url)
    print(f"Base URL Status: {r.status_code}")
except Exception as e:
    print(f"Base URL Error: {e}")

for c in candidates:
    url = base_url + c
    try:
        r = requests.head(url)
        print(f"{c}: {r.status_code}")
        if r.status_code == 200:
            print(f"FOUND: {url}")
            break
    except Exception as e:
        print(f"Error checking {c}: {e}")
