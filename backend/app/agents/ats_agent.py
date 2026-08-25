#region Imports
from __future__ import annotations
from typing import TYPE_CHECKING

from app.core.models import FlightStatus
from app.core.proposals import ScheduleUpdateProposal
from app.decisions.ats_decisions import decide_delay_risk

if TYPE_CHECKING:
    from app.agents.graph import GraphState
#endregion Imports


def _already_flagged(board, flight_id: str) -> bool:
    """
    True if this flight already has a delay_risk_flagged entry anywhere in
    decision_log. Derived from data already present in the read-only
    snapshot (board.decision_log), no new state needed, keeps this agent
    stateless the same way every other decision here is.
    """
    return any(
        e.action == "delay_risk_flagged" and flight_id in e.affected_flights
        for e in board.decision_log
    )


async def ats_agent_node(state: "GraphState") -> dict:
    """
    Reads state.snapshot only. Scans active (non-terminal) flights for
    delay risk via decide_delay_risk (rule-based, Decision #30/#31).
    Never writes shared state (Decision #19).

    EDITED (bug fix): now only proposes a flag ONCE per flight, not every
    tick for the flight's entire remaining lifecycle. Previously, since
    the fixed 10-minute taxi/landing buffer in simulator.py means nearly
    every flight ends up is_delayed=True almost permanently (an artifact
    of the simulation's timing model, not real schedule variance), this
    agent was re-flagging the same flights every single tick, flooding
    decision_log with hundreds of near-duplicate "X is running behind"
    entries and drowning out the genuinely interesting reasoning trace
    entries (gate assignments, conflict resolutions, disruption handling)
    the log exists to surface. _already_flagged() checks the snapshot's
    own decision_log for a prior flag on this flight_id before proposing
    another one.
    """
    proposals: list[ScheduleUpdateProposal] = []
    board = state.snapshot

    terminal_statuses = {FlightStatus.DEPARTED, FlightStatus.CANCELLED}

    for flight in board.flights.values():
        if flight.status in terminal_statuses:
            continue

        if _already_flagged(board, flight.flight_id):
            continue

        at_risk = decide_delay_risk(flight, board.current_tick)

        if not at_risk:
            continue

        proposals.append(
            ScheduleUpdateProposal(
                agent_id="ats_agent",
                tick=board.current_tick,
                reasoning=f"{flight.flight_id} is running behind its scheduled time, flagged for cascading delay risk.",
                flight_id=flight.flight_id,
                delay_risk_flag=True,
            )
        )

    return {"proposals": proposals}
