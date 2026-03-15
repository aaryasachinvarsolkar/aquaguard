import pandas as pd

def generate_features():

    print("Loading dataset...")

    df = pd.read_csv("data_processed/ocean_master_dataset.csv")

    print("Generating features...")

    # temperature anomaly
    df["temperature_anomaly"] = df["temperature"] - df["temperature"].mean()

    # chlorophyll growth
    df["chlorophyll_growth"] = df["chlorophyll"].pct_change().fillna(0)

    # species density
    df["species_density"] = df["species_count"]

    df = df.fillna(0)

    df.to_csv("data_processed/features_dataset.csv", index=False)

    print("Feature dataset saved.")

if __name__ == "__main__":
    generate_features()