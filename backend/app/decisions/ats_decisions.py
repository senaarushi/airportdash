from app.core.models import Flight, FlightStatus, AircraftType


def decide_delay_risk(flight: Flight, current_tick: int) -> bool:
    """
    Rule-based: checking already-computed timing fields plus a light
    structural heuristic is a deterministic lookup, not a nuanced judgment
    call worth spending an LLM call on every tick for every active flight,
    an LLM here would just be added latency and cost for no quality gain.

    NOTE: current_tick is accepted for contract stability and future
    extension (e.g. escalating flagged severity the longer a delay
    persists across consecutive ticks, once some tracking mechanism
    exists), but isn't decision-critical in this version, is_delayed
    already reflects real elapsed time correctly since it's computed
    directly from timestamps, not tick count.
    """
    if flight.is_delayed:
        return True

    # Secondary heuristic: wide-body aircraft have tighter turnaround
    # margins relative to their scheduled window, flag them as elevated
    # risk slightly earlier, once landed but not yet at a gate, even
    # before they're formally "delayed" by the timestamp check above.
    if flight.aircraft_type == AircraftType.WIDE_BODY and flight.status == FlightStatus.LANDED:
        return True

    return False