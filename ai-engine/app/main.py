"""Sentinel-AI — serviço FastAPI.

Routers separados por responsabilidade:
  /gateway  fonte REST simulada de sensores (consumida pelo Pentaho)
  /ai       inferência com Qwen3 via Ollama (stateless)         [etapa seguinte]
  /ops      orquestração de Jobs Pentaho (X-API-Key)            [pós-MVP]
"""
import httpx
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from . import config
from .routers import gateway

app = FastAPI(title="Sentinel-AI (EDCA)", version="0.1.0")
app.include_router(gateway.router)


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
