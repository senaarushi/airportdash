# Airport Operations — Multi-Agent Simulation

A simulated airport operations system driven by five coordinating AI agents — Gate Handling, Ground Crew, ATS (schedule tracking), Disruption, and an Orchestrator — that plan gate assignments, crew turnarounds, and disruption response in a time-stepped simulation, with every decision logged in a live, human-readable reasoning trace.

This isn't a live-data dashboard: it's a scripted scenario (an 18-flight schedule with three deliberately staged disruptions) built to make multi-agent coordination *visible* — when a disruption hits, you can watch gates get reassigned, crew reshuffled, and conflicts raised and resolved, tick by tick, with a readable trail of *why* each decision was made.

## Why this exists

This is a portfolio project built to demonstrate agentic system design: multiple independent agents proposing actions, a central coordinator resolving conflicts between them, and a decision layer that can be swapped between deterministic rule-based logic and LLM-based reasoning without touching anything else in the codebase. See [`docs/architecture.md`](docs/architecture.md) for the full design rationale.

## Tech stack

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph |
| Backend API | FastAPI |
| Data validation | Pydantic v2 |
| LLM reasoning | Google Gemini (`gemini-3.6-flash`) via `langchain-google-genai` |
| Package manager | `uv` (backend) |
| Frontend | React 19 + Vite (planned, not yet built) |

## Project structure

```
airport-ops/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint, starts the simulation loop
│   │   ├── config.py            # Settings (env vars, tick pacing, CORS)
│   │   ├── core/                # Domain models, event bus, simulator, proposals
│   │   ├── agents/              # LangGraph agent nodes — never contain decision logic
│   │   ├── decisions/           # Swappable decision logic (rule-based or LLM)
│   │   ├── api/                 # REST routes + websocket
│   │   └── data/                # Mock data generators (flights, gates, crew, disruptions)
│   ├── tests/
│   ├── pyproject.toml           # pytest config
│   └── .env                     # API keys, not committed
├── frontend/                     # not yet built
├── docs/
│   ├── architecture.md
│   └── demo_script.md
└── requirements.txt
```

## Setup

**1. Clone and enter the backend:**
```bash
cd backend
```

**2. Create a virtual environment and install dependencies:**
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r ../requirements.txt
```

**3. Set your Gemini API key.**
Create `backend/.env`:
```
GOOGLE_API_KEY=your-key-here
```
Get a free key from [Google AI Studio](https://aistudio.google.com/apikey). Without a valid key, the LLM-based decision functions (disruption priority scoring, conflict resolution) fall back to deterministic reasoning automatically — the simulation still runs, just without real LLM-generated explanations.

**4. Run the server:**
```bash
uvicorn app.main:app --reload
```
The API is now live at `http://127.0.0.1:8000` (docs at `/docs`), and the simulation starts ticking automatically in the background.

**5. Run the tests:**
```bash
pytest
```
(Run from inside `backend/` — the pytest config, and the `app` package `pytest` needs to import, both live there.)

## API

All REST endpoints are under `/api`:

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness check |
| `GET /api/status` | Full current `AirportStatus` snapshot |
| `GET /api/flights`, `/api/flights/{flight_id}` | Flight state |
| `GET /api/gates`, `/api/gates/{gate_id}` | Gate state |
| `GET /api/crew`, `/api/crew/{crew_id}` | Crew state |
| `GET /api/disruptions` | Open disruptions |
| `GET /api/conflicts` | Open/resolved conflicts |
| `GET /api/decisions` | The live decision/reasoning log |

`GET /ws` — a websocket pushing a full `AirportStatus` snapshot whenever a flight departs its origin, lands, departs, or a disruption triggers.

## How the simulation works, briefly

A world-clock `Simulator` advances flights through their lifecycle (`SCHEDULED → IN_AIR → LANDED → AT_GATE → READY_FOR_PUSHBACK → DEPARTED`) and injects three scripted disruptions at fixed times. On every tick, it hands control to a compiled LangGraph: four agents (Gate, Crew, ATS, Disruption) run concurrently against a read-only snapshot of state and each return proposals; the Orchestrator — the only agent allowed to write to shared state — collects those proposals, detects conflicts between them, resolves them (via rule-based logic or an LLM call, depending on the conflict type), and applies the outcome. Every decision, resolved or not, is appended to a live decision log.

Full design reasoning — why agents never touch shared state directly, why decision logic is a separate swappable layer from agent plumbing, why both an event bus and a shared blackboard exist — is in [`docs/architecture.md`](docs/architecture.md).

## Status

Backend is functionally complete: all 5 agents, all decision logic (rule-based + Gemini-based), the simulator, the API, and the full test suite are written and passing. Frontend has not been started yet. See the project's internal decision log for the full history of design tradeoffs and fixes.