"""
Pollution Detection Service
============================
Detects sudden pollutant discharge events by comparing current satellite
readings against a rolling baseline for the same location.

Pollution signals:
  - Turbidity spike  : sudden increase > 2x baseline (sediment/industrial discharge)
  - Chlorophyll spike: rapid bloom onset > 3x baseline (nutrient runoff)
  - SAR anomaly      : low backscatter patch not explained by wind (oil/chemical slick)
  - Temp anomaly     : thermal discharge from power plants / industrial cooling

Data sources:
  - Baseline: 90-day rolling mean from GEE (same NOAA OISST + MODIS pipeline)
  - Current:  30-day mean (already fetched by environment_service)
"""

import os
import json
from datetime import datetime, timezone
from utils.logger import get_logger

logger = get_logger(__name__)

POLLUTION_HISTORY_FILE = "outputs/pollution_history.json"


# ── Pollution type definitions ─────────────────────────────────────────────────
POLLUTION_TYPES = {
    "turbidity_spike": {
        "name":        "Sediment / Industrial Discharge",
        "description": "Sudden turbidity increase indicates sediment runoff, dredging, or industrial effluent discharge.",
        "severity_fn": lambda ratio: "Critical" if ratio > 4 else ("High" if ratio > 2.5 else "Moderate"),
        "color":       "#ff8c00",
    },
    "chlorophyll_spike": {
        "name":        "Nutrient Pollution / Eutrophication",
        "description": "Rapid chlorophyll increase indicates nutrient runoff (fertilizers, sewage) causing eutrophication.",
        "severity_fn": lambda ratio: "Critical" if ratio > 5 else ("High" if ratio > 3 else "Moderate"),
        "color":       "#ff4d4d",
    },
    "sar_slick": {
        "name":        "Oil / Chemical Slick",
        "description": "Low SAR backscatter patch indicates surface oil film or chemical discharge dampening ocean surface.",
        "severity_fn": lambda db_drop: "Critical" if db_drop > 8 else ("High" if db_drop > 5 else "Moderate"),
        "color":       "#cc0000",
    },
    "thermal_discharge": {
        "name":        "Thermal Pollution",
        "description": "Anomalous SST increase indicates thermal discharge from industrial cooling or power plant.",
        "severity_fn": lambda delta: "Critical" if delta > 5 else ("High" if delta > 3 else "Moderate"),
        "color":       "#ff6b35",
    },
}


