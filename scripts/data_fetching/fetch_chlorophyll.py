import xarray as xr
import pandas as pd
import os

print("Processing chlorophyll dataset...")

# expected file path
file_path = "../../data_raw/chlorophyll/chlorophyll.nc"

# check file existence
if not os.path.exists(file_path):
    print("ERROR: chlorophyll.nc file not found.")
    print("Place the downloaded NASA OceanColor .nc file here:")
    print(file_path)
    exit()

# open dataset
dataset = xr.open_dataset(file_path)

print("Dataset variables:")
print(dataset)

# automatically detect chlorophyll variable
possible_vars = ["chlor_a", "CHL", "chlorophyll"]

chl_var = None

for var in possible_vars:
    if var in dataset.variables:
        chl_var = var
        break

if chl_var is None:
    print("ERROR: Chlorophyll variable not found in dataset")
    exit()

print("Using chlorophyll variable:", chl_var)

chl = dataset[chl_var]

# convert to dataframe
df = chl.to_dataframe().reset_index()

# rename columns safely
rename_dict = {}

if "lat" in df.columns:
    rename_dict["lat"] = "latitude"

if "lon" in df.columns:
    rename_dict["lon"] = "longitude"

rename_dict[chl_var] = "chlorophyll"

df = df.rename(columns=rename_dict)

# remove missing values
df = df.dropna()

# keep only required columns
cols = ["latitude", "longitude", "chlorophyll"]

df = df[cols]

# save processed dataset
os.makedirs("../../data_raw/chlorophyll", exist_ok=True)

output_path = "../../data_raw/chlorophyll/chlorophyll_data.csv"

df.to_csv(output_path, index=False)

print("Chlorophyll dataset processed successfully")
print("Saved to:", output_path)

print(df.head())