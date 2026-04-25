"""
OceanSense — Scientifically Correct ML Training
================================================
Risk label logic based on peer-reviewed ocean science:

RISK = HIGH when ANY of these conditions are true:
  1. Chlorophyll > 5 mg/m³  (algal bloom / eutrophication)
  2. Chlorophyll > 3 AND SST > 28°C  (bloom + thermal stress combo)
  3. Turbidity > 0.5 AND chlorophyll > 2  (sediment + nutrient combo)
  4. SST > 31°C  (extreme thermal stress — mass bleaching threshold)
  5. Turbidity > 1.0  (severe water quality degradation)

RISK = LOW when:
  - SST 27-30°C with low chlorophyll (<1 mg/m³) = normal tropical ocean
  - SST < 27°C with moderate chlorophyll = healthy temperate ocean
  - All parameters within normal ranges for that region

This means Bay of Bengal at SST=29°C, Chl=0.5 = LOW RISK (correct)
And Bay of Bengal at SST=29°C, Chl=6.0 = HIGH RISK (correct)

Anti-overfitting:
  - Stratified 5-fold CV
  - 20% held-out test set never seen during training
  - Max depth 4, min_samples_leaf 10
  - Subsampling 0.8
  - Train/test accuracy gap checked
"""

import numpy as np
import pandas as pd
import joblib
import warnings
warnings.filterwarnings("ignore")

from sklearn.model_selection import (
    train_test_split, StratifiedKFold, RandomizedSearchCV, cross_val_score
)
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score,
    classification_report, confusion_matrix
)
from sklearn.ensemble import IsolationForest
from xgboost import XGBClassifier

SEED = 42
np.random.seed(SEED)


# ══════════════════════════════════════════════════════════════════════════════
# 1. SCIENTIFICALLY CORRECT RISK LABELING
# ══════════════════════════════════════════════════════════════════════════════

def label_risk(temp: float, chl: float, turb: float) -> int:
    """
    Multi-factor risk label based on peer-reviewed ocean science thresholds.
    Returns 1 (High) or 0 (Low).

    Sources:
    - Coral bleaching: NOAA Coral Reef Watch (SST > 1°C above MMM, ~29-30°C tropical)
    - Algal bloom: Chl-a > 5 mg/m³ (HELCOM, EPA standards)
    - Eutrophication: Chl > 3 + SST > 28 (nutrient + thermal combo)
    - Turbidity: > 0.5 NTU = poor water quality (WHO guidelines)
    """
    # Extreme single-factor conditions
    if chl > 5.0:           return 1   # algal bloom threshold
    if temp > 31.0:         return 1   # extreme thermal stress
    if turb > 1.0:          return 1   # severe turbidity

    # Combined multi-factor conditions
    if chl > 3.0 and temp > 28.0:   return 1   # bloom + thermal
    if chl > 2.0 and turb > 0.5:    return 1   # nutrient + sediment
    if temp > 29.5 and turb > 0.3:  return 1   # thermal + turbidity

    return 0


def label_bloom(chl: float, temp: float) -> int:
    """
    Bloom label: chlorophyll-driven with temperature modifier.
    Chl > 5 = definite bloom. Chl 3-5 + warm water = likely bloom.
    """
    if chl > 5.0:                    return 1
    if chl > 3.0 and temp > 25.0:   return 1
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════════════════

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    turb_null = df["turbidity"].isnull()
    df.loc[turb_null, "turbidity"] = (0.05 + 0.08 * df.loc[turb_null, "chlorophyll"]).clip(0.01, 3.0)

    df["chl_log"]            = np.log1p(df["chlorophyll"])
    df["chl_temp"]           = df["chlorophyll"] * df["temperature"]
    df["temp_anomaly"]       = (df["temperature"] - 26.0).clip(0)   # deviation above 26°C
    df["turb_chl_ratio"]     = df["turbidity"] / (df["chlorophyll"] + 0.01)
    df["chl_squared"]        = df["chlorophyll"] ** 2
    df["temp_chl_bloom_idx"] = (df["chlorophyll"] > 3).astype(float) * (df["temperature"] > 27).astype(float)
    df["is_tropical"]        = (df["latitude"].abs() < 23.5).astype(float) if "latitude" in df.columns else 1.0
    df["lat_abs"]            = df["latitude"].abs() if "latitude" in df.columns else 10.0
    return df


FEATURES = [
    "temperature", "chlorophyll", "turbidity",
    "chl_log", "chl_temp", "temp_anomaly",
    "turb_chl_ratio", "chl_squared", "temp_chl_bloom_idx",
    "is_tropical", "lat_abs"
]


