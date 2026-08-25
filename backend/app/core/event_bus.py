import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from pydantic import BaseModel, Field, PrivateAttr

# Import your existing models
from app.core.models import AirportStatus, DecisionLogEntry


class Event(BaseModel):
    """
    The standardized payload for any message passed across the event bus.
    """
    event_type: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """
    An asynchronous Publish-Subscribe message broker.

    Kept alongside Blackboard deliberately, not as a redundant second
    source of truth, but as the decoupled notification layer:
    Blackboard/AirportStatus is the single source of truth for actual
    state, EventBus is how agents and the frontend get notified that
    something happened without needing direct references to each other.
    """

    def __init__(self):
        # defaultdict automatically creates a new empty list if the event_type key doesn't exist
        self._subscribers: dict[str, list[Callable[[Event], Awaitable[None]]]] = defaultdict(list)
        # Internal log for the history method
        self._event_history: list[Event] = []

    def subscribe(self, event_type: str, handler: Callable[[Event], Awaitable[None]]) -> None:
        """
        Registers an async handler function to listen for a specific event type.
        """
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        """
        Records the event to history and broadcasts it concurrently to all subscribers.
        """
        self._event_history.append(event)

        # Uses .get() instead of indexing the defaultdict directly, indexing would
        # silently create an empty list entry for every event type ever published,
        # even ones with zero subscribers.
        handlers = self._subscribers.get(event.event_type)
        if handlers:
            await asyncio.gather(*(handler(event) for handler in handlers))

    def history(self, event_type: str | None = None) -> list[Event]:
        """
        Returns the history of published events.
        Can be filtered by a specific event_type.
        """
        if event_type:
            return [e for e in self._event_history if e.event_type == event_type]
        return self._event_history


class Blackboard(AirportStatus):
    """
    Wraps the core AirportStatus Pydantic model to add specific
    business logic methods required by the simulation engine.

    CONCURRENCY FIX: the project now runs agent nodes as async, and
    multiple agents can be scheduled concurrently (e.g. via
    asyncio.gather when Orchestrator fans out re-evaluation to Gate,
    Crew, and ATS agents at once). Without synchronization, two
    coroutines mutating this same object in the same tick (e.g. two
    agents both appending to decision_log, or both writing to
    self.gates) can interleave and corrupt state, a real race
    condition, not a hypothetical one, once concurrent execution is
    in play. `_lock` gives every mutation a single point of
    serialization.

    Any agent code that mutates Blackboard fields directly (not just
    through log_decision) should acquire `_lock` for the duration of
    that mutation:

        async with board.lock:
            board.gates[gate_id].gate_status = GateStatus.OCCUPIED
    """

    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    async def log_decision(
        self,
        agent_id: str,
        action: str,
        detail: str,
        affected_flights: list[str] | None = None,
    ) -> None:
        """
        Helper method to standardize how agents append to the decision log.
        Now async and lock-protected, matching the project's async agent
        architecture and preventing concurrent-write corruption of
        decision_log when multiple agents log in the same tick.
        """
        entry = DecisionLogEntry(
            tick=self.current_tick,
            agent_id=agent_id,
            action=action,
            detail=detail,
            affected_flights=affected_flights or []
        )
        async with self._lock:
            self.decision_log.append(entry)


# Module-level shared singletons
bus = EventBus()
board = Blackboard()