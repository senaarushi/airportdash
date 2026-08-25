"""
Export endpoints for Power BI and other BI tools.

GET /api/export/all
    Returns a ZIP archive containing five CSVs covering every domain
    the simulation tracks. This is the primary Power BI target: load
    the ZIP into Power BI Desktop's "Get Data > Folder" connector, or
    extract and use individual files.

GET /api/export/{table}
    Returns a single CSV for one of: flights, decisions, disruptions,
    conflicts, crew. Useful for ad-hoc Power Query refreshes or quick
    inspection in Excel without unpacking a ZIP.

Data decisions:
- affected_flights columns are semicolon-delimited strings rather than
  JSON arrays, because Power BI's CSV parser handles delimited strings
  natively via "Split Column" and doesn't require a JSON parsing step.
- All datetimes are ISO 8601 UTC strings. Power BI auto-detects these
  as DateTime when the column type is set to "Using Locale > English
  (United States)" in the Power Query editor.
- delay_minutes_arrival / delay_minutes_departure are pre-computed here
  so Power BI measures for OTP don't need DAX date arithmetic.
- The snapshot is taken once under board.lock (same read-isolation
  pattern as routes.py) so the five CSVs are guaranteed to be
  internally consistent -- they all describe the same tick.
"""

import csv
import io
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.event_bus import board

router = APIRouter()

_VALID_TABLES = {"flights", "decisions", "disruptions", "conflicts", "crew"}


# ── helpers ──────────────────────────────────────────────────────────────────


async def _snapshot() -> dict:
    """Lock-protected copy of the live board; identical to routes.py pattern."""
    async with board.lock:
        return board.model_dump()


