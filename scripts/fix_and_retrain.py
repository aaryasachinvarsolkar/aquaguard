"""
Retrain risk and bloom models with realistic data.

Key fixes:
- Labels have noise/uncertainty near decision boundaries
- Feature overlap between classes (real ocean data is messy)
- Proper train/test split with stratification
- Regularized models to prevent overfitting
"""

import numpy as np
import joblib
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from xgboost import XGBClassifier

SEED = 42
np.random.seed(SEED)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)


def generate_ocean_dataset(n=4000):
    """
    Generate realistic ocean data with:
    - Overlapping feature distributions near boundaries
    - Label noise (~8%) to simulate real-world uncertainty
    - Natural sensor measurement noise
    """
    # Base features sampled from realistic ocean ranges
    temp = np.random.uniform(8, 34, n)
    chl  = np.abs(np.random.lognormal(mean=0.2, sigma=1.0, size=n))  # log-normal like real chl
    chl  = np.clip(chl, 0.01, 25.0)
    turb = 0.05 + 0.08 * chl + np.random.normal(0, 0.03, n)
    turb = np.clip(turb, 0.0, 3.0)

    # ── Bloom label ────────────────────────────────────────────────────────────
    # Soft boundary: probability increases around chl=4, not a hard cutoff
    bloom_prob = 1 / (1 + np.exp(-2.5 * (chl - 4.0)))   # sigmoid centred at 4
    bloom_prob += np.random.normal(0, 0.08, n)            # label noise
    bloom_prob = np.clip(bloom_prob, 0, 1)
    bloom = (bloom_prob > 0.5).astype(int)

    # ── Risk label ─────────────────────────────────────────────────────────────
    # Risk depends on combination of temp + chl + turbidity
    risk_score = (
        0.4 * (chl / 4.0) +
        0.35 * ((temp - 27) / 3.0) +
        0.25 * (turb / 0.5)
    )
    risk_prob = 1 / (1 + np.exp(-2.0 * (risk_score - 0.5)))
    risk_prob += np.random.normal(0, 0.10, n)             # more label noise for risk
    risk_prob = np.clip(risk_prob, 0, 1)
    risk = (risk_prob > 0.5).astype(int)

    import pandas as pd
    df = pd.DataFrame({
        "temperature": np.round(temp, 4),
        "chlorophyll": np.round(chl, 4),
        "turbidity":   np.round(turb, 4),
        "bloom":       bloom,
        "risk":        risk
    })
    return df


df = generate_ocean_dataset(4000)
print(f"Dataset        : {len(df)} rows")
print(f"Risk  dist     : {df['risk'].value_counts().to_dict()}")
print(f"Bloom dist     : {df['bloom'].value_counts().to_dict()}")

X = df[["temperature", "chlorophyll", "turbidity"]]


# ── Risk Model ─────────────────────────────────────────────────────────────────

y_risk = df["risk"]
X_tr, X_te, y_tr, y_te = train_test_split(
    X, y_risk, test_size=0.2, random_state=SEED, stratify=y_risk
)

risk_model = RandomForestClassifier(
    n_estimators=150,
    max_depth=5,
    min_samples_leaf=8,
    max_features="sqrt",
    class_weight="balanced",
    random_state=SEED
)
risk_model.fit(X_tr, y_tr)

y_pred_risk = risk_model.predict(X_te)
cv_risk = cross_val_score(risk_model, X, y_risk, cv=cv, scoring="accuracy")

print("\n" + "="*55)
print("  RISK MODEL  (Random Forest)")
print("="*55)
print(f"  Train Accuracy : {accuracy_score(y_tr, risk_model.predict(X_tr)):.4f}")
print(f"  Test Accuracy  : {accuracy_score(y_te, y_pred_risk):.4f}")
print(f"  CV (5-fold)    : {cv_risk.mean():.4f} ± {cv_risk.std():.4f}")
print(classification_report(y_te, y_pred_risk, zero_division=0))

joblib.dump(risk_model, "models/risk_model.pkl")
print("  Saved → models/risk_model.pkl")


# ── Bloom Model ────────────────────────────────────────────────────────────────

y_bloom = df["bloom"]
X_tr, X_te, y_tr, y_te = train_test_split(
    X, y_bloom, test_size=0.2, random_state=SEED, stratify=y_bloom
)

bloom_model = XGBClassifier(
    n_estimators=150,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.75,
    colsample_bytree=0.75,
    reg_alpha=0.5,
    reg_lambda=2.0,
    eval_metric="logloss",
    random_state=SEED
)
bloom_model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

y_pred_bloom = bloom_model.predict(X_te)
cv_bloom = cross_val_score(bloom_model, X, y_bloom, cv=cv, scoring="accuracy")

print("\n" + "="*55)
print("  BLOOM MODEL  (XGBoost)")
print("="*55)
print(f"  Train Accuracy : {accuracy_score(y_tr, bloom_model.predict(X_tr)):.4f}")
print(f"  Test Accuracy  : {accuracy_score(y_te, y_pred_bloom):.4f}")
print(f"  CV (5-fold)    : {cv_bloom.mean():.4f} ± {cv_bloom.std():.4f}")
print(classification_report(y_te, y_pred_bloom, zero_division=0))

joblib.dump(bloom_model, "models/bloom_model.pkl")
print("  Saved → models/bloom_model.pkl")
