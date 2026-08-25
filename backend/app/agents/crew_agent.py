#region Imports
from __future__ import annotations
from typing import TYPE_CHECKING

from app.core.models import FlightStatus
from app.core.proposals import CrewAssignmentProposal
from app.decisions.crew_decisions import decide_crew_assignment

if TYPE_CHECKING:
    from app.agents.graph import GraphState
#endregion Imports


async def crew_agent_node(state: "GraphState") -> dict:
    """
    Reads state.snapshot only. For every flight that has reached its gate
    but has no crew assigned yet, proposes a crew assignment via
    decide_crew_assignment (rule-based, Decision #30/#31). Never writes
    shared state, only ever returns proposals (Decision #19).

    EDITED (bug fix): now ALWAYS emits a CrewAssignmentProposal, even when
    decide_crew_assignment returns an empty list (no eligible crew for any
    required role this tick). Previously this case was silently skipped,
    no proposal reached the Orchestrator, so Orchestrator's already-
    existing "no unclaimed crew remained" Conflict logic in
    _apply_crew_proposals never actually triggered for total scarcity,
    only for head-to-head contention between two proposals. A flight
    could depart having never received any crew at all, with zero trace
    of why. Emitting the (possibly empty) proposal every time lets
    Orchestrator's existing logic catch this case correctly.
    """
    proposals: list[CrewAssignmentProposal] = []
    board = state.snapshot

    available_crew = [c for c in board.crew.values() if c.available]

    for flight in board.flights.values():
        needs_crew = flight.status == FlightStatus.AT_GATE and not flight.assigned_crew
        if not needs_crew:
            continue

        proposed_crew_ids = decide_crew_assignment(flight, available_crew)

        reasoning = (
            f"Assigned {len(proposed_crew_ids)} available crew member(s) to {flight.flight_id}'s turnaround."
            if proposed_crew_ids
            else f"No eligible crew available for any required role on {flight.flight_id}'s turnaround this tick."
        )

        proposals.append(
            CrewAssignmentProposal(
                agent_id="crew_agent",
                tick=board.current_tick,
                reasoning=reasoning,
                flight_id=flight.flight_id,
                proposed_crew_ids=proposed_crew_ids,
            )
        )

    return {"proposals": proposals}
