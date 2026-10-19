"""Contratos de dados do serviço de inferência (/ai).

Entrada: um caso já correlacionado pelo Pentaho (factos + contexto, sem veredicto das regras).
Saída: resposta plana, fácil de consumir no Kettle (JSON Input com caminhos $.campo).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RiskLevel = Literal["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
IncidentType = Literal[
    "POTENTIAL_INTRUSION", "UNAUTHORIZED_ACCESS", "BRUTE_FORCE_ATTEMPT", "TAILGATING",
    "CREDENTIAL_MISUSE", "OFF_HOURS_ACTIVITY", "SENSOR_ANOMALY", "BENIGN_ACTIVITY",
]
Status = Literal["OK", "TIMEOUT", "INVALID_OUTPUT", "INVALID_INPUT", "MODEL_ERROR"]


# ----------------------------------------------------------------------------- entrada
class ZoneContext(BaseModel):
    zone_id: str = Field(pattern=r"^Z[0-9]{2}$")
    name: str
    security_level: Literal["PUBLIC", "INTERNAL", "RESTRICTED", "CRITICAL"]
    open_time: str
    close_time: str
    open_weekends: bool


class UserContext(BaseModel):
    user_id: str = Field(pattern=r"^U[0-9]{3}$")
    role: str
    schedule_start: str | None = None
    schedule_end: str | None = None
    active: bool
    has_permission_for_zone: bool


class CaseEvent(BaseModel):
    event_id: str = Field(pattern=r"^[A-Z]{3}[0-9]{4}$")
    timestamp: datetime
    source: Literal["ACCESS", "SENSOR"]
    event_type: Literal["ACCESS_GRANTED", "ACCESS_DENIED", "MOTION", "DOOR_OPEN"]
    device_id: str | None = None
    user: UserContext | None = None
    zone_closed_at_event_time: bool
    outside_user_schedule: bool


class CaseInput(BaseModel):
    case_id: str = Field(pattern=r"^CASE-Z[0-9]{2}-[0-9]{8}-[0-9]{6}$")
    zone: ZoneContext
    start_ts: datetime
    end_ts: datetime
    events: list[CaseEvent] = Field(min_length=1, max_length=50)


# ----------------------------------------------------------------------------- saída do modelo
class ModelOutput(BaseModel):
    """Estrutura exigida ao LLM; campos extra são rejeitados."""
    model_config = ConfigDict(extra="forbid")

    is_suspicious: bool
    risk_level: RiskLevel
    incident_type: IncidentType
    explanation: str = Field(min_length=10, max_length=1200)
    evidence_event_ids: list[str] = Field(min_length=1)
    recommended_action: str = Field(min_length=5, max_length=400)

    @field_validator("evidence_event_ids")
    @classmethod
    def unique_ids(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


# ----------------------------------------------------------------------------- resposta da API
class AnalysisResponse(BaseModel):
    case_id: str | None
    status: Status
    is_suspicious: bool | None = None
    risk_level: RiskLevel | None = None
    incident_type: IncidentType | None = None
    explanation: str | None = None
    recommended_action: str | None = None
    evidence_event_ids: list[str] = []
    evidence_event_ids_csv: str | None = None
    model: str
    model_digest: str | None = None
    prompt_version: str
    latency_ms: int | None = None
    error: str | None = None
    raw_model_output: str | None = None
