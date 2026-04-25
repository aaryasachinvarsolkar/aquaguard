import pandas as pd
import joblib

bloom_model = joblib.load("models/bloom_model.pkl")
risk_model = joblib.load("models/risk_model.pkl")

def predict_region(lat, lon):

    df = pd.read_csv("outputs/ecosystem_predictions.csv")

    region = df[
        (df["lat_bin"] == round(lat)) &
        (df["lon_bin"] == round(lon))
    ]

    return region.to_dict()