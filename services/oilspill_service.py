import random
import math
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

# ── GEE initialisation (lazy, optional) ───────────────────────────────────────
_ee_ready = False

def _try_init_ee():
    """Attempt to initialise GEE. Returns True on success, False otherwise."""
    global _ee_ready
    if _ee_ready:
        return True
    try:
        import ee
        from utils.config_loader import get_config
        config = get_config()
        project = config.get("gee", {}).get("project", "")
        if not project or "${" in project:
            logger.warning("GEE project not configured — using synthetic SAR fallback")
            return False
        ee.Initialize(project=project)
        _ee_ready = True
        logger.info(f"GEE initialised (project={project})")
        return True
    except Exception as e:
        logger.warning(f"GEE init failed — using synthetic SAR fallback: {e}")
        return False


# ── Location-aware synthetic SAR fallback ────────────────────────────────────
# Known high-risk ocean regions based on shipping density, refinery proximity,
# and historical spill frequency (IMO / ITOPF data).
_HIGH_RISK_ZONES = [
    # (lat_center, lon_center, radius_deg, risk_weight, label)
    (15.0,  88.0, 12.0, 0.75, "Bay of Bengal — dense shipping + offshore rigs"),
    (25.5,  56.0, 10.0, 0.80, "Persian Gulf — world's highest tanker traffic"),
    (25.0, -90.0, 12.0, 0.65, "Gulf of Mexico — offshore drilling"),
    (56.5,  18.0,  8.0, 0.55, "Baltic Sea — aging tanker routes"),
    ( 1.5, 104.5,  6.0, 0.60, "Strait of Malacca — ultra-high traffic"),
    (29.0,  48.5,  5.0, 0.70, "Kuwait / Northern Gulf — refinery discharge"),
    (51.5,   2.0,  6.0, 0.50, "North Sea — oil platform density"),
    (22.0, -77.0,  8.0, 0.45, "Caribbean — tanker routes"),
    (-8.0,  13.0,  7.0, 0.60, "Gulf of Guinea — Nigerian offshore fields"),
    (30.5,  32.0,  5.0, 0.50, "Suez Canal zone — tanker congestion"),
]

def _synthetic_sar(lat: float, lon: float) -> dict:
    """
    Generate a realistic synthetic SAR backscatter value using location risk.
    Typical clean ocean VV backscatter: -10 to -7 dB.
    Oil-dampened surface (spill): -25 to -20 dB.
    Threshold in config: -20 dB.
    """
    # Base backscatter for open ocean (dB)
    base_sar = random.uniform(-12.0, -7.0)

    # Compute composite risk score from proximity to known high-risk zones
    risk_score = 0.0
    matched_zone = None
    for z_lat, z_lon, radius, weight, label in _HIGH_RISK_ZONES:
        dist = math.sqrt((lat - z_lat) ** 2 + (lon - z_lon) ** 2)
        if dist <= radius:
            # Closer to centre → higher risk contribution
            proximity_factor = 1.0 - (dist / radius)
            contribution = weight * proximity_factor
            if contribution > risk_score:
                risk_score = contribution
                matched_zone = label

    # Deterministic seed so the same location always gives same result per day
    day_seed = int(datetime.utcnow().strftime("%Y%m%d"))
    rng = random.Random(hash((round(lat, 1), round(lon, 1), day_seed)))

    oil_detected = False
    sar_value = base_sar

    if risk_score > 0:
        # Roll whether a spill is active today based on risk_score
        if rng.random() < risk_score * 0.6:   # e.g. 0.75 risk → 45% daily chance
            # Spill: low backscatter (oil dampens capillary waves)
            sar_value = rng.uniform(-26.0, -20.5)
            oil_detected = True
            logger.info(
                f"Synthetic SAR: OIL SPILL at ({lat},{lon}) | "
                f"SAR={sar_value:.2f} dB | zone={matched_zone}"
            )
        else:
            # High-risk zone but no active spill today — slightly noisy
            sar_value = rng.uniform(-18.0, -10.0)
            logger.info(
                f"Synthetic SAR: clear at ({lat},{lon}) | "
                f"SAR={sar_value:.2f} dB | risk_score={risk_score:.2f}"
            )
    else:
        # Low-risk open ocean
        sar_value = rng.uniform(-11.0, -7.0)
        logger.info(f"Synthetic SAR: open ocean clear at ({lat},{lon}) | SAR={sar_value:.2f} dB")

    threshold = -20.0
    return {
        "sar_value":       round(sar_value, 4),
        "oil_spill":       1 if oil_detected else 0,
        "threshold_used":  threshold,
        "scenes_used":     0,
        "risk_score":      round(risk_score, 3),
        "matched_zone":    matched_zone or "Open ocean",
        "source":          "Synthetic SAR (location-risk model — GEE unavailable)",
    }


# ── Public API ────────────────────────────────────────────────────────────────

def detect_oil_spill(lat: float, lon: float) -> dict:
    """
    Detect oil spill using Sentinel-1 SAR backscatter (VV band).
    Falls back to a location-aware synthetic model when GEE is unavailable.
    """
    if _try_init_ee():
        return _detect_oil_spill_gee(lat, lon)
    return _synthetic_sar(lat, lon)


def _detect_oil_spill_gee(lat: float, lon: float) -> dict:
    """
    Real Sentinel-1 SAR oil-spill detection via Google Earth Engine.
    """
    try:
        import ee
        from utils.config_loader import get_config
        config = get_config()["gee"]["sentinel1"]

        lookback   = config["lookback_days"]
        end_date   = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=lookback)).strftime("%Y-%m-%d")
        logger.info(f"Fetching Sentinel-1 SAR for ({lat},{lon}) | {start_date}→{end_date}")

        point      = ee.Geometry.Point([lon, lat])
        collection = (
            ee.ImageCollection(config["collection"])
            .filterBounds(point)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .select(config["sar_band"])
        )

        size = collection.size().getInfo()
        if size == 0:
            raise ValueError(f"No Sentinel-1 scenes for ({lat},{lon}) in last {lookback}d")

        image = collection.mean()
        sar_stat = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=point.buffer(1000),
            scale=config["scale"],
        ).get(config["sar_band"])

        sar_value = sar_stat.getInfo()
        if sar_value is None:
            raise ValueError("SAR value is null")

        threshold  = config["oil_spill_threshold"]
        oil_spill  = 1 if sar_value < threshold else 0

        result = {
            "sar_value":      round(sar_value, 4),
            "oil_spill":      oil_spill,
            "threshold_used": threshold,
            "scenes_used":    size,
            "date_range":     f"{start_date} to {end_date}",
            "source":         "Copernicus Sentinel-1 GRD (real-time)",
        }
        logger.info(f"GEE SAR result: {result}")
        return result

    except Exception as e:
        logger.error(f"GEE Sentinel-1 failed, falling back to synthetic: {e}")
        return _synthetic_sar(lat, lon)
