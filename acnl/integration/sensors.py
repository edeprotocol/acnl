from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import List, Optional

from acnl.energy.types import (
    EntityID,
    Coord,
    EnergyObservableKind,
    Observable,
    make_entity_id,
)
from acnl.energy.events import Assertion, SigEnvelope
from acnl.energy.crypto import SignatureScheme, MockSignatureScheme, wrap_with_signature


@dataclass
class SensorConfig:
    """Configuration for a simulated sensor."""
    sensor_id: str
    region_id: str
    observable_kind: EnergyObservableKind
    base_value: float
    unit: str
    noise_pct: float = 0.05  # 5% noise
    daily_pattern: bool = True
    daily_amplitude: float = 0.2  # 20% daily variation


class SimulatedSensor:
    """
    Simulated sensor that generates realistic energy observations.

    Useful for testing and demos without real sensor infrastructure.
    """

    def __init__(
        self,
        config: SensorConfig,
        signer: SignatureScheme | None = None,
    ):
        self._config = config
        self._sensor_id = make_entity_id("sensor", config.sensor_id)
        self._signer = signer or MockSignatureScheme(f"sensor-{config.sensor_id}")

    @property
    def sensor_id(self) -> EntityID:
        return self._sensor_id

    def read(self, subject: EntityID, now_ms: int | None = None) -> SigEnvelope[Assertion]:
        """Generate a simulated reading for a subject."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        value = self._generate_value(now_ms)

        assertion = Assertion.create(
            issuer=self._sensor_id,
            subject=subject,
            coord=Coord(region_id=self._config.region_id, ts_ms=now_ms),
            observable=Observable(
                kind=self._config.observable_kind,
                value=value,
                unit=self._config.unit,
            ),
        )

        return wrap_with_signature(assertion, self._sensor_id, self._signer)

    def _generate_value(self, now_ms: int) -> float:
        """Generate a realistic value with patterns and noise."""
        base = self._config.base_value

        # Daily pattern (sinusoidal)
        if self._config.daily_pattern:
            # Hours since midnight
            hour = (now_ms / 3600_000) % 24
            # Peak at noon, trough at midnight
            daily_factor = 1.0 + self._config.daily_amplitude * math.sin(
                (hour - 6) * math.pi / 12
            )
            base *= daily_factor

        # Add noise
        noise = random.gauss(0, self._config.noise_pct * self._config.base_value)
        value = base + noise

        return max(0.0, value)  # Non-negative


def generate_simulated_assertions(
    region_id: str,
    num_compute_nodes: int = 3,
    num_plants: int = 2,
    readings_per_entity: int = 5,
    signer: SignatureScheme | None = None,
) -> List[SigEnvelope[Assertion]]:
    """
    Generate simulated assertions for testing.

    Creates a realistic set of assertions for:
    - Compute nodes (consumption, utilization)
    - Power plants (generation, carbon intensity)
    """
    signer = signer or MockSignatureScheme("sim-sensor")
    now_ms = int(time.time() * 1000)

    assertions = []

    # Compute nodes
    for i in range(num_compute_nodes):
        node_id = make_entity_id("compute-node", f"node-{i+1}")

        # Power sensor
        power_sensor = SimulatedSensor(
            SensorConfig(
                sensor_id=f"power-sensor-{i+1}",
                region_id=region_id,
                observable_kind=EnergyObservableKind.CONSUMPTION_POWER,
                base_value=50.0 + i * 20,  # 50-90 MW
                unit="MW",
            ),
            signer,
        )

        # Available power sensor
        available_sensor = SimulatedSensor(
            SensorConfig(
                sensor_id=f"available-sensor-{i+1}",
                region_id=region_id,
                observable_kind=EnergyObservableKind.AVAILABLE_POWER,
                base_value=100.0 + i * 30,  # 100-160 MW
                unit="MW",
            ),
            signer,
        )

        # Utilization sensor
        util_sensor = SimulatedSensor(
            SensorConfig(
                sensor_id=f"util-sensor-{i+1}",
                region_id=region_id,
                observable_kind=EnergyObservableKind.COMPUTE_UTILIZATION,
                base_value=0.6 + i * 0.1,  # 60-80%
                unit="fraction",
                noise_pct=0.1,
            ),
            signer,
        )

        for j in range(readings_per_entity):
            ts = now_ms - j * 1000
            assertions.append(power_sensor.read(node_id, ts))
            assertions.append(available_sensor.read(node_id, ts))
            assertions.append(util_sensor.read(node_id, ts))

    # Power plants
    for i in range(num_plants):
        plant_id = make_entity_id("plant", f"plant-{i+1}")

        # Generation sensor
        gen_sensor = SimulatedSensor(
            SensorConfig(
                sensor_id=f"gen-sensor-{i+1}",
                region_id=region_id,
                observable_kind=EnergyObservableKind.GENERATION_POWER,
                base_value=200.0 + i * 100,  # 200-300 MW
                unit="MW",
                daily_amplitude=0.3,  # Higher daily variation (solar/wind)
            ),
            signer,
        )

        # Carbon intensity sensor
        carbon_sensor = SimulatedSensor(
            SensorConfig(
                sensor_id=f"carbon-sensor-{i+1}",
                region_id=region_id,
                observable_kind=EnergyObservableKind.CARBON_INTENSITY,
                base_value=50.0 + i * 100,  # 50-150 gCO2/kWh
                unit="gCO2/kWh",
                daily_pattern=False,
                noise_pct=0.02,
            ),
            signer,
        )

        for j in range(readings_per_entity):
            ts = now_ms - j * 1000
            assertions.append(gen_sensor.read(plant_id, ts))
            assertions.append(carbon_sensor.read(plant_id, ts))

    return assertions


class SensorRegistry:
    """Registry of sensors for a region."""

    def __init__(self, region_id: str):
        self._region_id = region_id
        self._sensors: dict[str, SimulatedSensor] = {}

    def register(self, sensor: SimulatedSensor) -> None:
        """Register a sensor."""
        self._sensors[str(sensor.sensor_id)] = sensor

    def get(self, sensor_id: str) -> Optional[SimulatedSensor]:
        """Get a sensor by ID."""
        return self._sensors.get(sensor_id)

    def read_all(self, subjects: List[EntityID]) -> List[SigEnvelope[Assertion]]:
        """Read from all sensors for given subjects."""
        assertions = []
        now_ms = int(time.time() * 1000)

        for subject in subjects:
            for sensor in self._sensors.values():
                assertions.append(sensor.read(subject, now_ms))

        return assertions
