"""Configuração lida do .env na raiz do projeto (sem dependências extra)."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), os.path.expandvars(value.strip()))


_load_env(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
SENSOR_SOURCE_FILE = DATA_DIR / "raw" / "sensor_events.json"
SIMULATED_INBOX_FILE = DATA_DIR / "inbox" / "simulated_sensor_events.json"

OPS_API_TOKEN = os.environ.get("OPS_API_TOKEN", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")

PG_DSN = (f"host={os.environ.get('PG_HOST', 'localhost')} port={os.environ.get('PG_PORT', '5432')} "
          f"dbname={os.environ.get('PG_DB', 'sentinel')} user={os.environ.get('PG_USER', 'sentinel')} "
          f"password={os.environ.get('PG_PASSWORD', '')}")
