import pandas as pd

species = pd.read_csv("../../data_processed/species_clean.csv")
temperature = pd.read_csv("../../data_processed/temperature_clean.csv")
chlorophyll = pd.read_csv("../../data_processed/chlorophyll_clean.csv")

print("\nSpecies latitude range:", species["latitude"].min(), species["latitude"].max())
print("Species longitude range:", species["longitude"].min(), species["longitude"].max())

print("\nTemperature latitude range:", temperature["latitude"].min(), temperature["latitude"].max())
print("Temperature longitude range:", temperature["longitude"].min(), temperature["longitude"].max())

print("\nChlorophyll latitude range:", chlorophyll["latitude"].min(), chlorophyll["latitude"].max())
print("Chlorophyll longitude range:", chlorophyll["longitude"].min(), chlorophyll["longitude"].max())