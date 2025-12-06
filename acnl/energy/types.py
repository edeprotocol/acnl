from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NewType, Literal, Union
import time

# ============ Entity Identity ============ #

EntityID = NewType("EntityID", str)

EntityKind = Literal[
    "plant",          # generation: nuke, hydro, solar, wind, hydrogen, orbital
    "substation",     # grid hub
    "line",           # transmission line, HVDC
    "storage",        # battery, H2, pumped hydro
    "compute-node",   # GPU/CPU cluster
    "sensor",         # physical sensor
    "pattern",        # SFL pattern
    "sovereign",      # state, central bank
    "lfi",            # Local Field Integrator
    "rc",             # Regional Coordinator
    "gh",             # Global Harmonizer
]


def make_entity_id(kind: EntityKind, name: str) -> EntityID:
    """Create EntityID from kind and name."""
    return EntityID(f"{kind}:{name}")


def parse_entity_id(entity_id: EntityID) -> tuple[str, str]:
    """Parse EntityID into (kind, name)."""
    parts = str(entity_id).split(":", 1)
    if len(parts) == 2:
        return (parts[0], parts[1])
    return ("unknown", str(entity_id))


# ============ Coordinates ============ #

@dataclass(frozen=True)
class Coord:
    """
    Spatio-temporal coordinate in energy-compute graph.

    region_id: hierarchical path, e.g. "earth/eu/fr/rte-1", "orbit/leo-1", "mars/valles-1"
    ts_ms: milliseconds since epoch
    """
    region_id: str
    ts_ms: int

    @staticmethod
    def now(region_id: str) -> "Coord":
        return Coord(region_id=region_id, ts_ms=int(time.time() * 1000))

    def age_ms(self, now_ms: int | None = None) -> int:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return now_ms - self.ts_ms


# ============ Observables ============ #

class EnergyObservableKind(str, Enum):
    # Generation / Consumption
    GENERATION_POWER = "generation_power"       # MW produced
    CONSUMPTION_POWER = "consumption_power"     # MW consumed
    AVAILABLE_POWER = "available_power"         # MW available headroom
    ENERGY_WINDOW = "energy_window"             # kWh over window

    # Grid
    GRID_FREQUENCY = "grid_frequency"           # Hz
    VOLTAGE_LEVEL = "voltage_level"             # kV
    LINE_LOADING = "line_loading"               # fraction 0..1
    THERMAL_MARGIN = "thermal_margin"           # fraction remaining vs limit

    # Storage
    STORAGE_SOC = "storage_soc"                 # fraction 0..1

    # Environment / Cost
    CARBON_INTENSITY = "carbon_intensity"       # gCO2/kWh
    PRICE_SIGNAL = "price_signal"               # €/MWh or token/MWh
    CURTAILMENT = "curtailment"                 # MW curtailed
    OUTAGE = "outage"                           # 0/1 bool
    TEMP_CELSIUS = "temp_celsius"               # °C

    # Compute
    COMPUTE_UTILIZATION = "compute_utilization" # fraction 0..1
    TCU_RATE = "tcu_rate"                       # TCU/s
    ERROR_RATE = "error_rate"                   # errors/s
    LATENCY_MS = "latency_ms"                   # ms

    # Custom
    CUSTOM = "custom"


Number = Union[int, float]


@dataclass(frozen=True)
class Observable:
    """
    Elementary observation from a sensor/node.
    """
    kind: EnergyObservableKind
    value: Union[Number, str]
    unit: str  # "MW", "kWh", "Hz", "gCO2/kWh", "€/MWh", etc.
    quality: Literal["raw", "filtered", "forecast"] = "raw"

    def as_float(self) -> float | None:
        if isinstance(self.value, (int, float)):
            return float(self.value)
        return None
