"""
Tests for decisions/*.py -- the swappable rule-based/ML/LLM decision layer
(Decision #5/#6). Each decision function is tested in complete isolation
from its agent shell, matching the architecture's own separation: these
tests would need zero changes if a decisions/*.py file were later swapped
for an ML-based implementation with the same signature.

gate_decisions.py, crew_decisions.py, and ats_decisions.py are pure/rule-
based and exercised directly, no mocking needed.

disruption_decisions.py and orchestrator_decisions.py wrap a real
ChatAnthropic call. Rather than hitting the network (slow, flaky, costs
money, and requires ANTHROPIC_API_KEY), the module-level `_structured_llm`
singleton in each file is monkeypatched with a stub that returns a
controlled structured-output object or raises, so both the happy path and
the "never let an LLM failure crash the tick" fallback path (Decision #31)
are exercised deterministically.

Requires pytest and pytest-asyncio (already added to requirements.txt).
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.models import (
    AircraftType,
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
from app.core.proposals import GateAssignmentProposal
from app.decisions.gate_decisions import decide_gate_assignment
from app.decisions.crew_decisions import decide_crew_assignment
from app.decisions.ats_decisions import decide_delay_risk
import app.decisions.disruption_decisions as disruption_decisions
import app.decisions.orchestrator_decisions as orchestrator_decisions
from app.decisions.disruption_decisions import decide_disruption_priority, _PriorityAssessment
from app.decisions.orchestrator_decisions import decide_conflict_resolution, _ResolutionChoice


BASE_TIME = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


#region Fixtures / helpers
def make_flight(
    flight_id: str = "AI101",
    aircraft_type: AircraftType = AircraftType.NARROW_BODY,
    status: FlightStatus = FlightStatus.LANDED,
    turnaround_time: int = 45,
    arrival_offset_min: int = 0,
    actual_arrival_offset_min: int | None = None,
) -> Flight:
    arrival = BASE_TIME + timedelta(minutes=arrival_offset_min)
    actual_arrival = (
        BASE_TIME + timedelta(minutes=actual_arrival_offset_min)
        if actual_arrival_offset_min is not None
        else None
    )
    return Flight(
        flight_id=flight_id,
        airline="AI",
        aircraft_type=aircraft_type,
        scheduled_arrival=arrival,
        scheduled_departure=arrival + timedelta(minutes=turnaround_time),
        actual_arrival=actual_arrival,
        status=status,
        turnaround_time=turnaround_time,
    )


def make_gate(gate_id: str, supports_wide_body: bool, status: GateStatus = GateStatus.OPEN) -> Gate:
    return Gate(gate_id=gate_id, supports_wide_body=supports_wide_body, gate_status=status)


def make_crew(
    crew_id: str,
    role: CrewRole,
    available: bool = True,
    shift_minutes_remaining: int = 120,
) -> CrewMember:
    return CrewMember(
        crew_id=crew_id,
        role=role,
        available=available,
        shift_minutes_remaining=shift_minutes_remaining,
    )


def make_disruption(
    event_id: str = "DIS1",
    severity: DisruptionSeverity = DisruptionSeverity.LEVEL_3,
    affected_flights: list[str] | None = None,
) -> DisruptionEvent:
    return DisruptionEvent(
        event_id=event_id,
        disruption_type=DisruptionType.WEATHER,
        trigger_time=BASE_TIME,
        severity=severity,
        disruption_description="Test disruption",
        affected_flights=affected_flights or ["AI101"],
    )


def make_proposal(flight_id: str, gate_id: str, agent_id: str = "gate_agent", tick: int = 1) -> GateAssignmentProposal:
    return GateAssignmentProposal(
        agent_id=agent_id,
        tick=tick,
        reasoning=f"{gate_id} is compatible with {flight_id}.",
        flight_id=flight_id,
        proposed_gate_id=gate_id,
    )


class _StubStructuredLLM:
    """
    Drop-in replacement for `_structured_llm` in disruption_decisions.py /
    orchestrator_decisions.py. Returns a fixed structured-output object, or
    raises a fixed exception, so both the happy path and the fallback path
    can be tested without a real network call.
    """

    def __init__(self, result=None, exc: Exception | None = None):
        self._result = result
        self._exc = exc
        self.calls = 0

    async def ainvoke(self, prompt: str):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result
#endregion Fixtures / helpers


#region gate_decisions.py (rule-based)
def test_gate_assignment_returns_none_when_no_gates_available():
    flight = make_flight(aircraft_type=AircraftType.NARROW_BODY)
    assert decide_gate_assignment(flight, []) is None


def test_wide_body_flight_gets_wide_body_capable_gate():
    flight = make_flight(aircraft_type=AircraftType.WIDE_BODY)
    gates = [make_gate("G1", supports_wide_body=False), make_gate("G2", supports_wide_body=True)]
    assert decide_gate_assignment(flight, gates) == "G2"


def test_wide_body_flight_returns_none_if_no_compatible_gate():
    flight = make_flight(aircraft_type=AircraftType.WIDE_BODY)
    gates = [make_gate("G1", supports_wide_body=False)]
    assert decide_gate_assignment(flight, gates) is None


def test_narrow_body_flight_prefers_narrow_only_gate_over_wide_body_capable():
    flight = make_flight(aircraft_type=AircraftType.NARROW_BODY)
    gates = [make_gate("G1", supports_wide_body=True), make_gate("G2", supports_wide_body=False)]
    # G2 (narrow-only, exact fit) should win over G1, even though G1 is listed first,
    # so a wide-body-capable gate isn't needlessly consumed by a narrow-body flight.
    assert decide_gate_assignment(flight, gates) == "G2"


def test_narrow_body_flight_falls_back_to_wide_body_capable_gate_if_thats_all_thats_open():
    flight = make_flight(aircraft_type=AircraftType.NARROW_BODY)
    gates = [make_gate("G1", supports_wide_body=True)]
    assert decide_gate_assignment(flight, gates) == "G1"
#endregion gate_decisions.py (rule-based)


#region crew_decisions.py (rule-based)
def test_crew_assignment_fills_each_required_role():
    flight = make_flight(turnaround_time=45)
    crew = [
        make_crew("C1", CrewRole.BAGGAGE),
        make_crew("C2", CrewRole.PUSHBACK),
        make_crew("C3", CrewRole.CLEANING),
    ]
    assigned = decide_crew_assignment(flight, crew)
    assert set(assigned) == {"C1", "C2", "C3"}


def test_crew_assignment_skips_role_with_no_eligible_member():
    flight = make_flight(turnaround_time=45)
    crew = [make_crew("C1", CrewRole.BAGGAGE)]  # no PUSHBACK or CLEANING available
    assigned = decide_crew_assignment(flight, crew)
    assert assigned == ["C1"]


def test_crew_assignment_excludes_unavailable_members():
    flight = make_flight(turnaround_time=45)
    crew = [make_crew("C1", CrewRole.BAGGAGE, available=False)]
    assert decide_crew_assignment(flight, crew) == []


def test_crew_assignment_excludes_insufficient_shift_time():
    flight = make_flight(turnaround_time=45)
    crew = [make_crew("C1", CrewRole.BAGGAGE, shift_minutes_remaining=30)]  # < turnaround_time
    assert decide_crew_assignment(flight, crew) == []


def test_crew_assignment_exactly_equal_shift_time_is_eligible():
    flight = make_flight(turnaround_time=45)
    crew = [make_crew("C1", CrewRole.BAGGAGE, shift_minutes_remaining=45)]  # exactly ==
    assert decide_crew_assignment(flight, crew) == ["C1"]


def test_crew_assignment_prefers_member_with_most_shift_time_remaining():
    flight = make_flight(turnaround_time=45)
    crew = [
        make_crew("C1", CrewRole.BAGGAGE, shift_minutes_remaining=50),
        make_crew("C2", CrewRole.BAGGAGE, shift_minutes_remaining=200),
    ]
    assigned = decide_crew_assignment(flight, crew)
    assert assigned == ["C2"]
#endregion crew_decisions.py (rule-based)


#region ats_decisions.py (rule-based)
def test_delay_risk_true_when_flight_is_delayed():
    flight = make_flight(
        aircraft_type=AircraftType.NARROW_BODY,
        status=FlightStatus.AT_GATE,
        arrival_offset_min=0,
        actual_arrival_offset_min=30,  # arrived 30 min later than scheduled -> is_delayed True
    )
    assert decide_delay_risk(flight, current_tick=5) is True


def test_delay_risk_true_for_wide_body_landed_even_if_not_yet_delayed():
    flight = make_flight(aircraft_type=AircraftType.WIDE_BODY, status=FlightStatus.LANDED)
    assert decide_delay_risk(flight, current_tick=1) is True


def test_delay_risk_false_for_narrow_body_landed_not_delayed():
    flight = make_flight(aircraft_type=AircraftType.NARROW_BODY, status=FlightStatus.LANDED)
    assert decide_delay_risk(flight, current_tick=1) is False


def test_delay_risk_false_for_wide_body_not_yet_landed():
    flight = make_flight(aircraft_type=AircraftType.WIDE_BODY, status=FlightStatus.IN_AIR)
    assert decide_delay_risk(flight, current_tick=1) is False
#endregion ats_decisions.py (rule-based)


#region disruption_decisions.py (LLM-based)
@pytest.mark.asyncio
async def test_disruption_priority_returns_llm_reasoning_on_success(monkeypatch):
    stub = _StubStructuredLLM(result=_PriorityAssessment(reasoning="Escalate immediately, 5 flights affected."))
    monkeypatch.setattr(disruption_decisions, "_structured_llm", stub)

    disruption = make_disruption(severity=DisruptionSeverity.LEVEL_4)
    result = await decide_disruption_priority(disruption)

    assert result == "Escalate immediately, 5 flights affected."
    assert stub.calls == 1


@pytest.mark.asyncio
async def test_disruption_priority_falls_back_on_api_failure(monkeypatch):
    stub = _StubStructuredLLM(exc=RuntimeError("connection refused"))
    monkeypatch.setattr(disruption_decisions, "_structured_llm", stub)

    disruption = make_disruption(event_id="DIS-WEATHER-001", severity=DisruptionSeverity.LEVEL_4)
    result = await decide_disruption_priority(disruption)

    # Never raises -- falls back to a deterministic string instead of crashing the tick.
    assert "DIS-WEATHER-001" in result
    assert "unavailable" in result
    assert "RuntimeError" in result
#endregion disruption_decisions.py (LLM-based)


#region orchestrator_decisions.py (LLM-based)
@pytest.mark.asyncio
async def test_conflict_resolution_short_circuits_for_single_proposal(monkeypatch):
    # Must not touch the LLM at all when there's nothing to actually resolve.
    stub = _StubStructuredLLM(exc=AssertionError("LLM should not be called for a single proposal"))
    monkeypatch.setattr(orchestrator_decisions, "_structured_llm", stub)

    only_proposal = make_proposal("AI101", "G1")
    winner = await decide_conflict_resolution([only_proposal])

    assert winner is only_proposal
    assert stub.calls == 0


@pytest.mark.asyncio
async def test_conflict_resolution_returns_chosen_winner_with_llm_reasoning(monkeypatch):
    p1 = make_proposal("AI101", "G1")
    p2 = make_proposal("AI102", "G1")
    stub = _StubStructuredLLM(
        result=_ResolutionChoice(winning_proposal_id=p2.proposal_id, reasoning="AI102 has a tighter connection.")
    )
    monkeypatch.setattr(orchestrator_decisions, "_structured_llm", stub)

    winner = await decide_conflict_resolution([p1, p2])

    assert winner.proposal_id == p2.proposal_id
    assert winner.flight_id == "AI102"
    assert winner.reasoning == "AI102 has a tighter connection."  # replaced with the LLM's own explanation


@pytest.mark.asyncio
async def test_conflict_resolution_falls_back_when_llm_hallucinates_unknown_id(monkeypatch):
    p1 = make_proposal("AI101", "G1")
    p2 = make_proposal("AI102", "G1")
    stub = _StubStructuredLLM(
        result=_ResolutionChoice(winning_proposal_id="not-a-real-proposal-id", reasoning="hallucinated")
    )
    monkeypatch.setattr(orchestrator_decisions, "_structured_llm", stub)

    winner = await decide_conflict_resolution([p1, p2])

    # A hallucinated id must never be trusted -- falls back to the first proposal
    # (matching the old placeholder's behavior) rather than corrupting state.
    assert winner is p1


@pytest.mark.asyncio
async def test_conflict_resolution_falls_back_on_api_failure(monkeypatch):
    p1 = make_proposal("AI101", "G1")
    p2 = make_proposal("AI102", "G1")
    stub = _StubStructuredLLM(exc=RuntimeError("connection refused"))
    monkeypatch.setattr(orchestrator_decisions, "_structured_llm", stub)

    winner = await decide_conflict_resolution([p1, p2])

    assert winner is p1
#endregion orchestrator_decisions.py (LLM-based)