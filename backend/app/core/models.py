#region Imports
from pydantic import BaseModel, Field, computed_field, field_validator
from enum import Enum, IntEnum
from datetime import datetime, timezone
from typing import Annotated
#endregion Imports

#region Enums
class AircraftType(str,Enum):
    NARROW_BODY = 'NARROW_BODY'
    WIDE_BODY = 'WIDE_BODY'


class FlightStatus(str, Enum):
    """Tracks the physical operational phase of the aircraft."""

    SCHEDULED = "SCHEDULED" # The flight is in the system but has not yet departed its origin airport.
    IN_AIR = "IN_AIR" # The flight has taken off and is currently en route to the airport.
    LANDED = "LANDED" # The aircraft has touched down and is taxiing; the assigned gate must be open now.
    AT_GATE = "AT_GATE" # The aircraft is parked at the gate; ground crew operations (baggage, cleaning) are active.
    READY_FOR_PUSHBACK = "READY_FOR_PUSHBACK" # Turnaround is complete, doors are closed, and it is awaiting clearance to leave the gate.
    DEPARTED = "DEPARTED" # The aircraft has pushed back and taken off; resources can be freed.
    CANCELLED = "CANCELLED" # The flight has been cancelled; resources can be freed.


class GateStatus(str, Enum):
    """Tracks the availability of a gate."""

    OPEN = "OPEN"
    OCCUPIED = "OCCUPIED"
    UNAVAILABLE = "UNAVAILABLE"

class CrewRole(str, Enum):
    """Tracks the role of a crew member."""

    BAGGAGE = "BAGGAGE"
    PUSHBACK = "PUSHBACK"
    CLEANING = "CLEANING"

class DisruptionType(str, Enum):
    """Tracks the type of a disruption."""

    WEATHER = "WEATHER"
    TECH_ISSUE = "TECH_ISSUE"
    CREW_SHORTAGE = "CREW_SHORTAGE"

class DisruptionSeverity(IntEnum):
    """Tracks the severity of a disruption on a 1-5 scale."""

    LEVEL_1 = 1 # Minor delay, highly localized
    LEVEL_2 = 2 # Moderate issue, manageable locally
    LEVEL_3 = 3 # Major disruption, requires partial replanning
    LEVEL_4 = 4 # Severe disruption, cascades across multiple flights
    LEVEL_5 = 5 # Critical system-wide halt (e.g., airport closure)
#endregion Enums


#region Shared validation
def _coerce_utc(value: datetime | str | None) -> datetime | None:
    """
    FIX (real-world-data readiness): real flight/ops data feeds are almost
    always timezone-aware (usually UTC or with an explicit offset). Mock
    data generated in-process previously used naive datetimes. Mixing the
    two silently crashes on comparison (e.g. Flight.is_delayed) the moment
    real data is introduced, Python raises TypeError comparing a naive and
    an aware datetime rather than giving a useful error at the boundary.

    This normalizes every datetime field to timezone-aware UTC on the way
    in: naive values are assumed UTC and tagged, aware values are converted
    to UTC. This means mock data and real data are guaranteed to be
    comparable no matter which source produced them.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
#endregion Shared validation


#region Schemas
class Flight(BaseModel):
    """
    Represents an individual flight and its real-time operational status.
    """

    flight_id: str
    airline: str
    aircraft_type: AircraftType
    scheduled_arrival: datetime
    scheduled_departure: datetime
    actual_arrival: Annotated[datetime | None, Field(default = None)]
    actual_departure: Annotated[datetime | None, Field(default = None)]
    status: Annotated[FlightStatus, Field(default = FlightStatus.SCHEDULED)]
    assigned_gate: Annotated[str | None, Field(default = None)]
    assigned_crew: Annotated[list[str], Field(default_factory=list)]
    turnaround_time: Annotated[int, Field(gt=0, description= 'must be a positive integer')]

    @field_validator(
        "scheduled_arrival", "scheduled_departure", "actual_arrival", "actual_departure",
        mode="before",
    )
    @classmethod
    def _normalize_timestamps(cls, v):
        return _coerce_utc(v)

    @computed_field
    @property
    def is_delayed(self) -> bool:
        """
        Evaluates temporal state independently of physical status.
        Returns True if the flight actually arrived or actually departed later
        than its scheduled time.
        """
        # Check if it arrived late
        if self.actual_arrival and self.scheduled_arrival:
            if self.actual_arrival > self.scheduled_arrival:
                return True

        # Check if it departed late
        if self.actual_departure and self.scheduled_departure:
            if self.actual_departure > self.scheduled_departure:
                return True

        return False

class CrewMember(BaseModel):
    """
    Tracks individual ground crew personnel, their roles, and fatigue limits.
    """

    crew_id: str
    role: CrewRole
    available:bool
    assigned_flight: Annotated[str | None, Field(default = None)]
    shift_minutes_remaining: Annotated[int, Field(ge=0, description= 'must be a positive integer')]

class Gate(BaseModel):
    """
    Represents a physical terminal gate and its current availability.
    """

    gate_id: str
    supports_wide_body: bool
    gate_status: Annotated[GateStatus, Field(default = GateStatus.OPEN)]
    assigned_flight: Annotated[str | None, Field(default = None)]

class DisruptionEvent(BaseModel):
    """
    Defines a systemic or localized disruption that requires system replanning.
    """

    event_id: str
    disruption_type: DisruptionType
    trigger_time: datetime
    severity: DisruptionSeverity
    disruption_description:str
    affected_flights: Annotated[list[str], Field(default_factory=list)]
    resolved: Annotated[bool, Field(default = False)]

    @field_validator("trigger_time", mode="before")
    @classmethod
    def _normalize_trigger_time(cls, v):
        return _coerce_utc(v)

class Conflict(BaseModel):
    """
    A standardized distress signal raised by an agent when it cannot resolve an issue locally.
    """

    conflict_id: str
    agent_id: str
    conflict_description: str
    resolved: Annotated[bool, Field(default = False)]
    affected_flights: Annotated[list[str], Field(default_factory=list)]

class DecisionLogEntry(BaseModel):
    """
    A single record of an agent's action, used to drive the frontend's
    live reasoning trace. Pure data, no logic, agents are responsible
    for constructing and appending these.
    """

    tick: Annotated[int, Field(ge=0, description='must be a positive integer')]
    agent_id: str
    action: str  # e.g. "gate_assignment", "conflict_raised", "conflict_resolved", "crew_reassigned"
    detail: str  # human-readable sentence for the reasoning trace
    affected_flights: Annotated[list[str], Field(default_factory=list)]

class AirportStatus(BaseModel):
    """The global blackboard state passed between all LangGraph agents during a simulation tick."""

    current_tick: Annotated[int, Field(ge=0, description= 'must be a positive integer', default = 0)]
    flights: Annotated[dict[str, Flight], Field(default_factory=dict)]
    crew: Annotated[dict[str, CrewMember], Field(default_factory=dict)]
    gates: Annotated[dict[str, Gate], Field(default_factory=dict)]
    open_disruptions: Annotated[list[DisruptionEvent], Field(default_factory=list)]
    open_conflicts: Annotated[list[Conflict], Field(default_factory=list)]
    decision_log: Annotated[list[DecisionLogEntry], Field(default_factory=list)]
#endregion Schemas