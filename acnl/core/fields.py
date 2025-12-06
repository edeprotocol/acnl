"""
ACNL Core — Energy-Compute Fields

Fields are tensor views of "what's possible" for a region.
Agents read fields to decide where/when to allocate themselves.

NAIVE DESIGN (rejected):
- Flat database tables
- REST API for each metric

CRITIQUE:
- No native tensor representation
- Query latency incompatible with AGI decision loops
- Human-centric data model

FRACTAL DESIGN (implemented):
- FieldPoint = atomic observation for one subject
- LocalField = tensor aggregation for a region
- Native conversion to numpy/torch tensors
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal, Callable
import time

from .coord import Coord
from .ids import EntityID, entity_kind


# ══════════════════════════════════════════════════════════════════════════════
# FIELD POINT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FieldPoint:
    """
    Single point in the energy-compute field.
    Represents aggregated state of one subject at one coordinate.
    """
    coord: Coord
    subject: EntityID

    # Core metrics (all optional, filled by aggregation)
    metrics: Dict[str, float] = field(default_factory=dict)

    # Quality indicators
    confidence: float = 0.0           # 0..1
    reliability: float = 1.0          # 0..1 (from challenge history)
    assertion_count: int = 0
    last_update_ms: int = 0

    def get(self, metric: str, default: float = 0.0) -> float:
        return self.metrics.get(metric, default)

    def set(self, metric: str, value: float) -> None:
        self.metrics[metric] = value

    @property
    def subject_kind(self) -> str:
        return entity_kind(self.subject)

    # Common metric accessors
    @property
    def available_power_mw(self) -> float:
        return self.get("available_power_mw", 0.0)

    @property
    def consumption_power_mw(self) -> float:
        return self.get("consumption_power_mw", 0.0)

    @property
    def generation_power_mw(self) -> float:
        return self.get("generation_power_mw", 0.0)

    @property
    def carbon_intensity(self) -> float:
        return self.get("carbon_intensity", 0.0)

    @property
    def price_energy(self) -> float:
        return self.get("price_energy", 0.0)

    @property
    def line_loading(self) -> float:
        return self.get("line_loading", 0.0)

    @property
    def compute_utilization(self) -> float:
        return self.get("compute_utilization", 0.0)

    @property
    def temp_celsius(self) -> float:
        return self.get("temp_celsius", 0.0)

    @property
    def price_e_per_mwh(self) -> float:
        """Price per MWh (alias for price_energy)."""
        return self.get("price_energy", 0.0)

    @property
    def price_tcu(self) -> float:
        """Price per TCU (Trusted Compute Unit)."""
        return self.get("price_tcu", 0.0)

    @property
    def congestion(self) -> float:
        """Congestion level 0..1 (derived from line_loading)."""
        return self.get("line_loading", 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL FIELD
# ══════════════════════════════════════════════════════════════════════════════

# Standard feature keys for tensor export
STANDARD_ENERGY_FEATURES = [
    "available_power_mw",
    "consumption_power_mw",
    "generation_power_mw",
    "line_loading",
    "thermal_margin",
    "carbon_intensity",
    "price_energy",
    "reliability",
    "confidence",
]

STANDARD_COMPUTE_FEATURES = [
    "compute_utilization",
    "memory_utilization",
    "tcu_rate",
    "error_rate",
    "temp_celsius",
    "available_power_mw",
    "price_energy",
    "reliability",
    "confidence",
]


@dataclass
class LocalField:
    """
    Tensor view of energy-compute state for a region.

    This is what agents read to make allocation decisions.
    """
    region_id: str
    generated_at_ms: int
    points: Dict[EntityID, FieldPoint] = field(default_factory=dict)

    # ──────────────────────────────────────────────────────────────────────────
    # Point access
    # ──────────────────────────────────────────────────────────────────────────

    def get_point(self, subject: EntityID) -> Optional[FieldPoint]:
        return self.points.get(subject)

    def all_points(self) -> List[FieldPoint]:
        return list(self.points.values())

    def filter_by_kind(self, kind: str) -> List[FieldPoint]:
        return [p for p in self.points.values() if p.subject_kind == kind]

    def compute_nodes(self) -> List[FieldPoint]:
        return self.filter_by_kind("compute-node")

    def plants(self) -> List[FieldPoint]:
        return self.filter_by_kind("plant")

    def lines(self) -> List[FieldPoint]:
        return self.filter_by_kind("line")

    def storage(self) -> List[FieldPoint]:
        return self.filter_by_kind("storage")

    # ──────────────────────────────────────────────────────────────────────────
    # Aggregate metrics
    # ──────────────────────────────────────────────────────────────────────────

    def total(self, metric: str) -> float:
        return sum(p.get(metric, 0.0) for p in self.points.values())

    def avg(self, metric: str) -> float:
        values = [p.get(metric) for p in self.points.values() if metric in p.metrics]
        return sum(values) / len(values) if values else 0.0

    def total_available_power(self) -> float:
        return self.total("available_power_mw")

    def total_consumption(self) -> float:
        return self.total("consumption_power_mw")

    def total_generation(self) -> float:
        return self.total("generation_power_mw")

    def avg_carbon_intensity(self) -> float:
        return self.avg("carbon_intensity")

    def avg_line_loading(self) -> float:
        return self.avg("line_loading")

    def avg_price_energy(self) -> float:
        return self.avg("price_energy")

    # ──────────────────────────────────────────────────────────────────────────
    # Ranking
    # ──────────────────────────────────────────────────────────────────────────

    def top_k_by(self, metric: str, k: int, descending: bool = True) -> List[FieldPoint]:
        sorted_points = sorted(
            self.points.values(),
            key=lambda p: p.get(metric, float('-inf') if descending else float('inf')),
            reverse=descending,
        )
        return sorted_points[:k]

    def sorted_by_cost(self) -> List[FieldPoint]:
        """Sort points by cost (price + carbon weighted)."""
        return sorted(
            self.points.values(),
            key=lambda p: (p.price_energy + p.carbon_intensity * 0.1, -p.reliability),
        )

    def sorted_by_efficiency(self) -> List[FieldPoint]:
        """Sort compute nodes by efficiency (low carbon, high reliability)."""
        return sorted(
            self.compute_nodes(),
            key=lambda p: (
                p.carbon_intensity,
                1 - p.reliability,
                p.price_energy,
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Tensor export
    # ──────────────────────────────────────────────────────────────────────────

    def as_tensor(
        self,
        feature_keys: List[str],
        subject_filter: Optional[Callable[[EntityID], bool]] = None,
        backend: Literal["numpy", "torch"] = "numpy",
    ):
        """
        Convert field to tensor for agent consumption.

        Returns:
            (subject_ids, tensor) where tensor has shape (n_subjects, n_features)
        """
        from .tensors import field_to_tensor
        return field_to_tensor(self, feature_keys, subject_filter, backend)

    def as_compute_tensor(self, backend: Literal["numpy", "torch"] = "numpy"):
        """Tensor of compute nodes with standard features."""
        return self.as_tensor(
            STANDARD_COMPUTE_FEATURES,
            subject_filter=lambda s: entity_kind(s) == "compute-node",
            backend=backend,
        )

    def as_energy_tensor(self, backend: Literal["numpy", "torch"] = "numpy"):
        """Tensor of all energy assets with standard features."""
        return self.as_tensor(
            STANDARD_ENERGY_FEATURES,
            backend=backend,
        )


@dataclass
class RegionalField:
    """
    Aggregated field from multiple LFIs for a region.
    Used by Regional Coordinator.
    """
    region_id: str
    generated_at_ms: int
    lfi_fields: Dict[str, LocalField] = field(default_factory=dict)
    aggregated: Optional[LocalField] = None

    def add_lfi_field(self, lfi_id: str, local_field: LocalField) -> None:
        self.lfi_fields[lfi_id] = local_field

    def aggregate(self) -> LocalField:
        """Aggregate LFI fields into single regional field."""
        agg = LocalField(
            region_id=self.region_id,
            generated_at_ms=self.generated_at_ms,
        )

        for lfi_field in self.lfi_fields.values():
            for subject, point in lfi_field.points.items():
                # Merge or create point
                if subject in agg.points:
                    # Simple averaging for now
                    existing = agg.points[subject]
                    for metric, value in point.metrics.items():
                        if metric in existing.metrics:
                            existing.metrics[metric] = (existing.metrics[metric] + value) / 2
                        else:
                            existing.metrics[metric] = value
                    existing.confidence = (existing.confidence + point.confidence) / 2
                    existing.reliability = min(existing.reliability, point.reliability)
                else:
                    # Copy point with reduced confidence
                    new_point = FieldPoint(
                        coord=Coord(self.region_id, self.generated_at_ms),
                        subject=subject,
                        metrics=dict(point.metrics),
                        confidence=point.confidence * 0.9,  # decay for aggregation
                        reliability=point.reliability,
                        assertion_count=point.assertion_count,
                    )
                    agg.points[subject] = new_point

        self.aggregated = agg
        return agg
