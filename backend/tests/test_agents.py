"""
Tests for agents/*.py -- the "agent shell" layer (Decision #6).

Gate/Crew/ATS/Disruption agent nodes only ever read state.snapshot (a
detached AirportStatus) and return proposals, they're tested by building a
GraphState with a hand-built snapshot and asserting on the returned
proposal list. They never touch state.board, so state.board is populated
with an empty Blackboard() in these tests purely to satisfy GraphState's
required field, nothing in these 4 nodes reads it.

orchestrator_node is different: it's the sole writer to shared state
(Decision #19), so its tests build a real Blackboard, run the node, and
assert on the board's resulting mutations (flights/gates/crew/conflicts/
decision_log) directly rather than on a return value.

decide_gate_assignment/decide_crew_assignment/decide_delay_risk are rule-
based and exercised for real (no mocking needed, they're pure functions).
decide_disruption_priority and decide_conflict_resolution wrap a real LLM
call; both agents import them by name into their own module namespace
(`from app.decisions.x import y`), so they're monkeypatched at the POINT
OF USE (app.agents.disruption_agent.decide_disruption_priority /
app.agents.orchestrator.decide_conflict_resolution), not at their
original definition site, matching how Python name binding actually works
for `from x import y` imports.

Requires pytest and pytest-asyncio (already added to requirements.txt).
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.agents.graph import GraphState
from app.agents import disruption_agent as disruption_agent_module
from app.agents import orchestrator as orchestrator_module
from app.agents.ats_agent import ats_agent_node
from app.agents.crew_agent import crew_agent_node
from app.agents.disruption_agent import disruption_agent_node
from app.agents.gate_agent import gate_agent_node
from app.agents.orchestrator import orchestrator_node
from app.core.event_bus import Blackboard
from app.core.models import (
    AircraftType,
    AirportStatus,
    Conflict,
    CrewMember,
    CrewRole,
    DisruptionEvent,
    DisruptionSeverity,
    DisruptionType,
    Flight,
    FlightStatus,
    Gate,
    GateStatus,
)
from app.core.proposals import (
    AgentProposal,
    CrewAssignmentProposal,
    DisruptionInjectionProposal,
    GateAssignmentProposal,
    ScheduleUpdateProposal,
)


BASE_TIME = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


#region Fixtures / helpers
def make_flight(
    flight_id: str = "AI101",
    aircraft_type: AircraftType = AircraftType.NARROW_BODY,
    status: FlightStatus = FlightStatus.LANDED,
    turnaround_time: int = 45,
    assigned_gate: str | None = None,
    assigned_crew: list[str] | None = None,
) -> Flight:
    return Flight(
        flight_id=flight_id,
        airline="AI",
        aircraft_type=aircraft_type,
        scheduled_arrival=BASE_TIME,
        scheduled_departure=BASE_TIME + timedelta(minutes=turnaround_time),
        status=status,
        assigned_gate=assigned_gate,
        assigned_crew=assigned_crew or [],
        turnaround_time=turnaround_time,
    )


def make_gate(gate_id: str, supports_wide_body: bool = False, status: GateStatus = GateStatus.OPEN) -> Gate:
    return Gate(gate_id=gate_id, supports_wide_body=supports_wide_body, gate_status=status)


def make_crew(crew_id: str, role: CrewRole, available: bool = True, shift_minutes_remaining: int = 120) -> CrewMember:
    return CrewMember(crew_id=crew_id, role=role, available=available, shift_minutes_remaining=shift_minutes_remaining)


def make_disruption(
    event_id: str = "DIS1",
    resolved: bool = False,
    affected_flights: list[str] | None = None,
) -> DisruptionEvent:
    return DisruptionEvent(
        event_id=event_id,
        disruption_type=DisruptionType.WEATHER,
        trigger_time=BASE_TIME,
        severity=DisruptionSeverity.LEVEL_3,
        disruption_description="Test disruption",
        affected_flights=affected_flights or [],
        resolved=resolved,
    )


def make_snapshot_state(
    flights: dict[str, Flight] | None = None,
    gates: dict[str, Gate] | None = None,
    crew: dict[str, CrewMember] | None = None,
    open_disruptions: list[DisruptionEvent] | None = None,
    current_tick: int = 1,
) -> GraphState:
    """
    Builds a GraphState for the 4 read-only agent nodes. state.board is an
    empty Blackboard purely to satisfy the required field, none of these 4
    nodes ever reads it -- only state.snapshot is used.
    """
    snapshot = AirportStatus(
        current_tick=current_tick,
        flights=flights or {},
        gates=gates or {},
        crew=crew or {},
        open_disruptions=open_disruptions or [],
    )
    return GraphState(snapshot=snapshot, board=Blackboard(), proposals=[])


def make_board_state(
    board: Blackboard,
    proposals: list[AgentProposal],
) -> GraphState:
    """Builds a GraphState for orchestrator_node, the sole writer of `board`."""
    snapshot = AirportStatus.model_validate(board.model_dump())
    return GraphState(snapshot=snapshot, board=board, proposals=proposals)
#endregion Fixtures / helpers


#region gate_agent_node
@pytest.mark.asyncio
async def test_gate_agent_proposes_assignment_for_landed_flight_without_gate():
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.LANDED, assigned_gate=None)},
        gates={"G1": make_gate("G1")},
    )
    result = await gate_agent_node(state)

    proposals = result["proposals"]
    assert len(proposals) == 1
    assert isinstance(proposals[0], GateAssignmentProposal)
    assert proposals[0].flight_id == "AI101"
    assert proposals[0].proposed_gate_id == "G1"
    assert proposals[0].agent_id == "gate_agent"


@pytest.mark.asyncio
async def test_gate_agent_skips_flight_that_already_has_a_gate():
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.LANDED, assigned_gate="G1")},
        gates={"G1": make_gate("G1")},
    )
    result = await gate_agent_node(state)
    assert result["proposals"] == []


@pytest.mark.asyncio
async def test_gate_agent_skips_flight_not_yet_landed():
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.IN_AIR, assigned_gate=None)},
        gates={"G1": make_gate("G1")},
    )
    result = await gate_agent_node(state)
    assert result["proposals"] == []


@pytest.mark.asyncio
async def test_gate_agent_proposes_none_when_no_gate_open():
    """
    EDITED (bug fix, matches the fix in agents/gate_agent.py): this used
    to be test_gate_agent_no_proposal_when_no_gate_open and asserted
    result["proposals"] == []. That was testing the OLD, buggy behavior:
    total gate scarcity was silently invisible, no proposal, no Conflict,
    no decision_log entry. The fix makes gate_agent ALWAYS propose when a
    flight needs a gate, with proposed_gate_id=None representing "nothing
    available", so Orchestrator can raise a visible, unresolved Conflict
    instead of the flight just sitting there with no trace of why.
    """
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.LANDED, assigned_gate=None)},
        gates={"G1": make_gate("G1", status=GateStatus.OCCUPIED)},
    )
    result = await gate_agent_node(state)

    proposals = result["proposals"]
    assert len(proposals) == 1
    assert proposals[0].flight_id == "AI101"
    assert proposals[0].proposed_gate_id is None
#endregion gate_agent_node


#region crew_agent_node
@pytest.mark.asyncio
async def test_crew_agent_proposes_assignment_for_at_gate_flight_without_crew():
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.AT_GATE, assigned_crew=[])},
        crew={"C1": make_crew("C1", CrewRole.BAGGAGE)},
    )
    result = await crew_agent_node(state)

    proposals = result["proposals"]
    assert len(proposals) == 1
    assert isinstance(proposals[0], CrewAssignmentProposal)
    assert proposals[0].flight_id == "AI101"
    assert "C1" in proposals[0].proposed_crew_ids


@pytest.mark.asyncio
async def test_crew_agent_skips_flight_that_already_has_crew():
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.AT_GATE, assigned_crew=["C1"])},
        crew={"C1": make_crew("C1", CrewRole.BAGGAGE)},
    )
    result = await crew_agent_node(state)
    assert result["proposals"] == []


@pytest.mark.asyncio
async def test_crew_agent_skips_flight_not_yet_at_gate():
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.LANDED, assigned_crew=[])},
        crew={"C1": make_crew("C1", CrewRole.BAGGAGE)},
    )
    result = await crew_agent_node(state)
    assert result["proposals"] == []


@pytest.mark.asyncio
async def test_crew_agent_proposes_empty_list_when_no_eligible_crew():
    """
    NEW (matches the fix in agents/crew_agent.py): confirms crew_agent now
    still emits a proposal (with an empty proposed_crew_ids) when nothing
    is eligible, rather than silently skipping, so Orchestrator's existing
    "no unclaimed crew remained" Conflict logic actually gets a chance to
    fire for total scarcity, not just head-to-head contention.
    """
    state = make_snapshot_state(
        flights={"AI101": make_flight(status=FlightStatus.AT_GATE, assigned_crew=[])},
        crew={"C1": make_crew("C1", CrewRole.BAGGAGE, available=False)},
    )
    result = await crew_agent_node(state)

    proposals = result["proposals"]
    assert len(proposals) == 1
    assert proposals[0].flight_id == "AI101"
    assert proposals[0].proposed_crew_ids == []
#endregion crew_agent_node


#region ats_agent_node
@pytest.mark.asyncio
async def test_ats_agent_flags_wide_body_landed_flight_as_delay_risk():
    state = make_snapshot_state(
        flights={"AI101": make_flight(aircraft_type=AircraftType.WIDE_BODY, status=FlightStatus.LANDED)}
    )
    result = await ats_agent_node(state)

    proposals = result["proposals"]
    assert len(proposals) == 1
    assert isinstance(proposals[0], ScheduleUpdateProposal)
    assert proposals[0].delay_risk_flag is True
    assert proposals[0].flight_id == "AI101"


@pytest.mark.asyncio
async def test_ats_agent_no_proposal_for_narrow_body_landed_on_time():
    state = make_snapshot_state(
        flights={"AI101": make_flight(aircraft_type=AircraftType.NARROW_BODY, status=FlightStatus.LANDED)}
    )
    result = await ats_agent_node(state)
    assert result["proposals"] == []


@pytest.mark.asyncio
async def test_ats_agent_ignores_terminal_status_flights():
    state = make_snapshot_state(
        flights={
            "AI101": make_flight(aircraft_type=AircraftType.WIDE_BODY, status=FlightStatus.DEPARTED),
            "AI102": make_flight(flight_id="AI102", aircraft_type=AircraftType.WIDE_BODY, status=FlightStatus.CANCELLED),
        }
    )
    result = await ats_agent_node(state)
    assert result["proposals"] == []


@pytest.mark.asyncio
async def test_ats_agent_does_not_reflag_a_flight_already_flagged():
    """
    NEW (matches the fix in agents/ats_agent.py): a flight that already
    has a delay_risk_flagged entry in decision_log must not be proposed
    again. This is what fixes the real-run flooding issue where the same
    handful of flights got re-flagged on every single tick for their
    entire remaining lifecycle.
    """
    board = AirportStatus(
        current_tick=5,
        flights={"AI101": make_flight(aircraft_type=AircraftType.WIDE_BODY, status=FlightStatus.LANDED)},
        decision_log=[
            {
                "tick": 3,
                "agent_id": "ats_agent",
                "action": "delay_risk_flagged",
                "detail": "already flagged earlier",
                "affected_flights": ["AI101"],
            }
        ],
    )
    state = GraphState(snapshot=board, board=Blackboard(), proposals=[])

    result = await ats_agent_node(state)

    assert result["proposals"] == []
#endregion ats_agent_node


#region disruption_agent_node
@pytest.mark.asyncio
async def test_disruption_agent_reemits_unresolved_disruptions(monkeypatch):
    async def fake_priority(disruption: DisruptionEvent) -> str:
        return f"Priority reasoning for {disruption.event_id}"

    monkeypatch.setattr(disruption_agent_module, "decide_disruption_priority", fake_priority)

    state = make_snapshot_state(open_disruptions=[make_disruption("DIS1", resolved=False)])
    result = await disruption_agent_node(state)

    proposals = result["proposals"]
    assert len(proposals) == 1
    assert isinstance(proposals[0], DisruptionInjectionProposal)
    assert proposals[0].disruption_event.event_id == "DIS1"
    assert proposals[0].reasoning == "Priority reasoning for DIS1"


@pytest.mark.asyncio
async def test_disruption_agent_skips_already_resolved_disruptions(monkeypatch):
    async def fake_priority(disruption: DisruptionEvent) -> str:
        raise AssertionError("should not be called for an already-resolved disruption")

    monkeypatch.setattr(disruption_agent_module, "decide_disruption_priority", fake_priority)

    state = make_snapshot_state(open_disruptions=[make_disruption("DIS1", resolved=True)])
    result = await disruption_agent_node(state)

    assert result["proposals"] == []
#endregion disruption_agent_node


#region orchestrator_node -- gate conflict resolution
@pytest.mark.asyncio
async def test_orchestrator_applies_uncontested_gate_proposal():
    board = Blackboard()
    board.flights["AI101"] = make_flight(status=FlightStatus.LANDED)
    board.gates["G1"] = make_gate("G1")
    proposal = GateAssignmentProposal(agent_id="gate_agent", tick=1, reasoning="only option", flight_id="AI101", proposed_gate_id="G1")

    await orchestrator_node(make_board_state(board, [proposal]))

    assert board.flights["AI101"].assigned_gate == "G1"
    assert board.gates["G1"].assigned_flight == "AI101"
    assert board.gates["G1"].gate_status == GateStatus.OCCUPIED
    assert board.open_conflicts == []
    assert any(e.action == "gate_assignment" for e in board.decision_log)


@pytest.mark.asyncio
async def test_orchestrator_resolves_competing_gate_proposals_via_llm(monkeypatch):
    board = Blackboard()
    board.flights["AI101"] = make_flight("AI101", status=FlightStatus.LANDED)
    board.flights["AI102"] = make_flight("AI102", status=FlightStatus.LANDED)
    board.gates["G1"] = make_gate("G1")

    p1 = GateAssignmentProposal(agent_id="gate_agent", tick=1, reasoning="r1", flight_id="AI101", proposed_gate_id="G1")
    p2 = GateAssignmentProposal(agent_id="gate_agent", tick=1, reasoning="r2", flight_id="AI102", proposed_gate_id="G1")

    async def fake_resolve(competing):
        # Deterministically pick the proposal for AI102 as the winner.
        return next(p for p in competing if p.flight_id == "AI102")

    monkeypatch.setattr(orchestrator_module, "decide_conflict_resolution", fake_resolve)

    await orchestrator_node(make_board_state(board, [p1, p2]))

    assert board.flights["AI102"].assigned_gate == "G1"
    assert board.flights["AI101"].assigned_gate is None
    assert len(board.open_conflicts) == 1
    assert board.open_conflicts[0].resolved is True
    assert set(board.open_conflicts[0].affected_flights) == {"AI101", "AI102"}
    assert any(e.action == "conflict_resolved" for e in board.decision_log)


@pytest.mark.asyncio
async def test_orchestrator_raises_unresolved_conflict_when_gate_agent_finds_none(monkeypatch):
    """
    NEW: covers the proposed_gate_id=None path in
    agents/orchestrator.py's _apply_gate_proposals, added alongside the
    gate_agent.py fix. Must not be grouped with other None-valued
    proposals as if they were "competing for gate None" with each other.
    """
    board = Blackboard()
    board.flights["AI101"] = make_flight(status=FlightStatus.LANDED)
    proposal = GateAssignmentProposal(
        agent_id="gate_agent", tick=1, reasoning="nothing compatible", flight_id="AI101", proposed_gate_id=None
    )

    await orchestrator_node(make_board_state(board, [proposal]))

    assert board.flights["AI101"].assigned_gate is None
    assert len(board.open_conflicts) == 1
    assert board.open_conflicts[0].resolved is False
    assert any(e.action == "gate_unavailable" for e in board.decision_log)
#endregion orchestrator_node -- gate conflict resolution


#region orchestrator_node -- crew conflict resolution
@pytest.mark.asyncio
async def test_orchestrator_applies_uncontested_crew_proposal():
    board = Blackboard()
    board.flights["AI101"] = make_flight(status=FlightStatus.AT_GATE)
    board.crew["C1"] = make_crew("C1", CrewRole.BAGGAGE)
    proposal = CrewAssignmentProposal(agent_id="crew_agent", tick=1, reasoning="only option", flight_id="AI101", proposed_crew_ids=["C1"])

    await orchestrator_node(make_board_state(board, [proposal]))

    assert board.flights["AI101"].assigned_crew == ["C1"]
    assert board.crew["C1"].assigned_flight == "AI101"
    assert board.crew["C1"].available is False


@pytest.mark.asyncio
async def test_orchestrator_resolves_contested_crew_member_via_llm(monkeypatch):
    board = Blackboard()
    board.flights["AI101"] = make_flight("AI101", status=FlightStatus.AT_GATE)
    board.flights["AI102"] = make_flight("AI102", status=FlightStatus.AT_GATE)
    board.crew["C1"] = make_crew("C1", CrewRole.BAGGAGE)

    p1 = CrewAssignmentProposal(agent_id="crew_agent", tick=1, reasoning="r1", flight_id="AI101", proposed_crew_ids=["C1"])
    p2 = CrewAssignmentProposal(agent_id="crew_agent", tick=1, reasoning="r2", flight_id="AI102", proposed_crew_ids=["C1"])

    async def fake_resolve(competing):
        return next(p for p in competing if p.flight_id == "AI102")

    monkeypatch.setattr(orchestrator_module, "decide_conflict_resolution", fake_resolve)

    await orchestrator_node(make_board_state(board, [p1, p2]))

    assert board.flights["AI102"].assigned_crew == ["C1"]
    assert board.flights["AI101"].assigned_crew == []
    assert board.crew["C1"].assigned_flight == "AI102"
    assert any(
        c.conflict_description.startswith("Crew member C1") and c.resolved
        for c in board.open_conflicts
    )


@pytest.mark.asyncio
async def test_orchestrator_raises_unresolved_conflict_when_no_crew_left():
    board = Blackboard()
    board.flights["AI101"] = make_flight(status=FlightStatus.AT_GATE)
    # No crew on the board at all -- proposal references a crew_id that doesn't exist.
    proposal = CrewAssignmentProposal(agent_id="crew_agent", tick=1, reasoning="wanted C1", flight_id="AI101", proposed_crew_ids=[])

    await orchestrator_node(make_board_state(board, [proposal]))

    assert board.flights["AI101"].assigned_crew == []
    assert len(board.open_conflicts) == 1
    assert board.open_conflicts[0].resolved is False
#endregion orchestrator_node -- crew conflict resolution


#region orchestrator_node -- schedule updates and disruptions
@pytest.mark.asyncio
async def test_orchestrator_applies_schedule_update_and_logs_delay_risk():
    board = Blackboard()
    board.flights["AI101"] = make_flight(status=FlightStatus.IN_AIR)
    proposal = ScheduleUpdateProposal(
        agent_id="ats_agent", tick=1, reasoning="running behind", flight_id="AI101", delay_risk_flag=True
    )

    await orchestrator_node(make_board_state(board, [proposal]))

    assert any(e.action == "delay_risk_flagged" for e in board.decision_log)


@pytest.mark.asyncio
async def test_orchestrator_marks_disruption_resolved_once_all_affected_flights_have_gates():
    board = Blackboard()
    board.flights["AI101"] = make_flight(status=FlightStatus.AT_GATE, assigned_gate="G1")
    board.open_disruptions.append(make_disruption("DIS1", affected_flights=["AI101"]))
    proposal = DisruptionInjectionProposal(
        agent_id="disruption_agent", tick=1, reasoning="still tracking", disruption_event=board.open_disruptions[0]
    )

    await orchestrator_node(make_board_state(board, [proposal]))

    assert board.open_disruptions[0].resolved is True
    assert any(e.action == "disruption_resolved" for e in board.decision_log)


@pytest.mark.asyncio
async def test_orchestrator_keeps_disruption_open_while_a_flight_has_no_gate():
    board = Blackboard()
    board.flights["AI101"] = make_flight(status=FlightStatus.LANDED, assigned_gate=None)
    board.open_disruptions.append(make_disruption("DIS1", affected_flights=["AI101"]))
    proposal = DisruptionInjectionProposal(
        agent_id="disruption_agent", tick=1, reasoning="still tracking", disruption_event=board.open_disruptions[0]
    )

    await orchestrator_node(make_board_state(board, [proposal]))

    assert board.open_disruptions[0].resolved is False
    assert any(e.action == "disruption_monitored" for e in board.decision_log)
#endregion orchestrator_node -- schedule updates and disruptions
