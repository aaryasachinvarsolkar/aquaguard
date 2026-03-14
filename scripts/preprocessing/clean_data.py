import pandas as pd
import os

print("Starting data cleaning...")

# Create processed folder
os.makedirs("../../data_processed", exist_ok=True)

# ---------------------------
# 1. CLEAN SPECIES DATA
# ---------------------------

species = pd.read_csv("../../data_raw/species/species_data.csv")

# Remove missing values
species = species.dropna()

# Convert date
species["date"] = pd.to_datetime(species["date"], errors="coerce")

# Ensure numeric coordinates
species["latitude"] = pd.to_numeric(species["latitude"], errors="coerce")
species["longitude"] = pd.to_numeric(species["longitude"], errors="coerce")

# Remove invalid rows
species = species.dropna()

# Remove duplicates
species = species.drop_duplicates()

# Round coordinates for better merging
species["latitude"] = species["latitude"].round(2)
species["longitude"] = species["longitude"].round(2)

species.to_csv("../../data_processed/species_clean.csv", index=False)

print("Species dataset cleaned")

# ---------------------------
# 2. CLEAN TEMPERATURE DATA
# ---------------------------

temperature = pd.read_csv("../../data_raw/temperature/temperature_data.csv")

# Remove metadata rows
temperature = temperature[temperature["latitude"] != "degrees_north"]

# Convert columns to numeric
temperature["latitude"] = pd.to_numeric(temperature["latitude"], errors="coerce")
temperature["longitude"] = pd.to_numeric(temperature["longitude"], errors="coerce")
temperature["sst"] = pd.to_numeric(temperature["sst"], errors="coerce")

# Rename columns
temperature = temperature.rename(columns={
    "time": "date",
    "sst": "temperature"
})

# Convert date
temperature["date"] = pd.to_datetime(temperature["date"], errors="coerce")

# Drop missing
temperature = temperature.dropna()

# Remove duplicates
temperature = temperature.drop_duplicates()

# Round coordinates
temperature["latitude"] = temperature["latitude"].round(2)
temperature["longitude"] = temperature["longitude"].round(2)

temperature.to_csv("../../data_processed/temperature_clean.csv", index=False)

print("Temperature dataset cleaned")

# ---------------------------
# 3. CLEAN CHLOROPHYLL DATA
# ---------------------------

chlorophyll = pd.read_csv("../../data_raw/chlorophyll/chlorophyll_data.csv")

# Convert to numeric
chlorophyll["latitude"] = pd.to_numeric(chlorophyll["latitude"], errors="coerce")
chlorophyll["longitude"] = pd.to_numeric(chlorophyll["longitude"], errors="coerce")
chlorophyll["chlorophyll"] = pd.to_numeric(chlorophyll["chlorophyll"], errors="coerce")

# Remove invalid values
chlorophyll = chlorophyll.dropna()

# Remove duplicates
chlorophyll = chlorophyll.drop_duplicates()

# Remove negative values
chlorophyll = chlorophyll[chlorophyll["chlorophyll"] >= 0]

# Round coordinates
chlorophyll["latitude"] = chlorophyll["latitude"].round(2)
chlorophyll["longitude"] = chlorophyll["longitude"].round(2)

chlorophyll.to_csv("../../data_processed/chlorophyll_clean.csv", index=False)

print("Chlorophyll dataset cleaned")

print("\nAll datasets cleaned successfully\n")