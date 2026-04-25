"""
Backend API tests for AquaGuard.
Mocks all external services (GEE, GBIF, Groq) so tests run offline and fast.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


# ── Shared mock data ───────────────────────────────────────────────────────────

MOCK_ENV = {
    "temperature": 27.89,
    "chlorophyll": 0.5,
    "turbidity": 0.09,
    "date_range": "2026-02-20 to 2026-03-21",
    "source": "NASA MODIS-Aqua + NOAA OISST"
}

MOCK_PREDICTION = {
    "risk": 0,
    "risk_label": "Low",
    "risk_confidence": 0.93,
    "bloom": 0,
    "bloom_detected": False,
    "bloom_confidence": 0.99,
    "oil_spill": 0,
    "oil_spill_detected": False,
    "oil_spill_confidence": None,
    "sar_value": None,
    "rule_based_risk": {
        "risk_score": 0.175,
        "risk_label": "Low",
        "contributing_factors": ["Elevated temperature"]
    },
    "oil_spill_source": "Sentinel-1 unavailable"
}

MOCK_SPECIES = {
    "total_found": 5,
    "threatened_count": 1,
    "harmed_count": 0,
    "critically_endangered": [],
    "endangered": [],
    "vulnerable": [],
    "near_threatened": [],
    "least_concern": [],
    "data_deficient": [],
    "currently_harmed": [],
    "all_species": []
}

MOCK_PIPELINE_RESULT = {
    "location": "Arabian Sea",
    "coordinates": {"lat": 15.0, "lon": 65.0},
    "environment": MOCK_ENV,
    "prediction": MOCK_PREDICTION,
    "species": MOCK_SPECIES
}


# ── /health ────────────────────────────────────────────────────────────────────

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── /search ────────────────────────────────────────────────────────────────────

@patch("backend.app.run_prediction_pipeline", return_value=MOCK_PIPELINE_RESULT)
def test_search_valid_location(mock_pipeline):
    response = client.get("/search?location=Arabian Sea")
    assert response.status_code == 200
    data = response.json()
    assert data["location"] == "Arabian Sea"
    assert "environment" in data
    assert "prediction" in data
    assert "species" in data
    mock_pipeline.assert_called_once_with("Arabian Sea")


def test_search_missing_location():
    response = client.get("/search?location=")
    assert response.status_code == 400
    assert "Location parameter is required" in response.json()["detail"]


def test_search_no_location_param():
    response = client.get("/search")
    assert response.status_code == 422


@patch("backend.app.run_prediction_pipeline", return_value={"error": "Could not geocode location: xyz123"})
def test_search_invalid_location(mock_pipeline):
    response = client.get("/search?location=xyz123")
    assert response.status_code == 404
    assert "Could not geocode" in response.json()["detail"]


@patch("backend.app.run_prediction_pipeline", return_value=MOCK_PIPELINE_RESULT)
def test_search_strips_whitespace(mock_pipeline):
    response = client.get("/search?location=  Arabian Sea  ")
    assert response.status_code == 200
    mock_pipeline.assert_called_once_with("Arabian Sea")


@patch("backend.app.run_prediction_pipeline", return_value=MOCK_PIPELINE_RESULT)
def test_search_prediction_fields(mock_pipeline):
    response = client.get("/search?location=Arabian Sea")
    pred = response.json()["prediction"]
    assert "risk" in pred
    assert "risk_label" in pred
    assert "risk_confidence" in pred
    assert "bloom" in pred
    assert "bloom_confidence" in pred
    assert "oil_spill" in pred
    assert "rule_based_risk" in pred


@patch("backend.app.run_prediction_pipeline", return_value=MOCK_PIPELINE_RESULT)
def test_search_risk_is_binary(mock_pipeline):
    response = client.get("/search?location=Arabian Sea")
    risk = response.json()["prediction"]["risk"]
    assert risk in [0, 1]


@patch("backend.app.run_prediction_pipeline", return_value=MOCK_PIPELINE_RESULT)
def test_search_risk_label_values(mock_pipeline):
    response = client.get("/search?location=Arabian Sea")
    label = response.json()["prediction"]["risk_label"]
    assert label in ["Low", "High"]


@patch("backend.app.run_prediction_pipeline", return_value=MOCK_PIPELINE_RESULT)
def test_search_environment_fields(mock_pipeline):
    response = client.get("/search?location=Arabian Sea")
    env = response.json()["environment"]
    assert "temperature" in env
    assert "chlorophyll" in env
    assert "turbidity" in env


# ── /agent ─────────────────────────────────────────────────────────────────────

@patch("backend.app._get_agent")
def test_agent_valid_query(mock_get_agent):
    mock_agent = MagicMock()
    mock_agent.run.return_value = "The ocean health near the Arabian Sea is Low risk."
    mock_get_agent.return_value = mock_agent

    response = client.post("/agent", json={"query": "What is the ocean health near the Arabian Sea?"})
    assert response.status_code == 200
    data = response.json()
    assert "query" in data
    assert "answer" in data
    assert "Low risk" in data["answer"]


def test_agent_empty_query():
    response = client.post("/agent", json={"query": ""})
    assert response.status_code == 400
    assert "query field is required" in response.json()["detail"]


def test_agent_missing_body():
    response = client.post("/agent", json={})
    assert response.status_code == 422


@patch("backend.app._get_agent")
def test_agent_strips_whitespace(mock_get_agent):
    mock_agent = MagicMock()
    mock_agent.run.return_value = "Some answer"
    mock_get_agent.return_value = mock_agent

    response = client.post("/agent", json={"query": "  Arabian Sea?  "})
    assert response.status_code == 200
    mock_agent.run.assert_called_once_with("Arabian Sea?")


@patch("backend.app._get_agent")
def test_agent_handles_exception(mock_get_agent):
    mock_agent = MagicMock()
    mock_agent.run.side_effect = Exception("LLM unavailable")
    mock_get_agent.return_value = mock_agent

    response = client.post("/agent", json={"query": "What is the ocean health?"})
    assert response.status_code == 500
    assert "LLM unavailable" in response.json()["detail"]
