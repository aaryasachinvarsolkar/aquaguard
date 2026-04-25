import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__name__)))

from services.environment_service import get_environment_data
from services.prediction_service import get_environment_prediction

def test_region(name, lat, lon):
    print(f"\n--- Testing {name} ({lat}, {lon}) ---")
    env = get_environment_data(lat, lon)
    print(f"Env Data: {env}")
    pred = get_environment_prediction(env['temperature'], env['chlorophyll'], env['turbidity'], lat, lon)
    print(f"Risk: {pred['risk_label']} (Conf: {pred['risk_confidence']})")
    print(f"Bloom: {pred['bloom_detected']} (Conf: {pred['bloom_confidence']})")
    print(f"Explanation: {pred['explanations']['risk']}")

# Bay of Bengal (Hotspot)
test_region("Bay of Bengal", 15.0, 90.0)

# Random Mediterranean (Normal)
test_region("Mediterranean", 35.0, 15.0)

# Random South Pacific (Normal)
test_region("South Pacific", -20.0, -140.0)
