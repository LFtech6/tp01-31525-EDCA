"""Cliente do Ollama (Qwen3) com saída estruturada, validação e tratamento de falhas.

A IA NÃO correlaciona: recebe um caso já construído pelo Pentaho e só pode citar
como evidência IDs que pertencem a esse caso (enum no JSON schema + validação).
"""
import json
import os
import time

import httpx
from pydantic import ValidationError

from . import config
from .schemas import AnalysisResponse, CaseInput, ModelOutput

PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "v1")
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
TIMEOUT_S = float(os.environ.get("OLLAMA_TIMEOUT_S", "90"))
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "15m")

# Prompt v1 — congelado antes de observar resultados. Alterações exigem nova PROMPT_VERSION.
SYSTEM_PROMPT = """You are a security analyst in a Security Operations Centre.
You receive ONE security case: a group of physical-security events that a deterministic
ETL pipeline already correlated (same zone, close in time), with context about the zone
and the people involved. Decide whether the case deserves investigation.

Guidelines:
- Reason only from the facts given. Do not invent events, people or relations.
- Consider the context: a person's role and work shift, whether they are allowed in the
  zone, whether their account is active, the zone's security level and opening hours,
  and the order and timing of the events.
- Activity outside opening hours is not suspicious by itself if the person is authorised
  and working within their own shift.
- evidence_event_ids must list the event IDs that support your conclusion.
- explanation: 2-3 short sentences in European Portuguese.
- recommended_action: one short sentence in European Portuguese.
- If nothing is suspicious use is_suspicious=false, risk_level NONE or LOW and
  incident_type BENIGN_ACTIVITY."""

_digest_cache: dict[str, str] = {}


def _schema_for(case: CaseInput) -> dict:
    """JSON schema por pedido: as evidências só podem ser IDs deste caso."""
    schema = ModelOutput.model_json_schema()
    schema["properties"]["evidence_event_ids"]["items"] = {
        "type": "string", "enum": [e.event_id for e in case.events]}
    return schema


def _case_prompt(case: CaseInput) -> str:
    return "Security case to analyse (JSON):\n" + case.model_dump_json(exclude={"case_id"}, indent=1)


def model_digest(client: httpx.Client) -> str | None:
    if config.OLLAMA_MODEL in _digest_cache:
        return _digest_cache[config.OLLAMA_MODEL]
    try:
        tags = client.get(f"{config.OLLAMA_URL}/api/tags", timeout=5).json()
        for m in tags.get("models", []):
            if m.get("name") == config.OLLAMA_MODEL:
                _digest_cache[config.OLLAMA_MODEL] = m.get("digest")
                return m.get("digest")
    except (httpx.HTTPError, ValueError):
        return None
    return None


def analyze(case: CaseInput, client: httpx.Client) -> AnalysisResponse:
    base = dict(case_id=case.case_id, model=config.OLLAMA_MODEL, prompt_version=PROMPT_VERSION,
                model_digest=model_digest(client))
    body = {
        "model": config.OLLAMA_MODEL,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "format": _schema_for(case),
        "options": {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX, "num_predict": 400},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": _case_prompt(case)}],
    }
    t0 = time.perf_counter()
    try:
        r = client.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=TIMEOUT_S)
        r.raise_for_status()
        raw = r.json()["message"]["content"]
    except httpx.TimeoutException:
        return AnalysisResponse(**base, status="TIMEOUT", latency_ms=_ms(t0),
                                error=f"Ollama não respondeu em {TIMEOUT_S:.0f}s")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        return AnalysisResponse(**base, status="MODEL_ERROR", latency_ms=_ms(t0),
                                error=f"{type(exc).__name__}: {exc}"[:500])
    latency = _ms(t0)

    try:
        out = ModelOutput.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        return AnalysisResponse(**base, status="INVALID_OUTPUT", latency_ms=latency,
                                error=f"Resposta fora do schema: {str(exc)[:400]}", raw_model_output=raw)

    case_ids = {e.event_id for e in case.events}
    unknown = [i for i in out.evidence_event_ids if i not in case_ids]
    problem = None
    if unknown:
        problem = f"Evidências inexistentes no caso: {unknown}"
    elif not out.is_suspicious and out.risk_level in ("MEDIUM", "HIGH", "CRITICAL"):
        problem = f"Incoerente: is_suspicious=false com risk_level={out.risk_level}"
    elif out.is_suspicious and out.risk_level == "NONE":
        problem = "Incoerente: is_suspicious=true com risk_level=NONE"
    if problem:
        return AnalysisResponse(**base, status="INVALID_OUTPUT", latency_ms=latency, error=problem,
                                raw_model_output=raw)

    return AnalysisResponse(**base, status="OK", latency_ms=latency, raw_model_output=raw,
                            **out.model_dump(),
                            evidence_event_ids_csv=",".join(out.evidence_event_ids))


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
