"""Gateway de sensores simulado: fonte REST consumida pelo Pentaho.

Devolve os eventos tal como um gateway IoT os enviaria (sem limpeza: é o ETL que limpa).
Também aceita eventos simulados pelo dashboard, que ficam numa fila e só são
processados pelo Pentaho na execução seguinte.
"""
import json
import threading
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import config
from ..security import require_api_key

router = APIRouter(prefix="/gateway", tags=["gateway (fonte REST)"])
_inbox_lock = threading.Lock()


def _read_json_list(path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/sensors/events")
def list_sensor_events() -> list[dict]:
    """Eventos brutos dos sensores + eventos simulados pendentes."""
    return _read_json_list(config.SENSOR_SOURCE_FILE) + _read_json_list(config.SIMULATED_INBOX_FILE)


class SimulatedSensorEvent(BaseModel):
    sensor_id: str = Field(pattern=r"^[A-Z][0-9]{2}$", examples=["M03"])
    event_type: Literal["MOTION", "DOOR_OPEN"] = "MOTION"
    value: bool = True
    timestamp: datetime | None = Field(default=None, description="Hora local; por omissão, agora")


@router.post("/sensors/events", status_code=201, dependencies=[Depends(require_api_key)])
def simulate_sensor_event(event: SimulatedSensorEvent) -> dict:
    """Coloca um evento simulado na fila do gateway (processado na próxima execução do ETL)."""
    with _inbox_lock:
        inbox = _read_json_list(config.SIMULATED_INBOX_FILE)
        doc = {
            "event_id": f"SIM{len(inbox) + 1:04d}",
            "timestamp": (event.timestamp or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S"),
            "sensor_id": event.sensor_id,
            "event_type": event.event_type,
            "value": event.value,
        }
        inbox.append(doc)
        config.SIMULATED_INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = config.SIMULATED_INBOX_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(inbox, indent=2) + "\n", encoding="utf-8")
        tmp.replace(config.SIMULATED_INBOX_FILE)
    return {"queued": doc, "pending": len(inbox)}
