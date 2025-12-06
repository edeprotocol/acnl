"""
ACNL Integration — Sensors

Sensor interfaces and simulated implementations for testing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Protocol
import random
import time

from ..core.ids import EntityID, Coord, plant_id, compute_node_id, lfi_id
from ..core.observables import EnergyObservableKind, Observable, UNIT_MW, UNIT_GCO2_KWH
from ..core.events import Assertion


class SensorInterface(Protocol):
    """Protocol for sensors that generate assertions."""

    def poll(self) -> List[Assertion]:
        """Poll the sensor for new assertions."""
        ...


@dataclass
class SimulatedSensor:
    """
    Simulated sensor that generates realistic energy/compute observations.

    Simple interface for testing and demos.
    """
    region_id: str
    plant_ids: List[EntityID] = field(default_factory=list)
    compute_node_ids: List[EntityID] = field(default_factory=list)
    generation_base_mw: float = 100.0
    consumption_base_mw: float = 50.0
    carbon_base: float = 100.0
    noise_pct: float = 0.1

    def poll(self) -> List[Assertion]:
        """Generate assertions for all registered entities."""
        now_ms = int(time.time() * 1000)
        coord = Coord(region_id=self.region_id, ts_ms=now_ms)
        assertions = []
        issuer = lfi_id(self.region_id)

        # Generate assertions for plants
        for pid in self.plant_ids:
            gen_value = self._with_noise(self.generation_base_mw)
            assertions.append(Assertion.create(
                issuer=issuer,
                subject=pid,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.GENERATION_POWER,
                    value=gen_value,
                    unit=UNIT_MW,
                ),
            ))

            carbon_value = self._with_noise(self.carbon_base * 0.5)
            assertions.append(Assertion.create(
                issuer=issuer,
                subject=pid,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.CARBON_INTENSITY,
                    value=max(0, carbon_value),
                    unit=UNIT_GCO2_KWH,
                ),
            ))

        # Generate assertions for compute nodes
        for cid in self.compute_node_ids:
            cons_value = self._with_noise(self.consumption_base_mw)
            assertions.append(Assertion.create(
                issuer=issuer,
                subject=cid,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.CONSUMPTION_POWER,
                    value=cons_value,
                    unit=UNIT_MW,
                ),
            ))

            avail_value = self._with_noise(self.generation_base_mw - self.consumption_base_mw)
            assertions.append(Assertion.create(
                issuer=issuer,
                subject=cid,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.AVAILABLE_POWER,
                    value=max(0, avail_value),
                    unit=UNIT_MW,
                ),
            ))

            carbon_value = self._with_noise(self.carbon_base)
            assertions.append(Assertion.create(
                issuer=issuer,
                subject=cid,
                coord=coord,
                observable=Observable(
                    kind=EnergyObservableKind.CARBON_INTENSITY,
                    value=max(0, carbon_value),
                    unit=UNIT_GCO2_KWH,
                ),
            ))

        return assertions

    def _with_noise(self, value: float) -> float:
        """Add Gaussian noise to a value."""
        noise = random.gauss(0, self.noise_pct * value)
        return max(0, value + noise)


def generate_simulated_assertions(
    region_id: str,
    plant_count: int = 2,
    compute_count: int = 3,
) -> List[Assertion]:
    """
    Generate simulated assertions for testing.

    Creates assertions for specified number of plants and compute nodes.
    """
    pids = [plant_id(f"plant-{i+1}") for i in range(plant_count)]
    cids = [compute_node_id(f"node-{i+1}") for i in range(compute_count)]

    sensor = SimulatedSensor(
        region_id=region_id,
        plant_ids=pids,
        compute_node_ids=cids,
    )

    return sensor.poll()
