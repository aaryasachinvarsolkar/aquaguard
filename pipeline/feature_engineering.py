import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

# Load datasets
chlorophyll = pd.read_csv("data_processed/chlorophyll_clean.csv")
temperature = pd.read_csv("data_processed/temperature_clean.csv")

# Normalize column names
chlorophyll.columns = chlorophyll.columns.str.lower()
temperature.columns = temperature.columns.str.lower()

# Rename columns
chlorophyll = chlorophyll.rename(columns={
    "latitude": "lat",
    "longitude": "lon"
})

temperature = temperature.rename(columns={
    "latitude": "lat",
    "longitude": "lon",
    "sst": "temperature"
})

# Remove metadata rows
chlorophyll = chlorophyll[pd.to_numeric(chlorophyll["lat"], errors="coerce").notnull()]
temperature = temperature[pd.to_numeric(temperature["lat"], errors="coerce").notnull()]

chlorophyll["lat"] = chlorophyll["lat"].astype(float)
chlorophyll["lon"] = chlorophyll["lon"].astype(float)

temperature["lat"] = temperature["lat"].astype(float)
temperature["lon"] = temperature["lon"].astype(float)

# Remove time column
if "time" in temperature.columns:
    temperature = temperature.drop(columns=["time"])

# Build spatial index
temp_coords = np.vstack((temperature["lat"], temperature["lon"])).T
tree = cKDTree(temp_coords)

# Query nearest temperature point
chl_coords = np.vstack((chlorophyll["lat"], chlorophyll["lon"])).T
dist, idx = tree.query(chl_coords, k=1)

# Attach matched temperature
chlorophyll["temperature"] = temperature.iloc[idx]["temperature"].values

# Feature engineering
chlorophyll["turbidity"] = chlorophyll["chlorophyll"] * 0.25

# Save dataset
chlorophyll.to_csv("data_processed/features_dataset.csv", index=False)

print("Feature dataset created successfully")
print("Rows:", len(chlorophyll))