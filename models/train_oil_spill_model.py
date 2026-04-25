"""
Oil Spill Model — SAR-based XGBoost classifier.

Uses realistic overlapping SAR VV distributions near the -20 dB threshold
so the model has to actually learn, not just memorize a hard cutoff.
"""

import numpy as np
import joblib
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import accuracy_score, classification_report
from xgboost import XGBClassifier

SEED = 42
np.random.seed(SEED)


def generate_sar_dataset(n=3000):
    import pandas as pd

    # Clean water: SAR VV centred at -12 dB, wide spread
    n_clean = int(n * 0.72)
    sar_c   = np.random.normal(-12, 4.5, n_clean)       # overlaps with spill zone
    temp_c  = np.random.uniform(10, 32, n_clean)
    chl_c   = np.abs(np.random.lognormal(0.1, 0.8, n_clean))
    wind_c  = np.random.uniform(1, 14, n_clean)
    label_noise_c = np.random.random(n_clean) < 0.05    # 5% label noise
    labels_c = np.where(label_noise_c, 1, 0)

    # Oil spill: SAR VV centred at -22 dB, overlaps with calm clean water
    n_spill = n - n_clean
    sar_s   = np.random.normal(-22, 3.5, n_spill)       # overlaps with clean water
    temp_s  = np.random.uniform(10, 32, n_spill)
    chl_s   = np.abs(np.random.lognormal(0.1, 0.8, n_spill))
    wind_s  = np.random.uniform(0.5, 7, n_spill)        # low wind favours detection
    label_noise_s = np.random.random(n_spill) < 0.05
    labels_s = np.where(label_noise_s, 0, 1)

    sar   = np.concatenate([sar_c, sar_s])
    temp  = np.concatenate([temp_c, temp_s])
    chl   = np.concatenate([chl_c, chl_s])
    wind  = np.concatenate([wind_c, wind_s])
    label = np.concatenate([labels_c, labels_s])

    df = pd.DataFrame({
        "sar_vv":      np.round(sar, 4),
        "temperature": np.round(temp, 4),
        "chlorophyll": np.round(np.clip(chl, 0.01, 20), 4),
        "wind_speed":  np.round(wind, 4),
        "oil_spill":   label
    })
    return df.sample(frac=1, random_state=SEED).reset_index(drop=True)


df = generate_sar_dataset(3000)
print(f"Dataset: {len(df)} rows | {df['oil_spill'].value_counts().to_dict()}")

X = df[["sar_vv", "temperature", "chlorophyll", "wind_speed"]]
y = df["oil_spill"]

X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.2, random_state=SEED, stratify=y
)

model = XGBClassifier(
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
model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

y_pred = model.predict(X_te)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
cv_scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")

print("\n" + "="*55)
print("  OIL SPILL MODEL  (XGBoost — SAR features)")
print("="*55)
print(f"  Train Accuracy : {accuracy_score(y_tr, model.predict(X_tr)):.4f}")
print(f"  Test Accuracy  : {accuracy_score(y_te, y_pred):.4f}")
print(f"  CV (5-fold)    : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
print(classification_report(y_te, y_pred, zero_division=0))

joblib.dump(model, "models/oil_spill_model.pkl")
print("  Saved → models/oil_spill_model.pkl")
