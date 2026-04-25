import requests
import pandas as pd
import os

print("Fetching species data from OBIS...")

url = "https://api.obis.org/v3/occurrence"

params = {
    "size": 2000,
    "marine": "true"
}

response = requests.get(url, params=params)
data = response.json()

records = []

for item in data["results"]:

    lat = item.get("decimalLatitude")
    lon = item.get("decimalLongitude")
    species = item.get("scientificName")
    date = item.get("eventDate")

    if lat and lon and species:

        records.append({
            "latitude": lat,
            "longitude": lon,
            "date": date,
            "species_name": species
        })

df = pd.DataFrame(records)

# Save raw species occurrences
os.makedirs("data_processed", exist_ok=True)

df.to_csv("data_processed/species_occurrences.csv", index=False)

# Create species count dataset for ML
species_count = df.groupby(
    ["latitude","longitude","date"]
).size().reset_index(name="species_count")

species_count.to_csv("data_processed/species_clean.csv", index=False)

print("OBIS species data saved")
print("Total records:", len(df))