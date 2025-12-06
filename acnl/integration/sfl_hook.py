"""
ACNL Integration — SFL Hook

Integration hooks for Synthetic Field Layer (SFL) patterns.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Callable, Any

from ..core.ids import EntityID, make_entity_id
from ..control.lfi import LocalFieldIntegrator


@dataclass
class TauAllocation:
    """Tau allocation result for a pattern."""
    pattern_id: EntityID
    tau_limit: float
    energy_headroom_mw: float
    carbon_intensity: float
    region_id: str
    confidence: float


class SFLEnergyHook:
    """
    Hook for SFL patterns to query energy constraints.

    Patterns use this to:
    1. Get their current tau limit
    2. Check energy availability before spawning
    3. Report actual consumption back to mesh
    """

    def __init__(self, lfi: LocalFieldIntegrator):
        self._lfi = lfi
        self._pattern_nodes: Dict[EntityID, EntityID] = {}

    def register_pattern(
        self,
        pattern_name: str,
        compute_node_name: str,
    ) -> EntityID:
        """Register a pattern and its hosting compute node."""
        pid = make_entity_id("pattern", pattern_name)
        nid = make_entity_id("compute-node", compute_node_name)
        self._pattern_nodes[pid] = nid
        return pid

    def get_tau_limit(self, pattern_id: EntityID) -> float:
        """Get current tau limit for a pattern."""
        node_id = self._pattern_nodes.get(pattern_id)
        if node_id is None:
            return 0.0
        return self._lfi.get_tau_limit(node_id)

    def get_allocation(self, pattern_id: EntityID) -> Optional[TauAllocation]:
        """Get full allocation details for a pattern."""
        node_id = self._pattern_nodes.get(pattern_id)
        if node_id is None:
            return None

        field = self._lfi.get_field()
        if field is None:
            return None

        point = field.get_point(node_id)
        if point is None:
            return None

        tau_limit = self._lfi.get_tau_limit(node_id)

        return TauAllocation(
            pattern_id=pattern_id,
            tau_limit=tau_limit,
            energy_headroom_mw=point.available_power_mw,
            carbon_intensity=field.avg_carbon_intensity(),
            region_id=self._lfi.region_id,
            confidence=point.confidence,
        )

    def can_spawn(
        self,
        pattern_id: EntityID,
        required_tau: float = 0.1,
    ) -> bool:
        """Check if a pattern can spawn given energy constraints."""
        allocation = self.get_allocation(pattern_id)
        if allocation is None:
            return False
        return allocation.tau_limit >= required_tau

    def get_regional_summary(self) -> Dict[str, Any]:
        """Get regional energy summary."""
        return self._lfi.get_summary()


class EnergyConstrainedAllocator:
    """
    Allocator that respects energy constraints.

    Wraps pattern allocation decisions with energy checks.
    """

    def __init__(
        self,
        hook: SFLEnergyHook,
        base_allocator: Optional[Callable[[EntityID, float], bool]] = None,
    ):
        self._hook = hook
        self._base_allocator = base_allocator

    def allocate(
        self,
        pattern_id: EntityID,
        requested_tau: float,
    ) -> float:
        """
        Allocate tau to a pattern.

        Returns actual allocated tau (may be less than requested).
        """
        allocation = self._hook.get_allocation(pattern_id)
        if allocation is None:
            return 0.0

        # Clamp to available
        actual_tau = min(requested_tau, allocation.tau_limit)

        # Run base allocator if provided
        if self._base_allocator and actual_tau > 0:
            if not self._base_allocator(pattern_id, actual_tau):
                return 0.0

        return actual_tau

    def batch_allocate(
        self,
        requests: Dict[EntityID, float],
    ) -> Dict[EntityID, float]:
        """Allocate tau to multiple patterns."""
        allocations = {}
        for pid, requested in requests.items():
            allocations[pid] = self.allocate(pid, requested)
        return allocations
