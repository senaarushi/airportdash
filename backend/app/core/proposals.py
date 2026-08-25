#region Imports
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from app.core.models import FlightStatus, DisruptionEvent, _coerce_utc
# NOTE: _coerce_utc is a "private by convention" module-level function in
# models.py (underscore prefix), imported directly here rather than
# duplicated. Works fine in Python, underscore only excludes it from
# wildcard (`from x import *`) imports. If this shared-validation logic
# grows further, consider promoting it to its own core/validators.py that
# both models.py and this file import from, instead of proposals.py
# reaching into models.py's private helper.
#endregion Imports


#region Base
class AgentProposal(BaseModel):
    """
    Base class for every proposal an agent hands back to the Orchestrator.

    Part of the single-writer architecture: Gate, Crew, ATS, and Disruption
    agents never mutate Blackboard/AirportStatus directly, they only ever
    return one of these. The Orchestrator is the sole place in the codebase
    that reads a batch of AgentProposal objects, detects conflicts between
    them, resolves those conflicts, and writes the result to Blackboard.
    This makes race conditions structurally impossible rather than merely
    guarded against, and makes "resolves conflicts raised by other agents"
    a literal description of what Orchestrator does, not just a label.
    """

    proposal_id: Annotated[
        str,
        Field(default_factory=lambda: str(uuid4()), description="unique id per proposal, lets the Orchestrator trace which proposal produced which decision_log entry or Conflict"),
    ]
    agent_id: str  # which agent produced this, e.g. "gate_agent"
    tick: Annotated[int, Field(ge=0, description="which simulation tick this was proposed on")]
    reasoning: str  # human-readable justification; flows directly into DecisionLogEntry.detail once the Orchestrator acts on it
#endregion Base


#region Proposals
class GateAssignmentProposal(AgentProposal):
    """
    Gate Agent's proposed gate assignment for a single flight.

    EDITED (bug fix): proposed_gate_id is now `str | None`, previously it
    was a required `str`, which meant gate_agent had no way to represent
    "this flight needs a gate but none is available right now" as a
    proposal at all, it just silently skipped emitting anything. That
    made total gate scarcity completely invisible: no Conflict, no
    decision_log entry, nothing, a flight could sit starved indefinitely
    with zero trace of why. None now means exactly that case; Orchestrator
    handles it as an unresolved Conflict (see agents/orchestrator.py),
    mirroring how CrewAssignmentProposal already represented scarcity via
    an empty list.
    """

    flight_id: str
    proposed_gate_id: str | None


class CrewAssignmentProposal(AgentProposal):
    """Ground Crew Agent's proposed crew assignment for a single flight."""

    flight_id: str
    proposed_crew_ids: Annotated[list[str], Field(default_factory=list)]


class ScheduleUpdateProposal(AgentProposal):
    """
    ATS Agent's proposed update to a flight's tracked schedule state.
    delay_risk_flag is ATS's early-warning signal to the Orchestrator,
    distinct from an actual Conflict, which only the Orchestrator creates.
    """

    flight_id: str
    updated_status: Annotated[FlightStatus | None, Field(default=None)]
    actual_arrival: Annotated[datetime | None, Field(default=None)]
    actual_departure: Annotated[datetime | None, Field(default=None)]
    delay_risk_flag: Annotated[bool, Field(default=False)]

    @field_validator("actual_arrival", "actual_departure", mode="before")
    @classmethod
    def _normalize_timestamps(cls, v):
        # Same UTC-normalization as Flight in models.py, ATS will eventually
        # be fed real actual-time updates from a live data feed and needs
        # the same guarantee that timestamps are always comparable.
        return _coerce_utc(v)


class DisruptionInjectionProposal(AgentProposal):
    """
    Disruption Agent's request to inject a new disruption event.
    The Orchestrator decides whether and when to actually inject it, it
    could reject or defer injection if the system is mid-resolution of
    something else.
    """

    disruption_event: DisruptionEvent
#endregion Proposals
