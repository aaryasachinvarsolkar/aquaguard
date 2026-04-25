"""
Model evaluation script — prints accuracy, classification report,
and confusion matrix for all trained models.
"""

import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix
)

# ── Load dataset ───────────────────────────────────────────────────────────────

df = pd.read_csv("data_processed/training_dataset.csv").dropna(
    subset=["temperature", "chlorophyll", "turbidity"]
)

X = df[["temperature", "chlorophyll", "turbidity"]]

# ── Risk Model (Random Forest) ─────────────────────────────────────────────────

y_risk = df["risk"]
X_train, X_test, y_train, y_test = train_test_split(
    X, y_risk, test_size=0.2, random_state=42
)

risk_model = joblib.load("models/risk_model.pkl")
y_pred_risk = risk_model.predict(X_test)
cv_risk = cross_val_score(risk_model, X, y_risk, cv=5, scoring="accuracy")

print("=" * 55)
print("  RISK MODEL  (Random Forest Classifier)")
print("=" * 55)
print(f"  Test Accuracy     : {accuracy_score(y_test, y_pred_risk):.4f}")
print(f"  CV Accuracy (5-fold): {cv_risk.mean():.4f} ± {cv_risk.std():.4f}")
print(f"\n  Classification Report:\n")
print(classification_report(y_test, y_pred_risk,
      target_names=["Low (0)", "Moderate (1)"], zero_division=0))
print(f"  Confusion Matrix:\n{confusion_matrix(y_test, y_pred_risk)}\n")

# ── Bloom Model (XGBoost) ──────────────────────────────────────────────────────

df["bloom_label"] = (df["chlorophyll"] > 4).astype(int)
y_bloom = df["bloom_label"]
X_train, X_test, y_train, y_test = train_test_split(
    X, y_bloom, test_size=0.2, random_state=42
)

bloom_model = joblib.load("models/bloom_model.pkl")
y_pred_bloom = bloom_model.predict(X_test)
cv_bloom = cross_val_score(bloom_model, X, y_bloom, cv=5, scoring="accuracy")

print("=" * 55)
print("  BLOOM MODEL  (XGBoost Classifier)")
print("=" * 55)
print(f"  Test Accuracy       : {accuracy_score(y_test, y_pred_bloom):.4f}")
print(f"  CV Accuracy (5-fold): {cv_bloom.mean():.4f} ± {cv_bloom.std():.4f}")
print(f"\n  Classification Report:\n")
print(classification_report(y_test, y_pred_bloom,
      target_names=["No Bloom (0)", "Bloom (1)"], zero_division=0))
print(f"  Confusion Matrix:\n{confusion_matrix(y_test, y_pred_bloom)}\n")

# ── Oil Spill CNN ──────────────────────────────────────────────────────────────

print("=" * 55)
print("  OIL SPILL MODEL  (CNN — Keras)")
print("=" * 55)
print("  Note: CNN was trained on satellite image data.")
print("  Only 1 sample image exists in data_processed/satellite_images/")
print("  — cannot evaluate without a labelled image dataset.")
print("  Training used 80/20 split with ImageDataGenerator.")
print("  Accuracy is reported during training (see train_oil_spill_model.py).\n")

print("=" * 55)
print("  SUMMARY")
print("=" * 55)
print(f"  Risk Model  — Test Acc: {accuracy_score(y_test_risk := y_test, y_pred_risk if False else y_pred_risk):.4f}"
      .replace("y_test_risk := y_test, ", ""))

# clean summary reprint
_, X_test_r, _, y_test_r = train_test_split(X, y_risk, test_size=0.2, random_state=42)
_, X_test_b, _, y_test_b = train_test_split(X, y_bloom, test_size=0.2, random_state=42)

print(f"  Risk Model  — Test Acc : {accuracy_score(y_test_r, risk_model.predict(X_test_r)):.4f}  | CV: {cv_risk.mean():.4f}")
print(f"  Bloom Model — Test Acc : {accuracy_score(y_test_b, bloom_model.predict(X_test_b)):.4f}  | CV: {cv_bloom.mean():.4f}")
print(f"  Oil Spill CNN          : requires image dataset to evaluate")
print("=" * 55)
