from app.core.models import Flight, Gate, AircraftType


def decide_gate_assignment(flight: Flight, available_gates: list[Gate]) -> str | None:
    """
    Rule-based: gate compatibility (does this gate support this aircraft
    size, is it open) is a deterministic constraint-satisfaction check, not
    a judgment call. A rule beats an LLM call here on every axis, speed,
    determinism, testability, with zero loss of decision quality.

    Prefers an exact-fit gate over a compatible-but-oversized one, so a
    narrow-body flight doesn't needlessly occupy a wide-body-capable gate
    that a later wide-body flight might actually need this tick.
    """
    if not available_gates:
        return None

    if flight.aircraft_type == AircraftType.WIDE_BODY:
        candidates = [g for g in available_gates if g.supports_wide_body]
        return candidates[0].gate_id if candidates else None

    # Narrow-body: prefer a narrow-only gate first, only fall back to a
    # wide-body-capable gate if nothing else is available.
    exact_fit = [g for g in available_gates if not g.supports_wide_body]
    if exact_fit:
        return exact_fit[0].gate_id

    fallback = [g for g in available_gates if g.supports_wide_body]
    return fallback[0].gate_id if fallback else None