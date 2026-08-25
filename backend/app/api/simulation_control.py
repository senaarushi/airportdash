"""
NEW FILE — REST control surface for manual/auto tick mode.

Deliberately kept SEPARATE from api/routes.py: routes.py's own docstring
states it "never mutates the Blackboard" and is purely read-only, which is
still true of every endpoint there. These endpoints don't mutate the
Blackboard directly either, but they do mutate simulator control state
(SimulationController.mode) and can trigger a tick indirectly (which in
turn mutates the Blackboard through Simulator/Orchestrator, same as it
always did) -- different enough a contract that it earns its own file
and its own /api/simulation prefix rather than quietly breaking
routes.py's stated invariant.

Reaches the running SimulationController via app.state.sim_controller,
set up in main.py's lifespan(). Uses FastAPI's Request to get at
request.app.state rather than a module-level import, since the
controller instance doesn't exist until lifespan() constructs it at
startup -- there's nothing importable at module-load time here.
"""

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import SimulationModeRequest, SimulationModeResponse
from app.core.event_bus import board

router = APIRouter()


@router.get("/mode", response_model=SimulationModeResponse)
async def get_mode(request: Request) -> SimulationModeResponse:
    """Current tick mode, for the frontend to sync to on load/reconnect."""
    controller = request.app.state.sim_controller
    return SimulationModeResponse(mode=controller.mode, current_tick=board.current_tick)


@router.post("/mode", response_model=SimulationModeResponse)
async def set_mode(body: SimulationModeRequest, request: Request) -> SimulationModeResponse:
    """Switch between 'auto' (fixed-interval ticking, the original
    behavior) and 'manual' (ticks only on explicit /step calls)."""
    controller = request.app.state.sim_controller
    if controller.stopped:
        raise HTTPException(
            status_code=409,
            detail="Simulation has already halted after a tick failure -- see server logs. Restart the server to recover.",
        )
    controller.set_mode(body.mode)
    return SimulationModeResponse(mode=controller.mode, current_tick=board.current_tick)


@router.post("/step", response_model=SimulationModeResponse)
async def step(request: Request) -> SimulationModeResponse:
    """
    Fire exactly one tick. Only meaningful in manual mode -- returns 409
    if called while in auto mode, since auto mode is already ticking on
    its own timer and a manual step request would just be redundant/
    confusing rather than doing anything different.

    This returns immediately after SIGNALING the step, not after the tick
    has actually finished executing (the tick itself runs inside
    SimulationController.run_forever()'s own background task). The
    frontend finds out the tick actually completed via the websocket's
    tick_complete-triggered push, same as every other state change.
    """
    controller = request.app.state.sim_controller
    if controller.stopped:
        raise HTTPException(
            status_code=409,
            detail="Simulation has already halted after a tick failure -- see server logs. Restart the server to recover.",
        )
    if controller.mode != "manual":
        raise HTTPException(status_code=409, detail="Switch to manual mode before stepping.")
    controller.request_step()
    return SimulationModeResponse(mode=controller.mode, current_tick=board.current_tick)
