from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, List, Dict
import random
import time
import math

from sfl.energy.model import (
    Assertion,
    Observable,
    EnergyObservableKind,
    Coord,
    EntityID,
    make_entity_id,
)


class SensorInterface(Protocol):
    """Interface for physical sensors."""

    def read(self) -> List[Assertion]:
        ...


@dataclass
class SimulatedSensor:
    """Simulated sensor for development/testing."""

    sensor_id: str
    region_id: str
    subjects: List[EntityID]  # entities this sensor observes

    # Simulation params
    base_power_mw: float = 50.0
    power_variance: float = 10.0
    base_carbon: float = 200.0
    carbon_variance: float = 50.0

    def read(self) -> List[Assertion]:
        """Generate simulated assertions."""
        now_ms = int(time.time() * 1000)
        coord = Coord(region_id=self.region_id, ts_ms=now_ms)

        assertions = []

        for subject in self.subjects:
            kind, _ = subject.split(":", 1) if ":" in subject else ("unknown", subject)

            if kind == "compute-node":
                assertions.extend(self._read_compute_node(subject, coord))
            elif kind == "plant":
                assertions.extend(self._read_plant(subject, coord))
            elif kind == "line":
                assertions.extend(self._read_line(subject, coord))

        return assertions

    def _read_compute_node(self, subject: EntityID, coord: Coord) -> List[Assertion]:
        # Simulate daily pattern (sine wave)
        hour = (time.time() % 86400) / 3600
        daily_factor = 0.7 + 0.3 * math.sin(2 * math.pi * (hour - 6) / 24)

        power = (self.base_power_mw + random.gauss(0, self.power_variance)) * daily_factor
        utilization = 0.5 + 0.4 * daily_factor + random.gauss(0, 0.05)
        temp = 45 + 30 * utilization + random.gauss(0, 2)

        return [
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.CONSUMPTION_POWER,
                    value=max(0, power),
                    unit="MW",
                ),
            ),
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.AVAILABLE_POWER,
                    value=max(0, self.base_power_mw * 1.5 - power),
                    unit="MW",
                ),
            ),
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.COMPUTE_UTILIZATION,
                    value=min(1.0, max(0, utilization)),
                    unit="fraction",
                ),
            ),
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.TEMP_CELSIUS,
                    value=temp,
                    unit="°C",
                ),
            ),
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.CARBON_INTENSITY,
                    value=max(0, self.base_carbon + random.gauss(0, self.carbon_variance)),
                    unit="gCO2/kWh",
                ),
            ),
        ]

    def _read_plant(self, subject: EntityID, coord: Coord) -> List[Assertion]:
        # Simulate generation with some variability
        generation = self.base_power_mw * 2 + random.gauss(0, self.power_variance * 2)

        return [
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.GENERATION_POWER,
                    value=max(0, generation),
                    unit="MW",
                ),
            ),
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.CARBON_INTENSITY,
                    value=random.choice([20, 50, 200, 400]),  # different plant types
                    unit="gCO2/kWh",
                ),
            ),
        ]

    def _read_line(self, subject: EntityID, coord: Coord) -> List[Assertion]:
        loading = 0.4 + random.gauss(0, 0.15)

        return [
            Assertion.create(
                issuer=f"sensor:{self.sensor_id}",
                subject=subject,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.LINE_LOADING,
                    value=min(1.0, max(0, loading)),
                    unit="fraction",
                ),
            ),
        ]


class SensorManager:
    """Manages multiple sensors."""

    def __init__(self):
        self.sensors: List[SensorInterface] = []

    def add_sensor(self, sensor: SensorInterface) -> None:
        self.sensors.append(sensor)

    def read_all(self) -> List[Assertion]:
        assertions = []
        for sensor in self.sensors:
            try:
                assertions.extend(sensor.read())
            except Exception as e:
                print(f"Sensor read error: {e}")
        return assertions


def generate_simulated_assertions(
    region_id: str,
    num_compute_nodes: int = 3,
    num_plants: int = 1,
    num_lines: int = 2,
) -> List[Assertion]:
    """Convenience function to generate a batch of simulated assertions."""

    subjects = []
    subjects.extend([make_entity_id("compute-node", f"node-{i}") for i in range(num_compute_nodes)])
    subjects.extend([make_entity_id("plant", f"plant-{i}") for i in range(num_plants)])
    subjects.extend([make_entity_id("line", f"line-{i}") for i in range(num_lines)])

    sensor = SimulatedSensor(
        sensor_id="sim-sensor-0",
        region_id=region_id,
        subjects=subjects,
    )

    return sensor.read()
