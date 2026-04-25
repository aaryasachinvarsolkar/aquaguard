import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

df = pd.read_csv("data_processed/training_dataset.csv")

X = df[["temperature", "chlorophyll", "turbidity"]]
y = df["risk"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    class_weight="balanced"
)

model.fit(X_train, y_train)

joblib.dump(model, "models/risk_model.pkl")

print("✅ Risk model trained successfully")