def detect_pollution(
    current_env: dict,
    baseline_env: dict,
    prediction: dict,
    location: str,
) -> dict:
    """
    Compare current satellite readings against 90-day baseline.
    Returns pollution events detected with type, severity, and evidence.

    Args:
        current_env:  dict from environment_service (30-day mean)
        baseline_env: dict from environment_service (90-day mean = baseline)
        prediction:   dict from prediction_service (includes sar_value)
        location:     location name string

    Returns:
        {
          "pollution_detected": bool,
          "events": [...],
          "overall_severity": "None"|"Moderate"|"High"|"Critical",
          "summary": str
        }
    """
    events = []

    curr_turb = current_env.get("turbidity")
    base_turb = baseline_env.get("turbidity")
    curr_chl  = current_env.get("chlorophyll")
    base_chl  = baseline_env.get("chlorophyll")
    curr_temp = current_env.get("temperature")
    base_temp = baseline_env.get("temperature")
    sar_val   = prediction.get("sar_value")

    # ── 1. Turbidity spike ─────────────────────────────────────────────────────
    if curr_turb is not None and base_turb is not None and base_turb > 0.01:
        ratio = curr_turb / base_turb
        if ratio >= 2.0:
            ptype = POLLUTION_TYPES["turbidity_spike"]
            events.append({
                "type":        "turbidity_spike",
                "name":        ptype["name"],
                "description": ptype["description"],
                "severity":    ptype["severity_fn"](ratio),
                "evidence":    f"Turbidity {curr_turb:.3f} vs baseline {base_turb:.3f} ({ratio:.1f}x increase)",
                "current":     curr_turb,
                "baseline":    base_turb,
                "ratio":       round(ratio, 2),
            })

    # ── 2. Chlorophyll spike (nutrient pollution) ──────────────────────────────
    if curr_chl is not None and base_chl is not None and base_chl > 0.05:
        ratio = curr_chl / base_chl
        if ratio >= 3.0:
            ptype = POLLUTION_TYPES["chlorophyll_spike"]
            events.append({
                "type":        "chlorophyll_spike",
                "name":        ptype["name"],
                "description": ptype["description"],
                "severity":    ptype["severity_fn"](ratio),
                "evidence":    f"Chlorophyll {curr_chl:.3f} mg/m³ vs baseline {base_chl:.3f} mg/m³ ({ratio:.1f}x increase)",
                "current":     curr_chl,
                "baseline":    base_chl,
                "ratio":       round(ratio, 2),
            })

    # ── 3. SAR oil/chemical slick ──────────────────────────────────────────────
    if sar_val is not None and prediction.get("oil_spill_detected"):
        # SAR below -20 dB with oil spill flag = confirmed slick
        db_drop = abs(sar_val - (-12))  # -12 dB is clean ocean baseline
        if db_drop >= 5:
            ptype = POLLUTION_TYPES["sar_slick"]
            events.append({
                "type":        "sar_slick",
                "name":        ptype["name"],
                "description": ptype["description"],
                "severity":    ptype["severity_fn"](db_drop),
                "evidence":    f"SAR backscatter {sar_val:.2f} dB (clean ocean baseline ~-12 dB, drop = {db_drop:.1f} dB)",
                "sar_value":   sar_val,
                "db_drop":     round(db_drop, 2),
            })

    # ── 4. Thermal discharge ───────────────────────────────────────────────────
    if curr_temp is not None and base_temp is not None:
        delta = curr_temp - base_temp
        if delta >= 3.0:
            ptype = POLLUTION_TYPES["thermal_discharge"]
            events.append({
                "type":        "thermal_discharge",
                "name":        ptype["name"],
                "description": ptype["description"],
                "severity":    ptype["severity_fn"](delta),
                "evidence":    f"SST {curr_temp:.2f}°C vs baseline {base_temp:.2f}°C (+{delta:.1f}°C anomaly)",
                "current":     curr_temp,
                "baseline":    base_temp,
                "delta":       round(delta, 2),
            })

    # ── Aggregate severity ─────────────────────────────────────────────────────
    severity_rank = {"None": 0, "Moderate": 1, "High": 2, "Critical": 3}
    if events:
        overall = max(events, key=lambda e: severity_rank.get(e["severity"], 0))["severity"]
    else:
        overall = "None"

    pollution_detected = len(events) > 0

    if pollution_detected:
        names = ", ".join(e["name"] for e in events)
        summary = (
            f"{overall} pollution event detected at {location}: {names}. "
            f"Immediate monitoring recommended."
        )
    else:
        summary = f"No pollution discharge detected at {location}."

    result = {
        "pollution_detected": pollution_detected,
        "events":             events,
        "overall_severity":   overall,
        "summary":            summary,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "location":           location,
    }

    if pollution_detected:
        _save_pollution_history(result)

    return result


def _save_pollution_history(event: dict):
    """Append to pollution history file."""
    os.makedirs("outputs", exist_ok=True)
    history = []
    if os.path.exists(POLLUTION_HISTORY_FILE):
        try:
            with open(POLLUTION_HISTORY_FILE) as f:
                history = json.load(f)
        except Exception:
            history = []
    history.insert(0, event)
    history = history[:500]  # keep last 500
    with open(POLLUTION_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, default=str)


def get_pollution_history(limit: int = 50) -> list:
    if not os.path.exists(POLLUTION_HISTORY_FILE):
        return []
    try:
        with open(POLLUTION_HISTORY_FILE) as f:
            return json.load(f)[:limit]
    except Exception:
        return []
