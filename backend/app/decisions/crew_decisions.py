from app.core.models import Flight, CrewMember, CrewRole


def decide_crew_assignment(flight: Flight, available_crew: list[CrewMember]) -> list[str]:
    """
    Rule-based: crew eligibility (right role, available, enough shift time
    left to actually finish this turnaround) is a deterministic filter,
    not a judgment call worth an LLM's latency or cost.

    For each required role, picks the eligible crew member with the MOST
    shift_minutes_remaining, a simple load-balancing heuristic that spreads
    work toward crew furthest from their shift limit rather than exhausting
    whoever happens to be first in the list.
    """
    required_roles = [CrewRole.BAGGAGE, CrewRole.PUSHBACK, CrewRole.CLEANING]
    assigned: list[str] = []

    for role in required_roles:
        eligible = [
            c for c in available_crew
            if c.role == role
            and c.available
            and c.crew_id not in assigned
            and c.shift_minutes_remaining >= flight.turnaround_time
        ]
        if not eligible:
            continue  # role goes unfilled this tick, Orchestrator sees a partial proposal and may raise a Conflict
        best = max(eligible, key=lambda c: c.shift_minutes_remaining)
        assigned.append(best.crew_id)

    return assigned