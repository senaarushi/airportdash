"""
API-facing response/request schemas.

Deliberately kept separate from core/models.py: the internal domain
representation (core.models) is free to evolve -- add fields, rename
things, restructure -- without silently breaking the frontend contract
these schemas define. Where a field is a straight passthrough, schemas
here are built via `.model_validate(<core_dict>)` in routes.py/websocket.py
rather than by inheriting from the core models directly, so the coupling
stays explicit and one-directional (api -> core, never the reverse).

Enums ARE imported directly from core.models: an enum's meaning is
shared domain vocabulary, not something the API layer should fork a
second copy of.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.models import (
    AircraftType,
    CrewRole,
    DisruptionSeverity,
    DisruptionType,
    FlightStatus,
    GateStatus,
)


class FlightResponse(BaseModel):
    flight_id: str
    airline: str
    aircraft_type: AircraftType
    scheduled_arrival: datetime
    scheduled_departure: datetime
    actual_arrival: datetime | None = None
    actual_departure: datetime | None = None
    status: FlightStatus
    assigned_gate: str | None = None
    assigned_crew: list[str] = Field(default_factory=list)
    turnaround_time: int
    is_delayed: bool


class GateResponse(BaseModel):
    gate_id: str
    supports_wide_body: bool
    gate_status: GateStatus
    assigned_flight: str | None = None


class CrewMemberResponse(BaseModel):
    crew_id: str
    role: CrewRole
    available: bool
    assigned_flight: str | None = None
    shift_minutes_remaining: int


class DisruptionEventResponse(BaseModel):
    event_id: str
    disruption_type: DisruptionType
    trigger_time: datetime
    severity: DisruptionSeverity
    disruption_description: str
    affected_flights: list[str] = Field(default_factory=list)
    resolved: bool = False


class ConflictResponse(BaseModel):
    conflict_id: str
    agent_id: str
    conflict_description: str
    resolved: bool = False
    affected_flights: list[str] = Field(default_factory=list)


class DecisionLogEntryResponse(BaseModel):
    tick: int
    agent_id: str
    action: str
    detail: str
    affected_flights: list[str] = Field(default_factory=list)


class AirportStatusResponse(BaseModel):
    """Full-state snapshot. Used for GET /status and as the websocket push payload."""

    current_tick: int
    flights: dict[str, FlightResponse]
    crew: dict[str, CrewMemberResponse]
    gates: dict[str, GateResponse]
    open_disruptions: list[DisruptionEventResponse] = Field(default_factory=list)
    open_conflicts: list[ConflictResponse] = Field(default_factory=list)
    decision_log: list[DecisionLogEntryResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    current_tick: int


class ErrorResponse(BaseModel):
    detail: str


class WebSocketMessage(BaseModel):
    """Envelope for every message pushed over /ws."""

    type: str  # "connected" | "state_update" | "error"
    trigger_event: str | None = None  # the EventBus event_type that caused this push, if any
    payload: AirportStatusResponse | None = None
    detail: str | None = None  # human-readable note, used for "connected"/"error" messages


# NEW (manual/auto tick control): request/response models for
# api/simulation_control.py's endpoints.
class SimulationModeRequest(BaseModel):
    mode: Literal["auto", "manual"]


class SimulationModeResponse(BaseModel):
    mode: Literal["auto", "manual"]
    current_tick: int