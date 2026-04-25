"""Tests for scheduler status API endpoints and core scheduler logic."""

import json
import os
import pytest
from unittest.mock import patch, mock_open
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

MOCK_RESULTS = {
    "Arabian Sea": {
        "location": "Arabian Sea",
        "timestamp": "2026-03-21T18:00:00+00:00",
        "status": "ok",
        "risk_label": "Low",
        "risk_confidence": 0.93,
        "bloom_detected": False,
        "oil_spill_detected": False,
        "temperature": 27.89,
        "chlorophyll": 0.5,
        "threatened_count": 2,
        "harmed_count": 0
    },
    "Gulf of Mexico": {
        "location": "Gulf of Mexico",
        "timestamp": "2026-03-21T18:01:00+00:00",
        "status": "ok",
        "risk_label": "High",
        "risk_confidence": 0.88,
        "bloom_detected": True,
        "oil_spill_detected": False,
        "temperature": 30.1,
        "chlorophyll": 5.2,
        "threatened_count": 5,
        "harmed_count": 3
    }
}


# ── /scheduler/status ──────────────────────────────────────────────────────────

@patch("backend.app.os.path.exists", return_value=True)
@patch("builtins.open", mock_open(read_data=json.dumps(MOCK_RESULTS)))
def test_scheduler_status_ok(mock_exists):
    response = client.get("/scheduler/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["total_locations"] == 2
    assert "Arabian Sea" in data["results"]
    assert "Gulf of Mexico" in data["results"]


@patch("backend.app.os.path.exists", return_value=False)
def test_scheduler_status_no_runs(mock_exists):
    response = client.get("/scheduler/status")
    assert response.status_code == 200
    assert response.json()["status"] == "no_runs_yet"


@patch("backend.app.os.path.exists", return_value=True)
@patch("builtins.open", mock_open(read_data=json.dumps(MOCK_RESULTS)))
def test_scheduler_status_fields(mock_exists):
    response = client.get("/scheduler/status")
    gulf = response.json()["results"]["Gulf of Mexico"]
    assert gulf["risk_label"] == "High"
    assert gulf["bloom_detected"] is True
    assert gulf["harmed_count"] == 3


# ── /scheduler/history ─────────────────────────────────────────────────────────

MOCK_HISTORY = "[2026-03-21] Arabian Sea | status=ok | risk=Low\n[2026-03-21] Gulf of Mexico | status=ok | risk=High\n"

@patch("os.path.exists", return_value=True)
@patch("builtins.open", mock_open(read_data=MOCK_HISTORY))
def test_scheduler_history_ok(mock_exists):
    response = client.get("/scheduler/history")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["lines"]) >= 1


@patch("os.path.exists", return_value=False)
def test_scheduler_history_no_history(mock_exists):
    response = client.get("/scheduler/history")
    assert response.status_code == 200
    assert response.json()["status"] == "no_history_yet"


# ── Scheduler logic unit tests ─────────────────────────────────────────────────

def test_get_monitored_locations_from_env(monkeypatch):
    monkeypatch.setenv("MONITORED_LOCATIONS", "Red Sea, Black Sea, Caspian Sea")
    from scheduler.schedule_pipeline import get_monitored_locations
    locs = get_monitored_locations()
    assert locs == ["Red Sea", "Black Sea", "Caspian Sea"]


def test_get_monitored_locations_default(monkeypatch):
    monkeypatch.delenv("MONITORED_LOCATIONS", raising=False)
    from scheduler.schedule_pipeline import get_monitored_locations, DEFAULT_LOCATIONS
    locs = get_monitored_locations()
    assert locs == DEFAULT_LOCATIONS


def test_get_interval_hours_from_env(monkeypatch):
    monkeypatch.setenv("SCHEDULER_INTERVAL_HOURS", "12")
    from scheduler.schedule_pipeline import get_interval_hours
    assert get_interval_hours() == 12


def test_get_interval_hours_default(monkeypatch):
    monkeypatch.delenv("SCHEDULER_INTERVAL_HOURS", raising=False)
    from scheduler.schedule_pipeline import get_interval_hours, DEFAULT_INTERVAL_HOURS
    assert get_interval_hours() == DEFAULT_INTERVAL_HOURS  # 120 (5 days)


def test_summarise_extracts_fields():
    from scheduler.schedule_pipeline import _summarise
    raw = {
        "coordinates": {"lat": 15.0, "lon": 65.0},
        "environment": {"temperature": 27.5, "chlorophyll": 0.5, "turbidity": 0.09, "source": "MODIS"},
        "prediction": {
            "risk": 0, "risk_label": "Low", "risk_confidence": 0.93,
            "bloom_detected": False, "bloom_confidence": 0.99,
            "oil_spill_detected": False, "oil_spill_confidence": None,
            "sar_value": None,
            "rule_based_risk": {"risk_score": 0.175, "risk_label": "Low"}
        },
        "species": {"total_found": 5, "threatened_count": 1, "harmed_count": 0}
    }
    summary = _summarise("Arabian Sea", raw)
    assert summary["location"] == "Arabian Sea"
    assert summary["risk_label"] == "Low"
    assert summary["bloom_detected"] is False
    assert summary["threatened_count"] == 1
    assert summary["status"] == "ok"