def _to_csv_bytes(rows: list[dict], fieldnames: list[str]) -> bytes:
    """Serialize a list of flat dicts to UTF-8 CSV bytes."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _fmt(dt: datetime | None) -> str:
    """ISO 8601 UTC string, or empty string if None."""
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return str(dt)


def _delay_minutes(actual: datetime | None, scheduled: datetime | None) -> str:
    """
    Returns the delay in whole minutes as a string, empty if either
    timestamp is absent. Negative means early (ahead of schedule).
    """
    if actual is None or scheduled is None:
        return ""
    if isinstance(actual, str):
        actual = datetime.fromisoformat(actual)
    if isinstance(scheduled, str):
        scheduled = datetime.fromisoformat(scheduled)
    delta = actual - scheduled
    return str(int(delta.total_seconds() // 60))


# ── per-table builders ────────────────────────────────────────────────────────


def _build_flights(snap: dict) -> tuple[list[dict], list[str]]:
    fieldnames = [
        "flight_id",
        "airline",
        "aircraft_type",
        "status",
        "scheduled_arrival",
        "scheduled_departure",
        "actual_arrival",
        "actual_departure",
        "delay_minutes_arrival",
        "delay_minutes_departure",
        "is_delayed",
        "assigned_gate",
        "assigned_crew",
        "turnaround_time",
    ]
    rows = []
    for f in snap["flights"].values():
        rows.append({
            "flight_id": f["flight_id"],
            "airline": f["airline"],
            "aircraft_type": f["aircraft_type"],
            "status": f["status"],
            "scheduled_arrival": _fmt(f.get("scheduled_arrival")),
            "scheduled_departure": _fmt(f.get("scheduled_departure")),
            "actual_arrival": _fmt(f.get("actual_arrival")),
            "actual_departure": _fmt(f.get("actual_departure")),
            "delay_minutes_arrival": _delay_minutes(
                f.get("actual_arrival"), f.get("scheduled_arrival")
            ),
            "delay_minutes_departure": _delay_minutes(
                f.get("actual_departure"), f.get("scheduled_departure")
            ),
            "is_delayed": f.get("is_delayed", False),
            "assigned_gate": f.get("assigned_gate") or "",
            # semicolon-delimited so Power BI "Split Column" works cleanly
            "assigned_crew": ";".join(f.get("assigned_crew") or []),
            "turnaround_time": f.get("turnaround_time", ""),
        })
    return rows, fieldnames


def _build_decisions(snap: dict) -> tuple[list[dict], list[str]]:
    fieldnames = ["tick", "agent_id", "action", "detail", "affected_flights"]
    rows = []
    for entry in snap["decision_log"]:
        rows.append({
            "tick": entry["tick"],
            "agent_id": entry["agent_id"],
            "action": entry["action"],
            "detail": entry["detail"],
            "affected_flights": ";".join(entry.get("affected_flights") or []),
        })
    return rows, fieldnames


def _build_disruptions(snap: dict) -> tuple[list[dict], list[str]]:
    fieldnames = [
        "event_id",
        "disruption_type",
        "severity",
        "trigger_time",
        "disruption_description",
        "affected_flights",
        "resolved",
    ]
    rows = []
    for d in snap["open_disruptions"]:
        rows.append({
            "event_id": d["event_id"],
            "disruption_type": d["disruption_type"],
            "severity": d["severity"],
            "trigger_time": _fmt(d.get("trigger_time")),
            "disruption_description": d.get("disruption_description", ""),
            "affected_flights": ";".join(d.get("affected_flights") or []),
            "resolved": d.get("resolved", False),
        })
    return rows, fieldnames


def _build_conflicts(snap: dict) -> tuple[list[dict], list[str]]:
    fieldnames = [
        "conflict_id",
        "agent_id",
        "conflict_description",
        "affected_flights",
        "resolved",
    ]
    rows = []
    for c in snap["open_conflicts"]:
        rows.append({
            "conflict_id": c["conflict_id"],
            "agent_id": c["agent_id"],
            "conflict_description": c.get("conflict_description", ""),
            "affected_flights": ";".join(c.get("affected_flights") or []),
            "resolved": c.get("resolved", False),
        })
    return rows, fieldnames


def _build_crew(snap: dict) -> tuple[list[dict], list[str]]:
    fieldnames = [
        "crew_id",
        "role",
        "available",
        "assigned_flight",
        "shift_minutes_remaining",
    ]
    rows = []
    for c in snap["crew"].values():
        rows.append({
            "crew_id": c["crew_id"],
            "role": c["role"],
            "available": c.get("available", False),
            "assigned_flight": c.get("assigned_flight") or "",
            "shift_minutes_remaining": c.get("shift_minutes_remaining", ""),
        })
    return rows, fieldnames


_BUILDERS = {
    "flights": _build_flights,
    "decisions": _build_decisions,
    "disruptions": _build_disruptions,
    "conflicts": _build_conflicts,
    "crew": _build_crew,
}


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/all",
    summary="Export full simulation state as a ZIP of CSVs",
    response_description="ZIP archive containing flights.csv, decisions.csv, disruptions.csv, conflicts.csv, crew.csv",
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_all() -> Response:
    """
    Downloads a ZIP with one CSV per domain table.

    Power BI usage:
        Home > Get Data > More > All > Folder > Connect
        Point at the unzipped directory, then "Combine & Transform"
        to pull all five tables in at once.

    Alternatively: Get Data > Web, paste the endpoint URL, then
    unpack the ZIP in Power Query using Binary.Decompress or the
    built-in "Extract files" step.
    """
    snap = await _snapshot()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for table_name, builder in _BUILDERS.items():
            rows, fieldnames = builder(snap)
            csv_bytes = _to_csv_bytes(rows, fieldnames)
            zf.writestr(f"{table_name}.csv", csv_bytes)

    tick = snap.get("current_tick", 0)
    filename = f"airport_ops_tick_{tick}.zip"

    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{table}",
    summary="Export a single domain table as CSV",
    response_description="CSV file for the requested table",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_table(table: str) -> Response:
    """
    Downloads a single CSV. Valid values for `table`:
    `flights`, `decisions`, `disruptions`, `conflicts`, `crew`.

    Power BI usage:
        Home > Get Data > Text/CSV > paste the endpoint URL.
        Power Query will parse column types automatically.
    """
    if table not in _VALID_TABLES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown table '{table}'. Valid options: {sorted(_VALID_TABLES)}",
        )

    snap = await _snapshot()
    rows, fieldnames = _BUILDERS[table](snap)
    csv_bytes = _to_csv_bytes(rows, fieldnames)

    tick = snap.get("current_tick", 0)
    filename = f"airport_ops_{table}_tick_{tick}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
