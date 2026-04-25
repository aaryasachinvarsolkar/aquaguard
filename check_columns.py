import pandas as pd

chl = pd.read_csv("data_processed/chlorophyll_clean.csv")
temp = pd.read_csv("data_processed/temperature_clean.csv")

print("Chlorophyll columns:")
print(chl.columns)

print("\nTemperature columns:")
print(temp.columns)