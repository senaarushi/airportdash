import json
import random
from datetime import datetime, timedelta, timezone
import os

# Adjust import based on your exact structure, assuming execution from backend/ root
from app.core.models import Flight, AircraftType


def _generate_unique_flight_id(existing_ids: set[str], airline: str) -> str:
    """
    Retries until a unique flight_id is produced. flight_id is the dict key
    in AirportStatus.flights, a collision would silently overwrite one
    flight instead of erroring.

    NOTE (real-world-data readiness): this generates uniqueness only within
    a single generated batch/day. Real-world flight numbers repeat daily
    (AI101 flies every day), so a real ingestion pipeline will need to key
    on (flight_number, date) rather than flight_number alone once you're
    handling more than a single day of data. Not an issue for a one-day
    simulation, but worth remembering before extending the time horizon.
    """
    while True:
        candidate = f"{airline}{random.randint(100, 999)}"
        if candidate not in existing_ids:
            existing_ids.add(candidate)
            return candidate


def generate_mock_flights(seed: int | None = None) -> list[Flight]:
    """
    Generates a synthetic dataset of 18 flights.
    Includes a designed bottleneck (cluster of arrivals) to test agent conflict resolution.

    seed: pass an explicit int for a reproducible schedule (recommended for
    demos and tests, an unseeded run produces a different random schedule
    every time, which makes a live demo non-repeatable and makes bugs
    harder to reproduce). Leave as None for genuine randomness.
    """
    if seed is not None:
        random.seed(seed)

    flights = []
    used_ids: set[str] = set()

    # Establish a baseline simulation start time (e.g., 8:00 AM).
    # FIX (real-world-data readiness): timezone-aware (UTC), matching the
    # normalization now enforced in core/models.py. Real ops/flight data
    # feeds are virtually always timezone-aware; generating naive mock
    # timestamps would have caused a TypeError the moment real, aware
    # timestamps were compared against them (e.g. in Flight.is_delayed).
    base_time = datetime(2026, 7, 24, 8, 0, 0, tzinfo=timezone.utc)

    airlines = ["AI", "6E", "SG", "UK", "QP"]

    # --- PHASE 1: The Bottleneck (Morning Rush) ---
    # We force 5 flights to arrive within the exact same 5-minute window to trigger gate conflicts.
    for i in range(1, 6):
        airline = random.choice(airlines)
        flight_id = _generate_unique_flight_id(used_ids, airline)

        # 40% chance of wide-body during rush hour
        is_wide_body = random.random() < 0.4
        ac_type = AircraftType.WIDE_BODY if is_wide_body else AircraftType.NARROW_BODY
        # FIX: real turnaround times vary by aircraft, route, and airline,
        # not a single fixed constant. A narrow ranged draw resembles real
        # operational variability much more closely than two fixed values
        # (45 / 90) ever could, and is what you'd see feeding in from a
        # real ops data source.
        turnaround = random.randint(75, 110) if is_wide_body else random.randint(35, 55)

        # Cluster arrivals between 8:10 AM and 8:15 AM
        arrival_time = base_time + timedelta(minutes=random.randint(10, 15))
        departure_time = arrival_time + timedelta(minutes=turnaround)

        flight = Flight(
            flight_id=flight_id,
            airline=airline,
            aircraft_type=ac_type,
            scheduled_arrival=arrival_time,
            scheduled_departure=departure_time,
            turnaround_time=turnaround
        )
        flights.append(flight)

    # --- PHASE 2: Standard Operations ---
    # The remaining 13 flights are distributed normally over the next 3 hours
    for i in range(6, 19):
        airline = random.choice(airlines)
        flight_id = _generate_unique_flight_id(used_ids, airline)

        is_wide_body = random.random() < 0.25  # 25% chance of wide body generally
        ac_type = AircraftType.WIDE_BODY if is_wide_body else AircraftType.NARROW_BODY
        turnaround = random.randint(75, 110) if is_wide_body else random.randint(35, 55)

        # Random arrival between 8:30 AM and 11:30 AM
        arrival_offset = random.randint(30, 210)
        arrival_time = base_time + timedelta(minutes=arrival_offset)
        departure_time = arrival_time + timedelta(minutes=turnaround)

        flight = Flight(
            flight_id=flight_id,
            airline=airline,
            aircraft_type=ac_type,
            scheduled_arrival=arrival_time,
            scheduled_departure=departure_time,
            turnaround_time=turnaround
        )
        flights.append(flight)

    # Sort flights chronologically by arrival time so the simulation processes them in order
    flights.sort(key=lambda f: f.scheduled_arrival)
    return flights


def save_flights_to_json(flights: list[Flight], filepath: str = "seed_data.json"):
    """
    Serializes the Pydantic models to a JSON file so they can be easily loaded
    by the simulation loop without regenerating them every time.

    NOTE (real-world-data readiness): this function's signature,
    list[Flight] in, JSON out, is deliberately the same contract a real
    data loader should follow. When you're ready to plug in a real feed,
    write a sibling function (e.g. load_flights_from_source(...) ->
    list[Flight]) that produces the same Flight objects from a real API
    or file instead of random generation, and it becomes a drop-in
    replacement, the simulator and agents never need to know which one
    produced the data.
    """
    flight_data = [json.loads(f.model_dump_json()) for f in flights]

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

    with open(filepath, "w") as f:
        json.dump(flight_data, f, indent=4)
    print(f"Successfully seeded {len(flights)} flights into {filepath}")


if __name__ == "__main__":
    generated_flights = generate_mock_flights(seed=42)

    # Output path is independent of the current working decisions, always
    # writes next to this script regardless of where you run it from.
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flights_dataset.json")
    save_flights_to_json(generated_flights, output_path)