#region Imports
import asyncio
from datetime import datetime, timedelta
from typing import Callable, Awaitable

from app.core.event_bus import Blackboard, EventBus, Event
from app.core.models import Flight, FlightStatus, Gate, GateStatus, CrewMember, DisruptionEvent
#endregion Imports


class Simulator:
    """
    Owns the simulation's "world clock": the ground-truth progression of
    time and the physical facts that follow from it (a flight lands when
    its scheduled/actual arrival time arrives, a scripted disruption fires
    when its trigger_time arrives). This is deliberately separate from
    agent decision-making: the Simulator decides *what happens in the
    world*, agents decide *how to respond to it*.

    This keeps the single-writer principle (Decision #19) intact without
    contradiction: Simulator is the sole writer of world-clock-driven state
    (flight.status transitions, injecting scheduled disruptions) during its
    own sequential phase each tick, before agents ever run. Orchestrator
    remains the sole writer of decision-driven state (gate/crew
    assignments, conflict resolution) during the concurrent agent-execution
    phase that follows. The two phases don't overlap in time, so there is
    no contention between them, board.lock is still used defensively on
    Simulator's own writes for consistency and because bus subscribers may
    read board state concurrently with simulator writes.

    EDITED (bug fix): on READY_FOR_PUSHBACK -> DEPARTED, this class now
    frees BOTH the departed flight's gate and its assigned crew members
    (crew_member.available = True, assigned_flight = None) back to the
    pool. Previously only the gate was freed; crew was never released
    anywhere, so the crew roster monotonically exhausted over a run and
    later flights raised spurious "no crew available" conflicts. This was
    flagged in data/seed_crew.py's own docstring as a known, deliberately
    unfixed gap -- it's fixed here now, in the same block that already
    frees the gate, since both follow directly from time/status the same
    way.
    """

    def __init__(
        self,
        board: Blackboard,
        bus: EventBus,
        tick_duration_minutes: int = 5,
        on_tick: Callable[[Blackboard], Awaitable[None]] | None = None,
    ) -> None:
        """
        board: the shared Blackboard instance this simulator advances.
        bus: the shared EventBus instance, used to publish world-clock
            events (e.g. "flight_landed", "disruption_triggered") so
            agents/frontend can react without polling board state directly.
        tick_duration_minutes: how much simulated time one tick represents.
        on_tick: an async callback invoked once per tick, AFTER the
            world-clock phase and BEFORE the tick is considered complete.
            This is the hook where the compiled LangGraph agent graph gets
            invoked later. Deliberately injected rather than imported
            directly, so this file has zero dependency on agents/graph.py
            and can be built, run, and tested in complete isolation before
            a single agent exists. Wire the real graph in by passing it
            here once it's built, e.g. on_tick=compiled_graph.ainvoke.
        """
        self.board = board
        self.bus = bus
        self.tick_duration = timedelta(minutes=tick_duration_minutes)
        self.on_tick = on_tick

        # Sim clock is derived from the earliest scheduled flight once
        # flights are loaded, not hardcoded, so this simulator carries no
        # built-in assumption about what day/time a scenario starts, this
        # matters for plugging in real schedules later, which won't
        # necessarily start at a fixed mock timestamp.
        self.sim_time: datetime | None = None

        # Disruptions are staged here until their trigger_time arrives,
        # then moved into board.open_disruptions. Keeping them separate
        # from board.open_disruptions until trigger time is what makes
        # scripted, time-based disruption injection possible at all.
        self._pending_disruptions: list[DisruptionEvent] = []

    #region Setup
    def load_flights(self, flights: list[Flight]) -> None:
        """
        Seeds the board with the initial flight schedule and sets the
        simulation clock's start time to the earliest scheduled arrival
        across the loaded set.
        """
        for flight in flights:
            self.board.flights[flight.flight_id] = flight

        if flights:
            earliest = min(f.scheduled_arrival for f in flights)
            if self.sim_time is None or earliest < self.sim_time:
                self.sim_time = earliest

    def load_disruptions(self, disruptions: list[DisruptionEvent]) -> None:
        """
        Stages scripted disruptions to be injected once sim_time reaches
        each one's trigger_time. Kept sorted so _inject_due_disruptions
        doesn't need to re-sort every tick.
        """
        self._pending_disruptions.extend(disruptions)
        self._pending_disruptions.sort(key=lambda d: d.trigger_time)

    def load_gates(self, gates: list[Gate]) -> None:
        """
        Seeds the board with the airport's gate inventory. Unlike flights
        and disruptions, gates don't affect sim_time (they're static
        infrastructure, not schedule data), this is a straight load.

        NOTE: without this being called, board.gates stays an empty dict
        and gate_agent's `available_gates` list is permanently empty --
        every landed flight will stall at LANDED forever with no gate to
        move to, since Simulator's own world-clock only advances
        LANDED -> AT_GATE once `flight.assigned_gate` is set by an agent
        (see _advance_flight_statuses), and an agent can't assign a gate
        that was never loaded.
        """
        for gate in gates:
            self.board.gates[gate.gate_id] = gate

    def load_crew(self, crew: list[CrewMember]) -> None:
        """
        Seeds the board with the ground crew roster. Same rationale as
        load_gates: without this, board.crew stays empty and crew_agent
        can never propose a crew assignment for any flight that reaches
        AT_GATE.
        """
        for member in crew:
            self.board.crew[member.crew_id] = member
    #endregion Setup

    #region World clock
    async def _advance_flight_statuses(self) -> None:
        """
        Ground-truth physical progression: moves each flight through its
        lifecycle based on where sim_time sits relative to its scheduled
        times. This does not touch gate/crew assignment (that is agent/
        Orchestrator territory), only the flight's own status field and
        the bookkeeping (actual_arrival/actual_departure, freeing a gate
        on departure) that necessarily follows from time passing.
        """
        for flight in self.board.flights.values():
            if flight.status == FlightStatus.CANCELLED:
                continue  # cancelled flights are frozen, no further world-clock progression

            if flight.status == FlightStatus.SCHEDULED and self.sim_time >= flight.scheduled_arrival:
                async with self.board.lock:
                    flight.status = FlightStatus.IN_AIR
                await self.bus.publish(Event(
                    event_type="flight_departed_origin",
                    source="simulator",
                    payload={"flight_id": flight.flight_id, "tick": self.board.current_tick},
                ))

            elif flight.status == FlightStatus.IN_AIR and self.sim_time >= flight.scheduled_arrival + timedelta(minutes=10):
                # Fixed 10-minute taxi/landing buffer after scheduled arrival.
                # A real ADS-B/telemetry feed would replace this fixed-offset
                # assumption with an actual observed landing event instead.
                async with self.board.lock:
                    flight.status = FlightStatus.LANDED
                    if flight.actual_arrival is None:
                        flight.actual_arrival = self.sim_time
                await self.bus.publish(Event(
                    event_type="flight_landed",
                    source="simulator",
                    payload={"flight_id": flight.flight_id, "tick": self.board.current_tick},
                ))

            elif flight.status == FlightStatus.LANDED and flight.assigned_gate is not None:
                # Only advances to AT_GATE once an agent has actually assigned
                # a gate, this is the deliberate handoff point from
                # world-clock-driven state to agent-decision-driven state.
                async with self.board.lock:
                    flight.status = FlightStatus.AT_GATE

            elif flight.status == FlightStatus.AT_GATE and self.sim_time >= flight.scheduled_departure:
                async with self.board.lock:
                    flight.status = FlightStatus.READY_FOR_PUSHBACK

            elif flight.status == FlightStatus.READY_FOR_PUSHBACK:
                async with self.board.lock:
                    flight.status = FlightStatus.DEPARTED
                    if flight.actual_departure is None:
                        flight.actual_departure = self.sim_time
                    # Free the gate now that the flight has left, world-clock's
                    # responsibility since it follows directly from time/status,
                    # not a new resource-allocation decision.
                    if flight.assigned_gate and flight.assigned_gate in self.board.gates:
                        self.board.gates[flight.assigned_gate].assigned_flight = None
                        self.board.gates[flight.assigned_gate].gate_status = GateStatus.OPEN
                    # EDITED (bug fix, flagged in data/seed_crew.py's own
                    # docstring): free the crew the same way the gate is
                    # freed above. Previously orchestrator.py's
                    # _apply_crew_proposals set CrewMember.available = False
                    # on assignment with no symmetric release anywhere,
                    # so the roster monotonically exhausted over the course
                    # of a run and every flight after that point raised a
                    # spurious "no crew available" conflict unrelated to
                    # any real scripted shortage.
                    for crew_id in flight.assigned_crew:
                        crew_member = self.board.crew.get(crew_id)
                        if crew_member is not None:
                            crew_member.available = True
                            crew_member.assigned_flight = None
                await self.bus.publish(Event(
                    event_type="flight_departed",
                    source="simulator",
                    payload={"flight_id": flight.flight_id, "tick": self.board.current_tick},
                ))

    async def _inject_due_disruptions(self) -> None:
        """
        Moves any pending scripted disruption whose trigger_time has
        arrived into board.open_disruptions, and publishes an event so
        agents/frontend are notified immediately rather than needing to
        poll for new disruptions.
        """
        due = [d for d in self._pending_disruptions if self.sim_time >= d.trigger_time]
        if not due:
            return

        async with self.board.lock:
            for disruption in due:
                self.board.open_disruptions.append(disruption)
                self._pending_disruptions.remove(disruption)

        for disruption in due:
            await self.bus.publish(Event(
                event_type="disruption_triggered",
                source="simulator",
                payload={"event_id": disruption.event_id, "severity": int(disruption.severity)},
            ))
    #endregion World clock

    #region Tick loop
    async def run_tick(self) -> None:
        """Advances the simulation by exactly one tick."""
        if self.sim_time is None:
            raise RuntimeError("Simulator has no flights loaded, sim_time is unset. Call load_flights() first.")

        # World-clock phase: sequential, Simulator is sole writer here.
        await self._inject_due_disruptions()
        await self._advance_flight_statuses()

        async with self.board.lock:
            self.board.current_tick += 1
        self.sim_time += self.tick_duration

        # Agent-decision phase: delegated entirely to the injected callback.
        # Simulator does not know or care whether this is a LangGraph
        # invocation, a stub, or a test double, that decoupling is the
        # whole point of taking on_tick as a constructor argument instead
        # of importing agents/graph.py directly.
        if self.on_tick is not None:
            await self.on_tick(self.board)

        # EDITED (manual-tick-mode support): publish unconditionally, every
        # tick, regardless of whether anything else happened this tick.
        # Previously the websocket only pushed on flight_departed_origin/
        # flight_landed/flight_departed/disruption_triggered -- a "quiet"
        # tick produced no push at all. That was a known, deliberately
        # deferred gap in auto mode (harmless there, since the next
        # eventful tick arrives within seconds regardless). It stops being
        # optional once a manual "step" control exists: a person stepping
        # one tick at a time needs to see SOMETHING happen on every single
        # step, even a quiet one, or the button looks broken. api/websocket.py
        # subscribes to this event the same way it subscribes to the other 4.
        await self.bus.publish(Event(
            event_type="tick_complete",
            source="simulator",
            payload={"tick": self.board.current_tick, "sim_time": self.sim_time.isoformat()},
        ))

    async def run(self, num_ticks: int) -> None:
        """Runs the simulation forward for a fixed number of ticks."""
        for _ in range(num_ticks):
            await self.run_tick()

    async def run_until(self, stop_time: datetime) -> None:
        """Runs the simulation forward until sim_time reaches stop_time."""
        if self.sim_time is None:
            raise RuntimeError("Simulator has no flights loaded, sim_time is unset. Call load_flights() first.")
        while self.sim_time < stop_time:
            await self.run_tick()
    #endregion Tick loop