import random
import math
try:
    import ee
    _EE_AVAILABLE = True
except ImportError:
    _EE_AVAILABLE = False

from datetime import datetime, timedelta
from utils.config_loader import get_config
from utils.logger import get_logger

logger = get_logger(__name__)

def _init_ee():
    if not _EE_AVAILABLE:
        logger.warning("earthengine-api not installed — using synthetic fallback")
        return False
    try:
        config = get_config()
        ee.Initialize(project=config["gee"]["project"])
        return True
    except Exception as e:
        logger.warning(f"GEE init failed ({e}) — using synthetic fallback")
        return False

_EE_OK = _init_ee()


def _synthetic_env(lat: float, lon: float) -> dict:
    """Generate realistic synthetic ocean data when GEE is unavailable.

    Seed is derived ONLY from lat/lon so each location always gets a
    unique, consistent value.  The old code added the day-of-year
    (a large integer like 113) which dominated the seed and made every
    location return the same RNG sequence on the same day.
    """
    # Stable, location-unique seed — no date component
    seed = int(abs(round(lat, 2) * 1000 + round(lon, 2) * 100 + abs(lat * lon))) % 99991
    rng  = random.Random(seed)

    # ── Regional classification ────────────────────────────────────────────────
    is_bay_of_bengal   = (10 <= lat <= 22) and (80 <= lon <= 100)
    is_gulf_of_mexico  = (18 <= lat <= 31) and (-98 <= lon <= -81)
    is_arabic_sea      = (5  <= lat <= 25) and (50 <= lon <= 78)
    is_arctic          = abs(lat) > 65
    is_southern_ocean  = lat < -55

    # ── Sea Surface Temperature ────────────────────────────────────────────────
    base_sst = 28.0 - abs(lat) * 0.4          # tropical warm → polar cold
    if is_arctic or is_southern_ocean:
        base_sst -= 6
    if is_bay_of_bengal:
        base_sst += 2.5                        # reliably warm → triggers SST override
    if is_arabic_sea:
        base_sst += 1.5

    sst = round(base_sst + rng.uniform(-1.5, 1.5), 2)

    # ── Chlorophyll-a ──────────────────────────────────────────────────────────
    chl_min, chl_max = 0.1, 2.5               # open ocean baseline
    if is_bay_of_bengal:
        chl_min, chl_max = 5.0, 14.0          # always above 4.5 bloom threshold
    elif is_gulf_of_mexico:
        chl_min, chl_max = 2.0, 9.0
    elif is_arabic_sea:
        chl_min, chl_max = 1.5, 7.0
    elif is_arctic or is_southern_ocean:
        chl_min, chl_max = 0.3, 3.0

    chl = round(rng.uniform(chl_min, chl_max), 4)

    # ── Turbidity ─────────────────────────────────────────────────────────────
    base_turb = 0.05
    if is_bay_of_bengal:
        base_turb += 0.45   # Ganges/Brahmaputra sediment load
    elif is_gulf_of_mexico:
        base_turb += 0.15
    elif is_arabic_sea:
        base_turb += 0.10

    turbidity = round(base_turb + 0.08 * chl + rng.uniform(0, 0.08), 4)

    return {
        "temperature": sst,
        "chlorophyll": chl,
        "turbidity":   turbidity,
        "date_range":  "synthetic",
        "source":      "Synthetic (GEE unavailable) — Regional bias active"
    }


def _safe_get(stats_dict: dict, key: str):
    """Safely call getInfo on an EE computed value, return None if missing."""
    try:
        val = stats_dict.get(key)
        if val is None:
            return None
        return val.getInfo()
    except Exception as e:
        logger.warning(f"Could not retrieve '{key}' from EE result: {e}")
        return None


def _fetch_chlorophyll(region, start_date: str, end_date: str):
    """
    Try MODIS-Aqua L3SMI for chlorophyll.
    Falls back to a wider 90-day window if 30-day returns nothing.
    """
    for band in ["chlor_a", "Chlorophyll"]:
        try:
            col = (
                ee.ImageCollection("NASA/OCEANDATA/MODIS-Aqua/L3SMI")
                .filterDate(start_date, end_date)
                .select(band)
            )
            if col.size().getInfo() == 0:
                continue
            stats = col.mean().reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=4000,
                bestEffort=True
            ).getInfo()
            val = stats.get(band)
            if val is not None:
                return round(val, 4)
        except Exception as e:
            logger.warning(f"Chlorophyll fetch attempt with band '{band}' failed: {e}")
    return None


