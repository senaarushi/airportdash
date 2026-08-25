#region Imports
from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.models import GateStatus, Conflict
from app.core.proposals import (
    AgentProposal,
    GateAssignmentProposal,
    CrewAssignmentProposal,
    ScheduleUpdateProposal,
    DisruptionInjectionProposal,
)
from app.decisions.orchestrator_decisions import decide_conflict_resolution

if TYPE_CHECKING:
    from app.agents.graph import GraphState
#endregion Imports


async def orchestrator_node(state: "GraphState") -> dict:
    """
    The sole writer to shared state (Decision #19). Collects the merged
    batch of proposals from all 4 other agents (already combined via
    GraphState.proposals' operator.add reducer, this node only runs once
    all 4 have completed), detects conflicts between them, resolves those
    conflicts, and applies the final outcome directly to state.board, the
    LIVE Blackboard instance, the same object Simulator holds.

    IMPORTANT correctness point: proposals carry flight_ids/gate_ids/
    crew_ids, not live object references, since the other 4 agents only
    ever saw the detached read-only snapshot. Every write below looks up
    the corresponding object fresh in state.board by id. Nothing here ever
    mutates state.snapshot or an object embedded inside a proposal, those
    are copies taken at the start of the tick and are already stale.
    """
    board = state.board
    proposals = state.proposals

    gate_proposals = [p for p in proposals if isinstance(p, GateAssignmentProposal)]
    crew_proposals = [p for p in proposals if isinstance(p, CrewAssignmentProposal)]
    schedule_proposals = [p for p in proposals if isinstance(p, ScheduleUpdateProposal)]
    disruption_proposals = [p for p in proposals if isinstance(p, DisruptionInjectionProposal)]

    await _apply_gate_proposals(board, gate_proposals)
    await _apply_crew_proposals(board, crew_proposals)
    await _apply_schedule_proposals(board, schedule_proposals)
    await _apply_disruption_proposals(board, disruption_proposals)

    return {"board": board}


#region Gate resolution
async def _apply_gate_proposals(board, gate_proposals: list[GateAssignmentProposal]) -> None:
    # EDITED (bug fix): proposed_gate_id can now be None (gate_agent
    # couldn't find any compatible gate this tick, see agents/gate_agent.py).
    # These must be handled BEFORE grouping by gate_id, grouping them under
    # a literal `None` key would incorrectly treat every scarcity case
    # across every flight as if they were all "competing for gate None"
    # with each other, which is not the right semantics, there's nothing
    # to resolve between them, each is independently starved. Each gets
    # its own unresolved Conflict instead.
    no_gate_proposals = [p for p in gate_proposals if p.proposed_gate_id is None]
    contested_proposals = [p for p in gate_proposals if p.proposed_gate_id is not None]

    for p in no_gate_proposals:
        conflict = Conflict(
            conflict_id=str(uuid4()),
            agent_id="orchestrator",
            conflict_description=f"No compatible gate available for {p.flight_id} this tick.",
            resolved=False,
            affected_flights=[p.flight_id],
        )
        async with board.lock:
            board.open_conflicts.append(conflict)

        await board.log_decision(
            agent_id="orchestrator",
            action="gate_unavailable",
            detail=f"No compatible gate available for {p.flight_id}. {p.reasoning}",
            affected_flights=[p.flight_id],
        )

    # Group by proposed_gate_id, detection: any group with more than one
    # proposal is a genuine conflict, two flights wanting the same gate.
    by_gate: dict[str, list[GateAssignmentProposal]] = defaultdict(list)
    for p in contested_proposals:
        by_gate[p.proposed_gate_id].append(p)

    for gate_id, competing in by_gate.items():
        if len(competing) == 1:
            winner = competing[0]
        else:
            # LLM-based resolution (Decision #30/#31): decide_conflict_resolution
            # validates its own chosen winner against the real candidate set
            # and falls back to competing[0] internally on any invalid
            # response or API failure, no local placeholder needed anymore.
            winner = await decide_conflict_resolution(competing)
            losers = [p for p in competing if p.proposal_id != winner.proposal_id]

            conflict = Conflict(
                conflict_id=str(uuid4()),
                agent_id="orchestrator",
                conflict_description=(
                    f"Gate {gate_id} was proposed for multiple flights "
                    f"({', '.join(p.flight_id for p in competing)}), assigned to {winner.flight_id}."
                ),
                resolved=True,
                affected_flights=[p.flight_id for p in competing],
            )
            async with board.lock:
                board.open_conflicts.append(conflict)

            for loser in losers:
                await board.log_decision(
                    agent_id="orchestrator",
                    action="conflict_resolved",
                    detail=f"{loser.flight_id}'s request for gate {gate_id} deferred in favor of {winner.flight_id}. {winner.reasoning}",
                    affected_flights=[loser.flight_id, winner.flight_id],
                )

        flight = board.flights.get(winner.flight_id)
        gate = board.gates.get(gate_id)
        if flight is None or gate is None:
            continue  # referenced id no longer exists on the live board, skip rather than crash

        async with board.lock:
            flight.assigned_gate = gate_id
            gate.assigned_flight = winner.flight_id
            gate.gate_status = GateStatus.OCCUPIED

        await board.log_decision(
            agent_id="orchestrator",
            action="gate_assignment",
            detail=f"{winner.flight_id} assigned to gate {gate_id}. {winner.reasoning}",
            affected_flights=[winner.flight_id],
        )
#endregion Gate resolution


