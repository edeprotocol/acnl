"""
ACNL Core — Observable Types

Physical and economic observables that constitute the energy-compute field.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Union, Literal


class ObservableCategory(str, Enum):
    """High-level observable categories."""
    ENERGY = "energy"
    COMPUTE = "compute"
    CAPITAL = "capital"
    NETWORK = "network"
    ENVIRONMENT = "environment"


class EnergyObservableKind(str, Enum):
    """Energy-specific observables."""

    # Power (instantaneous)
    GENERATION_POWER = "generation_power"       # MW generated
    CONSUMPTION_POWER = "consumption_power"     # MW consumed
    AVAILABLE_POWER = "available_power"         # MW available headroom
    CURTAILMENT_POWER = "curtailment_power"     # MW curtailed

    # Energy (cumulative)
    ENERGY_GENERATED = "energy_generated"       # kWh over window
    ENERGY_CONSUMED = "energy_consumed"         # kWh over window

    # Grid state
    GRID_FREQUENCY = "grid_frequency"           # Hz (50/60 nominal)
    VOLTAGE_LEVEL = "voltage_level"             # kV
    LINE_LOADING = "line_loading"               # fraction 0..1
    THERMAL_MARGIN = "thermal_margin"           # fraction 0..1 remaining
    PHASE_ANGLE = "phase_angle"                 # degrees

    # Storage
    STORAGE_SOC = "storage_soc"                 # fraction 0..1
    STORAGE_POWER = "storage_power"             # MW (+ = discharge, - = charge)

    # Environment
    CARBON_INTENSITY = "carbon_intensity"       # gCO2/kWh
    TEMP_CELSIUS = "temp_celsius"               # °C
    SOLAR_IRRADIANCE = "solar_irradiance"       # W/m²
    WIND_SPEED = "wind_speed"                   # m/s

    # Economic
    PRICE_ENERGY = "price_energy"               # €/MWh or token/MWh
    PRICE_CAPACITY = "price_capacity"           # €/MW/h

    # Reliability
    OUTAGE = "outage"                           # 0/1 boolean
    FORCED_OUTAGE_RATE = "forced_outage_rate"   # fraction


class ComputeObservableKind(str, Enum):
    """Compute-specific observables."""

    # Utilization
    COMPUTE_UTILIZATION = "compute_utilization"   # fraction 0..1
    MEMORY_UTILIZATION = "memory_utilization"     # fraction 0..1

    # Throughput
    TCU_RATE = "tcu_rate"                         # TCU/s (Trusted Compute Units)
    FLOPS_RATE = "flops_rate"                     # FLOPS
    TOKENS_RATE = "tokens_rate"                   # tokens/s (for LLM inference)

    # Latency
    JOB_LATENCY_MS = "job_latency_ms"             # ms
    QUEUE_DEPTH = "queue_depth"                   # count

    # Quality
    ERROR_RATE = "error_rate"                     # errors/s
    SUCCESS_RATE = "success_rate"                 # fraction 0..1

    # Thermal
    GPU_TEMP_CELSIUS = "gpu_temp_celsius"         # °C
    THROTTLE_FACTOR = "throttle_factor"           # fraction 0..1


class CapitalObservableKind(str, Enum):
    """Capital/economic observables."""

    PRICE_TCU = "price_tcu"                       # €/TCU or token/TCU
    LIQUIDITY = "liquidity"                       # available capital
    CREDIT_LIMIT = "credit_limit"                 # max credit
    CREDIT_USED = "credit_used"                   # current credit
    MARGIN_RATIO = "margin_ratio"                 # fraction


# Union of all observable kinds
ObservableKind = Union[EnergyObservableKind, ComputeObservableKind, CapitalObservableKind, str]

Number = Union[int, float]


@dataclass(frozen=True)
class Observable:
    """
    Single observation of a physical or economic quantity.

    Attributes:
        kind: Type of observable
        value: Numeric value
        unit: Physical unit string
        quality: Data quality indicator
    """
    kind: ObservableKind
    value: Number
    unit: str
    quality: Literal["raw", "filtered", "forecast", "estimated"] = "raw"

    def as_float(self) -> float:
        return float(self.value)

    def __post_init__(self):
        if not isinstance(self.value, (int, float)):
            raise ValueError(f"Observable value must be numeric, got {type(self.value)}")


# Common unit constants
UNIT_MW = "MW"
UNIT_KWH = "kWh"
UNIT_HZ = "Hz"
UNIT_KV = "kV"
UNIT_FRACTION = "fraction"
UNIT_GCO2_KWH = "gCO2/kWh"
UNIT_EUR_MWH = "€/MWh"
UNIT_CELSIUS = "°C"
UNIT_MS = "ms"
UNIT_TCU_S = "TCU/s"
UNIT_COUNT = "count"
