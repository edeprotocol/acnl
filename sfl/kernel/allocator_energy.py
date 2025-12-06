"""
Hook to integrate Energy Mesh tau_limits into SFL Allocator.

This module provides the bridge between Energy Mesh (physical constraints)
and SFL core (pattern allocation).
"""

from __future__ import annotations
from typing import Dict, Optional, Protocol
from dataclasses import dataclass, field

from sfl.energy.model import EntityID, EnergyField


class TauLimitProvider(Protocol):
    """Interface for getting tau limits from Energy Mesh."""

    def get_tau_limit(self, node_id: EntityID) -> float:
        ...

    def get_tau_limits(self) -> Dict[EntityID, float]:
        ...


@dataclass
class EnergyConstrainedAllocator:
    """
    Wrapper that constrains tau_rate by energy availability.

    Integrates with existing SFL Allocator by wrapping tau computation.
    """

    tau_provider: Optional[TauLimitProvider] = None
    pattern_to_node: Dict[str, EntityID] = field(default_factory=dict)

    def set_tau_provider(self, provider: TauLimitProvider) -> None:
        """Set the tau limit provider (typically LFI or RC)."""
        self.tau_provider = provider

    def register_pattern_location(self, pattern_id: str, node_id: EntityID) -> None:
        """Register where a pattern is running."""
        self.pattern_to_node[pattern_id] = node_id

    def constrain_tau(self, pattern_id: str, base_tau: float) -> float:
        """
        Apply energy constraints to base tau.

        Args:
            pattern_id: The pattern requesting allocation
            base_tau: Tau computed by SFL core (based on contribution, etc.)

        Returns:
            Constrained tau_rate, min(base_tau, energy_tau_limit)
        """
        if not self.tau_provider:
            return base_tau

        node_id = self.pattern_to_node.get(pattern_id)
        if not node_id:
            return base_tau

        tau_limit = self.tau_provider.get_tau_limit(node_id)

        return min(base_tau, tau_limit)

    def get_energy_headroom(self, pattern_id: str) -> float:
        """
        Get remaining energy headroom for a pattern.

        Returns fraction in [0, 1] indicating how much of tau_limit is available.
        """
        if not self.tau_provider:
            return 1.0

        node_id = self.pattern_to_node.get(pattern_id)
        if not node_id:
            return 1.0

        tau_limit = self.tau_provider.get_tau_limit(node_id)
        return tau_limit  # simplified: tau_limit is already in [0, ~2]


# Integration example for existing SFL Allocator
def integrate_energy_constraints(allocator, lfi):
    """
    Example of how to integrate with existing SFL Allocator.

    Call this during SFL initialization to enable energy constraints.
    """
    energy_allocator = EnergyConstrainedAllocator()
    energy_allocator.set_tau_provider(lfi)

    # Monkey-patch or extend allocator
    original_compute_tau = allocator.compute_tau_rate

    def constrained_compute_tau(pattern_id: str) -> float:
        base_tau = original_compute_tau(pattern_id)
        return energy_allocator.constrain_tau(pattern_id, base_tau)

    allocator.compute_tau_rate = constrained_compute_tau

    return energy_allocator
