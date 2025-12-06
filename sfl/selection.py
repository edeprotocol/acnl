"""
SFL Selection — Pattern Selection Logic

Selects which patterns/jobs to run based on:
- tau limits from LFI
- Energy field state (carbon, congestion, availability)
- Pattern priorities and requirements
- Economic signals (price, settlements)

This is the compute allocation policy that respects physical reality.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import heapq

from sfl.energy.model import EntityID, EnergyField, EnergyFieldPoint, EnergyObservableKind


class SelectionStrategy(Enum):
    """Strategy for pattern selection when resources are constrained."""
    PRIORITY = "priority"           # Strict priority ordering
    FAIR_SHARE = "fair_share"       # Proportional allocation
    ENERGY_OPTIMAL = "energy_optimal"  # Minimize carbon/energy
    LATENCY_OPTIMAL = "latency_optimal"  # Minimize latency


@dataclass
class PatternSpec:
    """Specification for a compute pattern."""
    pattern_id: EntityID
    priority: int = 100               # Higher = more important
    min_tau: float = 0.1              # Minimum tau required to run
    max_tau: float = 2.0              # Maximum tau it can use
    preferred_carbon_max: float = 200.0  # gCO2/kWh preference
    energy_kwh_per_unit: float = 0.001   # Energy per compute unit
    can_preempt: bool = False         # Can preempt other patterns
    can_be_preempted: bool = True     # Can be preempted


@dataclass
class SelectionResult:
    """Result of pattern selection."""
    selected: List[EntityID]          # Selected pattern IDs
    allocated_tau: Dict[EntityID, float]  # Tau allocated to each
    rejected: List[EntityID]          # Patterns that couldn't run
    rejection_reasons: Dict[EntityID, str]  # Why patterns were rejected


@dataclass
class PatternSelector:
    """
    Selects patterns to run based on energy field state and tau limits.

    The selector respects physical constraints while optimizing for
    the chosen strategy.
    """

    strategy: SelectionStrategy = SelectionStrategy.PRIORITY
    max_concurrent_patterns: int = 100
    carbon_ceiling: float = 500.0     # gCO2/kWh hard limit

    _patterns: Dict[EntityID, PatternSpec] = field(default_factory=dict)

    def register_pattern(self, spec: PatternSpec) -> None:
        """Register a pattern for selection."""
        self._patterns[spec.pattern_id] = spec

    def unregister_pattern(self, pattern_id: EntityID) -> None:
        """Remove a pattern from selection."""
        self._patterns.pop(pattern_id, None)

    def select(
        self,
        field: EnergyField,
        tau_limits: Dict[EntityID, float],
        requested: List[EntityID] | None = None,
    ) -> SelectionResult:
        """
        Select patterns to run given current energy state.

        Args:
            field: Current energy field
            tau_limits: Tau limits for compute nodes
            requested: Optional list of patterns to consider (all if None)

        Returns:
            SelectionResult with selected patterns and allocations
        """
        if requested is None:
            requested = list(self._patterns.keys())

        # Filter to registered patterns
        candidates = [
            pid for pid in requested
            if pid in self._patterns
        ]

        # Get field-wide constraints
        avg_carbon = field.avg_carbon_intensity()
        total_tau_available = sum(tau_limits.values())

        result = SelectionResult(
            selected=[],
            allocated_tau={},
            rejected=[],
            rejection_reasons={},
        )

        # Apply strategy
        if self.strategy == SelectionStrategy.PRIORITY:
            self._select_by_priority(
                candidates, tau_limits, avg_carbon, total_tau_available, result
            )
        elif self.strategy == SelectionStrategy.FAIR_SHARE:
            self._select_fair_share(
                candidates, tau_limits, avg_carbon, total_tau_available, result
            )
        elif self.strategy == SelectionStrategy.ENERGY_OPTIMAL:
            self._select_energy_optimal(
                candidates, tau_limits, avg_carbon, total_tau_available, field, result
            )
        else:
            # Default to priority
            self._select_by_priority(
                candidates, tau_limits, avg_carbon, total_tau_available, result
            )

        return result

    def _select_by_priority(
        self,
        candidates: List[EntityID],
        tau_limits: Dict[EntityID, float],
        avg_carbon: float,
        total_tau: float,
        result: SelectionResult,
    ) -> None:
        """Select patterns in priority order."""
        # Sort by priority (descending)
        sorted_candidates = sorted(
            candidates,
            key=lambda pid: self._patterns[pid].priority,
            reverse=True,
        )

        remaining_tau = total_tau

        for pid in sorted_candidates:
            spec = self._patterns[pid]

            # Check carbon ceiling
            if avg_carbon > self.carbon_ceiling and spec.preferred_carbon_max < avg_carbon:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = f"carbon={avg_carbon:.0f} > ceiling={self.carbon_ceiling}"
                continue

            # Check minimum tau
            if remaining_tau < spec.min_tau:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = f"tau={remaining_tau:.3f} < min={spec.min_tau}"
                continue

            # Check max concurrent
            if len(result.selected) >= self.max_concurrent_patterns:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = "max_concurrent reached"
                continue

            # Allocate tau
            allocated = min(remaining_tau, spec.max_tau)
            result.selected.append(pid)
            result.allocated_tau[pid] = allocated
            remaining_tau -= spec.min_tau  # Reserve minimum

    def _select_fair_share(
        self,
        candidates: List[EntityID],
        tau_limits: Dict[EntityID, float],
        avg_carbon: float,
        total_tau: float,
        result: SelectionResult,
    ) -> None:
        """Allocate tau proportionally to all eligible patterns."""
        # First pass: determine eligible patterns
        eligible = []
        for pid in candidates:
            spec = self._patterns[pid]

            if avg_carbon > self.carbon_ceiling:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = f"carbon={avg_carbon:.0f} > ceiling"
                continue

            eligible.append(pid)

        if not eligible:
            return

        # Calculate fair share
        fair_share = total_tau / len(eligible)

        for pid in eligible:
            spec = self._patterns[pid]

            # Check if fair share meets minimum
            if fair_share < spec.min_tau:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = f"fair_share={fair_share:.3f} < min={spec.min_tau}"
                continue

            if len(result.selected) >= self.max_concurrent_patterns:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = "max_concurrent reached"
                continue

            # Allocate (capped at max_tau)
            allocated = min(fair_share, spec.max_tau)
            result.selected.append(pid)
            result.allocated_tau[pid] = allocated

    def _select_energy_optimal(
        self,
        candidates: List[EntityID],
        tau_limits: Dict[EntityID, float],
        avg_carbon: float,
        total_tau: float,
        field: EnergyField,
        result: SelectionResult,
    ) -> None:
        """Select patterns to minimize energy/carbon."""
        # Score patterns by energy efficiency
        scored = []
        for pid in candidates:
            spec = self._patterns[pid]

            if avg_carbon > self.carbon_ceiling:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = f"carbon > ceiling"
                continue

            # Score: priority / energy_per_unit (higher = better)
            score = spec.priority / max(spec.energy_kwh_per_unit, 0.0001)
            scored.append((score, pid))

        # Select top patterns by score
        scored.sort(reverse=True)
        remaining_tau = total_tau

        for score, pid in scored:
            spec = self._patterns[pid]

            if remaining_tau < spec.min_tau:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = f"insufficient tau"
                continue

            if len(result.selected) >= self.max_concurrent_patterns:
                result.rejected.append(pid)
                result.rejection_reasons[pid] = "max_concurrent reached"
                continue

            allocated = min(remaining_tau, spec.max_tau)
            result.selected.append(pid)
            result.allocated_tau[pid] = allocated
            remaining_tau -= spec.min_tau


@dataclass
class AdaptiveSelector:
    """
    Adaptive pattern selector that adjusts strategy based on field state.

    Uses different strategies depending on:
    - Carbon intensity (high → energy optimal)
    - Congestion (high → priority only)
    - Available power (low → strict rationing)
    """

    base_selector: PatternSelector = field(default_factory=PatternSelector)
    carbon_threshold: float = 300.0   # Switch to energy_optimal above this
    congestion_threshold: float = 0.8  # Switch to priority above this

    def select(
        self,
        field: EnergyField,
        tau_limits: Dict[EntityID, float],
        requested: List[EntityID] | None = None,
    ) -> SelectionResult:
        """Select with adaptive strategy."""
        avg_carbon = field.avg_carbon_intensity()
        avg_congestion = self._avg_congestion(field)

        # Choose strategy
        if avg_congestion > self.congestion_threshold:
            # High congestion: only run high-priority work
            self.base_selector.strategy = SelectionStrategy.PRIORITY
            self.base_selector.max_concurrent_patterns = 10  # Reduce
        elif avg_carbon > self.carbon_threshold:
            # High carbon: optimize for energy
            self.base_selector.strategy = SelectionStrategy.ENERGY_OPTIMAL
            self.base_selector.max_concurrent_patterns = 50
        else:
            # Normal: fair share
            self.base_selector.strategy = SelectionStrategy.FAIR_SHARE
            self.base_selector.max_concurrent_patterns = 100

        return self.base_selector.select(field, tau_limits, requested)

    def _avg_congestion(self, field: EnergyField) -> float:
        """Calculate average line congestion."""
        congestion_values = []
        for point in field.points:
            loading = point.get_metric(EnergyObservableKind.LINE_LOADING, None)
            if loading is not None:
                congestion_values.append(loading)

        if not congestion_values:
            return 0.0
        return sum(congestion_values) / len(congestion_values)

    def register_pattern(self, spec: PatternSpec) -> None:
        self.base_selector.register_pattern(spec)

    def unregister_pattern(self, pattern_id: EntityID) -> None:
        self.base_selector.unregister_pattern(pattern_id)
