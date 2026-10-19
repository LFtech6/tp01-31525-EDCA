"""Testes do serviço /ai com o Ollama simulado (httpx.MockTransport)."""
import json

import httpx
import pytest

from app import llm
from app.schemas import CaseInput

CASE = {
    "case_id": "CASE-Z03-20261012-021305",
    "zone": {"zone_id": "Z03", "name": "Laboratório", "security_level": "RESTRICTED",
             "open_time": "08:00", "close_time": "18:00", "open_weekends": False},
    "start_ts": "2026-10-12T02:13:05", "end_ts": "2026-10-12T02:14:10",
    "events": [
        {"event_id": "ACC0002", "timestamp": "2026-10-12T02:13:05", "source": "ACCESS",
         "event_type": "ACCESS_DENIED", "device_id": "D03", "zone_closed_at_event_time": True,
         "outside_user_schedule": True,
         "user": {"user_id": "U041", "role": "employee", "schedule_start": "08:00",
                  "schedule_end": "18:00", "active": True, "has_permission_for_zone": False}},
        {"event_id": "SEN0002", "timestamp": "2026-10-12T02:14:10", "source": "SENSOR",
         "event_type": "MOTION", "device_id": "M03", "zone_closed_at_event_time": True,
         "outside_user_schedule": False},
    ],
}
GOOD = {"is_suspicious": True, "risk_level": "HIGH", "incident_type": "POTENTIAL_INTRUSION",
        "explanation": "Acesso recusado fora de horas seguido de movimento na zona restrita.",
        "evidence_event_ids": ["ACC0002", "SEN0002"], "recommended_action": "Verificar as câmaras da zona."}


def client_returning(content=None, exc=None, captured=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:4b-instruct", "digest": "abc123"}]})
        if captured is not None:
            captured.append(json.loads(request.content))
        if exc:
            raise exc
        return httpx.Response(200, json={"message": {"content": content}})
    llm._digest_cache.clear()
    return httpx.Client(transport=httpx.MockTransport(handler))


def run(content=None, exc=None, captured=None):
    return llm.analyze(CaseInput.model_validate(CASE), client_returning(content, exc, captured))


def test_ok_response_is_validated_and_flattened():
    r = run(json.dumps(GOOD))
    assert r.status == "OK" and r.risk_level == "HIGH"
    assert r.evidence_event_ids_csv == "ACC0002,SEN0002"
    assert r.model_digest == "abc123"


def test_request_constrains_evidence_to_case_ids_and_hides_case_id():
    captured = []
    run(json.dumps(GOOD), captured=captured)
    body = captured[0]
    assert body["format"]["properties"]["evidence_event_ids"]["items"]["enum"] == ["ACC0002", "SEN0002"]
    assert body["options"]["temperature"] == 0
    assert "CASE-Z03" not in body["messages"][1]["content"]


def test_invented_evidence_is_rejected():
    r = run(json.dumps({**GOOD, "evidence_event_ids": ["ACC9999"]}))
    assert r.status == "INVALID_OUTPUT" and "ACC9999" in r.error


def test_incoherent_classification_is_rejected():
    r = run(json.dumps({**GOOD, "is_suspicious": False, "risk_level": "HIGH"}))
    assert r.status == "INVALID_OUTPUT"


@pytest.mark.parametrize("content", ["not json", json.dumps({**GOOD, "extra": 1}), json.dumps({"risk_level": "HIGH"})])
def test_invalid_model_output(content):
    assert run(content).status == "INVALID_OUTPUT"


def test_timeout():
    r = run(exc=httpx.ReadTimeout("slow"))
    assert r.status == "TIMEOUT" and r.is_suspicious is None


def test_ollama_down():
    assert run(exc=httpx.ConnectError("refused")).status == "MODEL_ERROR"


def test_endpoint_returns_200_with_invalid_input():
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).post("/ai/analyze", json={"case_id": "x", "events": []})
    assert r.status_code == 200 and r.json()["status"] == "INVALID_INPUT"


def test_ai_health_reports_503_when_model_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(llm, "model_digest", lambda client: None)
    assert TestClient(app).get("/ai/health").status_code == 503
    monkeypatch.setattr(llm, "model_digest", lambda client: "abc")
    assert TestClient(app).get("/ai/health").json()["digest"] == "abc"
