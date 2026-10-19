"""Serviço de inferência (stateless): não acede à base de dados.

Devolve sempre HTTP 200 com um campo `status`, para que o Pentaho registe falhas
(TIMEOUT, INVALID_OUTPUT, INVALID_INPUT, MODEL_ERROR) sem interromper o processamento.
"""
import json

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .. import config, llm
from ..schemas import AnalysisResponse, CaseInput

router = APIRouter(prefix="/ai", tags=["ai (inferência)"])
_client = httpx.Client()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: Request) -> AnalysisResponse:
    raw = await request.body()
    try:
        case = CaseInput.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        try:
            case_id = json.loads(raw).get("case_id")
        except (ValueError, AttributeError):
            case_id = None
        return AnalysisResponse(case_id=case_id, status="INVALID_INPUT", model=config.OLLAMA_MODEL,
                                prompt_version=llm.PROMPT_VERSION, error=str(exc)[:500])
    return llm.analyze(case, _client)


@router.get("/health")
def ai_health() -> JSONResponse:
    """200 se o modelo está disponível no Ollama; 503 caso contrário (usado pelo Job para decidir SKIPPED)."""
    llm._digest_cache.pop(config.OLLAMA_MODEL, None)  # verificação real, sem cache
    digest = llm.model_digest(_client)
    if digest is None:
        return JSONResponse({"available": False, "model": config.OLLAMA_MODEL}, status_code=503)
    return JSONResponse({"available": True, "model": config.OLLAMA_MODEL, "digest": digest,
                         "prompt_version": llm.PROMPT_VERSION})
