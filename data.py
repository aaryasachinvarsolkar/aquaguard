import pandas as pd

df = pd.read_csv("data_processed/features_dataset.csv")

print(df.head())
print(df.shape)
print(df.columns)
print(df.describe())