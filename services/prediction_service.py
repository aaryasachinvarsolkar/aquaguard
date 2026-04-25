import pandas as pd
import joblib
import numpy as np
import json
import os
from utils.config_loader import get_config
from utils.logger import get_logger
from services.oilspill_service import detect_oil_spill
from pipeline.risk_calculation import calculate_risk_score

try:
    import shap
    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False

logger = get_logger(__name__)

_config          = None
_risk_model      = None
_bloom_model     = None
_oil_spill_model = None
_oil_features    = None
_anomaly_model      = None
_feature_list       = None
_pollution_model    = None
_pollution_features = None

RISK_LABELS   = {0: "Low", 1: "High"}
BASE_FEATURES = ["temperature", "chlorophyll", "turbidity"]

# Extended feature list — matches train_improved_models.py
EXTENDED_FEATURES = [
    "temperature", "chlorophyll", "turbidity",
    "chl_log", "chl_temp", "temp_anomaly",
    "turb_chl_ratio", "chl_squared", "temp_chl_bloom_idx",
    "is_tropical", "lat_abs"
]


def _engineer_features(temp: float, chl: float, turb: float,
                        lat: float = 10.0) -> dict:
    """Build the full feature dict for a single prediction."""
    return {
        "temperature":        temp,
        "chlorophyll":        chl,
        "turbidity":          turb,
        "chl_log":            float(np.log1p(chl)),
        "chl_temp":           float(chl * temp),
        "temp_anomaly":       float(abs(temp - 28.0)),
        "turb_chl_ratio":     float(turb / (chl + 0.01)),
        "chl_squared":        float(chl ** 2),
        "temp_chl_bloom_idx": float((chl > 3) and (temp > 27)),
        "is_tropical":        float(abs(lat) < 23.5),
        "lat_abs":            float(abs(lat)),
    }


def _load_models():
    global _risk_model, _bloom_model, _oil_spill_model, _oil_features
    global _anomaly_model, _config, _feature_list
    global _pollution_model, _pollution_features

    if _risk_model is not None:
        return

    _config = get_config()["models"]

    _risk_model  = joblib.load(_config["risk_model_path"])
    _bloom_model = joblib.load(_config["bloom_model_path"])

    oil_raw = joblib.load(_config["oil_spill_model_path"])
    if isinstance(oil_raw, dict):
        _oil_spill_model = oil_raw["model"]
        _oil_features    = oil_raw["features"]
    else:
        _oil_spill_model = oil_raw
        _oil_features    = ["sar_vv", "temperature", "chlorophyll", "wind_speed"]

    try:
        _anomaly_model = joblib.load(_config["anomaly_model_path"])
    except Exception:
        _anomaly_model = None

    # Pollution model
    try:
        poll_raw = joblib.load("models/pollution_model.pkl")
        _pollution_model    = poll_raw
        _pollution_features = poll_raw.get("features", [])
    except Exception:
        _pollution_model = None

    try:
        feat_cfg_path = "models/feature_config.json"
        if os.path.exists(feat_cfg_path):
            with open(feat_cfg_path) as f:
                _feature_list = json.load(f)["features"]
        else:
            _feature_list = BASE_FEATURES
    except Exception:
        _feature_list = BASE_FEATURES

    logger.info(f"Models loaded | features={_feature_list}")


def _get_feature_contributions(model, feature_values: list, feature_names: list) -> list[dict]:
    """
    Extract per-feature contributions using SHAP if available,
    falling back to feature_importances_ for tree models.
    """
    # Try SHAP first — gives actual contribution values, not just importances
    if _SHAP_AVAILABLE:
        try:
            clf = model
            if hasattr(model, "named_steps"):
                clf = model.named_steps.get("clf", model)
            elif hasattr(model, "estimator"):
                inner = model.estimator
                if hasattr(inner, "named_steps"):
                    clf = inner.named_steps.get("clf", inner)

            row = np.array(feature_values).reshape(1, -1)
            explainer = shap.TreeExplainer(clf)
            shap_vals = explainer.shap_values(row)
            # For binary classifiers shap_values returns list [class0, class1]
            vals = shap_vals[1] if isinstance(shap_vals, list) else shap_vals
            vals = vals[0]  # single row
            abs_total = sum(abs(v) for v in vals) or 1
            contribs = []
            for name, val, sv in zip(feature_names, feature_values, vals):
                contribs.append({
                    "feature":          name,
                    "value":            round(float(val), 4),
                    "importance":       round(float(abs(sv)), 4),
                    "shap_value":       round(float(sv), 4),
                    "contribution_pct": round(float(abs(sv) / abs_total) * 100, 1)
                })
            return sorted(contribs, key=lambda x: x["importance"], reverse=True)
        except Exception as e:
            logger.debug(f"SHAP failed, falling back to feature_importances_: {e}")

    # Fallback — feature importances from tree model
    try:
        clf = model
        if hasattr(model, "named_steps"):
            clf = model.named_steps.get("clf", model)
        elif hasattr(model, "estimator"):
            inner = model.estimator
            if hasattr(inner, "named_steps"):
                clf = inner.named_steps.get("clf", inner)

        importances = clf.feature_importances_
        total = sum(importances) or 1
        contribs = []
        for name, val, imp in zip(feature_names, feature_values, importances):
            contribs.append({
                "feature":          name,
                "value":            round(float(val), 4),
                "importance":       round(float(imp), 4),
                "shap_value":       None,
                "contribution_pct": round(float(imp / total) * 100, 1)
            })
        return sorted(contribs, key=lambda x: x["importance"], reverse=True)
    except Exception:
        return []


