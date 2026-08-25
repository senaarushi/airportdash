#region Imports
from __future__ import annotations
from typing import TYPE_CHECKING

from app.core.models import FlightStatus, GateStatus
from app.core.proposals import GateAssignmentProposal
from app.decisions.gate_decisions import decide_gate_assignment

if TYPE_CHECKING:
    from app.agents.graph import GraphState
#endregion Imports


async def gate_agent_node(state: "GraphState") -> dict:
    """
    Reads state.snapshot (read-only AirportStatus, never state.board).
    For every flight that has physically landed but has no gate assigned
    yet, proposes a gate assignment via decide_gate_assignment (rule-based,
    Decision #30/#31). Never writes shared state, only ever returns
    proposals for the Orchestrator to apply, consistent with the
    single-writer architecture (Decision #19).

    EDITED (bug fix): now ALWAYS emits a GateAssignmentProposal for a
    flight that needs a gate, even when decide_gate_assignment returns
    None (no compatible gate available this tick). Previously this case
    was silently skipped entirely, no proposal was ever sent to the
    Orchestrator, which meant total gate scarcity was completely
    invisible: a flight could sit LANDED with no gate for the entire
    simulation with zero Conflict, zero decision_log entry, nothing.
    proposed_gate_id=None now flows through as a real proposal, and
    Orchestrator's _apply_gate_proposals handles it as an unresolved
    Conflict (see agents/orchestrator.py).
    """
    proposals: list[GateAssignmentProposal] = []
    board = state.snapshot

    available_gates = [g for g in board.gates.values() if g.gate_status == GateStatus.OPEN]

    for flight in board.flights.values():
        needs_gate = flight.status == FlightStatus.LANDED and flight.assigned_gate is None
        if not needs_gate:
            continue

        proposed_gate_id = decide_gate_assignment(flight, available_gates)

        reasoning = (
            f"Gate {proposed_gate_id} is open and compatible with {flight.flight_id}'s aircraft type."
            if proposed_gate_id is not None
            else f"No compatible open gate available for {flight.flight_id} this tick."
        )

        proposals.append(
            GateAssignmentProposal(
                agent_id="gate_agent",
                tick=board.current_tick,
                reasoning=reasoning,
                flight_id=flight.flight_id,
                proposed_gate_id=proposed_gate_id,
            )
        )

    return {"proposals": proposals}
