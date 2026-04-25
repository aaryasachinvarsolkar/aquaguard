import requests
import os
from utils.config_loader import get_config
from utils.logger import get_logger

logger = get_logger(__name__)

IUCN_LABELS = {
    "CR": "Critically Endangered",
    "EN": "Endangered",
    "VU": "Vulnerable",
    "NT": "Near Threatened",
    "LC": "Least Concern",
    "DD": "Data Deficient",
    "EX": "Extinct",
    "EW": "Extinct in the Wild"
}

# ── Harm rules: maps stressor → set of taxonomic keywords to match ─────────────
# Covers class, order, family, genus — all lowercased
# Sources: IUCN threat assessments, OBIS sensitivity literature
HARM_RULES = {
    "high_temperature": {
        # Corals
        "anthozoa", "scleractinia", "acropora", "porites", "pocillopora",
        "hexacorallia", "octocorallia",
        # Cold-water fish
        "salmonidae", "gadidae", "gadiformes", "salmoniformes",
        "cottidae", "scorpaenidae",
        # Marine mammals
        "cetacea", "mysticeti", "odontoceti", "delphinidae", "balaenidae",
        "pinnipedia", "phocidae", "otariidae",
        # Sea turtles
        "cheloniidae", "dermochelyidae", "testudines",
        # Seagrass
        "zosteraceae", "posidoniaceae", "cymodoceaceae",
    },
    "algal_bloom": {
        # Filter feeders — most vulnerable to HAB toxins
        "bivalvia", "mytilidae", "ostreidae", "pectinidae", "veneridae",
        "gastropoda", "muricidae",
        # Marine mammals that eat filter feeders
        "cetacea", "delphinidae", "balaenidae", "pinnipedia", "phocidae",
        # Seabirds
        "aves", "laridae", "sulidae", "phalacrocoracidae", "spheniscidae",
        # Sea turtles
        "cheloniidae", "dermochelyidae",
        # Small pelagic fish
        "engraulidae", "clupeidae", "engrauliformes", "clupeiformes",
        "scombridae",
    },
    "oil_spill": {
        # Seabirds — feather fouling
        "aves", "laridae", "alcidae", "spheniscidae", "phalacrocoracidae",
        "sulidae", "procellariidae", "charadriiformes", "pelecaniformes",
        # Marine mammals — fur/blubber contamination
        "cetacea", "delphinidae", "balaenidae", "pinnipedia", "phocidae",
        "otariidae", "mustelidae",
        # Sea turtles
        "cheloniidae", "dermochelyidae", "testudines",
        # Intertidal invertebrates
        "polychaeta", "crustacea", "malacostraca", "decapoda",
        "bivalvia", "gastropoda",
    },
    "high_turbidity": {
        # Corals — need clear water for photosynthesis
        "anthozoa", "scleractinia", "acropora", "hexacorallia",
        # Seagrass
        "zosteraceae", "posidoniaceae", "cymodoceaceae",
        # Rays and benthic fish — visual hunters
        "rajiformes", "rajidae", "myliobatiformes", "batoidea",
        # Seahorses and pipefish
        "syngnathidae", "syngnathiformes", "hippocampus",
        # Reef fish
        "labridae", "scaridae", "chaetodontidae", "pomacentridae",
    }
}


# Local fallback cache for common marine species
# Used when IUCN API is unavailable or token is missing
LOCAL_SPECIES_CACHE = {
    "Chelonia mydas":        {"common_name": "Green Sea Turtle", "status": "Endangered", "code": "EN"},
    "Dermochelys coriacea":  {"common_name": "Leatherback Turtle", "status": "Vulnerable", "code": "VU"},
    "Eretmochelys imbricata": {"common_name": "Hawksbill Turtle", "status": "Critically Endangered", "code": "CR"},
    "Balaenoptera musculus": {"common_name": "Blue Whale", "status": "Endangered", "code": "EN"},
    "Megaptera novaeangliae": {"common_name": "Humpback Whale", "status": "Least Concern", "code": "LC"},
    "Carcharodon carcharias": {"common_name": "Great White Shark", "status": "Vulnerable", "code": "VU"},
    "Rhincodon typus":       {"common_name": "Whale Shark", "status": "Endangered", "code": "EN"},
    "Dugong dugon":          {"common_name": "Dugong", "status": "Vulnerable", "code": "VU"},
    "Trichechus manatus":    {"common_name": "West Indian Manatee", "status": "Vulnerable", "code": "VU"},
    "Pinctada maxima":       {"common_name": "Pearl Oyster", "status": "Least Concern", "code": "LC"},
    "Acanthaster planci":    {"common_name": "Crown-of-thorns Starfish", "status": "Least Concern", "code": "LC"},
    "Physeter macrocephalus": {"common_name": "Sperm Whale", "status": "Vulnerable", "code": "VU"},
    "Mobula birostris":      {"common_name": "Giant Oceanic Manta Ray", "status": "Endangered", "code": "EN"},
}


