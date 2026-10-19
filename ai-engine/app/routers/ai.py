"""Serviço de inferência (stateless): não acede à base de dados.

Devolve sempre HTTP 200 com um campo `status`, para que o Pentaho registe falhas
(TIMEOUT, INVALID_OUTPUT, INVALID_INPUT, MODEL_ERROR) sem interromper o processamento.
"""
import json

import httpx
from fastapi import APIRouter, Request
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
