from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional

from acnl.energy.types import EntityID
from acnl.field.energy_field import EnergyField, EnergyFieldPoint


@dataclass
class TauLimitResult:
    """Result of tau limit computation for a node."""
    node_id: EntityID
    tau_limit: float  # 0..2 typically
    reason: str
    energy_headroom_mw: float
    carbon_factor: float
    confidence: float


class TauLimitPolicy(ABC):
    """
    Abstract policy for computing tau limits from energy state.

    Tau (τ) is the rate limit for compute operations.
    Higher tau = more compute allowed.
    """

    @abstractmethod
    def compute(
        self,
        point: EnergyFieldPoint,
        field: EnergyField,
        constraints: Dict[str, float] | None = None,
    ) -> TauLimitResult:
        """Compute tau limit for a single point."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Policy name for logging/debugging."""
        ...


class DefaultTauLimitPolicy(TauLimitPolicy):
    """
    Default tau limit policy based on:
    - Available power headroom
    - Carbon intensity (throttle high-carbon)
    - Grid frequency deviation
    - Regional constraints
    """

    def __init__(
        self,
        base_tau: float = 1.0,
        max_tau: float = 2.0,
        min_tau: float = 0.1,
        carbon_threshold: float = 200.0,  # gCO2/kWh
        freq_deadband: float = 0.05,  # Hz deviation from 50Hz
    ):
        self._base_tau = base_tau
        self._max_tau = max_tau
        self._min_tau = min_tau
        self._carbon_threshold = carbon_threshold
        self._freq_deadband = freq_deadband

    def name(self) -> str:
        return "default"

    def compute(
        self,
        point: EnergyFieldPoint,
        field: EnergyField,
        constraints: Dict[str, float] | None = None,
    ) -> TauLimitResult:
        constraints = constraints or {}

        # Start with base tau
        tau = self._base_tau

        # Factor 1: Available power headroom
        available_mw = point.available_power_mw
        if available_mw > 100:
            tau *= 1.2  # Plenty of headroom
        elif available_mw < 10:
            tau *= 0.5  # Limited headroom
        elif available_mw < 1:
            tau *= 0.1  # Critical

        # Factor 2: Carbon intensity
        carbon = field.average_carbon_intensity()
        carbon_factor = 1.0
        if carbon > self._carbon_threshold:
            # Throttle based on how much over threshold
            carbon_factor = max(0.3, 1.0 - (carbon - self._carbon_threshold) / 500.0)
            tau *= carbon_factor

        # Factor 3: Grid frequency
        freq = point.grid_frequency_hz
        freq_deviation = abs(freq - 50.0)
        if freq_deviation > self._freq_deadband:
            # Throttle proportionally to deviation
            freq_factor = max(0.5, 1.0 - freq_deviation * 2)
            tau *= freq_factor

        # Factor 4: Regional constraints
        if "carbon_throttle" in constraints:
            tau *= constraints["carbon_throttle"]
        if "emergency_curtail" in constraints:
            tau *= (1.0 - constraints["emergency_curtail"])

        # Clamp to limits
        tau = max(self._min_tau, min(self._max_tau, tau))

        return TauLimitResult(
            node_id=point.subject,
            tau_limit=tau,
            reason=f"default policy: headroom={available_mw:.1f}MW, carbon={carbon:.0f}",
            energy_headroom_mw=available_mw,
            carbon_factor=carbon_factor,
            confidence=point.confidence,
        )


class KardashevPolicy(TauLimitPolicy):
    """
    Kardashev-scale aware tau policy.

    Optimized for multi-planetary operation where:
    - Latency between nodes varies dramatically
    - Energy sources include orbital solar, fusion, etc.
    - Carbon may not be relevant (space operations)

    Named after the Kardashev scale for civilizational energy usage.
    """

    def __init__(
        self,
        base_tau: float = 1.0,
        max_tau: float = 5.0,  # Higher max for advanced energy
        min_tau: float = 0.01,
        energy_density_threshold: float = 1000.0,  # MW
    ):
        self._base_tau = base_tau
        self._max_tau = max_tau
        self._min_tau = min_tau
        self._density_threshold = energy_density_threshold

    def name(self) -> str:
        return "kardashev"

    def compute(
        self,
        point: EnergyFieldPoint,
        field: EnergyField,
        constraints: Dict[str, float] | None = None,
    ) -> TauLimitResult:
        constraints = constraints or {}

        # Energy density determines scaling
        total_gen = field.total_generation()
        num_nodes = len(field.get_compute_nodes()) or 1

        energy_per_node = total_gen / num_nodes

        # Scale tau based on energy density
        if energy_per_node > self._density_threshold:
            # Type II territory - abundant energy
            tau = self._base_tau * 2.0
        elif energy_per_node > self._density_threshold / 10:
            # Type I territory - planetary scale
            tau = self._base_tau * 1.5
        else:
            # Sub-planetary - careful allocation
            tau = self._base_tau

        # Available headroom still matters
        available_mw = point.available_power_mw
        headroom_factor = min(2.0, max(0.1, available_mw / 50.0))
        tau *= headroom_factor

        # Apply constraints
        if "priority_boost" in constraints:
            tau *= (1.0 + constraints["priority_boost"])

        # Clamp
        tau = max(self._min_tau, min(self._max_tau, tau))

        return TauLimitResult(
            node_id=point.subject,
            tau_limit=tau,
            reason=f"kardashev policy: density={energy_per_node:.0f}MW/node",
            energy_headroom_mw=available_mw,
            carbon_factor=1.0,  # Not used in Kardashev
            confidence=point.confidence,
        )


def get_policy(name: str) -> TauLimitPolicy:
    """Get a tau limit policy by name."""
    policies = {
        "default": DefaultTauLimitPolicy,
        "kardashev": KardashevPolicy,
    }
    if name not in policies:
        raise ValueError(f"Unknown policy: {name}. Available: {list(policies.keys())}")
    return policies[name]()
