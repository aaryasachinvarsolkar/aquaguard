import joblib

def load_models():

    bloom_model = joblib.load("models/bloom_model.pkl")
    risk_model = joblib.load("models/risk_model.pkl")

    return bloom_model, risk_model