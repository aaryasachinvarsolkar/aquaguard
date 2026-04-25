import requests
import math
from utils.logger import get_logger

logger = get_logger(__name__)

# Known ocean/coastal reference points for common Indian locations
# These are pre-validated offshore coordinates (in the water, not on land)
KNOWN_OCEAN_LOCATIONS = {
    "goa coast":        (15.5, 73.5),
    "goa":              (15.5, 73.5),
    "arabian sea":      (15.0, 65.0),
    "bay of bengal":    (15.0, 88.0),
    "lakshadweep":      (10.5, 72.5),
    "andaman":          (12.0, 93.0),
    "andaman sea":      (12.0, 96.0),
    "gulf of mannar":   (9.0,  79.5),
    "palk strait":      (9.5,  79.8),
    "kerala coast":     (10.0, 75.5),
    "mumbai coast":     (18.9, 72.5),
    "chennai coast":    (13.1, 80.5),
    "odisha coast":     (20.0, 87.5),
    "gujarat coast":    (22.0, 69.5),
    "karnataka coast":  (14.0, 74.0),
    "tamil nadu coast": (10.5, 80.5),
    "andhra coast":     (15.5, 81.5),
    "west bengal coast":(21.5, 88.5),
    "persian gulf":     (26.0, 53.0),
    "gulf of mexico":   (25.0, -90.0),
    "north sea":        (56.0, 3.0),
    "baltic sea":       (58.0, 20.0),
    "red sea":          (20.0, 38.0),
    "mediterranean":    (35.0, 18.0),
    "south china sea":  (15.0, 115.0),
    "coral sea":        (-18.0, 152.0),
    "great barrier reef":(-18.0, 147.5),
    "gulf of aden":     (12.0, 47.0),
    "indian ocean":     (-10.0, 75.0),
    "pacific ocean":    (0.0, -150.0),
    "atlantic ocean":   (0.0, -25.0),
    "arctic ocean":     (85.0, 0.0),
    "black sea":        (43.0, 34.0),
    "caspian sea":      (42.0, 51.0),
}


def _normalize(location: str) -> str:
    return location.lower().strip()


def _lookup_known(location: str):
    """Check known ocean locations dictionary."""
    norm = _normalize(location)
    # Exact match
    if norm in KNOWN_OCEAN_LOCATIONS:
        return KNOWN_OCEAN_LOCATIONS[norm]
    # Partial match
    for key, coords in KNOWN_OCEAN_LOCATIONS.items():
        if key in norm or norm in key:
            return coords
    return None


def _nominatim_search(query: str):
    """Search Nominatim for a location, return (lat, lon) or None."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 5},
            headers={"User-Agent": "oceansense-ocean-monitor"},
            timeout=10
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None

        # Prefer results with ocean/water/sea type
        water_types = {"water", "bay", "sea", "ocean", "strait", "gulf", "reef", "coastline", "natural"}
        for r in results:
            rtype = r.get("type", "").lower()
            rclass = r.get("class", "").lower()
            if rtype in water_types or rclass in water_types or rclass == "natural":
                return float(r["lat"]), float(r["lon"])

        # Fall back to first result
        return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.warning(f"Nominatim search failed for '{query}': {e}")
        return None


def _is_likely_land(lat: float, lon: float) -> bool:
    """
    Very rough check: if the coordinate is clearly inland
    (far from any coast), flag it. Uses a simple ocean bbox heuristic.
    """
    # Check against known major land masses (rough bounding boxes)
    # India mainland interior
    if 20 < lat < 30 and 75 < lon < 85:
        return True
    # Central Africa
    if -5 < lat < 15 and 15 < lon < 35:
        return True
    # Central South America
    if -20 < lat < 5 and -65 < lon < -45:
        return True
    return False


def get_coordinates(location: str) -> tuple[float | None, float | None]:
    """
    Geocode a location to (lat, lon).
    Priority:
    1. Known ocean locations dictionary (most accurate for Indian coastal areas)
    2. Nominatim search with water-type preference
    3. Nominatim search with 'sea' appended for coastal queries
    """
    norm = _normalize(location)

    # 1. Known locations — most reliable for Indian ocean/coastal areas
    known = _lookup_known(location)
    if known:
        lat, lon = known
        logger.info(f"Known location '{location}' → ({lat}, {lon})")
        return lat, lon

    # 2. Try Nominatim directly
    result = _nominatim_search(location)
    if result:
        lat, lon = result
        # If result looks like it's on land for a coastal query, try appending "sea" or "ocean"
        coastal_keywords = ["coast", "coastal", "shore", "beach", "port", "harbour", "harbor"]
        is_coastal = any(k in norm for k in coastal_keywords)
        if is_coastal and _is_likely_land(lat, lon):
            logger.info(f"Land coordinate detected for coastal query, retrying with 'sea'")
            retry = _nominatim_search(location + " sea")
            if retry:
                lat, lon = retry
        logger.info(f"Geocoded '{location}' → ({lat}, {lon})")
        return lat, lon

    # 3. Try with "ocean" appended
    result = _nominatim_search(location + " ocean")
    if result:
        lat, lon = result
        logger.info(f"Geocoded '{location}' (ocean retry) → ({lat}, {lon})")
        return lat, lon

    logger.warning(f"No geocoding result for: {location}")
    return None, None
