import pandas as pd
import joblib

print("Loading models...")

bloom_model = joblib.load("models/bloom_model.pkl")
risk_model = joblib.load("models/risk_model.pkl")

print("Loading feature dataset...")

df = pd.read_csv("data_processed/features_dataset.csv")

features = [
    "temperature",
    "chlorophyll",
    "species_count",
    "temperature_anomaly",
    "chlorophyll_growth"
]

X = df[features]

print("Generating predictions...")

df["bloom_prediction"] = bloom_model.predict(X)

df["risk_score"] = risk_model.predict(X)

df.to_csv("outputs/ecosystem_predictions.csv", index=False)

print("Predictions saved.")