from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
import time

from .model import (
    Assertion,
    EnergyField,
    EnergyFieldPoint,
    EntityID,
    Coord,
    EnergyObservableKind,
    parse_entity_id,
)
from .store import EventStore


@dataclass
class FieldConfig:
    horizon_ms: int = 5_000       # aggregation window
    min_confidence: float = 0.1   # minimum confidence to include point
    min_assertions: int = 1       # minimum assertions per subject
    decay_factor: float = 0.9     # recency weighting


class EnergyFieldBuilder:
    """Transforms local Assertions into EnergyField for AGI consumption."""

    def __init__(self, store: EventStore, config: FieldConfig, region_id: str):
        self.store = store
        self.config = config
        self.region_id = region_id

    def build(self, now_ms: int | None = None) -> EnergyField:
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        window_start = now_ms - self.config.horizon_ms

        # Get assertions in window
        assertions = self.store.get_assertions_in_window(
            region_id=self.region_id,
            start_ms=window_start,
            end_ms=now_ms,
        )

        # Group by subject
        by_subject: Dict[EntityID, List[Assertion]] = {}
        for a in assertions:
            by_subject.setdefault(a.subject, []).append(a)

        points: List[EnergyFieldPoint] = []

        for subject, subject_assertions in by_subject.items():
            if len(subject_assertions) < self.config.min_assertions:
                continue

            # Aggregate metrics with recency weighting
            metrics = self._aggregate_metrics(subject_assertions, now_ms)

            # Compute confidence based on assertion count and recency
            confidence = self._compute_confidence(subject_assertions, now_ms)

            if confidence < self.config.min_confidence:
                continue

            points.append(
                EnergyFieldPoint(
                    coord=Coord(region_id=self.region_id, ts_ms=now_ms),
                    subject=subject,
                    metrics=metrics,
                    confidence=confidence,
                )
            )

        return EnergyField(
            region_id=self.region_id,
            points=points,
            generated_at_ms=now_ms,
        )

    def _aggregate_metrics(
        self, assertions: List[Assertion], now_ms: int
    ) -> Dict[str, float]:
        """Aggregate observables into metrics with EWMA."""
        metrics: Dict[str, float] = {}
        weights: Dict[str, float] = {}

        for a in assertions:
            if not isinstance(a.observable.value, (int, float)):
                continue

            key = a.observable.kind.value
            value = float(a.observable.value)

            # Recency weight
            age_ms = now_ms - a.coord.ts_ms
            weight = self.config.decay_factor ** (age_ms / 1000.0)

            if key not in metrics:
                metrics[key] = 0.0
                weights[key] = 0.0

            metrics[key] += value * weight
            weights[key] += weight

        # Normalize
        for key in metrics:
            if weights[key] > 0:
                metrics[key] /= weights[key]

        return metrics

    def _compute_confidence(
        self, assertions: List[Assertion], now_ms: int
    ) -> float:
        """Confidence based on count and recency."""
        if not assertions:
            return 0.0

        # Base confidence from count (saturates at 10)
        count_confidence = min(1.0, len(assertions) / 10.0)

        # Recency: most recent assertion
        most_recent = max(a.coord.ts_ms for a in assertions)
        age_ms = now_ms - most_recent
        recency_confidence = self.config.decay_factor ** (age_ms / 1000.0)

        # Diversity: number of distinct issuers
        issuers = set(a.issuer for a in assertions)
        diversity_confidence = min(1.0, len(issuers) / 3.0)

        return count_confidence * recency_confidence * diversity_confidence
