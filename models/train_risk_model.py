import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.model_selection import train_test_split
import joblib

print("Loading dataset...")

df = pd.read_csv("data_processed/features_dataset.csv")

# create risk score
df["ecosystem_risk"] = (
    df["temperature_anomaly"].abs() +
    df["chlorophyll_growth"].abs()
)

features = [
    "temperature",
    "chlorophyll",
    "species_count",
    "temperature_anomaly",
    "chlorophyll_growth"
]

X = df[features]
y = df["ecosystem_risk"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print("Training LightGBM model...")

model = LGBMRegressor()

model.fit(X_train, y_train)

joblib.dump(model, "models/risk_model.pkl")

print("Risk model saved.")