"""
ACNL Agent — Agent Client

Tensor-native API for patterns/agents to interact with the energy mesh.

This is NOT a REST API. This is what an AGI pattern uses to:
- Query the energy field
- Get tau limits
- Register consumption
- Respond to challenges
- Emit assertions, claims, challenges, proofs

This is the MANDATORY interface for agents/AGI/SSI to interact with the
energy-compute fractal mesh.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

from ..core.ids import EntityID, pattern_id, Coord
from ..core.coord import RegionID
from ..core.fields import LocalField, FieldPoint, STANDARD_COMPUTE_FEATURES
from ..core.events import ComputeEvent, Assertion, Claim, Challenge, Proof
from ..core.tensors import field_to_tensor
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

    # ──────────────────────────────────────────────────────────────────────────
    # Event emission API (for agents/AGI/SSI)
    # ──────────────────────────────────────────────────────────────────────────

    def emit_assertions(self, assertions: List[Assertion]) -> None:
        """
        Emit multiple assertions to the event store.

        This is the primary way for agents to report observed state
        (energy readings, compute metrics, etc.) to the mesh.
        """
        for assertion in assertions:
            self._lfi.store.append(assertion)

    def emit_claim(self, claim: Claim) -> None:
        """
        Emit a claim to the event store.

        Claims bundle assertions together and represent a coherent
        statement about the state of an entity.
        """
        self._lfi.store.append(claim)

    def issue_challenge(self, challenge: Challenge) -> None:
        """
        Issue a challenge for physical verification.

        Challenges are used to verify that reported state matches
        physical reality (e.g., power consumption correlates with compute).
        """
        self._lfi.store.append(challenge)

    def submit_proof(self, proof: Proof) -> None:
        """
        Submit a proof in response to a challenge.

        Proofs contain evidence that the challenged entity's behavior
        matches its reported state.
        """
        self._lfi.store.append(proof)

    # ──────────────────────────────────────────────────────────────────────────
    # Field query API (tensor-native)
    # ──────────────────────────────────────────────────────────────────────────

    def get_local_field(self, region_id: RegionID, horizon_ms: int = 5000) -> Optional[LocalField]:
        """
        Get local field for a specific region.

        Args:
            region_id: The region to query (e.g., "earth/us/west")
            horizon_ms: Time horizon for aggregation in milliseconds

        Returns:
            LocalField containing aggregated state, or None if no data
        """
        # If querying own region, use cached field
        if region_id == self._lfi.region_id:
            return self._lfi.get_field()

        # For other regions, we would need to query the RC or GH
        # For now, return None (cross-region queries require mesh routing)
        return None

    def get_local_field_tensor(
        self,
        region_id: RegionID,
        horizon_ms: int = 5000,
        feature_keys: List[str] | None = None,
    ) -> Tuple[np.ndarray, Dict[str, int]]:
        """
        Get local field as a tensor for ML/AGI consumption.

        Args:
            region_id: The region to query
            horizon_ms: Time horizon for aggregation
            feature_keys: Optional list of features to include

        Returns:
            (tensor, feature_index) where:
            - tensor has shape (n_subjects, n_features)
            - feature_index maps feature name -> column index
        """
        field = self.get_local_field(region_id, horizon_ms)

        if field is None:
            features = feature_keys or STANDARD_COMPUTE_FEATURES
            empty = np.zeros((0, len(features)), dtype=np.float32)
            feature_index = {f: i for i, f in enumerate(features)}
            return empty, feature_index

        features = feature_keys or STANDARD_COMPUTE_FEATURES
        tensor = field_to_tensor(field, features)
        feature_index = {f: i for i, f in enumerate(features)}

        return tensor, feature_index

    # ──────────────────────────────────────────────────────────────────────────
    # Convenience methods for common operations
    # ──────────────────────────────────────────────────────────────────────────

    def get_tau(self) -> float:
        """Get current tau limit (shorthand for get_tau_limit)."""
        return self.get_tau_limit()

    def observe_power(self, subject: EntityID, power_mw: float) -> Assertion:
        """
        Create and emit an assertion about power consumption.

        Args:
            subject: The entity being observed
            power_mw: Power consumption in MW

        Returns:
            The created assertion
        """
        from ..core.observables import Observable, EnergyObservableKind, UNIT_MW

        assertion = Assertion.create(
            issuer=self._pattern_id,
            subject=subject,
            coord=Coord.now(self._lfi.region_id),
            observable=Observable(
                kind=EnergyObservableKind.CONSUMPTION_POWER,
                value=power_mw,
                unit=UNIT_MW,
            ),
        )
        self._lfi.store.append(assertion)
        return assertion
