import pandas as pd

print("Loading cleaned datasets...")

species = pd.read_csv("../../data_processed/species_clean.csv")
temperature = pd.read_csv("../../data_processed/temperature_clean.csv")
chlorophyll = pd.read_csv("../../data_processed/chlorophyll_clean.csv")

# -----------------------------
# Create spatial grid
# -----------------------------
species["lat_grid"] = species["latitude"].round(1)
species["lon_grid"] = species["longitude"].round(1)

temperature["lat_grid"] = temperature["latitude"].round(1)
temperature["lon_grid"] = temperature["longitude"].round(1)

chlorophyll["lat_grid"] = chlorophyll["latitude"].round(1)
chlorophyll["lon_grid"] = chlorophyll["longitude"].round(1)

# -----------------------------
# Aggregate datasets
# -----------------------------
species_grid = species.groupby(
    ["lat_grid","lon_grid"]
).agg({"species_count":"sum"}).reset_index()

chlorophyll_grid = chlorophyll.groupby(
    ["lat_grid","lon_grid"]
).agg({"chlorophyll":"mean"}).reset_index()

temperature_grid = temperature.groupby(
    ["lat_grid","lon_grid"]
).agg({"temperature":"mean"}).reset_index()

# -----------------------------
# Use temperature grid as base
# -----------------------------
dataset = temperature_grid.merge(
    chlorophyll_grid,
    on=["lat_grid","lon_grid"],
    how="left"
)

dataset = dataset.merge(
    species_grid,
    on=["lat_grid","lon_grid"],
    how="left"
)

dataset["species_count"] = dataset["species_count"].fillna(0)

dataset = dataset.rename(columns={
    "lat_grid":"latitude",
    "lon_grid":"longitude"
})

dataset.to_csv("../../data_processed/ocean_master_dataset.csv",index=False)

print("\nFinal dataset created successfully")
print(dataset.head())
print("\nTotal rows:",len(dataset))