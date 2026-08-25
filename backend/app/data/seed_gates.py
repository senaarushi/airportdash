"""
Generates the static gate inventory used by the simulation.

Unlike flights and disruptions, gates are physical infrastructure -- a
real airport's gate layout doesn't reshuffle randomly between simulation
runs, it's a fixed asset. generate_mock_gates() still accepts a `seed`
parameter purely for interface consistency with generate_mock_flights()/
generate_mock_disruptions() (and in case a randomized-layout variant is
ever wanted for testing), but the layout itself is deterministic
regardless of seed value.

DELIBERATE SCARCITY (mirrors the bottleneck design already in
seed_flights.py): with seed=42, the first 5 flights (the "bottleneck
cluster", Decision Log #24's designated demo centerpiece) include 3
WIDE_BODY aircraft arriving within minutes of each other. Only 2 of the 6
gates generated here support wide-body aircraft, so that cluster produces
a genuine 3-proposals-for-2-gates conflict for the Orchestrator to run
through decide_conflict_resolution -- intentional, not an oversight. A
more generous gate count would mean the "money moment" (Decision #2/#22:
multi-flight cascading replanning) never actually happens.
"""

import json
import os

from app.core.models import Gate


def generate_mock_gates(seed: int | None = None) -> list[Gate]:
    """
    Generates a fixed 6-gate inventory: 4 narrow-body-only gates
    (G1-G4) and 2 wide-body-capable gates (G5-G6).

    `seed` is accepted for interface consistency with the other
    generate_mock_*() functions (and so call sites don't need special-
    casing) but is currently unused -- gate layout is deterministic.
    """
    del seed  # unused, kept for interface consistency; see module docstring

    narrow_only = [Gate(gate_id=f"G{i}", supports_wide_body=False) for i in range(1, 5)]
    wide_capable = [Gate(gate_id=f"G{i}", supports_wide_body=True) for i in range(5, 7)]
    return narrow_only + wide_capable


def save_gates_to_json(gates: list[Gate], filepath: str) -> None:
    """
    Same save-pattern as seed_flights.py/seed_disruptions.py: any future
    real gate-inventory source (e.g. an airport's own gate management
    system) should produce the same list[Gate] and can reuse this
    function unchanged.
    """
    gate_data = [json.loads(g.model_dump_json()) for g in gates]

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

    with open(filepath, "w") as f:
        json.dump(gate_data, f, indent=4)
    print(f"Successfully seeded {len(gates)} gates into {filepath}")


if __name__ == "__main__":
    generated_gates = generate_mock_gates()

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gates_dataset.json")
    save_gates_to_json(generated_gates, output_path)