"""
Tests for core/simulator.py.

These tests exercise Simulator entirely on its own, with on_tick either
omitted or replaced with a simple recording stub, deliberately no
dependency on agents/graph.py, matching the isolation Simulator itself
was built for. Requires pytest and pytest-asyncio (add both to
requirements.txt, neither is currently listed).
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.core.event_bus import Blackboard, EventBus
from app.core.models import (
    Flight,
    Gate,
    AircraftType,
    FlightStatus,
    GateStatus,
    DisruptionEvent,
    DisruptionType,
    DisruptionSeverity,
)
from app.core.simulator import Simulator


#region Fixtures / helpers
@pytest.fixture
def board() -> Blackboard:
    # Fresh instance per test, never the module-level singleton, to avoid
    # state leaking between tests.
    return Blackboard()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def make_flight(
    flight_id: str = "AI101",
    arrival_offset_min: int = 0,
    turnaround_time: int = 30,
    base_time: datetime | None = None,
) -> Flight:
    base = base_time or datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    arrival = base + timedelta(minutes=arrival_offset_min)
    return Flight(
        flight_id=flight_id,
        airline="AI",
        aircraft_type=AircraftType.NARROW_BODY,
        scheduled_arrival=arrival,
        scheduled_departure=arrival + timedelta(minutes=turnaround_time),
        turnaround_time=turnaround_time,
    )


def make_disruption(
    event_id: str = "DIS1",
    trigger_offset_min: int = 0,
    base_time: datetime | None = None,
    severity: DisruptionSeverity = DisruptionSeverity.LEVEL_3,
) -> DisruptionEvent:
    base = base_time or datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    return DisruptionEvent(
        event_id=event_id,
        disruption_type=DisruptionType.WEATHER,
        trigger_time=base + timedelta(minutes=trigger_offset_min),
        severity=severity,
        disruption_description="Test disruption",
    )
#endregion Fixtures / helpers


#region Setup behavior
def test_load_flights_sets_sim_time_to_earliest_arrival(board, bus):
    sim = Simulator(board, bus)
    early = make_flight("AI101", arrival_offset_min=30)
    later = make_flight("AI102", arrival_offset_min=90)

    sim.load_flights([later, early])

    assert sim.sim_time == early.scheduled_arrival
    assert "AI101" in board.flights
    assert "AI102" in board.flights


@pytest.mark.asyncio
async def test_run_tick_without_flights_raises(board, bus):
    sim = Simulator(board, bus)
    with pytest.raises(RuntimeError):
        await sim.run_tick()
#endregion Setup behavior


#region Flight lifecycle transitions
@pytest.mark.asyncio
async def test_scheduled_to_in_air_on_first_tick(board, bus):
    flight = make_flight(turnaround_time=30)
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    await sim.run_tick()

    assert board.flights[flight.flight_id].status == FlightStatus.IN_AIR


@pytest.mark.asyncio
async def test_in_air_to_landed_after_taxi_buffer_sets_actual_arrival(board, bus):
    flight = make_flight(turnaround_time=60)
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    # tick 1: SCHEDULED -> IN_AIR (sim_time == scheduled_arrival)
    # tick 2: sim_time == arrival+5, still short of the 10-min buffer, stays IN_AIR
    # tick 3: sim_time == arrival+10, buffer reached, IN_AIR -> LANDED
    for _ in range(3):
        await sim.run_tick()

    updated = board.flights[flight.flight_id]
    assert updated.status == FlightStatus.LANDED
    assert updated.actual_arrival == flight.scheduled_arrival + timedelta(minutes=10)


@pytest.mark.asyncio
async def test_landed_flight_stalls_without_gate_assignment(board, bus):
    flight = make_flight(turnaround_time=60)
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    for _ in range(6):  # well past landing, no agent has assigned a gate
        await sim.run_tick()

    assert board.flights[flight.flight_id].status == FlightStatus.LANDED


@pytest.mark.asyncio
async def test_landed_to_at_gate_once_gate_assigned(board, bus):
    flight = make_flight(turnaround_time=60)
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    for _ in range(3):  # reach LANDED
        await sim.run_tick()
    assert board.flights[flight.flight_id].status == FlightStatus.LANDED

    # Simulate what an agent would do: assign a gate directly on the board.
    board.flights[flight.flight_id].assigned_gate = "G1"

    await sim.run_tick()

    assert board.flights[flight.flight_id].status == FlightStatus.AT_GATE


@pytest.mark.asyncio
async def test_full_lifecycle_to_departed_frees_gate(board, bus):
    flight = make_flight(turnaround_time=20)
    board.gates["G1"] = Gate(gate_id="G1", supports_wide_body=False, gate_status=GateStatus.OCCUPIED, assigned_flight=flight.flight_id)
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    # tick1: SCHEDULED->IN_AIR, tick2: still IN_AIR, tick3: IN_AIR->LANDED (arrival+10)
    for _ in range(3):
        await sim.run_tick()
    board.flights[flight.flight_id].assigned_gate = "G1"

    # tick4: LANDED->AT_GATE (sim_time now arrival+15)
    await sim.run_tick()
    assert board.flights[flight.flight_id].status == FlightStatus.AT_GATE

    # scheduled_departure = arrival + 20min. sim_time after tick4 is arrival+20.
    # tick5: AT_GATE -> READY_FOR_PUSHBACK (sim_time >= scheduled_departure)
    await sim.run_tick()
    assert board.flights[flight.flight_id].status == FlightStatus.READY_FOR_PUSHBACK

    # tick6: READY_FOR_PUSHBACK -> DEPARTED, gate freed, actual_departure set
    await sim.run_tick()
    updated = board.flights[flight.flight_id]
    assert updated.status == FlightStatus.DEPARTED
    assert updated.actual_departure is not None
    assert board.gates["G1"].assigned_flight is None
    assert board.gates["G1"].gate_status == GateStatus.OPEN


@pytest.mark.asyncio
async def test_cancelled_flight_never_progresses(board, bus):
    flight = make_flight(turnaround_time=30)
    flight.status = FlightStatus.CANCELLED
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    for _ in range(10):
        await sim.run_tick()

    assert board.flights[flight.flight_id].status == FlightStatus.CANCELLED
#endregion Flight lifecycle transitions


#region Disruption injection
@pytest.mark.asyncio
async def test_disruption_not_injected_before_trigger_time(board, bus):
    flight = make_flight()
    disruption = make_disruption(trigger_offset_min=60)  # well after sim start
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])
    sim.load_disruptions([disruption])

    await sim.run_tick()

    assert board.open_disruptions == []


@pytest.mark.asyncio
async def test_disruption_injected_once_trigger_time_reached(board, bus):
    flight = make_flight()
    disruption = make_disruption(trigger_offset_min=10)
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])
    sim.load_disruptions([disruption])

    # sim_time starts at flight.scheduled_arrival; trigger is 10 min later.
    # tick1: sim_time == arrival, not due yet. tick2: sim_time == arrival+5, not due.
    # tick3: sim_time == arrival+10, due, injected during this tick's check
    # (check happens against sim_time BEFORE it's advanced for the tick).
    await sim.run_tick()
    await sim.run_tick()
    assert board.open_disruptions == []
    await sim.run_tick()

    assert len(board.open_disruptions) == 1
    assert board.open_disruptions[0].event_id == disruption.event_id

    published = bus.history("disruption_triggered")
    assert len(published) == 1
    assert published[0].payload["event_id"] == disruption.event_id
#endregion Disruption injection


#region Tick loop / on_tick integration
@pytest.mark.asyncio
async def test_on_tick_callback_invoked_each_tick_with_current_board(board, bus):
    calls = []

    async def recorder(b: Blackboard) -> None:
        calls.append(b.current_tick)

    flight = make_flight()
    sim = Simulator(board, bus, tick_duration_minutes=5, on_tick=recorder)
    sim.load_flights([flight])

    await sim.run(3)

    assert calls == [1, 2, 3]  # current_tick is incremented before on_tick fires


@pytest.mark.asyncio
async def test_run_advances_current_tick_by_exactly_num_ticks(board, bus):
    flight = make_flight()
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    await sim.run(4)

    assert board.current_tick == 4


@pytest.mark.asyncio
async def test_run_until_stops_once_sim_time_reaches_target(board, bus):
    flight = make_flight(turnaround_time=30)
    sim = Simulator(board, bus, tick_duration_minutes=5)
    sim.load_flights([flight])

    stop_time = flight.scheduled_arrival + timedelta(minutes=20)
    await sim.run_until(stop_time)

    assert sim.sim_time >= stop_time
#endregion Tick loop / on_tick integration