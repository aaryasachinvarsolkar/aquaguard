import requests
import pandas as pd
import os

print("Downloading species data from OBIS...")

os.makedirs("../../data_raw/species", exist_ok=True)

url = "https://api.obis.org/v3/occurrence"

params = {
    "scientificname": "Thunnus",
    "decimalLatitude": "-10,10",
    "decimalLongitude": "60,80",
    "size": 500
}

response = requests.get(url, params=params)
data = response.json()["results"]

records = []

for item in data:

    lat = item.get("decimalLatitude")
    lon = item.get("decimalLongitude")
    date = item.get("eventDate")

    if lat and lon:

        records.append({
            "latitude": lat,
            "longitude": lon,
            "date": date,
            "species_count": 1
        })

df = pd.DataFrame(records)

df.to_csv("../../data_raw/species/species_data.csv", index=False)

print("Species dataset downloaded")
print("Total records:", len(df))