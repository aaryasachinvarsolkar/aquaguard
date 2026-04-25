"""
Anomaly Detection Model — Isolation Forest on ocean environmental features.
Detects when current conditions are statistically unusual vs historical baseline.
"""

import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

SEED = 42
np.random.seed(SEED)


def generate_normal_ocean_data(n=5000):
    """Generate realistic 'normal' ocean conditions as training baseline."""
    import pandas as pd

    # Normal ocean conditions — varied by region/season
    chunk = n // 3
    temp = np.concatenate([
        np.random.normal(26, 3, chunk),
        np.random.normal(18, 4, chunk),
        np.random.normal(10, 3, n - 2 * chunk),
    ])
    chl  = np.abs(np.random.lognormal(mean=-0.3, sigma=0.8, size=n))
    chl  = np.clip(chl, 0.01, 8.0)   # normal range, no bloom
    turb = 0.05 + 0.08 * chl + np.random.normal(0, 0.02, n)
    turb = np.clip(turb, 0.0, 1.0)

    return pd.DataFrame({
        "temperature": np.round(temp, 4),
        "chlorophyll": np.round(chl, 4),
        "turbidity":   np.round(turb, 4),
    })


df = generate_normal_ocean_data(5000)
X  = df[["temperature", "chlorophyll", "turbidity"]]

# Isolation Forest — contamination=0.05 means ~5% of training data treated as anomalies
model = Pipeline([
    ("scaler", StandardScaler()),
    ("iso",    IsolationForest(
        n_estimators=200,
        contamination=0.05,
        max_samples="auto",
        random_state=SEED
    ))
])

model.fit(X)

# Quick validation
scores = model.decision_function(X)
preds  = model.predict(X)  # -1 = anomaly, 1 = normal
anomaly_rate = (preds == -1).mean()
print(f"Anomaly model trained | anomaly rate on training data: {anomaly_rate:.2%}")

joblib.dump(model, "models/anomaly_model.pkl")
print("Saved → models/anomaly_model.pkl")
