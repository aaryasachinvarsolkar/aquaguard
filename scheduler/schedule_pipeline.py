"""
AquaGuard Scheduler — runs the full prediction pipeline on a configurable
interval for all monitored ocean locations.

Features:
- Saves each run result to outputs/scheduler_results.json
- Maintains a run history log (outputs/scheduler_history.log)
- Graceful shutdown on Ctrl+C
- Interval configurable via SCHEDULER_INTERVAL_HOURS env var (default: 6)

Run:
    python scheduler/schedule_pipeline.py
"""

import os
import json
import signal
import sys
import time
from datetime import datetime, timezone

import schedule

from pipeline.prediction_pipeline import run_prediction_pipeline
from services.alert_service import send_alert
from utils.logger import get_logger

logger = get_logger(__name__)

RESULTS_FILE  = "outputs/scheduler_results.json"
HISTORY_FILE  = "outputs/scheduler_history.log"
DEFAULT_INTERVAL_HOURS = 120  # 5 days

DEFAULT_LOCATIONS = [
    "Arabian Sea",
    "Gulf of Mexico",
    "Bay of Bengal",
    "Persian Gulf",
    "Baltic Sea",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_monitored_locations() -> list[str]:
    env = os.getenv("MONITORED_LOCATIONS", "")
    if env.strip():
        return [loc.strip() for loc in env.split(",") if loc.strip()]
    return DEFAULT_LOCATIONS


def get_interval_hours() -> int:
    try:
        return int(os.getenv("SCHEDULER_INTERVAL_HOURS", DEFAULT_INTERVAL_HOURS))
    except ValueError:
        return DEFAULT_INTERVAL_HOURS


def _ensure_outputs_dir():
    os.makedirs("outputs", exist_ok=True)


def _load_results() -> dict:
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_results(results: dict):
    _ensure_outputs_dir()
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, default=str)


def _append_history(line: str):
    _ensure_outputs_dir()
    with open(HISTORY_FILE, "a") as f:
        f.write(line + "\n")


def _summarise(location: str, result: dict) -> dict:
    """Extract a compact summary from a full pipeline result."""
    pred     = result.get("prediction", {})
    env      = result.get("environment", {})
    species  = result.get("species", {})
    coords   = result.get("coordinates", {})
    pollution = result.get("pollution", {})

    return {
        "location":         location,
        "lat":              coords.get("lat"),
        "lon":              coords.get("lon"),
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "temperature":      env.get("temperature"),
        "chlorophyll":      env.get("chlorophyll"),
        "turbidity":        env.get("turbidity"),
        "data_source":      env.get("source"),
        "risk":             pred.get("risk"),
        "risk_label":       pred.get("risk_label"),
        "risk_confidence":  pred.get("risk_confidence"),
        "bloom_detected":   pred.get("bloom_detected"),
        "bloom_confidence": pred.get("bloom_confidence"),
        "oil_spill_detected":   pred.get("oil_spill_detected"),
        "oil_spill_confidence": pred.get("oil_spill_confidence"),
        "sar_value":        pred.get("sar_value"),
        "rule_risk_score":  pred.get("rule_based_risk", {}).get("risk_score"),
        "rule_risk_label":  pred.get("rule_based_risk", {}).get("risk_label"),
        "total_species":    species.get("total_found", 0),
        "threatened_count": species.get("threatened_count", 0),
        "harmed_count":     species.get("harmed_count", 0),
        "pollution_detected": pollution.get("pollution_detected", False),
        "pollution_severity": pollution.get("overall_severity", "None"),
        "pollution_events":   [e.get("type") for e in pollution.get("events", [])],
        "status":           "ok"
    }


# ── Main run function ──────────────────────────────────────────────────────────

def run_all_locations(progress_callback=None):
    locations = get_monitored_locations()
    run_time  = datetime.now(timezone.utc).isoformat()

    logger.info(f"Scheduled run started at {run_time} — {len(locations)} locations")
    _append_history(f"\n[{run_time}] === Scheduled run started ===")

    results = _load_results()

    for idx, location in enumerate(locations):
        if progress_callback:
            progress_callback(f"Processing {idx+1}/{len(locations)}: {location}")
        logger.info(f"Running pipeline for: {location}")
        try:
            raw = run_prediction_pipeline(location)

            if "error" in raw:
                summary = {
                    "location":  location,
                    "timestamp": run_time,
                    "status":    "error",
                    "error":     raw["error"]
                }
                logger.warning(f"{location} — pipeline error: {raw['error']}")
            else:
                summary = _summarise(location, raw)
                logger.info(
                    f"{location} | Risk={summary['risk_label']} "
                    f"({summary['risk_confidence']}) | "
                    f"Bloom={summary['bloom_detected']} | "
                    f"OilSpill={summary['oil_spill_detected']} | "
                    f"Threatened={summary['threatened_count']} | "
                    f"Harmed={summary['harmed_count']}"
                )

                # Send alert email if high-risk conditions detected
                try:
                    send_alert(
                        location=location,
                        prediction=raw.get("prediction", {}),
                        environment=raw.get("environment", {}),
                        species=raw.get("species", {})
                    )
                except Exception as ae:
                    logger.warning(f"Alert send failed for {location}: {ae}")

            results[location] = summary
            _save_results(results)

            history_line = (
                f"[{run_time}] {location} | "
                f"status={summary['status']} | "
                f"risk={summary.get('risk_label', 'N/A')} | "
                f"bloom={summary.get('bloom_detected', 'N/A')} | "
                f"oil={summary.get('oil_spill_detected', 'N/A')}"
            )
            _append_history(history_line)

        except Exception as e:
            logger.error(f"Pipeline failed for {location}: {e}")
            results[location] = {
                "location":  location,
                "timestamp": run_time,
                "status":    "error",
                "error":     str(e)
            }
            _save_results(results)
            _append_history(f"[{run_time}] {location} | status=error | {e}")

    logger.info(f"Scheduled run complete — results saved to {RESULTS_FILE}")
    _append_history(f"[{run_time}] === Run complete ===")


# ── Graceful shutdown ──────────────────────────────────────────────────────────

def _handle_shutdown(sig, frame):
    logger.info("Scheduler shutting down gracefully...")
    sys.exit(0)


signal.signal(signal.SIGINT,  _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    interval = get_interval_hours()
    locations = get_monitored_locations()

    logger.info(f"AquaGuard Scheduler starting — interval: every {interval}h")
    logger.info(f"Monitoring {len(locations)} locations: {locations}")

    # Run immediately on startup
    run_all_locations()

    # Schedule recurring runs
    schedule.every(interval).hours.do(run_all_locations)

    while True:
        schedule.run_pending()
        time.sleep(30)