def _explain_risk(risk: int, risk_conf: float, contribs: list, temp: float, chl: float, turb: float) -> str:
    top = contribs[0]["feature"] if contribs else "environmental conditions"
    label = RISK_LABELS.get(risk, "Unknown")
    conf_pct = round(risk_conf * 100, 1)

    if risk == 1:
        return (
            f"Ecosystem risk is HIGH ({conf_pct}% confidence). "
            f"The primary driver is {top} (T={temp}°C, Chl={chl} mg/m³, Turb={turb}). "
            f"These values exceed safe thresholds for marine ecosystem health."
        )
    else:
        return (
            f"Ecosystem risk is LOW ({conf_pct}% confidence). "
            f"Current conditions — T={temp}°C, Chl={chl} mg/m³, Turb={turb} — "
            f"are within normal ranges. The most influential factor was {top}."
        )


def _explain_bloom(bloom: int, bloom_conf: float, contribs: list, chl: float) -> str:
    conf_pct = round(bloom_conf * 100, 1)
    top = contribs[0]["feature"] if contribs else "chlorophyll"
    if bloom == 1:
        return (
            f"Algal bloom DETECTED ({conf_pct}% confidence). "
            f"Chlorophyll-a concentration ({chl} mg/m³) is the primary indicator. "
            f"Elevated {top} levels suggest active phytoplankton growth."
        )
    else:
        return (
            f"No algal bloom detected ({conf_pct}% confidence). "
            f"Chlorophyll-a ({chl} mg/m³) is within normal range."
        )


def _explain_oil(oil: int, sar_value, oil_conf, source: str) -> str:
    if sar_value is None:
        return f"Oil spill assessment used fallback method ({source}). SAR data unavailable for this region/time."
    sar_str = f"{sar_value:.2f} dB"
    if oil == 1:
        return (
            f"Oil spill DETECTED. SAR backscatter = {sar_str} (low backscatter indicates surface dampening). "
            f"ML model confidence: {round(oil_conf*100,1) if oil_conf else 'N/A'}%. Source: {source}."
        )
    else:
        return (
            f"No oil spill detected. SAR backscatter = {sar_str} is within normal ocean surface range. "
            f"Source: {source}."
        )


def _ml_oil_spill(sar_value: float, temp: float, chlorophyll: float) -> dict:
    cfg        = get_config()["oil_spill_model"]
    wind_proxy = max(
        cfg["wind_proxy_min"],
        cfg["wind_proxy_base"] - chlorophyll * cfg["wind_proxy_chl_factor"]
    )
    # Build feature dict matching whatever features the model was trained on
    all_feats = {
        "sar_vv":          sar_value,
        "temperature":     temp,
        "chlorophyll":     chlorophyll,
        "wind_speed":      wind_proxy,
        "wave_height":     max(0.3, wind_proxy * 0.25),
        "sar_wind_ratio":  sar_value / (wind_proxy + 0.1),
    }
    feat_row = pd.DataFrame([{k: all_feats[k] for k in _oil_features if k in all_feats}])
    oil_pred = int(_oil_spill_model.predict(feat_row)[0])
    oil_prob = float(_oil_spill_model.predict_proba(feat_row)[0][1])
    return {"oil_spill": oil_pred, "oil_spill_confidence": round(oil_prob, 4)}


