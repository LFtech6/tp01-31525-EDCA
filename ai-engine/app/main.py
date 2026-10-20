"""Sentinel-AI — serviço FastAPI.

Routers separados por responsabilidade:
  /gateway  fonte REST simulada de sensores (consumida pelo Pentaho)
  /ai       inferência com Qwen3 via Ollama (stateless)
  /ops      orquestração de Jobs Pentaho (X-API-Key)
"""
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import config, llm
from .routers import ai, gateway, ops

app = FastAPI(title="Sentinel-AI (EDCA)", version="0.2.0")
app.include_router(gateway.router)
app.include_router(ai.router)
app.include_router(ops.router)


@app.on_event("startup")
def _startup() -> None:
    ops.recover_orphan_runs()


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # O /ai responde sempre JSON com status, para o Pentaho nunca receber HTML/500 sem contexto
    if request.url.path.startswith("/ai"):
        return JSONResponse({"case_id": None, "status": "MODEL_ERROR", "model": config.OLLAMA_MODEL,
                             "prompt_version": llm.PROMPT_VERSION, "error": f"{type(exc).__name__}: {exc}"[:500]})
    return JSONResponse({"detail": "Erro interno"}, status_code=500)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health", tags=["health"])
def health() -> dict:
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/version", timeout=2)
        ollama = {"reachable": r.status_code == 200, "version": r.json().get("version")}
    except httpx.HTTPError as exc:
        ollama = {"reachable": False, "error": type(exc).__name__}
    return {"status": "ok", "ollama": ollama, "model": config.OLLAMA_MODEL}
