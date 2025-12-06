"""
ACNL Mesh — Event Aggregator

Transforms raw events into LocalField tensors.
Core bridge between event stream and agent-readable fields.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict
import time

from ..core.ids import EntityID, Coord
from ..core.events import Assertion
from ..core.fields import FieldPoint, LocalField
from ..store.event_store import EventStore


@dataclass
class AggregatorConfig:
    """Configuration for field aggregation."""
    window_ms: int = 5_000              # Time window for aggregation
    min_assertions: int = 1             # Minimum assertions per subject
    min_confidence: float = 0.1         # Minimum confidence to include
    decay_factor: float = 0.95          # EWMA decay per second
    reliability_decay: float = 0.99     # Reliability decay per tick without proof


class LocalFieldBuilder:
    """
    Builds LocalField from EventStore.

    Aggregation strategy:
      1. Collect assertions in time window
      2. Group by subject
      3. Compute EWMA of metrics with recency weighting
      4. Compute confidence from assertion count and freshness
      5. Compute reliability from challenge history
    """

    def __init__(
        self,
        store: EventStore,
        region_id: str,
        config: AggregatorConfig | None = None,
    ):
        self.store = store
        self.region_id = region_id
        self.config = config or AggregatorConfig()

        # Track reliability per subject
        self._reliability: Dict[EntityID, float] = defaultdict(lambda: 1.0)

    def build(self, now_ms: int | None = None) -> LocalField:
        """Build LocalField from current events."""

        if now_ms is None:
            now_ms = int(time.time() * 1000)

        # Get assertions in window
        assertions = self.store.get_assertions_in_window(
            region_id=self.region_id,
            window_ms=self.config.window_ms,
            now_ms=now_ms,
        )

        # Group by subject
        by_subject: Dict[EntityID, List[Assertion]] = defaultdict(list)
        for a in assertions:
            by_subject[a.subject].append(a)

        # Build field
        local_field = LocalField(
            region_id=self.region_id,
            generated_at_ms=now_ms,
        )

        for subject, subject_assertions in by_subject.items():
            if len(subject_assertions) < self.config.min_assertions:
                continue

            point = self._build_point(subject, subject_assertions, now_ms)

            if point.confidence >= self.config.min_confidence:
                local_field.points[subject] = point

        return local_field

    def _build_point(
        self,
        subject: EntityID,
        assertions: List[Assertion],
        now_ms: int,
    ) -> FieldPoint:
        """Build single FieldPoint from assertions."""

        # Find most recent coord
        latest = max(assertions, key=lambda a: a.coord.ts_ms)

        point = FieldPoint(
            coord=latest.coord,
            subject=subject,
            last_update_ms=latest.coord.ts_ms,
        )

        # Aggregate metrics with EWMA
        metrics = self._aggregate_metrics(assertions, now_ms)
        point.metrics = metrics

        # Compute confidence
        point.confidence = self._compute_confidence(assertions, now_ms)
        point.assertion_count = len(assertions)

        # Apply reliability from challenge history
        point.reliability = self._reliability[subject]

        return point

    def _aggregate_metrics(
        self,
        assertions: List[Assertion],
        now_ms: int,
    ) -> Dict[str, float]:
        """Aggregate observable values with EWMA."""

        metrics: Dict[str, float] = {}
        weights: Dict[str, float] = {}

        for a in assertions:
            value = a.observable.as_float()
            kind = str(a.observable.kind.value) if hasattr(a.observable.kind, 'value') else str(a.observable.kind)

            # Map observable kind to metric name
            metric_name = self._observable_to_metric(kind)
            if not metric_name:
                continue

            # Recency weight
            age_s = (now_ms - a.coord.ts_ms) / 1000.0
            weight = self.config.decay_factor ** age_s

            if metric_name not in metrics:
                metrics[metric_name] = 0.0
                weights[metric_name] = 0.0

            metrics[metric_name] += value * weight
            weights[metric_name] += weight

        # Normalize
        for metric in metrics:
            if weights[metric] > 0:
                metrics[metric] /= weights[metric]

        return metrics

    def _observable_to_metric(self, kind: str) -> Optional[str]:
        """Map observable kind to field metric name."""
        mapping = {
            "available_power": "available_power_mw",
            "consumption_power": "consumption_power_mw",
            "generation_power": "generation_power_mw",
            "line_loading": "line_loading",
            "thermal_margin": "thermal_margin",
            "thermal_limit": "thermal_margin",
            "carbon_intensity": "carbon_intensity",
            "price_signal": "price_energy",
            "price_energy": "price_energy",
            "compute_utilization": "compute_utilization",
            "memory_utilization": "memory_utilization",
            "temp_celsius": "temp_celsius",
            "temp": "temp_celsius",
            "gpu_temp_celsius": "temp_celsius",
            "error_rate": "error_rate",
            "tcu_rate": "tcu_rate",
            "storage_soc": "storage_soc",
            "grid_frequency": "grid_frequency",
            "voltage_level": "voltage_level",
        }
        return mapping.get(kind)

    def _compute_confidence(
        self,
        assertions: List[Assertion],
        now_ms: int,
    ) -> float:
        """Compute confidence from count, recency, diversity."""

        if not assertions:
            return 0.0

        # Count confidence (saturates at 10)
        count_conf = min(1.0, len(assertions) / 10.0)

        # Recency confidence
        most_recent_ts = max(a.coord.ts_ms for a in assertions)
        age_s = (now_ms - most_recent_ts) / 1000.0
        recency_conf = self.config.decay_factor ** age_s

        # Diversity: number of distinct issuers
        issuers = set(a.issuer for a in assertions)
        diversity_conf = min(1.0, len(issuers) / 3.0)

        return count_conf * recency_conf * diversity_conf

    def update_reliability(self, subject: EntityID, success: bool) -> None:
        """Update reliability based on challenge result."""
        current = self._reliability[subject]
        if success:
            self._reliability[subject] = min(1.0, current + 0.1 * (1 - current))
        else:
            self._reliability[subject] = max(0.0, current * 0.5)

    def decay_reliability(self) -> None:
        """Decay reliability for all subjects (call periodically)."""
        for subject in list(self._reliability.keys()):
            self._reliability[subject] *= self.config.reliability_decay
