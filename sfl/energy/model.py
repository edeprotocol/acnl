from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Literal, Union
import time

# ============ IDs & Coordinates ============ #

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

EntityID = str  # format: "{kind}:{opaque_id}"


def make_entity_id(kind: EntityKind, opaque_id: str) -> EntityID:
    return f"{kind}:{opaque_id}"


def parse_entity_id(entity_id: EntityID) -> tuple[str, str]:
    parts = entity_id.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("unknown", entity_id)


@dataclass(frozen=True)
class Coord:
    """Spatio-temporal coordinate in energy-network regime."""
    region_id: str   # e.g. "earth/eu-fr-rte-1", "orbit/leo-1", "mars/valles-1"
    ts_ms: int       # local timestamp (ms since epoch)

    @staticmethod
    def now(region_id: str) -> "Coord":
        return Coord(region_id=region_id, ts_ms=int(time.time() * 1000))


# ============ Observables ============ #

class EnergyObservableKind(str, Enum):
    GENERATION_POWER = "generation_power"       # MW
    CONSUMPTION_POWER = "consumption_power"     # MW
    AVAILABLE_POWER = "available_power"         # MW
    ENERGY_WINDOW = "energy_window"             # kWh over window
    GRID_FREQUENCY = "grid_frequency"           # Hz
    VOLTAGE_LEVEL = "voltage_level"             # kV
    LINE_LOADING = "line_loading"               # fraction 0..1
    STORAGE_SOC = "storage_soc"                 # fraction 0..1
    CARBON_INTENSITY = "carbon_intensity"       # gCO2/kWh
    PRICE_SIGNAL = "price_signal"               # token/MWh or fiat/MWh
    CURTAILMENT = "curtailment"                 # MW
    OUTAGE = "outage"                           # bool as 0/1
    THERMAL_MARGIN = "thermal_margin"           # fraction remaining vs limit
    LATENCY_MS = "latency_ms"                   # ms
    COMPUTE_UTILIZATION = "compute_utilization" # fraction 0..1
    TEMP_CELSIUS = "temp_celsius"               # °C
    TCU_RATE = "tcu_rate"                       # TCU/s
    ERROR_RATE = "error_rate"                   # errors/s
    CUSTOM = "custom"


@dataclass
class Observable:
    kind: EnergyObservableKind
    value: Union[float, int, str]
    unit: str  # "MW", "kWh", "Hz", "gCO2/kWh", etc.
    meta: Dict[str, str] = field(default_factory=dict)


# ============ RFL-E Core Objects ============ #

@dataclass
class Assertion:
    """Single observation from an issuer about a subject."""
    assertion_id: str
    issuer: EntityID
    subject: EntityID
    coord: Coord
    observable: Observable

    @staticmethod
    def create(
        issuer: EntityID,
        subject: EntityID,
        coord: Coord,
        observable: Observable
    ) -> "Assertion":
        import uuid
        return Assertion(
            assertion_id=str(uuid.uuid4()),
            issuer=issuer,
            subject=subject,
            coord=coord,
            observable=observable,
        )


@dataclass
class Claim:
    """Aggregated claim from multiple assertions."""
    claim_id: str
    subject: EntityID
    coord: Coord
    assertions: List[Assertion]
    confidence: float = 0.0  # 0..1


@dataclass
class Challenge:
    """Active probe to verify physical state."""
    challenge_id: str
    challenger: EntityID
    target: EntityID
    coord: Coord
    challenge_type: str  # "power_correlation", "latency_check", "compute_benchmark"
    payload: Dict[str, Union[float, int, str]]
    timeout_ms: int
    status: str = "pending"  # pending, completed, failed, timeout


@dataclass
class Proof:
    """Response to a challenge."""
    proof_id: str
    challenge_id: str
    responder: EntityID
    coord: Coord
    result: Dict[str, Union[float, int, str]]
    verified: bool = False
    verification_method: str = ""


# ============ Energy Field ============ #

@dataclass
class EnergyFieldPoint:
    """Single point in the energy field, representing state of an entity."""
    coord: Coord
    subject: EntityID
    metrics: Dict[str, float]  # observable_kind -> value
    confidence: float  # 0..1, based on assertion count and recency

    def get_metric(self, kind: EnergyObservableKind, default: float = 0.0) -> float:
        return self.metrics.get(kind.value, default)


@dataclass
class EnergyField:
    """Aggregated energy field for a region."""
    region_id: str
    points: List[EnergyFieldPoint]
    generated_at_ms: int

    def get_point(self, subject: EntityID) -> EnergyFieldPoint | None:
        for p in self.points:
            if p.subject == subject:
                return p
        return None

    def get_compute_nodes(self) -> List[EnergyFieldPoint]:
        return [p for p in self.points if parse_entity_id(p.subject)[0] == "compute-node"]

    def total_available_power(self) -> float:
        return sum(
            p.get_metric(EnergyObservableKind.AVAILABLE_POWER)
            for p in self.points
        )

    def avg_carbon_intensity(self) -> float:
        intensities = [
            p.get_metric(EnergyObservableKind.CARBON_INTENSITY)
            for p in self.points
            if p.get_metric(EnergyObservableKind.CARBON_INTENSITY) > 0
        ]
        return sum(intensities) / max(len(intensities), 1)
