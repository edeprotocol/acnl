"""
ACNL Control — Regional Coordinator (RC)

RC = middle level of the fractal hierarchy.

Responsibilities:
- Aggregate summaries from multiple LFIs
- Compute regional constraints
- Balance load across LFIs
- Report to Global Harmonizer
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

from ..core.ids import EntityID, rc_id


@dataclass
class RCConfig:
    """Configuration for Regional Coordinator."""
    region_id: str
    rc_name: str = "rc-1"
    carbon_limit: float = 300.0  # gCO2/kWh
    max_total_consumption_mw: float = 10000.0
    rebalance_interval_ms: int = 5000


@dataclass
class LFISummary:
    """Summary from an LFI."""
    lfi_id: EntityID
    region_id: str
    timestamp_ms: int
    total_available_mw: float
    total_consumption_mw: float
    total_generation_mw: float
    avg_carbon_intensity: float
    compute_nodes: int
    tau_limits: Dict[str, float]


class RegionalCoordinator:
    """
    Regional Coordinator — middle level of the fractal hierarchy.
    """

    def __init__(self, config: RCConfig):
        self._config = config
        self._rc_id = rc_id(config.rc_name)

        self._lfi_summaries: Dict[EntityID, LFISummary] = {}
        self._regional_constraints: Dict[str, float] = {}
        self._global_constraints: Dict[str, float] = {}

        self._last_rebalance_ms = 0

    @property
    def rc_id(self) -> EntityID:
        return self._rc_id

    @property
    def region_id(self) -> str:
        return self._config.region_id

    def receive_lfi_summary(self, summary: Dict[str, Any]) -> None:
        """Receive summary from an LFI."""
        lfi_id_str = summary.get("lfi_id", "unknown")
        lfi_entity = EntityID(lfi_id_str)

        self._lfi_summaries[lfi_entity] = LFISummary(
            lfi_id=lfi_entity,
            region_id=summary.get("region_id", ""),
            timestamp_ms=summary.get("timestamp_ms", int(time.time() * 1000)),
            total_available_mw=summary.get("total_available_mw", 0.0),
            total_consumption_mw=summary.get("total_consumption_mw", 0.0),
            total_generation_mw=summary.get("total_generation_mw", 0.0),
            avg_carbon_intensity=summary.get("avg_carbon_intensity", 0.0),
            compute_nodes=summary.get("compute_nodes", 0),
            tau_limits=summary.get("tau_limits", {}),
        )

    def tick(self, now_ms: int | None = None) -> None:
        """Run one tick of the RC."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        # Check if rebalance needed
        if now_ms - self._last_rebalance_ms >= self._config.rebalance_interval_ms:
            self._rebalance()
            self._last_rebalance_ms = now_ms

    def _rebalance(self) -> None:
        """Recompute regional constraints based on aggregated state."""
        if not self._lfi_summaries:
            return

        # Aggregate metrics
        total_consumption = sum(s.total_consumption_mw for s in self._lfi_summaries.values())
        total_generation = sum(s.total_generation_mw for s in self._lfi_summaries.values())
        total_available = sum(s.total_available_mw for s in self._lfi_summaries.values())

        # Weighted average carbon intensity
        total_gen_weight = 0.0
        weighted_carbon = 0.0
        for s in self._lfi_summaries.values():
            gen = s.total_generation_mw
            if gen > 0:
                total_gen_weight += gen
                weighted_carbon += gen * s.avg_carbon_intensity
        avg_carbon = weighted_carbon / total_gen_weight if total_gen_weight > 0 else 0.0

        # Compute constraints
        constraints: Dict[str, float] = {}

        # Carbon throttle
        if avg_carbon > self._config.carbon_limit:
            excess = (avg_carbon - self._config.carbon_limit) / self._config.carbon_limit
            constraints["carbon_throttle"] = max(0.3, 1.0 - excess)

        # Consumption limit
        if total_consumption > self._config.max_total_consumption_mw:
            excess = (total_consumption - self._config.max_total_consumption_mw) / self._config.max_total_consumption_mw
            constraints["consumption_throttle"] = max(0.5, 1.0 - excess)

        # Available power constraint
        if total_available < total_consumption * 0.1:
            constraints["emergency_factor"] = 0.5

        # Apply global constraints
        for k, v in self._global_constraints.items():
            if k in constraints:
                constraints[k] = min(constraints[k], v)
            else:
                constraints[k] = v

        self._regional_constraints = constraints

    def get_constraints_for_lfi(self, lfi_id: EntityID) -> Dict[str, float]:
        """Get constraints to send to an LFI."""
        return self._regional_constraints.copy()

    def set_global_constraints(self, constraints: Dict[str, float]) -> None:
        """Set constraints from Global Harmonizer."""
        self._global_constraints = constraints

    def get_summary(self) -> Dict[str, Any]:
        """Get summary for Global Harmonizer."""
        if not self._lfi_summaries:
            return {
                "region_id": self._config.region_id,
                "rc_id": str(self._rc_id),
                "timestamp_ms": int(time.time() * 1000),
                "num_lfis": 0,
                "total_available_mw": 0.0,
                "total_consumption_mw": 0.0,
                "total_generation_mw": 0.0,
                "avg_carbon_intensity": 0.0,
                "total_compute_nodes": 0,
                "constraints": {},
            }

        total_consumption = sum(s.total_consumption_mw for s in self._lfi_summaries.values())
        total_generation = sum(s.total_generation_mw for s in self._lfi_summaries.values())
        total_available = sum(s.total_available_mw for s in self._lfi_summaries.values())
        total_compute = sum(s.compute_nodes for s in self._lfi_summaries.values())

        # Weighted carbon
        total_gen_weight = 0.0
        weighted_carbon = 0.0
        for s in self._lfi_summaries.values():
            gen = s.total_generation_mw
            if gen > 0:
                total_gen_weight += gen
                weighted_carbon += gen * s.avg_carbon_intensity
        avg_carbon = weighted_carbon / total_gen_weight if total_gen_weight > 0 else 0.0

        return {
            "region_id": self._config.region_id,
            "rc_id": str(self._rc_id),
            "timestamp_ms": int(time.time() * 1000),
            "num_lfis": len(self._lfi_summaries),
            "total_available_mw": total_available,
            "total_consumption_mw": total_consumption,
            "total_generation_mw": total_generation,
            "avg_carbon_intensity": avg_carbon,
            "total_compute_nodes": total_compute,
            "constraints": self._regional_constraints,
        }

    def get_lfi_rankings(self) -> List[EntityID]:
        """Rank LFIs by efficiency (low carbon, high availability)."""
        rankings = []
        for lfi_id_entity, summary in self._lfi_summaries.items():
            # Score: lower carbon is better, higher available is better
            carbon_score = 1.0 / (1.0 + summary.avg_carbon_intensity / 100.0)
            available_score = summary.total_available_mw / max(1.0, summary.total_consumption_mw)
            score = carbon_score * 0.5 + available_score * 0.5
            rankings.append((lfi_id_entity, score))

        rankings.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in rankings]
