"""
Ocean Facts Service — provides interesting, scientifically-backed facts 
about marine biology, ocean chemistry, and historical events.
"""

import random

FACTS = [
    "The ocean covers more than 70% of the Earth's surface and contains 97% of Earth's water.",
    "The Great Barrier Reef is the largest living structure on Earth and can be seen from space.",
    "The Mariana Trench is the deepest part of the world's oceans, reaching roughly 10,935 meters (35,876 feet).",
    "Phytoplankton in the ocean produce about 50% to 80% of the Earth's oxygen through photosynthesis.",
    "The Blue Whale is the largest animal ever known to have existed, even larger than the biggest dinosaurs.",
    "Only about 5% of the world's oceans have been explored and charted.",
    "The ocean absorbs about 30% of the carbon dioxide produced by humans, buffering the impacts of global warming.",
    "The Gulf Stream is a powerful, warm ocean current that influences the climate of the east coast of North America and Western Europe.",
    "Coral reefs are known as the 'rainforests of the sea' because they support about 25% of all marine species.",
    "Sound travels 4.5 times faster in water than in air.",
    "The Challenger Deep is the deepest known point in the Earth's seabed hydrosphere.",
    "Ocean acidification is caused by the uptake of carbon dioxide from the atmosphere, lowering the pH of the water.",
    "The Antarctic Circumpolar Current is the world's strongest ocean current.",
    "Bioluminescence is the production and emission of light by a living organism, common in deep-sea creatures.",
    "Plastic pollution is a major threat to marine life, with millions of tons of plastic entering the ocean every year."
]

def get_random_ocean_fact() -> str:
    """Returns a random interesting ocean fact."""
    return random.choice(FACTS)

def get_fact_by_topic(topic: str) -> str:
    """Finds a fact related to a specific topic."""
    topic = topic.lower()
    matches = [f for f in FACTS if topic in f.lower()]
    return random.choice(matches) if matches else get_random_ocean_fact()