#region Crew resolution
async def _apply_crew_proposals(board, crew_proposals: list[CrewAssignmentProposal]) -> None:
    """
    Crew contention doesn't map onto decide_conflict_resolution the same
    way gate contention does: a gate conflict is N proposals competing for
    exactly 1 resource, one winner takes it all. A crew proposal wants a
    LIST of crew members, contention happens at the level of one
    individual crew_id being wanted by more than one flight's proposal,
    not whole proposals competing wholesale. So resolution happens
    per-contested-crew-member: for each crew_id requested by more than one
    proposal, decide_conflict_resolution picks which proposal (i.e. which
    flight) gets that specific person, other proposals simply don't get
    that one crew_id but keep whichever of their other requested crew
    members weren't contested.
    """
    # Map each requested crew_id to every proposal that wants it, so
    # contested crew_ids (wanted by 2+ proposals) can be identified.
    requesters_by_crew_id: dict[str, list[CrewAssignmentProposal]] = defaultdict(list)
    for p in crew_proposals:
        for cid in p.proposed_crew_ids:
            requesters_by_crew_id[cid].append(p)

    # Resolve each contested crew_id up front, before assigning anything,
    # so assignment below can just check "did I win this specific person".
    winner_proposal_id_by_crew_id: dict[str, str] = {}
    for cid, requesters in requesters_by_crew_id.items():
        if len(requesters) == 1:
            winner_proposal_id_by_crew_id[cid] = requesters[0].proposal_id
            continue

        winner = await decide_conflict_resolution(requesters)
        winner_proposal_id_by_crew_id[cid] = winner.proposal_id

        losers = [p for p in requesters if p.proposal_id != winner.proposal_id]
        conflict = Conflict(
            conflict_id=str(uuid4()),
            agent_id="orchestrator",
            conflict_description=(
                f"Crew member {cid} was requested by multiple flights "
                f"({', '.join(p.flight_id for p in requesters)}), assigned to {winner.flight_id}."
            ),
            resolved=True,
            affected_flights=[p.flight_id for p in requesters],
        )
        async with board.lock:
            board.open_conflicts.append(conflict)

        for loser in losers:
            await board.log_decision(
                agent_id="orchestrator",
                action="conflict_resolved",
                detail=f"{loser.flight_id}'s request for crew member {cid} deferred in favor of {winner.flight_id}. {winner.reasoning}",
                affected_flights=[loser.flight_id, winner.flight_id],
            )

    # A crew_id can only ever be claimed once per tick even outside direct
    # contention (e.g. it was already assigned to an earlier-processed
    # proposal that won a DIFFERENT contested crew_id but happened to also
    # list this one uncontested), this tracks that.
    claimed_crew_ids: set[str] = set()

    for p in crew_proposals:
        flight = board.flights.get(p.flight_id)
        if flight is None:
            continue

        available_ids = [
            cid for cid in p.proposed_crew_ids
            if cid not in claimed_crew_ids
            and winner_proposal_id_by_crew_id.get(cid) == p.proposal_id
        ]

        if not available_ids:
            conflict = Conflict(
                conflict_id=str(uuid4()),
                agent_id="orchestrator",
                conflict_description=f"No unclaimed crew remained for {p.flight_id}'s turnaround this tick.",
                resolved=False,
                affected_flights=[p.flight_id],
            )
            async with board.lock:
                board.open_conflicts.append(conflict)
            continue

        claimed_crew_ids.update(available_ids)

        async with board.lock:
            flight.assigned_crew = available_ids
            for cid in available_ids:
                crew_member = board.crew.get(cid)
                if crew_member is not None:
                    crew_member.assigned_flight = p.flight_id
                    crew_member.available = False

        await board.log_decision(
            agent_id="orchestrator",
            action="crew_reassigned",
            detail=f"{len(available_ids)} crew member(s) assigned to {p.flight_id}. {p.reasoning}",
            affected_flights=[p.flight_id],
        )
#endregion Crew resolution


#region Schedule updates
async def _apply_schedule_proposals(board, schedule_proposals: list[ScheduleUpdateProposal]) -> None:
    for p in schedule_proposals:
        flight = board.flights.get(p.flight_id)
        if flight is None:
            continue

        async with board.lock:
            if p.updated_status is not None:
                flight.status = p.updated_status
            if p.actual_arrival is not None:
                flight.actual_arrival = p.actual_arrival
            if p.actual_departure is not None:
                flight.actual_departure = p.actual_departure

        if p.delay_risk_flag:
            await board.log_decision(
                agent_id="orchestrator",
                action="delay_risk_flagged",
                detail=p.reasoning,
                affected_flights=[p.flight_id],
            )
#endregion Schedule updates


#region Disruption handling
async def _apply_disruption_proposals(board, disruption_proposals: list[DisruptionInjectionProposal]) -> None:
    for p in disruption_proposals:
        # Look up the LIVE disruption on board.open_disruptions by
        # event_id, never mutate p.disruption_event directly, it's a
        # detached copy from the snapshot taken at the start of this tick.
        live_disruption = next(
            (d for d in board.open_disruptions if d.event_id == p.disruption_event.event_id),
            None,
        )
        if live_disruption is None:
            continue

        # Placeholder resolution check: consider a disruption resolved once
        # every flight it affected has a gate assigned again. Structural
        # bookkeeping, not really "intelligence", though the threshold for
        # what counts as "resolved" could become more nuanced later.
        affected_flights_resolved = all(
            board.flights[fid].assigned_gate is not None
            for fid in live_disruption.affected_flights
            if fid in board.flights
        )

        async with board.lock:
            if affected_flights_resolved and not live_disruption.resolved:
                live_disruption.resolved = True

        await board.log_decision(
            agent_id="orchestrator",
            action="disruption_resolved" if affected_flights_resolved else "disruption_monitored",
            detail=p.reasoning,
            affected_flights=live_disruption.affected_flights,
        )
#endregion Disruption handling
