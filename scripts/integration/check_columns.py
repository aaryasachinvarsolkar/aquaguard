import pandas as pd

species = pd.read_csv("../../data_processed/species_clean.csv")
temperature = pd.read_csv("../../data_processed/temperature_clean.csv")
chlorophyll = pd.read_csv("../../data_processed/chlorophyll_clean.csv")

print("\nSpecies columns:")
print(species.columns)

print("\nTemperature columns:")
print(temperature.columns)

print("\nChlorophyll columns:")
print(chlorophyll.columns)