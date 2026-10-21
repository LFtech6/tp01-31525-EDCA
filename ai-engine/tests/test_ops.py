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


# ----------------------------------------------------------------------------- configuração de e-mail
from app.routers import ops  # noqa: E402

MAIL = {"smtp_host": "smtp.office365.com", "smtp_port": 587, "smtp_user": "a1@alunos.ipca.pt",
        "smtp_password": "segredo-de-teste", "mail_from": "a1@alunos.ipca.pt", "mail_to": "x@ipca.pt, y@ipca.pt"}


@pytest.fixture
def clean_mail():
    ops._mail_override.clear()
    yield
    ops._mail_override.clear()


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_mail_settings_require_api_key(client, method):
    kw = {"json": MAIL} if method == "put" else {}
    assert getattr(client, method)("/ops/mail-settings", **kw).status_code == 401


def test_mail_settings_never_return_password_and_reach_kitchen_env(client, clean_mail):
    r = client.put("/ops/mail-settings", json=MAIL, headers={"X-API-Key": TOKEN})
    assert r.status_code == 200
    assert "segredo-de-teste" not in r.text and r.json()["password_set"] and r.json()["source"] == "dashboard"
    assert r.json()["mail_to"] == "x@ipca.pt y@ipca.pt"  # separador do Kettle
    env = ops._kitchen_env()
    assert env["OVERRIDE_SMTP_PASSWORD"] == "segredo-de-teste" and env["OVERRIDE_MAIL_TO"] == "x@ipca.pt y@ipca.pt"
    # password vazia mantém a anterior
    r = client.put("/ops/mail-settings", json={**MAIL, "smtp_password": ""}, headers={"X-API-Key": TOKEN})
    assert ops._kitchen_env()["OVERRIDE_SMTP_PASSWORD"] == "segredo-de-teste"
    assert client.delete("/ops/mail-settings", headers={"X-API-Key": TOKEN}).json()["source"] == ".env"
    assert "OVERRIDE_SMTP_PASSWORD" not in ops._kitchen_env()


@pytest.mark.parametrize("field,value", [("mail_to", "não-é-email"), ("mail_to", "a@b.pt\nBcc: z@evil.com"),
                                         ("mail_from", "x"), ("smtp_host", "smtp.x.com; rm -rf /"),
                                         ("smtp_port", 0), ("smtp_password", "a\r\nb")])
def test_mail_settings_validation(client, clean_mail, field, value):
    r = client.put("/ops/mail-settings", json={**MAIL, field: value}, headers={"X-API-Key": TOKEN})
    assert r.status_code == 422
    assert ops._mail_override == {}
