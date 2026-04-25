"""
Entry points for the AquaGuard agentic AI.

CLI usage:
    python -m agents.agent_runner "What is the ocean health near the Great Barrier Reef?"

FastAPI route is also registered in backend/app.py via /agent endpoint.
"""

import sys
from dotenv import load_dotenv
from agents.ocean_agent import OceanAgent

load_dotenv()


def run_cli():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is the current ocean health near the Gulf of Mexico?"
    agent = OceanAgent()
    print(f"\nQuery: {query}\n")
    answer = agent.run(query, verbose=True)
    print(f"\n{'='*60}\nAnswer:\n{answer}\n")


if __name__ == "__main__":
    run_cli()
