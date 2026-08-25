"""
NEW FILE — added for manual/automatic tick control.

Wraps a Simulator with pacing control: "auto" mode ticks on a fixed
real-world interval exactly like the original single loop in main.py did;
"manual" mode ticks only when request_step() is called externally (e.g.
from a REST endpoint driven by a frontend "Step" button).

Deliberately kept separate from FastAPI/main.py and from Simulator itself,
same reasoning as Simulator's own on_tick injection: this class only knows
about asyncio and Simulator, nothing about HTTP. That keeps it unit-testable
in isolation (feed it a Simulator + a fake clock, assert tick counts) the
same way core/simulator.py already is.

Concurrency note: a single asyncio.Lock guards each actual tick so that a
manual step() call arriving at the exact moment mode is flipped to "auto"
(or vice versa) can never overlap with the loop's own tick and cause two
ticks to race on the same Blackboard write.
"""

import asyncio
import logging
from typing import Literal

from app.core.simulator import Simulator

logger = logging.getLogger("airport_ops.sim_controller")

SimMode = Literal["auto", "manual"]


class SimulationController:
    def __init__(self, simulator: Simulator, tick_interval_seconds: float) -> None:
        self.simulator = simulator
        self.tick_interval_seconds = tick_interval_seconds
        self.mode: SimMode = "auto"
        self.stopped = False  # set True if a tick raises, mirrors the old loop's "halt on failure" behavior

        self._tick_lock = asyncio.Lock()
        self._step_event = asyncio.Event()

    def set_mode(self, mode: SimMode) -> None:
        if mode not in ("auto", "manual"):
            raise ValueError(f"mode must be 'auto' or 'manual', got {mode!r}")
        self.mode = mode
        if mode == "auto":
            # Wake the loop immediately if it's currently blocked waiting
            # for a manual step -- otherwise switching back to auto would
            # silently do nothing until someone happened to call step()
            # one more time. run_forever() checks self.mode again right
            # after waking and will NOT double-tick; see there for why.
            self._step_event.set()

    def request_step(self) -> None:
        """Fire one tick. Only meaningful in manual mode; a no-op signal in
        auto mode since the loop isn't waiting on this event there anyway."""
        self._step_event.set()

    async def _tick_once(self) -> None:
        async with self._tick_lock:
            try:
                await self.simulator.run_tick()
            except Exception:
                logger.exception("Simulator tick failed -- halting simulation loop.")
                self.stopped = True
                raise

    async def run_forever(self) -> None:
        """
        Background task body. Mirrors the original main.py loop's
        "log loudly and stop, don't retry silently" behavior (Decision
        #32) -- a tick failure propagates out of this coroutine and the
        asyncio.Task simply ends; main.py's shutdown handling already
        awaits/cancels this task cleanly either way.
        """
        while True:
            if self.mode == "auto":
                await self._tick_once()
                await asyncio.sleep(self.tick_interval_seconds)
            else:
                await self._step_event.wait()
                self._step_event.clear()
                # Only tick if we're still in manual mode after waking --
                # set_mode("auto") also sets this same event to unblock us,
                # and in that case we want to fall through to the top of
                # the loop and let the "auto" branch take over cleanly on
                # the next iteration, not sneak in an extra manual tick.
                if self.mode == "manual":
                    await self._tick_once()
