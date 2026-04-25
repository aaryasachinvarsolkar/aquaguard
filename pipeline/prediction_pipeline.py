from services.location_service import get_coordinates
from services.environment_service import get_environment_data
from services.prediction_service import get_environment_prediction
from services.species_service import get_species_impact
from services.alert_service import send_alert, send_pollution_alert
from services.pollution_service import detect_pollution
from utils.logger import get_logger

logger = get_logger(__name__)


def run_prediction_pipeline(location: str) -> dict:
    """
    Full real-time prediction pipeline:
    1. Geocode location
    2. Fetch current satellite data (30-day mean) + baseline (90-day mean)
    3. Run ML models (risk, bloom, oil spill, anomaly)
    4. Detect pollution discharge by comparing current vs baseline
    5. Fetch species with IUCN status + harm reasons
    6. Send alerts: risk/bloom/oil alert + dedicated pollution alert if discharge detected
    """

    # 1. Location → lat/lon
    lat, lon = get_coordinates(location)
    if lat is None or lon is None:
        return {"error": f"Could not geocode location: {location}"}

    logger.info(f"Pipeline started | location={location} | coords=({lat}, {lon})")

    # 2a. Current satellite data (30-day mean)
    try:
        env = get_environment_data(lat, lon)
    except RuntimeError as e:
        logger.error(f"Environment data fetch failed: {e}")
        return {"error": str(e)}

    # 2b. Baseline satellite data (90-day mean) for pollution comparison
    try:
        baseline_env = get_environment_data(lat, lon, lookback_days=90)
    except Exception:
        baseline_env = env  # fallback: no baseline comparison possible

    temp        = env.get("temperature") or 0
    chlorophyll = env.get("chlorophyll") or 0
    turbidity   = env.get("turbidity") or 0

    # 3. ML predictions
    prediction = get_environment_prediction(temp, chlorophyll, turbidity, lat, lon)

    # 4. Pollution discharge detection (current vs 90-day baseline)
    pollution = detect_pollution(
        current_env=env,
        baseline_env=baseline_env,
        prediction=prediction,
        location=location,
    )
    if pollution["pollution_detected"]:
        logger.warning(
            f"POLLUTION DETECTED at {location} | "
            f"Severity={pollution['overall_severity']} | "
            f"Events={[e['type'] for e in pollution['events']]}"
        )
        send_pollution_alert(location, pollution, env)

    # 5. Species impact
    species = get_species_impact(lat, lon, prediction=prediction, environment=env)

    # 6. Standard risk/bloom/oil alert
    should_alert = (
        prediction.get("oil_spill") == 1
        or prediction.get("risk") == 1
        or species.get("harmed_count", 0) > 0
    )
    if should_alert:
        send_alert(location, prediction, env, species)

    return {
        "location":    location,
        "coordinates": {"lat": lat, "lon": lon},
        "environment": env,
        "baseline_environment": baseline_env,
        "prediction":  prediction,
        "pollution":   pollution,
        "species":     species,
    }
