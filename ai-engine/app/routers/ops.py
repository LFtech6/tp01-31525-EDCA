"""API de orquestração (/ops): lançar o Job Pentaho e consultar o estado das execuções.

Segurança:
  - todos os endpoints exigem X-API-Key; o serviço só escuta em 127.0.0.1;
  - o pedido indica um NOME LÓGICO de Job (lista branca), nunca um caminho ou comando;
  - o Kitchen é lançado com subprocess e lista de argumentos (sem shell);
  - concorrência: no máximo uma execução ativa (índice único parcial em etl_run → HTTP 409);
  - configuração de e-mail definida no dashboard: validada, guardada só em memória (nunca em disco/BD/Git),
    a password nunca é devolvida, e chega ao Kitchen por variáveis de ambiente (não aparece na linha de comandos).
O Pentaho continua a ser o único responsável pelo processamento ETL (incluindo o envio do e-mail).
"""
import os
import re
import subprocess
import threading
from datetime import datetime
from secrets import token_hex
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from .. import config
from ..security import require_api_key

router = APIRouter(prefix="/ops", tags=["ops (orquestração)"], dependencies=[Depends(require_api_key)])

JOBS = {"main": config.PROJECT_ROOT / "etl" / "jobs" / "jb_sentinel_main.kjb"}
PDI_WRAPPER = config.PROJECT_ROOT / "scripts" / "pdi.sh"
LOG_DIR = config.PROJECT_ROOT / "results" / "logs"
RUN_ID_RE = re.compile(r"^run-[0-9]{8}-[0-9]{6}(-[0-9a-f]{4})?$")


def _conn() -> psycopg.Connection:
    return psycopg.connect(config.PG_DSN, row_factory=dict_row, autocommit=True)


class RunRequest(BaseModel):
    job: Literal["main"] = "main"


# ----------------------------------------------------------------------------- configuração de e-mail (SMTP)
MAIL_KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO")
EMAIL_RE = re.compile(r"^[^@\s,;<>\"']+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_mail_override: dict[str, str] = {}
_mail_lock = threading.Lock()


class MailSettings(BaseModel):
    smtp_host: str = Field(pattern=r"^[A-Za-z0-9.-]{1,253}$")
    smtp_port: int = Field(ge=1, le=65535)
    smtp_user: str = Field(min_length=1, max_length=254, pattern=r"^[^\s]+$")
    smtp_password: str | None = Field(default=None, max_length=256)  # vazio = manter a atual
    mail_from: str
    mail_to: str = Field(description="Um ou mais endereços separados por vírgula, ponto e vírgula ou espaço")

    @field_validator("smtp_password")
    @classmethod
    def _no_newlines(cls, v):
        if v and ("\n" in v or "\r" in v):
            raise ValueError("password inválida")
        return v or None

    @field_validator("mail_from")
    @classmethod
    def _from(cls, v):
        v = v.strip()
        if not EMAIL_RE.match(v):
            raise ValueError("endereço do remetente inválido")
        return v

    @field_validator("mail_to")
    @classmethod
    def _to(cls, v):
        addrs = [a for a in re.split(r"[,;\s]+", v.strip()) if a]
        if not 1 <= len(addrs) <= 10 or not all(EMAIL_RE.match(a) for a in addrs):
            raise ValueError("indique 1 a 10 endereços de destino válidos")
        return " ".join(addrs)  # a entrada Mail do Kettle separa destinatários por espaço


def _effective_mail() -> dict[str, str]:
    with _mail_lock:
        return {k: _mail_override.get(k, os.environ.get(k, "")) for k in MAIL_KEYS}


def _public_mail() -> dict:
    m = _effective_mail()
    with _mail_lock:
        source = "dashboard" if _mail_override else ".env"
    pw = m["SMTP_PASSWORD"]
    return {"smtp_host": m["SMTP_HOST"], "smtp_port": int(m["SMTP_PORT"] or 0), "smtp_user": m["SMTP_USER"],
            "mail_from": m["MAIL_FROM"], "mail_to": m["MAIL_TO"],
            "password_set": bool(pw) and pw != "change_me", "source": source}


@router.get("/mail-settings")
def get_mail_settings() -> dict:
    return _public_mail()


@router.put("/mail-settings")
def put_mail_settings(s: MailSettings) -> dict:
    current = _effective_mail()
    with _mail_lock:
        _mail_override.update({"SMTP_HOST": s.smtp_host, "SMTP_PORT": str(s.smtp_port), "SMTP_USER": s.smtp_user,
                               "SMTP_PASSWORD": s.smtp_password or current["SMTP_PASSWORD"],
                               "MAIL_FROM": s.mail_from, "MAIL_TO": s.mail_to})
    return _public_mail()


@router.delete("/mail-settings")
def reset_mail_settings() -> dict:
    with _mail_lock:
        _mail_override.clear()
    return _public_mail()


def _kitchen_env() -> dict[str, str]:
    env = os.environ.copy()
    with _mail_lock:
        env.update({f"OVERRIDE_{k}": v for k, v in _mail_override.items()})
    return env


def _watch(run_id: str, proc: subprocess.Popen, log_file) -> None:
    """Espera pelo Kitchen; se o Job não fechou a execução (ex.: falhou antes de a registar), fecha-a aqui."""
    rc = proc.wait()
    log_file.close()
    with _conn() as c:
        c.execute("""UPDATE etl_run SET exit_code = %s,
                         status = CASE WHEN status IN ('PENDING','RUNNING') THEN CASE WHEN %s = 0 THEN 'SUCCEEDED' ELSE 'FAILED' END ELSE status END,
                         error_message = CASE WHEN status IN ('PENDING','RUNNING') AND %s <> 0
                                              THEN 'Kitchen terminou com exit code ' || %s ELSE error_message END,
                         finished_at = coalesce(finished_at, now())
                     WHERE run_id = %s""", (rc, rc, rc, rc, run_id))


@router.post("/runs", status_code=202)
def start_run(req: RunRequest) -> dict:
    run_id = f"run-{datetime.now():%Y%m%d-%H%M%S}-{token_hex(2)}"
    log_path = LOG_DIR / f"{run_id}.log"
    try:
        with _conn() as c:
            c.execute("""INSERT INTO etl_run (run_id, job_name, trigger_source, status, log_path)
                         VALUES (%s, %s, 'dashboard', 'PENDING', %s)""", (run_id, JOBS[req.job].stem, str(log_path)))
    except psycopg.errors.UniqueViolation:
        with _conn() as c:
            active = c.execute("SELECT run_id, status FROM etl_run WHERE status IN ('PENDING','RUNNING')").fetchone()
        raise HTTPException(409, {"message": "Já existe uma execução ativa", "active": active})

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(PDI_WRAPPER), "kitchen", str(JOBS[req.job]), "Basic", f"-param:RUN_ID={run_id}", "-param:TRIGGER=dashboard"],
        stdout=log_file, stderr=subprocess.STDOUT, cwd=config.PROJECT_ROOT, env=_kitchen_env(), start_new_session=True)
    threading.Thread(target=_watch, args=(run_id, proc, log_file), daemon=True).start()
    return {"run_id": run_id, "status": "PENDING", "job": req.job}


