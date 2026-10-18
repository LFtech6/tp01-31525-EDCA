"""Autenticação por token para endpoints que alteram estado (X-API-Key)."""
import secrets

from fastapi import Header, HTTPException, status

from . import config


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not config.OPS_API_TOKEN:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OPS_API_TOKEN não configurado")
    if x_api_key is None or not secrets.compare_digest(x_api_key, config.OPS_API_TOKEN):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-API-Key inválida ou em falta")
