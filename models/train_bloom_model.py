import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib

print("Loading feature dataset...")

df = pd.read_csv("data_processed/features_dataset.csv")

# create label automatically
df["bloom_risk"] = (
    (df["chlorophyll"] > df["chlorophyll"].quantile(0.75)) &
    (df["temperature"] > df["temperature"].mean())
).astype(int)

features = [
    "temperature",
    "chlorophyll",
    "species_count",
    "temperature_anomaly",
    "chlorophyll_growth",
]

X = df[features]
y = df["bloom_risk"]

print("Splitting dataset...")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print("Training XGBoost model...")

model = XGBClassifier()

model.fit(X_train, y_train)

predictions = model.predict(X_test)

accuracy = accuracy_score(y_test, predictions)

print("Model accuracy:", accuracy)

joblib.dump(model, "models/bloom_model.pkl")

print("Bloom model saved.")