def get_environment_prediction(
    temp: float, chlorophyll: float, turbidity: float, lat: float, lon: float
) -> dict:
    _load_models()

    # Build feature row — extended if new models, base if old
    feat_dict = _engineer_features(temp, chlorophyll, turbidity, lat)
    feat_vals = [feat_dict[f] for f in _feature_list]
    features  = pd.DataFrame([feat_dict])[_feature_list]

    # Risk
    risk      = int(_risk_model.predict(features)[0])
    risk_prob = _risk_model.predict_proba(features)[0]
    risk_conf = round(float(max(risk_prob)), 4)
    risk_contribs = _get_feature_contributions(_risk_model, feat_vals, _feature_list)

    # Confidence calibration check
    # If confidence is extremely high (> 0.99), it may be an overfit on synthetic data
    requires_verification = risk_conf > 0.99

    # Bloom
    bloom      = int(_bloom_model.predict(features)[0])
    bloom_prob = _bloom_model.predict_proba(features)[0]
    bloom_conf = round(float(max(bloom_prob)), 4)
    bloom_contribs = _get_feature_contributions(_bloom_model, feat_vals, _feature_list)

    # Rule-based risk — computed first, used as override only for extreme cases
    rule_risk = calculate_risk_score(temp, chlorophyll, turbidity)

    # SAR oil spill
    sar_result = detect_oil_spill(lat, lon)
    sar_value  = sar_result.get("sar_value")

    if sar_value is not None:
        ml_oil         = _ml_oil_spill(sar_value, temp, chlorophyll)
        oil_spill      = ml_oil["oil_spill"]
        oil_confidence = ml_oil["oil_spill_confidence"]
        oil_source     = f"ML model on {sar_result.get('source', 'Sentinel-1')}"
    else:
        oil_spill      = sar_result.get("oil_spill", 0)
        oil_confidence = None
        oil_source     = sar_result.get("source", "Sentinel-1 unavailable")

    # ── Targeted overrides for extreme single-factor conditions ───────────────
    # These are scientifically unambiguous — no model uncertainty needed
    if risk == 0:
        if temp > 30.5:                          # lowered from 31.0
            risk = 1; risk_conf = 0.90
            logger.info("Risk→High: extreme SST (>30.5°C)")
        elif chlorophyll > 2.5 and temp > 26.5:  # lowered from 3.0 / 27.0
            risk = 1; risk_conf = 0.85
            logger.info("Risk→High: bloom+warm combo")
        elif turbidity > 0.7:                    # lowered from 1.0
            risk = 1; risk_conf = 0.85
            logger.info("Risk→High: severe turbidity (>0.7)")

    if bloom == 0 and chlorophyll > 4.5:         # lowered from 5.0
        bloom = 1; bloom_conf = 0.90
        logger.info(f"Bloom→detected: Chl={chlorophyll} > 4.5 mg/m³")

    # Human-readable explanations
    explanations = {
        "risk":      _explain_risk(risk, risk_conf, risk_contribs, temp, chlorophyll, turbidity),
        "bloom":     _explain_bloom(bloom, bloom_conf, bloom_contribs, chlorophyll),
        "oil_spill": _explain_oil(oil_spill, sar_value, oil_confidence, oil_source),
        "rule_based": (
            f"Rule-based score: {rule_risk.get('risk_score', 'N/A')}/1.0 ({rule_risk.get('risk_label')}). "
            f"Factors: {', '.join(rule_risk.get('contributing_factors', [])) or 'None detected'}."
        )
    }

    # Anomaly detection — is this location behaving unusually?
    anomaly_result = {"is_anomaly": False, "anomaly_score": None, "anomaly_explanation": ""}
    if _anomaly_model is not None:
        try:
            iso_pred  = _anomaly_model.predict(features)[0]   # -1=anomaly, 1=normal
            iso_score = float(_anomaly_model.decision_function(features)[0])
            is_anomaly = iso_pred == -1
            anomaly_reasons = []
            if temp > 31:
                anomaly_reasons.append(f"unusually high temperature ({temp}°C)")
            if chlorophyll > 8:
                anomaly_reasons.append(f"extreme chlorophyll ({chlorophyll} mg/m³)")
            if turbidity > 0.8:
                anomaly_reasons.append(f"very high turbidity ({turbidity})")
            anomaly_result = {
                "is_anomaly": bool(is_anomaly),
                "anomaly_score": round(iso_score, 4),
                "anomaly_explanation": (
                    f"Anomalous conditions detected: {'; '.join(anomaly_reasons)}." if is_anomaly and anomaly_reasons
                    else "Anomalous pattern detected — conditions are statistically unusual." if is_anomaly
                    else "Conditions are within normal historical range."
                )
            }
        except Exception as e:
            logger.warning(f"Anomaly detection failed: {e}")

    result = {
        "risk":               risk,
        "risk_label":         RISK_LABELS.get(risk, "Unknown"),
        "risk_confidence":    risk_conf,
        "risk_feature_contributions": risk_contribs,
        "bloom":              bloom,
        "bloom_detected":     bloom == 1,
        "bloom_confidence":   bloom_conf,
        "bloom_feature_contributions": bloom_contribs,
        "oil_spill":          oil_spill,
        "oil_spill_detected": oil_spill == 1,
        "oil_spill_confidence": oil_confidence,
        "sar_value":          sar_value,
        "rule_based_risk":    rule_risk,
        "oil_spill_source":   oil_source,
        "anomaly":            anomaly_result,
        "explanations":       explanations
    }

    logger.info(f"Prediction result: risk={result['risk_label']} bloom={bloom} oil={oil_spill}")
    return result