# ══════════════════════════════════════════════════════════════════════════════
# 3. DATA GENERATION — globally diverse, scientifically labeled
# ══════════════════════════════════════════════════════════════════════════════

def load_real_data() -> pd.DataFrame:
    df = pd.read_csv("data_processed/training_dataset.csv")
    print(f"Real data loaded: {len(df)} rows")
    df["turbidity"] = df["turbidity"].fillna(0.05 + 0.08 * df["chlorophyll"]).clip(0.01, 3.0)
    # Re-label with correct science-based labels
    df["risk"]  = df.apply(lambda r: label_risk(r.temperature, r.chlorophyll, r.turbidity), axis=1)
    df["bloom"] = df.apply(lambda r: label_bloom(r.chlorophyll, r.temperature), axis=1)
    print(f"  Re-labeled: Risk={df.risk.value_counts().to_dict()} Bloom={df.bloom.value_counts().to_dict()}")
    return df


def build_synthetic(n: int = 8000) -> pd.DataFrame:
    """
    Generate globally diverse synthetic ocean data with correct science-based labels.
    Covers all ocean types so the model generalises beyond Indian Ocean.
    """
    rng = np.random.default_rng(SEED)

    # Each region: (temp_mean, temp_std, chl_mean, chl_log_std, lat_range, weight)
    regions = [
        # Normal tropical ocean — LOW risk baseline
        ("tropical_clear",    28.0, 1.2,  0.4, 0.6,  (-15, 25),  0.20),
        # Upwelling zones — HIGH chl, moderate temp
        ("upwelling",         16.0, 3.0,  8.0, 0.8,  (-30, 15),  0.15),
        # Temperate productive — moderate chl
        ("temperate",         15.0, 5.0,  2.5, 0.7,  (30,  60),  0.15),
        # Bloom hotspots — HIGH chl + warm
        ("bloom_hotspot",     24.0, 3.0, 10.0, 0.7,  (40,  70),  0.12),
        # Arctic/subarctic — cold, low chl
        ("arctic",             4.0, 3.0,  1.2, 0.6,  (60,  85),  0.08),
        # Coastal eutrophic — HIGH chl + turbidity
        ("coastal_eutrophic", 22.0, 4.0,  7.0, 0.8,  (10,  50),  0.15),
        # Extreme thermal (coral bleaching zones)
        ("thermal_stress",    30.5, 0.8,  0.6, 0.5,  (-20, 30),  0.08),
        # Normal Indian Ocean — LOW risk (matches real data)
        ("indian_ocean",      28.5, 0.8,  0.5, 0.4,  (-10, 25),  0.07),
    ]

    rows = []
    for name, tm, ts, cm, cs, (la, lb), w in regions:
        n_r = int(n * w)
        temp = rng.normal(tm, ts, n_r).clip(-2, 35)
        chl  = np.abs(rng.lognormal(np.log(cm + 0.01), cs, n_r)).clip(0.01, 30)
        turb = (0.05 + 0.08 * chl + rng.normal(0, 0.04, n_r)).clip(0.01, 3.0)
        lat  = rng.uniform(la, lb, n_r)
        lon  = rng.uniform(-180, 180, n_r)

        for i in range(n_r):
            # Add Gaussian noise to prevent over-fitting (models should not have AUC=1.0)
            t = float(temp[i]) + rng.normal(0, 0.05)
            c = float(chl[i]) + rng.normal(0, 0.08)
            u = float(turb[i]) + rng.normal(0, 0.02)
            
            # Clip after noise
            t = round(float(np.clip(t, -2, 35)), 4)
            c = round(float(np.clip(c, 0.01, 30)), 4)
            u = round(float(np.clip(u, 0.01, 3.0)), 4)

            rows.append({
                "latitude":    round(float(lat[i]), 3),
                "longitude":   round(float(lon[i]), 3),
                "temperature": t,
                "chlorophyll": c,
                "turbidity":   u,
                "risk":        label_risk(t, c, u),
                "bloom":       label_bloom(c, t),
            })

    df = pd.DataFrame(rows)
    print(f"Synthetic data: {len(df)} rows")
    print(f"  Risk={df.risk.value_counts().to_dict()} Bloom={df.bloom.value_counts().to_dict()}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 4. EVALUATION HELPER
# ══════════════════════════════════════════════════════════════════════════════

def evaluate(name, model, X_tr, X_te, y_tr, y_te, cv, X_full, y_full):
    y_pred = model.predict(X_te)
    y_prob = model.predict_proba(X_te)[:, 1]
    train_acc = accuracy_score(y_tr, model.predict(X_tr))
    test_acc  = accuracy_score(y_te, y_pred)
    f1        = f1_score(y_te, y_pred, average="weighted")
    auc       = roc_auc_score(y_te, y_prob)
    cv_scores = cross_val_score(model, X_full, y_full, cv=cv, scoring="roc_auc")

    print(f"\n{'='*58}")
    print(f"  {name}")
    print(f"{'='*58}")
    print(f"  Train Acc : {train_acc:.4f}")
    print(f"  Test  Acc : {test_acc:.4f}  {'⚠ OVERFIT' if train_acc - test_acc > 0.08 else '✓ ok'}")
    print(f"  F1        : {f1:.4f}")
    print(f"  ROC-AUC   : {auc:.4f}")
    print(f"  CV AUC    : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
    print(classification_report(y_te, y_pred, zero_division=0))
    cm = confusion_matrix(y_te, y_pred)
    print(f"  TN={cm[0,0]} FP={cm[0,1]} FN={cm[1,0]} TP={cm[1,1]}")
    return {"test_acc": test_acc, "f1": f1, "auc": auc, "cv_auc": cv_scores.mean()}


# ══════════════════════════════════════════════════════════════════════════════
# 5. SANITY CHECK — verify labels make scientific sense
# ══════════════════════════════════════════════════════════════════════════════

def sanity_check():
    print("\n── Sanity Check: label_risk() ──")
    cases = [
        # (temp, chl, turb, expected, description)
        (29.4, 0.5, 0.09, 0, "Bay of Bengal normal — LOW"),
        (29.4, 6.0, 0.09, 1, "Bay of Bengal bloom — HIGH"),
        (31.5, 0.5, 0.09, 1, "Extreme thermal stress — HIGH"),
        (28.0, 0.5, 0.09, 0, "Normal tropical — LOW"),
        (25.0, 8.0, 0.15, 1, "Upwelling bloom — HIGH"),
        (15.0, 2.0, 0.10, 0, "Temperate normal — LOW"),
        (22.0, 4.0, 0.60, 1, "Coastal eutrophic — HIGH"),
        (28.5, 3.5, 0.09, 1, "Bloom + warm combo — HIGH"),
        (20.0, 1.0, 0.08, 0, "Clean temperate — LOW"),
        (30.0, 0.4, 0.40, 1, "Thermal + turbidity — HIGH"),
    ]
    all_pass = True
    for temp, chl, turb, expected, desc in cases:
        got = label_risk(temp, chl, turb)
        status = "✓" if got == expected else "✗ FAIL"
        if got != expected:
            all_pass = False
        print(f"  {status}  T={temp} Chl={chl} Turb={turb} → {got} ({desc})")
    print(f"\n  {'All cases pass ✓' if all_pass else 'SOME CASES FAILED ✗'}")
    return all_pass


# ══════════════════════════════════════════════════════════════════════════════
# 6. MAIN TRAINING
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "█"*58)
    print("  OceanSense — Scientifically Correct ML Training")
    print("█"*58)

    sanity_check()

    df_real = load_real_data()
    df_syn  = build_synthetic(n=8000)
    df      = pd.concat([
        df_real[["latitude","longitude","temperature","chlorophyll","turbidity","risk","bloom"]],
        df_syn
    ], ignore_index=True).sample(frac=1, random_state=SEED).reset_index(drop=True)

    df = engineer_features(df)
    X  = df[FEATURES]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    print(f"\nFinal dataset: {len(df)} rows")
    print(f"  Risk  balance: {df.risk.value_counts().to_dict()}")
    print(f"  Bloom balance: {df.bloom.value_counts().to_dict()}")

    def make_pipeline(clf):
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler",  StandardScaler()),
            ("clf",     clf)
        ])

    # ── RISK MODEL ─────────────────────────────────────────────────────────────
    print("\n\n▶ Training RISK MODEL...")
    y_risk = df["risk"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y_risk, test_size=0.2, random_state=SEED, stratify=y_risk)

    risk_params = {
        "clf__n_estimators":     [150, 250, 350],
        "clf__max_depth":        [3, 4],          # shallow = less overfit
        "clf__learning_rate":    [0.03, 0.05, 0.08],
        "clf__subsample":        [0.7, 0.8],
        "clf__min_samples_leaf": [10, 20, 30],    # large leaf = less overfit
        "clf__max_features":     ["sqrt", 0.7],
    }
    risk_search = RandomizedSearchCV(
        make_pipeline(GradientBoostingClassifier(random_state=SEED)),
        risk_params, n_iter=25, cv=cv, scoring="roc_auc",
        random_state=SEED, n_jobs=-1, verbose=0
    )
    risk_search.fit(X_tr, y_tr)
    risk_model = risk_search.best_estimator_
    print(f"  Best: {risk_search.best_params_}")
    risk_metrics = evaluate("RISK MODEL", risk_model, X_tr, X_te, y_tr, y_te, cv, X, y_risk)
    joblib.dump(risk_model, "models/risk_model.pkl")
    print("  ✓ Saved → models/risk_model.pkl")

    # ── BLOOM MODEL ────────────────────────────────────────────────────────────
    print("\n\n▶ Training BLOOM MODEL...")
    y_bloom = df["bloom"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y_bloom, test_size=0.2, random_state=SEED, stratify=y_bloom)

    bloom_params = {
        "clf__n_estimators":    [150, 250, 350],
        "clf__max_depth":       [3, 4, 5],
        "clf__learning_rate":   [0.03, 0.05, 0.08],
        "clf__subsample":       [0.7, 0.8],
        "clf__colsample_bytree":[0.7, 0.8, 1.0],
        "clf__reg_alpha":       [0.1, 0.5, 1.0],
        "clf__reg_lambda":      [1.0, 2.0, 3.0],
        "clf__min_child_weight":[5, 10],
    }
    bloom_search = RandomizedSearchCV(
        make_pipeline(XGBClassifier(eval_metric="logloss", random_state=SEED)),
        bloom_params, n_iter=25, cv=cv, scoring="roc_auc",
        random_state=SEED, n_jobs=-1, verbose=0
    )
    bloom_search.fit(X_tr, y_tr)
    bloom_model = CalibratedClassifierCV(bloom_search.best_estimator_, cv=3, method="isotonic")
    bloom_model.fit(X_tr, y_tr)
    print(f"  Best: {bloom_search.best_params_}")
    bloom_metrics = evaluate("BLOOM MODEL", bloom_model, X_tr, X_te, y_tr, y_te, cv, X, y_bloom)
    joblib.dump(bloom_model, "models/bloom_model.pkl")
    print("  ✓ Saved → models/bloom_model.pkl")

    # ── OIL SPILL MODEL ────────────────────────────────────────────────────────
    print("\n\n▶ Training OIL SPILL MODEL...")
    rng = np.random.default_rng(SEED)
    n = 5000; nc = int(n * 0.72); ns = n - nc
    sar_c = rng.normal(-12, 4.5, nc); tc = rng.uniform(5,33,nc)
    cc = np.abs(rng.lognormal(0.1,0.8,nc)).clip(0.01,20)
    wc = rng.uniform(1,15,nc); wvc = rng.uniform(0.3,4.0,nc)
    lc = (rng.random(nc) < 0.04).astype(int)
    sar_s = rng.normal(-22, 3.5, ns); ts = rng.uniform(5,33,ns)
    cs2 = np.abs(rng.lognormal(0.1,0.8,ns)).clip(0.01,20)
    ws = rng.uniform(0.5,8,ns); wvs = rng.uniform(0.1,1.5,ns)
    ls = np.where(rng.random(ns) < 0.04, 0, 1)
    df_sar = pd.DataFrame({
        "sar_vv":       np.concatenate([sar_c,sar_s]).round(4),
        "temperature":  np.concatenate([tc,ts]).round(4),
        "chlorophyll":  np.concatenate([cc,cs2]).round(4),
        "wind_speed":   np.concatenate([wc,ws]).round(4),
        "wave_height":  np.concatenate([wvc,wvs]).round(4),
        "sar_wind_ratio": (np.concatenate([sar_c,sar_s])/(np.concatenate([wc,ws])+0.1)).round(4),
        "oil_spill":    np.concatenate([lc,ls])
    }).sample(frac=1, random_state=SEED).reset_index(drop=True)

    SAR_FEATURES = ["sar_vv","temperature","chlorophyll","wind_speed","wave_height","sar_wind_ratio"]
    X_sar = df_sar[SAR_FEATURES]; y_sar = df_sar["oil_spill"]
    X_tr, X_te, y_tr, y_te = train_test_split(X_sar, y_sar, test_size=0.2, random_state=SEED, stratify=y_sar)

    oil_params = {
        "clf__n_estimators":    [150, 250, 350],
        "clf__max_depth":       [3, 4, 5],
        "clf__learning_rate":   [0.03, 0.05, 0.08],
        "clf__subsample":       [0.7, 0.8, 0.9],
        "clf__colsample_bytree":[0.7, 0.8, 1.0],
        "clf__scale_pos_weight":[1, 2, 3],
    }
    oil_search = RandomizedSearchCV(
        make_pipeline(XGBClassifier(eval_metric="logloss", random_state=SEED)),
        oil_params, n_iter=20, cv=StratifiedKFold(5, shuffle=True, random_state=SEED),
        scoring="roc_auc", random_state=SEED, n_jobs=-1, verbose=0
    )
    oil_search.fit(X_tr, y_tr)
    oil_model = oil_search.best_estimator_
    print(f"  Best: {oil_search.best_params_}")
    oil_metrics = evaluate("OIL SPILL MODEL", oil_model, X_tr, X_te, y_tr, y_te,
                            StratifiedKFold(5, shuffle=True, random_state=SEED), X_sar, y_sar)
    joblib.dump({"model": oil_model, "features": SAR_FEATURES}, "models/oil_spill_model.pkl")
    print("  ✓ Saved → models/oil_spill_model.pkl")

    # ── ANOMALY MODEL ──────────────────────────────────────────────────────────
    print("\n\n▶ Training ANOMALY MODEL...")
    df_normal = df[(df["risk"] == 0) & (df["bloom"] == 0)].copy()
    print(f"  Normal samples: {len(df_normal)}")
    anomaly_model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
        ("iso",     IsolationForest(n_estimators=300, contamination=0.04,
                                    max_samples=min(256, len(df_normal)), random_state=SEED))
    ])
    anomaly_model.fit(df_normal[FEATURES])
    preds_normal = anomaly_model.predict(df_normal[FEATURES])
    preds_risky  = anomaly_model.predict(df[(df["risk"]==1)|(df["bloom"]==1)][FEATURES])
    print(f"  Anomaly rate — normal: {(preds_normal==-1).mean():.2%} | risky: {(preds_risky==-1).mean():.2%}")
    joblib.dump(anomaly_model, "models/anomaly_model.pkl")
    print("  ✓ Saved → models/anomaly_model.pkl")

    # ── SUMMARY ────────────────────────────────────────────────────────────────
    print("\n\n" + "█"*58)
    print("  TRAINING COMPLETE")
    print("█"*58)
    print(f"  Risk  — AUC:{risk_metrics['auc']:.4f}  F1:{risk_metrics['f1']:.4f}  Acc:{risk_metrics['test_acc']:.4f}")
    print(f"  Bloom — AUC:{bloom_metrics['auc']:.4f}  F1:{bloom_metrics['f1']:.4f}  Acc:{bloom_metrics['test_acc']:.4f}")
    print(f"  Oil   — AUC:{oil_metrics['auc']:.4f}  F1:{oil_metrics['f1']:.4f}  Acc:{oil_metrics['test_acc']:.4f}")

    import json
    with open("models/feature_config.json", "w") as f:
        json.dump({"features": FEATURES, "sar_features": SAR_FEATURES}, f, indent=2)
    print("  ✓ Feature config saved → models/feature_config.json")
    print("█"*58)

    # Final sanity check on trained model
    print("\n── Post-training prediction check ──")
    import services.prediction_service as ps
    ps._risk_model = None  # force reload
    from services.prediction_service import get_environment_prediction
    test_cases = [
        (29.4, 0.5, 0.09, 15.0, 88.0,  "Bay of Bengal normal",    "Low"),
        (29.4, 6.0, 0.09, 15.0, 88.0,  "Bay of Bengal bloom",     "High"),
        (31.5, 0.5, 0.09, 10.0, 75.0,  "Extreme thermal stress",  "High"),
        (25.0, 8.0, 0.15, -10.0, 70.0, "Upwelling bloom",         "High"),
        (15.0, 2.0, 0.10, 50.0, 5.0,   "Temperate normal",        "Low"),
        (22.0, 7.0, 0.60, 20.0, 80.0,  "Coastal eutrophic",       "High"),
    ]
    for temp, chl, turb, lat, lon, desc, expected in test_cases:
        r = get_environment_prediction(temp, chl, turb, lat, lon)
        got = r["risk_label"]
        status = "✓" if got == expected else "✗ WRONG"
        print(f"  {status}  {desc}: T={temp} Chl={chl} → {got} (expected {expected})")


if __name__ == "__main__":
    main()
