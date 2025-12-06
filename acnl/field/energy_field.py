from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from acnl.energy.types import EntityID, Coord, EnergyObservableKind, Observable, parse_entity_id
from acnl.energy.events import Assertion, SigEnvelope
from acnl.energy.store import EnergyEventStore


@dataclass
class EnergyFieldPoint:
    """
    A point in the energy field representing a single entity's state.
    """
    subject: EntityID
    coord: Coord
    metrics: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    issuer_count: int = 0
    assertion_count: int = 0

    # Explicit typed fields for common metrics
    available_power_mw: float = 0.0
    consumption_power_mw: float = 0.0
    generation_power_mw: float = 0.0
    carbon_intensity: float = 0.0
    compute_utilization: float = 0.0
    grid_frequency_hz: float = 50.0
    storage_soc: float = 0.0

    def get_metric(self, kind: EnergyObservableKind) -> float:
        """Get a metric value by kind."""
        return self.metrics.get(kind.value, 0.0)

    def get_entity_kind(self) -> str:
        """Get the kind portion of the entity ID."""
        kind, _ = parse_entity_id(self.subject)
        return kind


@dataclass
class EnergyField:
    """
    Aggregated energy field for a region at a point in time.
    """
    region_id: str
    timestamp_ms: int
    points: List[EnergyFieldPoint] = field(default_factory=list)

    def get_point(self, subject: EntityID) -> Optional[EnergyFieldPoint]:
        """Get point for a specific subject."""
        for p in self.points:
            if p.subject == subject:
                return p
        return None

    def get_compute_nodes(self) -> List[EnergyFieldPoint]:
        """Get all compute node points."""
        return [p for p in self.points if p.get_entity_kind() == "compute-node"]

    def get_plants(self) -> List[EnergyFieldPoint]:
        """Get all generation plant points."""
        return [p for p in self.points if p.get_entity_kind() == "plant"]

    def get_storage(self) -> List[EnergyFieldPoint]:
        """Get all storage points."""
        return [p for p in self.points if p.get_entity_kind() == "storage"]

    def total_available_power(self) -> float:
        """Total available power across all points."""
        return sum(p.available_power_mw for p in self.points)

    def total_consumption(self) -> float:
        """Total consumption across all points."""
        return sum(p.consumption_power_mw for p in self.points)

    def total_generation(self) -> float:
        """Total generation across all points."""
        return sum(p.generation_power_mw for p in self.points)

    def average_carbon_intensity(self) -> float:
        """Average carbon intensity weighted by generation."""
        total_gen = 0.0
        weighted_carbon = 0.0
        for p in self.get_plants():
            gen = p.generation_power_mw
            if gen > 0:
                total_gen += gen
                weighted_carbon += gen * p.carbon_intensity
        return weighted_carbon / total_gen if total_gen > 0 else 0.0


@dataclass
class FieldConfig:
    """Configuration for EnergyFieldBuilder."""
    horizon_ms: int = 15 * 60 * 1000  # 15 minutes
    decay_factor: float = 0.9  # EWMA decay
    min_confidence: float = 0.1
    min_assertions: int = 1


class EnergyFieldBuilder:
    """
    Builds an EnergyField from assertions in the store.

    Uses EWMA (Exponential Weighted Moving Average) with time decay
    to aggregate multiple assertions into a coherent field.
    """

    def __init__(
        self,
        store: EnergyEventStore,
        config: FieldConfig | None = None,
        region_id: str = "default",
    ):
        self._store = store
        self._config = config or FieldConfig()
        self._region_id = region_id

    def build(self, now_ms: int | None = None) -> EnergyField:
        """Build energy field from current assertions."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        since_ms = now_ms - self._config.horizon_ms

        # Get all assertions in time window
        assertions = self._store.get_assertions(since_ms=since_ms, until_ms=now_ms)

        # Group by subject
        by_subject: Dict[EntityID, List[SigEnvelope[Assertion]]] = {}
        for env in assertions:
            subject = env.payload.subject
            if subject not in by_subject:
                by_subject[subject] = []
            by_subject[subject].append(env)

        # Build points
        points: List[EnergyFieldPoint] = []
        for subject, envs in by_subject.items():
            point = self._build_point(subject, envs, now_ms)
            if point.confidence >= self._config.min_confidence:
                points.append(point)

        return EnergyField(
            region_id=self._region_id,
            timestamp_ms=now_ms,
            points=points,
        )

    def _build_point(
        self,
        subject: EntityID,
        envs: List[SigEnvelope[Assertion]],
        now_ms: int,
    ) -> EnergyFieldPoint:
        """Build a single field point from assertions."""
        # Aggregate metrics using EWMA
        metrics: Dict[str, float] = {}
        weights: Dict[str, float] = {}

        issuers: Set[EntityID] = set()

        for env in envs:
            assertion = env.payload
            issuers.add(assertion.issuer)

            age_ms = now_ms - assertion.coord.ts_ms
            # Exponential decay based on age
            weight = math.exp(-age_ms / (self._config.horizon_ms * self._config.decay_factor))

            kind = assertion.observable.kind.value
            value = assertion.observable.as_float()

            if value is not None:
                if kind not in metrics:
                    metrics[kind] = 0.0
                    weights[kind] = 0.0

                metrics[kind] += value * weight
                weights[kind] += weight

        # Normalize by weights
        for kind in metrics:
            if weights[kind] > 0:
                metrics[kind] /= weights[kind]

        # Calculate confidence based on:
        # - Number of assertions
        # - Number of unique issuers
        # - Recency of most recent assertion
        assertion_score = min(len(envs) / 10.0, 1.0)
        issuer_score = min(len(issuers) / 3.0, 1.0)

        most_recent = max(env.payload.coord.ts_ms for env in envs)
        recency_score = math.exp(-(now_ms - most_recent) / self._config.horizon_ms)

        confidence = (assertion_score * 0.3 + issuer_score * 0.4 + recency_score * 0.3)

        # Get latest coord
        latest_env = max(envs, key=lambda e: e.payload.coord.ts_ms)
        coord = latest_env.payload.coord

        # Build point with typed fields
        point = EnergyFieldPoint(
            subject=subject,
            coord=coord,
            metrics=metrics,
            confidence=confidence,
            issuer_count=len(issuers),
            assertion_count=len(envs),
        )

        # Set typed fields from metrics
        point.available_power_mw = metrics.get(EnergyObservableKind.AVAILABLE_POWER.value, 0.0)
        point.consumption_power_mw = metrics.get(EnergyObservableKind.CONSUMPTION_POWER.value, 0.0)
        point.generation_power_mw = metrics.get(EnergyObservableKind.GENERATION_POWER.value, 0.0)
        point.carbon_intensity = metrics.get(EnergyObservableKind.CARBON_INTENSITY.value, 0.0)
        point.compute_utilization = metrics.get(EnergyObservableKind.COMPUTE_UTILIZATION.value, 0.0)
        point.grid_frequency_hz = metrics.get(EnergyObservableKind.GRID_FREQUENCY.value, 50.0)
        point.storage_soc = metrics.get(EnergyObservableKind.STORAGE_SOC.value, 0.0)

        return point
