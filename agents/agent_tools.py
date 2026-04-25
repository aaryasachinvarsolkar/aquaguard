"""
Tool definitions for the AquaGuard agentic AI.
Each tool wraps an existing service and returns structured results.
"""

from services.location_service import get_coordinates
from services.environment_service import get_environment_data
from services.prediction_service import get_environment_prediction
from services.species_service import get_species_impact
from services.alert_service import send_alert
from pipeline.risk_calculation import calculate_risk_score
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Tool registry ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "geocode_location",
        "description": (
            "Convert a place name or location string into latitude and longitude coordinates. "
            "Always call this first before any other tool that requires lat/lon."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Human-readable location name, e.g. 'Great Barrier Reef' or 'Gulf of Mexico'"
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "fetch_environment_data",
        "description": (
            "Fetch real-time satellite ocean data (sea surface temperature, chlorophyll-a, turbidity) "
            "for a given coordinate using NASA MODIS and NOAA OISST via Google Earth Engine."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude"},
                "lon": {"type": "number", "description": "Longitude"}
            },
            "required": ["lat", "lon"]
        }
    },
    {
        "name": "run_ml_predictions",
        "description": (
            "Run all ML models (algal bloom XGBoost classifier, ecosystem risk Random Forest, "
            "XGBoost oil spill detector using SAR + env features) and rule-based risk scoring. "
            "Returns predictions with confidence scores for each model. "
            "Requires temperature, chlorophyll, turbidity, lat, and lon."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "description": "Sea surface temperature in °C"},
                "chlorophyll": {"type": "number", "description": "Chlorophyll-a concentration in mg/m³"},
                "turbidity": {"type": "number", "description": "Turbidity proxy value"},
                "lat": {"type": "number", "description": "Latitude"},
                "lon": {"type": "number", "description": "Longitude"}
            },
            "required": ["temperature", "chlorophyll", "turbidity", "lat", "lon"]
        }
    },
    {
        "name": "assess_species_impact",
        "description": (
            "Fetch marine species in the region via GBIF, enrich with IUCN Red List conservation status, "
            "and determine which species are currently harmed by environmental conditions. "
            "Pass the prediction and environment dicts from previous tool calls for accurate harm assessment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude"},
                "lon": {"type": "number", "description": "Longitude"},
                "prediction": {"type": "object", "description": "Output from run_ml_predictions"},
                "environment": {"type": "object", "description": "Output from fetch_environment_data"}
            },
            "required": ["lat", "lon"]
        }
    },
    {
        "name": "calculate_rule_based_risk",
        "description": (
            "Calculate a rule-based risk score (0–1) from environmental parameters using "
            "oceanographic thresholds. Complements the ML risk model."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "temperature": {"type": "number"},
                "chlorophyll": {"type": "number"},
                "turbidity": {"type": "number"}
            },
            "required": ["temperature", "chlorophyll", "turbidity"]
        }
    },
    {
        "name": "send_alert",
        "description": (
            "Send an email alert when a critical condition is detected "
            "(oil spill, high ecosystem risk, or threatened species harmed). "
            "Only call this when genuinely critical conditions are confirmed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "prediction": {"type": "object"},
                "environment": {"type": "object"},
                "species": {"type": "object"}
            },
            "required": ["location", "prediction", "environment"]
        }
    },
    {
        "name": "check_model_drift",
        "description": (
            "Check whether current live environmental conditions are significantly different "
            "from the model's training data distribution. Returns z-scores and drift flags "
            "for each feature. Use this when the user asks about model reliability or data quality."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location to check drift for"
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_pollution_events",
        "description": "Get a history of recent pollution discharge events globally or for a specific location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Optional location filter"},
                "limit": {"type": "integer", "description": "Number of events to return", "default": 5}
            }
        }
    },
    {
        "name": "get_historical_trends",
        "description": "Fetch historical trends (SST, Chlorophyll) for a location over a period of days.",
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "days": {"type": "integer", "default": 30}
            },
            "required": ["lat", "lon"]
        }
    },
    {
        "name": "compare_locations",
        "description": "Compare environmental health and risk between two ocean locations.",
        "parameters": {
            "type": "object",
            "properties": {
                "loc1": {"type": "string", "description": "First location name"},
                "loc2": {"type": "string", "description": "Second location name"}
            },
            "required": ["loc1", "loc2"]
        }
    },
    {
        "name": "get_ocean_facts",
        "description": "Get interesting scientifically-backed facts about the ocean, marine biology, or climate.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Optional topic keyword"}
            }
        }
    }
]


# ── Tool executor ──────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call by name and return its result."""
    logger.info(f"[Tool] {name}({args})")

    try:
        if name == "geocode_location":
            lat, lon = get_coordinates(args["location"])
            if lat is None:
                return {"error": f"Could not geocode: {args['location']}"}
            return {"lat": lat, "lon": lon}

        elif name == "fetch_environment_data":
            return get_environment_data(args["lat"], args["lon"])

        elif name == "run_ml_predictions":
            return get_environment_prediction(
                temp=args["temperature"],
                chlorophyll=args["chlorophyll"],
                turbidity=args["turbidity"],
                lat=args["lat"],
                lon=args["lon"]
            )

        elif name == "assess_species_impact":
            return get_species_impact(
                lat=args["lat"],
                lon=args["lon"],
                prediction=args.get("prediction", {}),
                environment=args.get("environment", {})
            )

        elif name == "calculate_rule_based_risk":
            return calculate_risk_score(
                temperature=args["temperature"],
                chlorophyll=args["chlorophyll"],
                turbidity=args["turbidity"]
            )

        elif name == "send_alert":
            send_alert(
                location=args["location"],
                prediction=args["prediction"],
                environment=args["environment"],
                species=args.get("species")
            )
            return {"status": "alert_sent", "location": args["location"]}

        elif name == "check_model_drift":
            import requests
            try:
                r = requests.get(
                    "http://localhost:8000/drift",
                    params={"location": args["location"]},
                    timeout=30
                )
                return r.json()
            except Exception as e:
                return {"error": f"Drift check failed: {e}"}

        elif name == "get_pollution_events":
            from services.pollution_service import get_pollution_history
            events = get_pollution_history(limit=args.get("limit", 5))
            if args.get("location"):
                loc = args["location"].lower()
                events = [e for e in events if loc in e.get("location", "").lower()]
            return {"events": events}

        elif name == "get_historical_trends":
            from services.trend_service import get_historical_trends
            return get_historical_trends(lat=args["lat"], lon=args["lon"], days=args.get("days", 30))

        elif name == "compare_locations":
            from pipeline.prediction_pipeline import run_prediction_pipeline
            res1 = run_prediction_pipeline(args["loc1"])
            res2 = run_prediction_pipeline(args["loc2"])
            return {
                "location1": {"name": args["loc1"], "data": res1},
                "location2": {"name": args["loc2"], "data": res2},
                "comparison": "Compare the risks, temperatures, and chlorophyll levels between these two locations."
            }

        elif name == "get_ocean_facts":
            from services.ocean_facts_service import get_fact_by_topic, get_random_ocean_fact
            if args.get("topic"):
                return {"fact": get_fact_by_topic(args["topic"])}
            return {"fact": get_random_ocean_fact()}

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        logger.error(f"Tool '{name}' failed: {e}")
        return {"error": str(e)}
