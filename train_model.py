import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import joblib

# load dataset
data = pd.read_csv("datasets/ocean_dataset.csv")

X = data[["temperature","chlorophyll","turbidity"]]
y = data["risk"]

model = RandomForestClassifier(n_estimators=200)

model.fit(X,y)

joblib.dump(model,"models/marine_model.pkl")

print("Model trained and saved")