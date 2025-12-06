"""
ACNL Agent — Agent Client

Tensor-native API for patterns/agents to interact with the energy mesh.

This is NOT a REST API. This is what an AGI pattern uses to:
- Query the energy field
- Get tau limits
- Register consumption
- Respond to challenges
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

from ..core.ids import EntityID, pattern_id, Coord
from ..core.fields import LocalField, FieldPoint, STANDARD_COMPUTE_FEATURES
from ..core.events import ComputeEvent
from ..control.lfi import LocalFieldIntegrator


@dataclass
class AllocationResult:
    """Result of a tau allocation request."""
    pattern_id: EntityID
    allocated_tau: float
    energy_headroom_mw: float
    carbon_intensity: float
    region_id: str
    confidence: float


class AgentClient:
    """
    Client for patterns/agents to interact with the energy mesh.

    Tensor-native: returns numpy/torch tensors, not JSON.
    """

    def __init__(self, lfi: LocalFieldIntegrator, pattern_name: str):
        self._lfi = lfi
        self._pattern_id = pattern_id(pattern_name)
        self._compute_node: Optional[EntityID] = None

    @property
    def pattern_id(self) -> EntityID:
        return self._pattern_id

    @property
    def region_id(self) -> str:
        return self._lfi.region_id

    def register_on_node(self, compute_node_id: EntityID) -> None:
        """Register this pattern on a compute node."""
        self._compute_node = compute_node_id

    def get_field(self) -> Optional[LocalField]:
        """Get current energy field."""
        return self._lfi.get_field()

    def get_field_tensor(
        self,
        feature_keys: List[str] | None = None,
        backend: str = "numpy",
    ) -> Tuple[List[EntityID], Any]:
        """
        Get energy field as tensor.

        Returns:
            (subject_ids, tensor) where tensor has shape (n_subjects, n_features)
        """
        field = self._lfi.get_field()
        if field is None:
            features = feature_keys or STANDARD_COMPUTE_FEATURES
            empty = np.zeros((0, len(features)), dtype=np.float32)
            return [], empty

        features = feature_keys or STANDARD_COMPUTE_FEATURES
        return field.as_tensor(features, backend=backend)

    def get_tau_limit(self) -> float:
        """Get current tau limit for this pattern's compute node."""
        if self._compute_node is None:
            return 0.0
        return self._lfi.get_tau_limit(self._compute_node)

    def get_all_tau_limits(self) -> Dict[EntityID, float]:
        """Get tau limits for all compute nodes."""
        return self._lfi.get_tau_limits()

    def get_allocation(self) -> Optional[AllocationResult]:
        """Get full allocation details for this pattern."""
        if self._compute_node is None:
            return None

        field = self._lfi.get_field()
        if field is None:
            return None

        point = field.get_point(self._compute_node)
        if point is None:
            return None

        tau_limit = self._lfi.get_tau_limit(self._compute_node)

        return AllocationResult(
            pattern_id=self._pattern_id,
            allocated_tau=tau_limit,
            energy_headroom_mw=point.available_power_mw,
            carbon_intensity=field.avg_carbon_intensity(),
            region_id=self._lfi.region_id,
            confidence=point.confidence,
        )

    def can_run(self, required_tau: float = 0.1) -> bool:
        """Check if pattern can run given energy constraints."""
        tau = self.get_tau_limit()
        return tau >= required_tau

    def report_compute(
        self,
        job_id: str,
        tcu_used: float,
        energy_kwh: float,
        latency_ms: float,
        success: bool,
        info_gain_bits: Optional[float] = None,
    ) -> ComputeEvent:
        """Report compute consumption."""
        if self._compute_node is None:
            raise ValueError("Pattern not registered on a compute node")

        event = ComputeEvent.create(
            pattern_id=self._pattern_id,
            compute_node_id=self._compute_node,
            coord=Coord.now(self._lfi.region_id),
            job_id=job_id,
            tcu_used=tcu_used,
            energy_kwh=energy_kwh,
            latency_ms=latency_ms,
            success=success,
            info_gain_bits=info_gain_bits,
        )

        self._lfi.store.add_compute_event(event)
        return event

    def get_efficient_nodes(self, top_k: int = 5) -> List[FieldPoint]:
        """Get most efficient compute nodes (low carbon, high reliability)."""
        field = self._lfi.get_field()
        if field is None:
            return []
        return field.sorted_by_efficiency()[:top_k]

    def get_regional_summary(self) -> Dict[str, Any]:
        """Get regional energy summary."""
        return self._lfi.get_summary()
