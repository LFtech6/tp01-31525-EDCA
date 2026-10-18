import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

TOKEN = "test-token"


@pytest.fixture
def client(tmp_path, monkeypatch):
    src = tmp_path / "sensor_events.json"
    src.write_text(json.dumps([{"event_id": "SEN0001", "sensor_id": "M03", "value": "true"}]))
    monkeypatch.setattr(config, "SENSOR_SOURCE_FILE", src)
    monkeypatch.setattr(config, "SIMULATED_INBOX_FILE", tmp_path / "inbox" / "sim.json")
    monkeypatch.setattr(config, "OPS_API_TOKEN", TOKEN)
    return TestClient(app)


def test_get_returns_raw_source_events(client):
    r = client.get("/gateway/sensors/events")
    assert r.status_code == 200
    assert r.json() == [{"event_id": "SEN0001", "sensor_id": "M03", "value": "true"}]


def test_simulated_event_requires_api_key(client):
    assert client.post("/gateway/sensors/events", json={"sensor_id": "M03"}).status_code == 401
    r = client.post("/gateway/sensors/events", json={"sensor_id": "M03"}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_simulated_event_is_queued_and_served(client):
    r = client.post("/gateway/sensors/events", headers={"X-API-Key": TOKEN},
                    json={"sensor_id": "M04", "timestamp": "2026-10-14T03:00:00"})
    assert r.status_code == 201
    assert r.json()["queued"]["event_id"] == "SIM0001"
    ids = [e["event_id"] for e in client.get("/gateway/sensors/events").json()]
    assert ids == ["SEN0001", "SIM0001"]


@pytest.mark.parametrize("payload", [{"sensor_id": "m3"}, {"sensor_id": "M03", "event_type": "FIRE"}, {}])
def test_simulated_event_is_validated(client, payload):
    r = client.post("/gateway/sensors/events", json=payload, headers={"X-API-Key": TOKEN})
    assert r.status_code == 422