def _fetch_sst(region, start_date: str, end_date: str):
    """
    Fetch Sea Surface Temperature from NOAA OISST (more reliable global coverage).
    """
    try:
        col = (
            ee.ImageCollection("NOAA/CDR/OISST/V2_1")
            .filterDate(start_date, end_date)
            .select("sst")
        )
        if col.size().getInfo() == 0:
            return None
        stats = col.mean().reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=25000,
            bestEffort=True
        ).getInfo()
        val = stats.get("sst")
        if val is not None:
            # OISST SST is in Celsius * 100, need to divide
            return round(val / 100.0, 2)
    except Exception as e:
        logger.warning(f"SST fetch failed: {e}")
    return None


def get_environment_data(lat: float, lon: float, lookback_days: int = None) -> dict:
    """
    Fetch real-time chlorophyll and SST from satellite sources via GEE.
    Falls back to synthetic data if GEE is unavailable.

    Args:
        lookback_days: if set, uses exactly this lookback window (for baseline fetching).
                       If None, tries 30 → 90 → 180 days progressively.
    """
    if not _EE_OK:
        logger.warning(f"GEE unavailable — returning synthetic data for ({lat}, {lon})")
        return _synthetic_env(lat, lon)

    config = get_config()["gee"]["modis"]
    region = ee.Geometry.Point([lon, lat]).buffer(config["buffer_meters"])
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    # If a specific lookback is requested, use only that window
    lookback_sequence = [lookback_days] if lookback_days else [30, 90, 180]

    for days in lookback_sequence:
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        logger.info(f"Fetching satellite data for ({lat}, {lon}) | {start_date} → {end_date} (lookback={days}d)")

        chl = _fetch_chlorophyll(region, start_date, end_date)
        sst = _fetch_sst(region, start_date, end_date)

        if chl is not None or sst is not None:
            chl_synthetic = False
            if chl is None:
                # MODIS chlorophyll unavailable (cloud cover, off-season gap, etc.).
                # Use the regional-bias synthetic value rather than a global 0.5 constant
                # so that high-risk regions (Bay of Bengal, Gulf of Mexico…) still show
                # realistic, location-specific chlorophyll concentrations.
                synth = _synthetic_env(lat, lon)
                chl   = synth["chlorophyll"]
                chl_synthetic = True
                logger.info(
                    f"MODIS Chl unavailable for ({lat}, {lon}) — "
                    f"using synthetic regional estimate: {chl} mg/m³"
                )

            intercept = config.get("turbidity_intercept", 0.05)
            slope     = config.get("turbidity_slope", 0.08)
            # Regional turbidity bias (mirrors _synthetic_env)
            is_bay_of_bengal  = (10 <= lat <= 22) and (80 <= lon <= 100)
            is_gulf_of_mexico = (18 <= lat <= 31) and (-98 <= lon <= -81)
            is_arabic_sea     = ( 5 <= lat <= 25) and (50 <= lon <= 78)
            base_turb = intercept
            if is_bay_of_bengal:  base_turb += 0.45
            elif is_gulf_of_mexico: base_turb += 0.15
            elif is_arabic_sea:   base_turb += 0.10
            turbidity = round(base_turb + slope * chl, 4)

            chl_src = "synthetic-regional" if chl_synthetic else "NASA MODIS-Aqua"
            result = {
                "temperature": sst,
                "chlorophyll": chl,
                "turbidity":   turbidity,
                "date_range":  f"{start_date} to {end_date}",
                "source":      f"{chl_src} + NOAA OISST (lookback={days}d)"
            }
            logger.info(f"Satellite data fetched: {result}")
            return result

    logger.warning(f"No GEE data for ({lat}, {lon}) after {lookback_sequence[-1]}d — using synthetic fallback")
    return _synthetic_env(lat, lon)
