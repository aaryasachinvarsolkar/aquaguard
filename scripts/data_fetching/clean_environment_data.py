import pandas as pd
import os

print("Cleaning environmental datasets")

# Get project root directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

temperature_path = os.path.join(BASE_DIR, "data_raw", "temperature", "temperature_data.csv")
chlorophyll_path = os.path.join(BASE_DIR, "data_raw", "chlorophyll", "chlorophyll_data.csv")

temperature_output = os.path.join(BASE_DIR, "data_processed", "temperature_clean.csv")
chlorophyll_output = os.path.join(BASE_DIR, "data_processed", "chlorophyll_clean.csv")

# Load datasets
temp = pd.read_csv(temperature_path)
chl = pd.read_csv(chlorophyll_path)

# Clean data
temp = temp.dropna()
chl = chl.dropna()

# Save cleaned datasets
temp.to_csv(temperature_output, index=False)
chl.to_csv(chlorophyll_output, index=False)

print("Environmental datasets cleaned successfully")