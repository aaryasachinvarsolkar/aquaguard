"""
Historical trend service — fetches time-series SST and chlorophyll
from GEE over the past N days, returning weekly averages for charting.

Falls back to synthetic regional trends when GEE is unavailable or
returns all-None windows (very common with 7-day MODIS gaps).
"""

import random
import math
from datetime import datetime, timedelta
from utils.config_loader import get_config
from utils.logger import get_logger

try:
    import ee
    _EE_AVAILABLE = True
except ImportError:
    _EE_AVAILABLE = False

logger = get_logger(__name__)


# ── Synthetic trend generator ──────────────────────────────────────────────────
def _synthetic_trends(lat: float, lon: float, days: int) -> dict:
    """
    Generate plausible weekly trend data when GEE is unavailable.
    Values are seeded by lat/lon so the same location always produces
    the same curve shape, but with realistic seasonal variation.
    """
    seed = int(abs(round(lat, 1) * 1000 + round(lon, 1) * 100 + abs(lat * lon))) % 99991
    rng  = random.Random(seed)

    is_bob  = (10 <= lat <= 22) and (80 <= lon <= 100)
    is_gom  = (18 <= lat <= 31) and (-98 <= lon <= -81)
    is_ara  = ( 5 <= lat <= 25) and (50 <= lon <= 78)
    is_arc  = abs(lat) > 65

    # Base SST and Chl for this region
    base_sst = 28.0 - abs(lat) * 0.4
    if is_bob:  base_sst += 2.5
    if is_ara:  base_sst += 1.5
    if is_arc:  base_sst -= 6.0
    base_chl = 8.0 if is_bob else (4.0 if is_gom else (3.5 if is_ara else (1.0 if is_arc else 1.2)))

    end_dt   = datetime.utcnow()
    start_dt = end_dt - timedelta(days=days)

    labels = []
    sst_values  = []
    chl_values  = []
    turb_values = []

    cursor = start_dt
    week_i = 0
    while cursor < end_dt:
        window_end = min(cursor + timedelta(days=7), end_dt)
        labels.append(cursor.strftime("%b %d"))

        # Gentle seasonal oscillation + per-week noise
        t = week_i / max(days // 7, 1)
        sst = round(base_sst + 1.5 * math.sin(2 * math.pi * t) + rng.uniform(-0.8, 0.8), 2)
        chl = round(max(0.1, base_chl + 2.0 * math.sin(2 * math.pi * t + 1.0) + rng.uniform(-0.8, 0.8)), 4)

        sst_values.append(sst)
        chl_values.append(chl)
        turb_values.append(round(0.05 + (0.45 if is_bob else 0.05) + 0.08 * chl, 4))

        cursor  = window_end
        week_i += 1

    logger.info(f"Synthetic trend generated: {len(labels)} weeks for ({lat},{lon})")
    return {
        "labels":     labels,
        "sst":        sst_values,
        "chlorophyll": chl_values,
        "turbidity":  turb_values,
        "days":       days,
        "location":   {"lat": lat, "lon": lon},
        "source":     "Synthetic (GEE unavailable)"
    }


# ── Main entry point ───────────────────────────────────────────────────────────
def get_historical_trends(lat: float, lon: float, days: int = 90) -> dict:
    """
    Fetch weekly-averaged SST and chlorophyll for the past `days` days.
    Returns lists suitable for Chart.js rendering.
    Falls back to synthetic data if GEE is unavailable or returns insufficient data.
    """
    if not _EE_AVAILABLE:
        logger.warning("earthengine-api not installed — using synthetic trends")
        return _synthetic_trends(lat, lon, days)

    # Try GEE initialisation
    try:
        config = get_config()
        ee.Initialize(project=config["gee"]["project"])
    except Exception as e:
        logger.warning(f"GEE init failed for trends ({e}) — using synthetic fallback")
        return _synthetic_trends(lat, lon, days)

    gee_cfg = get_config()["gee"]
    region  = ee.Geometry.Point([lon, lat]).buffer(gee_cfg["modis"]["buffer_meters"])

    end_dt   = datetime.utcnow()
    start_dt = end_dt - timedelta(days=days)

    labels      = []
    sst_values  = []
    chl_values  = []
    turb_values = []
    none_count  = 0

    cursor = start_dt
    week_i = 0
    while cursor < end_dt:
        window_end = min(cursor + timedelta(days=7), end_dt)
        start_str  = cursor.strftime("%Y-%m-%d")
        end_str    = window_end.strftime("%Y-%m-%d")

        sst = _fetch_sst_window(region, start_str, end_str)
        chl = _fetch_chl_window(region, start_str, end_str)

        labels.append(cursor.strftime("%b %d"))
        sst_values.append(round(sst, 2) if sst is not None else None)
        chl_values.append(round(chl, 4) if chl is not None else None)

        if chl is not None:
            intercept = gee_cfg["modis"].get("turbidity_intercept", 0.05)
            slope     = gee_cfg["modis"].get("turbidity_slope", 0.08)
            turb_values.append(round(intercept + slope * chl, 4))
        else:
            turb_values.append(None)
            none_count += 1

        cursor  = window_end
        week_i += 1

    # If >80% of windows returned None, GEE data is too sparse — use synthetic
    total_weeks = max(len(labels), 1)
    if none_count / total_weeks > 0.8:
        logger.warning(
            f"GEE returned None for {none_count}/{total_weeks} windows — "
            f"using synthetic trends for ({lat},{lon})"
        )
        return _synthetic_trends(lat, lon, days)

    # Patch None values with synthetic estimates so charts never show gaps
    synth = _synthetic_trends(lat, lon, days)
    for i in range(len(sst_values)):
        if sst_values[i] is None and i < len(synth["sst"]):
            sst_values[i] = synth["sst"][i]
        if chl_values[i] is None and i < len(synth["chlorophyll"]):
            chl_values[i] = synth["chlorophyll"][i]
        if turb_values[i] is None and i < len(synth["turbidity"]):
            turb_values[i] = synth["turbidity"][i]

    logger.info(f"Trend data fetched: {len(labels)} weeks for ({lat},{lon})")
    return {
        "labels":     labels,
        "sst":        sst_values,
        "chlorophyll": chl_values,
        "turbidity":  turb_values,
        "days":       days,
        "location":   {"lat": lat, "lon": lon},
        "source":     "NASA MODIS + NOAA OISST (patched where sparse)"
    }


def _fetch_sst_window(region, start_date: str, end_date: str):
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
        return val / 100.0 if val is not None else None
    except Exception as e:
        logger.warning(f"SST window fetch failed ({start_date}→{end_date}): {e}")
        return None


def _fetch_chl_window(region, start_date: str, end_date: str):
    try:
        col = (
            ee.ImageCollection("NASA/OCEANDATA/MODIS-Aqua/L3SMI")
            .filterDate(start_date, end_date)
            .select("chlor_a")
        )
        if col.size().getInfo() == 0:
            return None
        stats = col.mean().reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=4000,
            bestEffort=True
        ).getInfo()
        return stats.get("chlor_a")
    except Exception as e:
        logger.warning(f"Chlorophyll window fetch failed ({start_date}→{end_date}): {e}")
        return None
