"""
REST endpoints: /flights, /gates, /crew, /decisions
(+ /disruptions, /conflicts, /status, /health).

Read-only. This router never mutates the Blackboard -- all writes to
shared state stay the Orchestrator's exclusive job (Decision #19).
These endpoints exist purely to expose current state to the frontend
(or curl/Postman during development).

Snapshot pattern: every handler takes the board's lock just long enough
to call .model_dump(), then releases it before building response
schemas. This mirrors the read-isolation approach already used for
agents (Decision #26) -- API reads can never observe a half-written
tick, and never hold the lock any longer than the copy itself takes.
"""

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    AirportStatusResponse,
    ConflictResponse,
    CrewMemberResponse,
    DecisionLogEntryResponse,
    DisruptionEventResponse,
    FlightResponse,
    GateResponse,
    HealthResponse,
)
from app.core.event_bus import board

router = APIRouter()


async def _snapshot() -> dict:
    """Lock-protected copy of the live board; safe to read from freely afterward."""
    async with board.lock:
        return board.model_dump()


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    return HealthResponse(current_tick=board.current_tick)


@router.get("/status", response_model=AirportStatusResponse)
async def get_status() -> AirportStatusResponse:
    return AirportStatusResponse.model_validate(await _snapshot())


@router.get("/flights", response_model=list[FlightResponse])
async def list_flights() -> list[FlightResponse]:
    snap = await _snapshot()
    return [FlightResponse.model_validate(f) for f in snap["flights"].values()]


@router.get("/flights/{flight_id}", response_model=FlightResponse)
async def get_flight(flight_id: str) -> FlightResponse:
    snap = await _snapshot()
    flight = snap["flights"].get(flight_id)
    if flight is None:
        raise HTTPException(status_code=404, detail=f"Flight '{flight_id}' not found")
    return FlightResponse.model_validate(flight)


@router.get("/gates", response_model=list[GateResponse])
async def list_gates() -> list[GateResponse]:
    snap = await _snapshot()
    return [GateResponse.model_validate(g) for g in snap["gates"].values()]


@router.get("/gates/{gate_id}", response_model=GateResponse)
async def get_gate(gate_id: str) -> GateResponse:
    snap = await _snapshot()
    gate = snap["gates"].get(gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail=f"Gate '{gate_id}' not found")
    return GateResponse.model_validate(gate)


@router.get("/crew", response_model=list[CrewMemberResponse])
async def list_crew() -> list[CrewMemberResponse]:
    snap = await _snapshot()
    return [CrewMemberResponse.model_validate(c) for c in snap["crew"].values()]


@router.get("/crew/{crew_id}", response_model=CrewMemberResponse)
async def get_crew_member(crew_id: str) -> CrewMemberResponse:
    snap = await _snapshot()
    crew = snap["crew"].get(crew_id)
    if crew is None:
        raise HTTPException(status_code=404, detail=f"Crew member '{crew_id}' not found")
    return CrewMemberResponse.model_validate(crew)


@router.get("/disruptions", response_model=list[DisruptionEventResponse])
async def list_disruptions(include_resolved: bool = False) -> list[DisruptionEventResponse]:
    snap = await _snapshot()
    disruptions = snap["open_disruptions"]
    if not include_resolved:
        disruptions = [d for d in disruptions if not d["resolved"]]
    return [DisruptionEventResponse.model_validate(d) for d in disruptions]


@router.get("/conflicts", response_model=list[ConflictResponse])
async def list_conflicts(include_resolved: bool = False) -> list[ConflictResponse]:
    snap = await _snapshot()
    conflicts = snap["open_conflicts"]
    if not include_resolved:
        conflicts = [c for c in conflicts if not c["resolved"]]
    return [ConflictResponse.model_validate(c) for c in conflicts]


@router.get("/decisions", response_model=list[DecisionLogEntryResponse])
async def list_decisions(
    agent_id: str | None = None,
    limit: int = 100,
) -> list[DecisionLogEntryResponse]:
    """Reasoning-trace feed for the dashboard. Returns the most recent `limit`
    entries (chronological order preserved), optionally filtered to one agent."""
    snap = await _snapshot()
    entries = snap["decision_log"]
    if agent_id is not None:
        entries = [e for e in entries if e["agent_id"] == agent_id]
    entries = entries[-limit:]
    return [DecisionLogEntryResponse.model_validate(e) for e in entries]