def _build_taxon_set(item: dict) -> set:
    """
    Build a set of all taxonomic keywords from a GBIF occurrence record.
    Includes class, order, family, genus, species name parts — all lowercased.
    This is much more robust than a single joined string.
    """
    fields = [
        item.get("kingdom", ""),
        item.get("phylum", ""),
        item.get("class", ""),
        item.get("order", ""),
        item.get("family", ""),
        item.get("genus", ""),
        item.get("species", ""),
        item.get("scientificName", ""),
        item.get("vernacularName", ""),
    ]
    tokens = set()
    for f in fields:
        if f:
            for part in f.lower().split():
                tokens.add(part)
    return tokens


def _get_iucn_status(species_name: str, iucn_token: str, base_url: str) -> dict:
    """Query IUCN Red List API v4 for real-time conservation status."""
    try:
        url  = f"{base_url}/taxa/scientific_name"
        resp = requests.get(
            url,
            params={"name": species_name},
            headers={"Authorization": f"Token {iucn_token}"},
            timeout=8
        )
        resp.raise_for_status()
        data = resp.json()
        taxa = data.get("taxa", [])
        if taxa:
            category = taxa[0].get("red_list_category", {}).get("code", "DD")
            return {"code": category, "label": IUCN_LABELS.get(category, category)}
    except Exception as e:
        logger.warning(f"IUCN lookup failed for '{species_name}': {e}")
    return {"code": "DD", "label": "Data Deficient"}


def _determine_harm_reasons(
    taxon_tokens: set,
    prediction: dict,
    environment: dict
) -> list[str]:
    """
    Determine harm reasons using real-time prediction + environment values.
    Uses a token-set approach so partial taxonomic info still matches.
    """
    reasons = []

    temp      = float(environment.get("temperature") or 0)
    turbidity = float(environment.get("turbidity") or 0)
    bloom     = bool(prediction.get("bloom_detected")) or prediction.get("bloom") == 1
    oil       = bool(prediction.get("oil_spill_detected")) or prediction.get("oil_spill") == 1

    rule_risk    = prediction.get("rule_based_risk", {})
    risk_factors = rule_risk.get("contributing_factors", [])
    high_temp      = any("temperature" in f.lower() for f in risk_factors) or temp > 28
    high_turbidity = any("turbidity" in f.lower() for f in risk_factors) or turbidity > 0.4

    # Check each stressor
    if high_temp and taxon_tokens & HARM_RULES["high_temperature"]:
        reasons.append(
            f"Elevated SST ({temp:.1f}°C) — thermal stress, coral bleaching risk"
        )

    if bloom and taxon_tokens & HARM_RULES["algal_bloom"]:
        reasons.append(
            "Active algal bloom — HAB toxin exposure, oxygen depletion risk"
        )

    if oil and taxon_tokens & HARM_RULES["oil_spill"]:
        reasons.append(
            "Oil spill detected — direct toxicity, feather/fur fouling"
        )

    if high_turbidity and taxon_tokens & HARM_RULES["high_turbidity"]:
        reasons.append(
            f"High turbidity ({turbidity:.3f}) — light reduction, feeding disruption"
        )

    return reasons


def _safe_reason(temp, turbidity, bloom, oil, high_temp, high_turbidity) -> str:
    """Return a plain-English reason why a species is NOT harmed."""
    parts = []
    if not high_temp:
        parts.append(f"SST normal ({temp:.1f}°C)")
    if not bloom:
        parts.append("no bloom")
    if not oil:
        parts.append("no oil spill")
    if not high_turbidity:
        parts.append(f"turbidity normal ({turbidity:.3f})")
    return "Conditions normal — " + ", ".join(parts) if parts else "No active stressors"


