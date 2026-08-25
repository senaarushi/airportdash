"""
Live push of AirportStatus + decision_log to the frontend over a single
/ws endpoint.

Design: a ConnectionManager tracks connected clients. Whenever the
EventBus fires one of the event types Simulator/Orchestrator already
publish, every connected client gets a fresh FULL-state snapshot -- not
a diff. At this scale (15-20 flights) re-sending the whole AirportStatus
is simpler and cheaper than diffing, and it means a client can never
drift out of sync even if it misses one push.

OPEN ITEM, NOW RESOLVED: core/simulator.py used to only publish
flight_departed_origin, flight_landed, flight_departed, and
disruption_triggered -- a tick where none of those fired produced no
websocket push. core/simulator.py's run_tick() now also publishes a
"tick_complete" event unconditionally at the end of every tick, added
below to _PUSH_TRIGGERING_EVENTS, so this file broadcasts on every tick
regardless of what else happened. This became necessary once manual
step-mode existed (see core/sim_controller.py): a person stepping one
tick at a time needs to see something happen on every step, even a quiet
one.

Wiring: register_event_subscriptions() must be called once at app
startup (from main.py's startup hook), before the Simulator starts
ticking, or early events will fire with nobody subscribed yet.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.schemas import AirportStatusResponse, WebSocketMessage
from app.core.event_bus import Event, board, bus

router = APIRouter()

_PUSH_TRIGGERING_EVENTS = (
    "flight_departed_origin",
    "flight_landed",
    "flight_departed",
    "disruption_triggered",
    "tick_complete",  # EDITED: added so every tick pushes, not just eventful ones
)


class ConnectionManager:
    """Tracks active websocket clients and broadcasts to all of them."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: WebSocketMessage) -> None:
        # Iterate a snapshot of the list: a dead connection disconnecting
        # mid-broadcast must not mutate active_connections while we walk it.
        payload = message.model_dump(mode="json")
        for connection in list(self.active_connections):
            try:
                await connection.send_json(payload)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


async def _broadcast_state(event: Event) -> None:
    """EventBus handler: snapshot the board and push it to every client."""
    async with board.lock:
        snapshot = board.model_dump()
    message = WebSocketMessage(
        type="state_update",
        trigger_event=event.event_type,
        payload=AirportStatusResponse.model_validate(snapshot),
    )
    await manager.broadcast(message)


def register_event_subscriptions() -> None:
    """Call once at startup, before the Simulator begins ticking."""
    for event_type in _PUSH_TRIGGERING_EVENTS:
        bus.subscribe(event_type, _broadcast_state)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        async with board.lock:
            snapshot = board.model_dump()
        await websocket.send_json(
            WebSocketMessage(
                type="connected",
                payload=AirportStatusResponse.model_validate(snapshot),
                detail="Connected to airport-ops live feed.",
            ).model_dump(mode="json")
        )
        while True:
            # This is a push-only feed -- there's no client->server message
            # contract yet. receive_text() just blocks here, keeping the
            # connection open and letting us detect disconnects promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)