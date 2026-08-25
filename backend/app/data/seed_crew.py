"""
Generates the ground crew roster used by the simulation.

Like seed_flights.py, shift lengths are randomized within a realistic
range rather than a fixed constant, so the roster behaves like real
staffing data instead of a uniform mock. `seed` is honored the same way
seed_flights.py/seed_disruptions.py honor it: pass an explicit int for a
reproducible roster (used as seed=42 in __main__, matching
config.py's simulator_seed).

DELIBERATE SCARCITY: 4 crew members per role (12 total) is sized to
comfortably cover the bottleneck cluster and the DIS-CREW-001 scripted
shortage scenario (Decision Log #24), forcing real per-crew-member
contention through decide_conflict_resolution the same way gate scarcity
does in seed_gates.py.

KNOWN GAP, NOW FIXED in core/simulator.py: nothing in agents/orchestrator.py
or core/simulator.py used to reset CrewMember.available back to True once
the flight that crew member was assigned to actually departed.
orchestrator.py's _apply_crew_proposals sets `crew_member.available = False`
on assignment; there was no symmetric release anywhere. core/simulator.py
already did this kind of release for gates (`_advance_flight_statuses`'s
READY_FOR_PUSHBACK -> DEPARTED transition frees `flight.assigned_gate`
back to GateStatus.OPEN) -- crew release has now been added to that same
block, checking `flight.assigned_crew` the same way it already checks
`flight.assigned_gate`. The roster is still kept realistically small here
on purpose (this was never a "make the roster bigger" problem, it was a
"nothing ever frees anyone" problem), the fix belongs in simulator.py and
now lives there.
"""

import json
import os
import random

from app.core.models import CrewMember, CrewRole


_ROLE_PREFIXES = {
    CrewRole.BAGGAGE: "BAG",
    CrewRole.PUSHBACK: "PB",
    CrewRole.CLEANING: "CLN",
}


def generate_mock_crew(seed: int | None = None, per_role: int = 4) -> list[CrewMember]:
    """
    Generates `per_role` crew members for each of the 3 CrewRole values
    (12 total by default). shift_minutes_remaining is randomized across a
    realistic 3-8 hour range (180-480 minutes) rather than a fixed
    constant, same real-world-variability principle as seed_flights.py's
    turnaround-time ranges.

    seed: pass an explicit int for a reproducible roster (recommended for
    demos and tests). Leave as None for genuine randomness.
    """
    if seed is not None:
        random.seed(seed)

    crew: list[CrewMember] = []
    for role, prefix in _ROLE_PREFIXES.items():
        for i in range(1, per_role + 1):
            crew.append(
                CrewMember(
                    crew_id=f"{prefix}{i:02d}",
                    role=role,
                    available=True,
                    shift_minutes_remaining=random.randint(180, 480),
                )
            )
    return crew


def save_crew_to_json(crew: list[CrewMember], filepath: str) -> None:
    """Same save-pattern as the other seed_*.py files."""
    crew_data = [json.loads(c.model_dump_json()) for c in crew]

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

    with open(filepath, "w") as f:
        json.dump(crew_data, f, indent=4)
    print(f"Successfully seeded {len(crew)} crew members into {filepath}")


if __name__ == "__main__":
    generated_crew = generate_mock_crew(seed=42)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crew_dataset.json")
    save_crew_to_json(generated_crew, output_path)