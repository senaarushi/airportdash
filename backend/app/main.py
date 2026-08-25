"""
FastAPI entrypoint. Mounts routes, starts the simulation loop.

Startup sequence (in lifespan()):
  1. Register websocket event subscriptions -- must happen before the
     Simulator starts ticking, or early events fire with nobody listening.
  2. Build the LangGraph agent graph and wrap it as the Simulator's on_tick
     callback (Decision #22/#27 -- this is the ONE place Simulator and the
     agent graph get connected; simulator.py itself has zero import of
     agents/graph.py, by design).
  3. Seed mock flights + disruptions (seed=settings.simulator_seed, matching
     the seed_flights.py / seed_disruptions.py __main__ convention) and load
     them into the Simulator.
  4. Launch the tick loop as a background asyncio task.

Shutdown: cancel that background task cleanly.

EDITED (import-order fix for ANTHROPIC_API_KEY / .env loading): settings
are now loaded and ANTHROPIC_API_KEY is bridged into os.environ at the
VERY TOP of this module, before `app.agents.graph` is imported. Previously
that import (which transitively imports decisions/disruption_decisions.py
and decisions/orchestrator_decisions.py, both of which construct
ChatAnthropic(...) at module import time) ran before lifespan() ever
called get_settings()/sync_anthropic_env(), so .env's ANTHROPIC_API_KEY
was never in the process environment yet when ChatAnthropic() was built --
only a truly ambient shell env var would have worked. The
get_settings()/sync_anthropic_env()/warn_if_api_key_missing() calls that
used to live at the top of lifespan() have been removed from there to
avoid calling them twice; lifespan() still reads `settings = get_settings()`
(cheap, @lru_cache'd, same instance) for the values it needs below.

EDITED (manual/auto tick control): the background task no longer ticks
the Simulator directly in a bare while-loop. It now runs a
core.sim_controller.SimulationController wrapping the Simulator, which
owns whether ticks happen on a fixed interval ("auto", the original
behavior) or only when explicitly requested ("manual", new). Mode is
switched and steps are requested via api/simulation_control.py's REST
endpoints, which reach the controller through app.state.sim_controller.
"""
import sys
import os

# Add the parent directory to sys.path so 'app' can be found on Vercel
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
    
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings, sync_groq_env, warn_if_api_key_missing

# EDITED: settings must be bootstrapped here, before ANY import that
# transitively touches decisions/disruption_decisions.py or
# decisions/orchestrator_decisions.py (both construct ChatAnthropic at
# module import time). app.agents.graph is exactly such an import, so it
# is deliberately kept below this block rather than grouped alphabetically
# with the other imports.
_settings = get_settings()
sync_groq_env(_settings)
warn_if_api_key_missing(_settings)

from app.agents.graph import build_graph, make_tick_handler
from app.api.export import router as export_router
from app.api.routes import router as api_router
from app.api.simulation_control import router as simulation_control_router
from app.api.websocket import register_event_subscriptions
from app.api.websocket import router as websocket_router
from app.core.event_bus import board, bus
from app.core.sim_controller import SimulationController
from app.core.simulator import Simulator
from app.data.seed_crew import generate_mock_crew
from app.data.seed_disruptions import generate_mock_disruptions
from app.data.seed_flights import generate_mock_flights
from app.data.seed_gates import generate_mock_gates

logger = logging.getLogger("airport_ops.main")


async def _run_simulation_loop(controller: SimulationController) -> None:
    """
    EDITED (manual/auto tick control): this now just delegates to
    SimulationController.run_forever(), which owns the actual auto-pacing
    vs manual-step-waiting logic (core/sim_controller.py). Kept as a thin
    wrapper here rather than inlining the call at the create_task() site
    below, so the "what does the background task actually run" question
    has one obvious answer when reading this file top to bottom.
    """
    await controller.run_forever()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # EDITED: get_settings()/sync_anthropic_env()/warn_if_api_key_missing()
    # used to run here. They now run once, earlier, at module import time
    # (see top of file) so ANTHROPIC_API_KEY is in os.environ before the
    # app.agents.graph import below it triggers ChatAnthropic() construction.
    # get_settings() is @lru_cache'd, so this just returns the same instance.
    settings = get_settings()

    register_event_subscriptions()

    compiled_graph = build_graph()
    tick_handler = make_tick_handler(compiled_graph)

    simulator = Simulator(
        board=board,
        bus=bus,
        tick_duration_minutes=settings.simulator_tick_duration_minutes,
        on_tick=tick_handler,
    )
    flights = generate_mock_flights(seed=settings.simulator_seed)
    disruptions = generate_mock_disruptions(flights, seed=settings.simulator_seed)
    gates = generate_mock_gates(seed=settings.simulator_seed)
    crew = generate_mock_crew(seed=settings.simulator_seed)
    simulator.load_flights(flights)
    simulator.load_disruptions(disruptions)
    simulator.load_gates(gates)
    simulator.load_crew(crew)

    app.state.simulator = simulator
    # EDITED (manual/auto tick control): the background task now runs a
    # SimulationController wrapping the simulator, instead of ticking the
    # simulator directly in a bare while-loop. app.state.sim_controller is
    # what api/simulation_control.py's endpoints reach into to flip modes
    # / request a manual step.
    app.state.sim_controller = SimulationController(
        simulator=simulator,
        tick_interval_seconds=settings.tick_interval_seconds,
    )
    app.state.sim_task = asyncio.create_task(
        _run_simulation_loop(app.state.sim_controller)
    )

    yield

    app.state.sim_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app.state.sim_task


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="Airport Ops",
        description="Multi-agent airport operations simulation.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api", tags=["airport-ops"])
    app.include_router(export_router, prefix="/api/export", tags=["export"])
    app.include_router(simulation_control_router, prefix="/api/simulation", tags=["simulation-control"])
    app.include_router(websocket_router)

    @app.get("/")
    async def root() -> dict:
        return {"service": "airport-ops", "docs": "/docs", "websocket": "/ws"}

    return app


app = create_app()