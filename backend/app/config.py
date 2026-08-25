"""
App-wide configuration: environment variables, constants, tunables.

Centralizes what Decision Log #32 flagged as a blocker: ANTHROPIC_API_KEY
was being read as a bare ambient env var by decisions/disruption_decisions.py
and decisions/orchestrator_decisions.py (via langchain_anthropic.ChatAnthropic's
own implicit os.environ lookup). This file doesn't change HOW those two
files get their key -- ChatAnthropic still reads ANTHROPIC_API_KEY from the
process environment internally -- but it centralizes WHERE that env var
actually gets populated from (.env or real env), validates it's present at
startup instead of failing silently on the first LLM call, and gives every
other tunable (tick pacing, CORS origins, host/port) one typed source of
truth instead of scattered magic numbers.

`pydantic-settings` is in requirements.txt (already added; an earlier
version of this comment claimed otherwise -- stale, since fixed).

EDITED (two related fixes, both required for ANTHROPIC_API_KEY to
actually reach ChatAnthropic()):
  1. env_file below is now an ABSOLUTE path (BASE_DIR / ".env") instead of
     the relative string ".env". A relative path is resolved against the
     process's current working directory, not this file's location -- if
     uvicorn/main.py is ever launched from anywhere other than backend/,
     Settings() would silently fail to find .env and anthropic_api_key
     would stay None with no error. This makes it independent of cwd.
  2. main.py now calls get_settings()/sync_anthropic_env() at module
     import time, before app.agents.graph (and therefore
     decisions/disruption_decisions.py and decisions/orchestrator_decisions.py,
     which construct ChatAnthropic() at THEIR module import time) is
     imported. Previously that import order meant ANTHROPIC_API_KEY was
     never in os.environ yet when ChatAnthropic() was built. See main.py's
     module docstring for the full explanation.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# EDITED: absolute path to backend/.env, independent of cwd (see docstring above).
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",  # EDITED: was the relative string ".env"
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    groq_api_key: str | None = None
    # Kept here so cost/latency tradeoffs can be tuned in one place.
    # decisions/*.py currently hardcodes "claude-haiku-4-5-20251001" itself
    # (Decision #31) -- wiring decisions/*.py to read it from Settings
    # instead is a natural follow-up, not done in this pass.
    groq_model: str = "openai/gpt-oss-20b"

    # --- Simulator ---
    simulator_tick_duration_minutes: int = 5  # sim-time advanced per tick
    tick_interval_seconds: float = 2.0  # real-world pacing between ticks, demo-watchable
    simulator_seed: int = 42  # matches seed_flights.py / seed_disruptions.py __main__ convention

    # --- API / CORS ---
    host: str = "0.0.0.0"
    port: int = 8000
    cors_allow_origins: list[str] = ["http://localhost:5173"]  # Vite dev server default

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor -- standard FastAPI dependency-injection pattern."""
    return Settings()


def sync_groq_env(settings: Settings) -> None:
    """
    Ensure GROQ_API_KEY is actually present in os.environ.

    decisions/disruption_decisions.py and decisions/orchestrator_decisions.py
    instantiate ChatAnthropic() without an explicit api_key argument, so it
    falls back to reading os.environ["GROQ_API_KEY"] itself. Settings
    may have loaded the key from a .env file, which pydantic-settings does
    NOT push into the process environment automatically -- this bridges
    that gap without requiring any changes to the already-written
    decisions/*.py files.
    """
    if settings.groq_api_key:
        os.environ.setdefault("GROQ_API_KEY", settings.groq_api_key)


def warn_if_api_key_missing(settings: Settings) -> None:
    """
    Fail LOUD at startup instead of failing SILENT on the first LLM call.

    Both LLM-based decision functions catch their own exceptions and fall
    back to a deterministic result (Decision #31's "must never crash the
    simulation tick" requirement) -- correct behavior, but it means a
    missing API key would otherwise show up as nothing worse than slightly
    blander reasoning text, never an actual error. That's exactly the
    "silent bug" failure mode Decision #32 flagged as more dangerous than
    a crash. This makes it loud instead.
    """
    if not settings.groq_api_key and not os.environ.get("GROQ_API_KEY"):
        logging.getLogger("airport_ops.config").warning(
            "GROQ_API_KEY is not set. decide_disruption_priority() and "
            "decide_conflict_resolution() will silently fall back to "
            "deterministic reasoning on every call -- the simulation will "
            "still run, but none of the LLM-based reasoning will actually fire."
        )