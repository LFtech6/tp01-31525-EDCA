"""Testes da API /ops (segurança e validação; sem lançar o Kitchen)."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

TOKEN = "test-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "OPS_API_TOKEN", TOKEN)
    return TestClient(app)


@pytest.mark.parametrize("method,url", [("get", "/ops/runs"), ("post", "/ops/runs"), ("get", "/ops/runs/run-20261019-000000/log")])
def test_requires_api_key(client, method, url):
    assert getattr(client, method)(url).status_code == 401


def test_only_whitelisted_jobs(client):
    r = client.post("/ops/runs", json={"job": "../../etc/passwd"}, headers={"X-API-Key": TOKEN})
    assert r.status_code == 422


@pytest.mark.parametrize("run_id", ["..%2F..%2F.env", "run-x", "run-20261019-000000;rm"])
def test_run_id_is_validated_against_path_traversal(client, run_id):
    r = client.get(f"/ops/runs/{run_id}/log", headers={"X-API-Key": TOKEN})
    assert r.status_code in (400, 404)
    assert "PG_PASSWORD" not in r.text
