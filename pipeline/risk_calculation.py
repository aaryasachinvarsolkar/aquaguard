from utils.config_loader import get_config
from utils.logger import get_logger

logger = get_logger(__name__)


def calculate_risk_score(temperature: float, chlorophyll: float, turbidity: float) -> dict:
    """
    Rule-based risk scoring as a complement to the ML model.
    All thresholds and weights are loaded from config.yaml — nothing hardcoded.
    """
    cfg = get_config()["risk_calculation"]

    score   = 0.0
    factors = []

    # Chlorophyll contribution
    if chlorophyll >= cfg["chlorophyll_high"]:
        score += cfg["weight_chlorophyll"]
        factors.append("High chlorophyll (bloom risk)")
    elif chlorophyll >= cfg["chlorophyll_moderate"]:
        score += cfg["weight_chlorophyll"] * 0.5
        factors.append("Elevated chlorophyll")

    # Temperature contribution
    if temperature >= cfg["temperature_high"]:
        score += cfg["weight_temperature"]
        factors.append("High sea surface temperature")
    elif temperature >= cfg["temperature_moderate"]:
        score += cfg["weight_temperature"] * 0.5
        factors.append("Elevated temperature")

    # Turbidity contribution
    if turbidity >= cfg["turbidity_high"]:
        score += cfg["weight_turbidity"]
        factors.append("High turbidity")
    elif turbidity >= cfg["turbidity_moderate"]:
        score += cfg["weight_turbidity"] * 0.5
        factors.append("Moderate turbidity")

    score = round(min(score, 1.0), 3)

    if score >= cfg["label_high_threshold"]:
        label = "High"
    elif score >= cfg["label_moderate_threshold"]:
        label = "Moderate"
    else:
        label = "Low"

    result = {
        "risk_score":           score,
        "risk_label":           label,
        "contributing_factors": factors
    }
    logger.info(f"Risk calculation: {result}")
    return result
