import joblib
import numpy as np

model = joblib.load("models/risk_model.pkl")

test_sample = np.array([[29.4,5.1,1.2]])

prediction = model.predict(test_sample)

print("Predicted risk:", prediction)