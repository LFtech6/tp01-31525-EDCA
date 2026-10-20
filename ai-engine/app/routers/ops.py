"""API de orquestração (/ops): lançar o Job Pentaho e consultar o estado das execuções.

Segurança:
  - todos os endpoints exigem X-API-Key; o serviço só escuta em 127.0.0.1;
  - o pedido indica um NOME LÓGICO de Job (lista branca), nunca um caminho ou comando;
  - o Kitchen é lançado com subprocess e lista de argumentos (sem shell);
  - concorrência: no máximo uma execução ativa (índice único parcial em etl_run → HTTP 409).
O Pentaho continua a ser o único responsável pelo processamento ETL.
"""
import re
import subprocess
import threading
from datetime import datetime
from secrets import token_hex
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel

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
        stdout=log_file, stderr=subprocess.STDOUT, cwd=config.PROJECT_ROOT, start_new_session=True)
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
