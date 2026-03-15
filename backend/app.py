from fastapi import FastAPI, UploadFile
import pandas as pd
import numpy as np
import cv2
import tensorflow as tf
import joblib

app = FastAPI()

# Load models
bloom_model = joblib.load("models/bloom_model.pkl")
risk_model = joblib.load("models/risk_model.pkl")
oil_model = tf.keras.models.load_model("models/oil_spill_model.h5")


@app.get("/")
def home():
    return {"message": "Aquaguard API running"}


@app.get("/ecosystem-prediction")

def ecosystem_prediction():

    df = pd.read_csv("data_processed/features_dataset.csv")

    features = [
        "temperature",
        "chlorophyll",
        "species_count",
        "temperature_anomaly",
        "chlorophyll_growth"
    ]

    X = df[features]

    df["bloom_prediction"] = bloom_model.predict(X)

    df["risk_score"] = risk_model.predict(X)

    return df.head().to_dict()


@app.post("/detect-oil-spill")

async def detect_spill(file: UploadFile):

    contents = await file.read()

    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)

    image = cv2.resize(image, (128,128))

    image = image / 255.0

    image = np.expand_dims(image, axis=0)

    prediction = oil_model.predict(image)

    return {"spill_probability": float(prediction[0][0])}