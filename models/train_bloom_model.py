import pandas as pd
import joblib
from xgboost import XGBClassifier

df = pd.read_csv("data_processed/training_dataset.csv")

df["bloom"] = (df["chlorophyll"] > 4).astype(int)

X = df[["temperature","chlorophyll","turbidity"]]
y = df["bloom"]

model = XGBClassifier(
    n_estimators=400,
    max_depth=7,
    learning_rate=0.05
)

model.fit(X,y)

joblib.dump(model,"models/bloom_model.pkl")

print("Bloom model trained")