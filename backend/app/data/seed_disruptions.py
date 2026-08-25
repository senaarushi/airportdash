import json
import os
import random
from datetime import timedelta

from app.core.models import Flight, DisruptionEvent, DisruptionType, DisruptionSeverity


def generate_mock_disruptions(flights: list[Flight], seed: int | None = None) -> list[DisruptionEvent]:
    """
    Generates a small set of scripted disruption scenarios tied to a given
    flight schedule.

    Takes `flights` as an explicit parameter (rather than generating its
    own) so this function works identically whether `flights` came from
    generate_mock_flights() or from a real data source later, same
    real-world-data-readiness principle as seed_flights.py: swap what feeds
    this function, not the function itself.

    seed: pass an explicit int for a reproducible scenario. Leave as None
    for genuine randomness.

    Three scenarios are deliberately designed for different demo purposes:
      1. WEATHER, LEVEL_4: hits the bottleneck cluster of flights that
         seed_flights.py deliberately arrives together, this is the "money
         moment" scenario, several flights affected at once, forcing real
         cascading replanning across Gate, Crew, and ATS agents at the same
         time.
      2. TECH_ISSUE, LEVEL_2: hits a single, isolated flight later in the
         schedule, a localized-impact scenario, good for demonstrating that
         the system doesn't over-react to minor issues.
      3. CREW_SHORTAGE, LEVEL_3: hits two flights that aren't necessarily
         adjacent, testing crew-specific resource contention independent of
         gate conflicts.
    """
    if seed is not None:
        random.seed(seed)

    if not flights:
        return []

    sorted_flights = sorted(flights, key=lambda f: f.scheduled_arrival)
    earliest_arrival = sorted_flights[0].scheduled_arrival

    # --- Scenario 1: Weather event hitting the bottleneck cluster ---
    # seed_flights.py clusters ~5 flights within the first 15 minutes of the
    # schedule, identify flights arriving within that same early window.
    bottleneck_window_end = earliest_arrival + timedelta(minutes=20)
    bottleneck_flights = [
        f for f in sorted_flights if f.scheduled_arrival <= bottleneck_window_end
    ]
    weather_affected = [f.flight_id for f in bottleneck_flights[:5]] or [sorted_flights[0].flight_id]

    weather_disruption = DisruptionEvent(
        event_id="DIS-WEATHER-001",
        disruption_type=DisruptionType.WEATHER,
        # Triggered shortly after the bottleneck cluster has landed, while
        # gates/crew are actively occupied, this is what forces real
        # replanning rather than hitting flights that haven't arrived yet.
        trigger_time=earliest_arrival + timedelta(minutes=25),
        severity=DisruptionSeverity.LEVEL_4,
        disruption_description=(
            "Sudden low-visibility weather event grounds ground operations, "
            "gates supporting affected flights become temporarily unusable."
        ),
        affected_flights=weather_affected,
    )

    # --- Scenario 2: Isolated technical issue, single flight ---
    later_flights = [f for f in sorted_flights if f.scheduled_arrival > bottleneck_window_end]
    tech_target = random.choice(later_flights) if later_flights else sorted_flights[-1]

    tech_disruption = DisruptionEvent(
        event_id="DIS-TECH-001",
        disruption_type=DisruptionType.TECH_ISSUE,
        trigger_time=tech_target.scheduled_arrival + timedelta(minutes=5),
        severity=DisruptionSeverity.LEVEL_2,
        disruption_description=(
            f"Aircraft operating {tech_target.flight_id} flagged for an "
            "unscheduled technical inspection after landing."
        ),
        affected_flights=[tech_target.flight_id],
    )

    # --- Scenario 3: Crew shortage, two non-adjacent flights ---
    remaining_pool = [f for f in sorted_flights if f.flight_id != tech_target.flight_id]
    crew_targets = random.sample(remaining_pool, k=min(2, len(remaining_pool)))
    crew_affected = [f.flight_id for f in crew_targets]

    # Trigger partway through the schedule, independent of the other two scenarios.
    mid_point = sorted_flights[len(sorted_flights) // 2].scheduled_arrival

    crew_disruption = DisruptionEvent(
        event_id="DIS-CREW-001",
        disruption_type=DisruptionType.CREW_SHORTAGE,
        trigger_time=mid_point,
        severity=DisruptionSeverity.LEVEL_3,
        disruption_description=(
            "Two ground crew members called in sick, baggage and pushback "
            "coverage is short for the affected turnarounds."
        ),
        affected_flights=crew_affected,
    )

    disruptions = [weather_disruption, tech_disruption, crew_disruption]
    disruptions.sort(key=lambda d: d.trigger_time)
    return disruptions


def save_disruptions_to_json(disruptions: list[DisruptionEvent], filepath: str) -> None:
    """
    Serializes disruption events to JSON, same pattern as
    seed_flights.save_flights_to_json: any future real-data disruption feed
    (e.g. a live NOTAM/weather API) should produce the same list[DisruptionEvent]
    and can reuse this function unchanged.
    """
    disruption_data = [json.loads(d.model_dump_json()) for d in disruptions]

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

    with open(filepath, "w") as f:
        json.dump(disruption_data, f, indent=4)
    print(f"Successfully seeded {len(disruptions)} disruptions into {filepath}")


if __name__ == "__main__":
    # Loads the flight schedule generated by seed_flights.py so disruptions
    # reference real, existing flight_ids rather than guessing at them.
    from app.data.seed_flights import generate_mock_flights

    generated_flights = generate_mock_flights(seed=42)
    generated_disruptions = generate_mock_disruptions(generated_flights, seed=42)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disruptions_dataset.json")
    save_disruptions_to_json(generated_disruptions, output_path)