def get_species_impact(
    lat: float, lon: float,
    prediction: dict = None,
    environment: dict = None
) -> dict:
    """
    Fetch real-time marine species from GBIF, enrich with IUCN status,
    and assess harm based on current satellite + ML data.
    Every species gets a clear harmed/safe status with reason.
    """
    config     = get_config()
    gbif_cfg   = config["gbif"]
    iucn_cfg   = config["iucn"]
    iucn_token = os.getenv("IUCN_API_TOKEN")

    if prediction is None:
        prediction = {}
    if environment is None:
        environment = {}

    # Pre-compute stressor flags once (not per-species)
    temp      = float(environment.get("temperature") or 0)
    turbidity = float(environment.get("turbidity") or 0)
    bloom     = bool(prediction.get("bloom_detected")) or prediction.get("bloom") == 1
    oil       = bool(prediction.get("oil_spill_detected")) or prediction.get("oil_spill") == 1
    rule_risk    = prediction.get("rule_based_risk", {})
    risk_factors = rule_risk.get("contributing_factors", [])
    high_temp      = any("temperature" in f.lower() for f in risk_factors) or temp > 28
    high_turbidity = any("turbidity" in f.lower() for f in risk_factors) or turbidity > 0.4

    radius  = gbif_cfg["search_radius_deg"]
    lat_min = round(lat - radius, 4)
    lat_max = round(lat + radius, 4)
    lon_min = round(lon - radius, 4)
    lon_max = round(lon + radius, 4)

    logger.info(f"Fetching GBIF species for bbox ({lat_min},{lon_min})→({lat_max},{lon_max})")

    # Marine phyla — filter to only genuinely marine organisms
    MARINE_PHYLA = {
        "chordata", "mollusca", "echinodermata", "arthropoda",
        "annelida", "cnidaria", "porifera", "bryozoa", "brachiopoda",
        "chaetognatha", "ctenophora", "platyhelminthes", "nemertea",
        "sipuncula", "xenacoelomorpha"
    }

    iucn_token_missing = not bool(iucn_token)

    try:
        params = {
            "decimalLatitude":  f"{lat_min},{lat_max}",
            "decimalLongitude": f"{lon_min},{lon_max}",
            "limit":            gbif_cfg["limit"],
            "hasCoordinate":    "true",
            "kingdom":          "Animalia",
            "occurrenceStatus": "PRESENT"
        }
        resp = requests.get(gbif_cfg["occurrence_url"], params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        seen        = set()
        all_species = []

        for item in data.get("results", []):
            name = item.get("species") or item.get("scientificName")
            if not name or name in seen:
                continue
            seen.add(name)

            taxon_tokens  = _build_taxon_set(item)
            species_class = item.get("class", "")
            order         = item.get("order", "")
            family        = item.get("family", "")

            # Skip non-marine species (terrestrial/freshwater)
            phylum = (item.get("phylum") or "").lower()
            if phylum and phylum not in MARINE_PHYLA:
                continue

            # IUCN status
            iucn = {"code": "DD", "label": "Data Deficient"}
            
            # Check local cache first
            if name in LOCAL_SPECIES_CACHE:
                cached = LOCAL_SPECIES_CACHE[name]
                iucn = {"code": cached["code"], "label": cached["status"]}
                if not item.get("vernacularName"):
                    item["vernacularName"] = cached["common_name"]
            elif iucn_token:
                try:
                    iucn = _get_iucn_status(name, iucn_token, iucn_cfg["base_url"])
                except Exception as e:
                    logger.warning(f"IUCN API failed for {name}: {e}. Falling back to DD.")
                    # If API fails, we still have DD, but maybe we can try fuzzy match in cache
                    for cname, cdata in LOCAL_SPECIES_CACHE.items():
                        if cname in name or name in cname:
                            iucn = {"code": cdata["code"], "label": cdata["status"]}
                            break

            # Harm assessment
            harm_reasons = _determine_harm_reasons(taxon_tokens, prediction, environment)
            is_harmed    = len(harm_reasons) > 0

            # Safe reason — always explain why not harmed too
            safe_reason = (
                None if is_harmed
                else _safe_reason(temp, turbidity, bloom, oil, high_temp, high_turbidity)
            )

            all_species.append({
                "name":             name,
                "common_name":      item.get("vernacularName"),
                "class":            species_class,
                "order":            order,
                "family":           family,
                "iucn_status_code": iucn["code"],
                "iucn_status":      iucn["label"],
                "currently_harmed": is_harmed,
                "harm_reasons":     harm_reasons,
                "safe_reason":      safe_reason,
            })

        def by_status(code):
            return [s for s in all_species if s["iucn_status_code"] == code]

        threatened_codes = iucn_cfg["threatened_categories"]
        threatened = [s for s in all_species if s["iucn_status_code"] in threatened_codes]
        harmed     = [s for s in all_species if s["currently_harmed"]]

        result = {
            "total_found":           len(all_species),
            "critically_endangered": by_status("CR"),
            "endangered":            by_status("EN"),
            "vulnerable":            by_status("VU"),
            "near_threatened":       by_status("NT"),
            "least_concern":         by_status("LC"),
            "data_deficient":        by_status("DD"),
            "threatened_count":      len(threatened),
            "currently_harmed":      harmed,
            "harmed_count":          len(harmed),
            "all_species":           all_species,
            "iucn_token_missing":    iucn_token_missing,
            "active_stressors": {
                "high_temperature": high_temp,
                "algal_bloom":      bloom,
                "oil_spill":        oil,
                "high_turbidity":   high_turbidity,
            }
        }

        logger.info(
            f"Species: {len(all_species)} found | "
            f"{len(threatened)} threatened | {len(harmed)} harmed"
        )
        return result

    except Exception as e:
        logger.error(f"Species fetch failed: {e}")
        return {
            "total_found": 0, "error": str(e),
            "critically_endangered": [], "endangered": [],
            "vulnerable": [], "near_threatened": [],
            "least_concern": [], "data_deficient": [],
            "threatened_count": 0, "currently_harmed": [],
            "harmed_count": 0, "all_species": [],
            "active_stressors": {}
        }
