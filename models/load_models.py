import joblib


def load_models():
    """Load all three trained models. Returns (bloom_model, risk_model, oil_spill_model)."""
    bloom_model     = joblib.load("models/bloom_model.pkl")
    risk_model      = joblib.load("models/risk_model.pkl")
    oil_spill_model = joblib.load("models/oil_spill_model.pkl")
    return bloom_model, risk_model, oil_spill_model