@router.get("/runs")
def list_runs(limit: int = Query(10, ge=1, le=100)) -> list[dict]:
    with _conn() as c:
        return c.execute("""SELECT run_id, job_name, trigger_source, status, requested_at, started_at, finished_at,
                                   exit_code, error_message
                            FROM etl_run ORDER BY requested_at DESC LIMIT %s""", (limit,)).fetchall()


def _check_id(run_id: str) -> None:
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id inválido")


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    _check_id(run_id)
    with _conn() as c:
        run = c.execute("SELECT * FROM etl_run WHERE run_id = %s", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Execução não encontrada")
        run["stages"] = c.execute("""SELECT stage, status, started_at, finished_at, rows_processed, message
                                     FROM etl_run_stage WHERE run_id = %s ORDER BY started_at""", (run_id,)).fetchall()
    return run


@router.get("/runs/{run_id}/log")
def get_run_log(run_id: str, lines: int = Query(200, ge=1, le=2000)) -> dict:
    _check_id(run_id)
    path = LOG_DIR / f"{run_id}.log"
    if not path.exists():
        raise HTTPException(404, "Log não encontrado")
    tail = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    return {"run_id": run_id, "lines": tail, "errors": [l for l in tail if " ERROR " in l or "Exception" in l]}


def recover_orphan_runs() -> int:
    """No arranque: execuções lançadas pelo dashboard e ainda ativas ficaram órfãs (a API foi reiniciada)."""
    try:
        with _conn() as c:
            cur = c.execute("""UPDATE etl_run SET status = 'FAILED', finished_at = now(),
                                   error_message = 'Execução interrompida: a API de orquestração foi reiniciada'
                               WHERE trigger_source = 'dashboard' AND status IN ('PENDING','RUNNING')""")
            return cur.rowcount
    except psycopg.Error:
        return 0
