"""
ACNL Control — Global Harmonizer (GH)

GH = top level of the fractal hierarchy.
Civilizational-scale coordination.

Responsibilities:
- Aggregate summaries from all Regional Coordinators
- Compute global constraints and policies
- Balance load across regions
- Optimize for global objectives (carbon, efficiency, Kardashev trajectory)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

from ..core.ids import EntityID, gh_id


@dataclass
class GHConfig:
    """Configuration for Global Harmonizer."""
    foyer: str = "earth"
    gh_name: str = "gh-1"
    global_carbon_target: float = 100.0  # gCO2/kWh target
    harmonize_interval_ms: int = 10000


@dataclass
class RCSummary:
    """Summary from a Regional Coordinator."""
    rc_id: EntityID
    region_id: str
    timestamp_ms: int
    num_lfis: int
    total_available_mw: float
    total_consumption_mw: float
    total_generation_mw: float
    avg_carbon_intensity: float
    total_compute_nodes: int
    constraints: Dict[str, float]


class GlobalHarmonizer:
    """
    Global Harmonizer — top level of the fractal hierarchy.
    """

    def __init__(self, config: GHConfig | None = None):
        self._config = config or GHConfig()
        self._gh_id = gh_id(self._config.foyer)

        self._rc_summaries: Dict[EntityID, RCSummary] = {}
        self._global_constraints: Dict[str, float] = {}

        self._last_harmonize_ms = 0

    @property
    def gh_id(self) -> EntityID:
        return self._gh_id

    @property
    def foyer(self) -> str:
        return self._config.foyer

    def receive_rc_summary(self, summary: Dict[str, Any]) -> None:
        """Receive summary from a Regional Coordinator."""
        rc_id_str = summary.get("rc_id", "unknown")
        rc_entity = EntityID(rc_id_str)

        self._rc_summaries[rc_entity] = RCSummary(
            rc_id=rc_entity,
            region_id=summary.get("region_id", ""),
            timestamp_ms=summary.get("timestamp_ms", int(time.time() * 1000)),
            num_lfis=summary.get("num_lfis", 0),
            total_available_mw=summary.get("total_available_mw", 0.0),
            total_consumption_mw=summary.get("total_consumption_mw", 0.0),
            total_generation_mw=summary.get("total_generation_mw", 0.0),
            avg_carbon_intensity=summary.get("avg_carbon_intensity", 0.0),
            total_compute_nodes=summary.get("total_compute_nodes", 0),
            constraints=summary.get("constraints", {}),
        )

    def tick(self, now_ms: int | None = None) -> None:
        """Run one tick of the GH."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        if now_ms - self._last_harmonize_ms >= self._config.harmonize_interval_ms:
            self._harmonize()
            self._last_harmonize_ms = now_ms

    def _harmonize(self) -> None:
        """Compute global constraints and load balancing."""
        if not self._rc_summaries:
            return

        # Global aggregates
        total_consumption = sum(s.total_consumption_mw for s in self._rc_summaries.values())
        total_generation = sum(s.total_generation_mw for s in self._rc_summaries.values())

        # Global weighted carbon
        total_gen_weight = 0.0
        weighted_carbon = 0.0
        for s in self._rc_summaries.values():
            gen = s.total_generation_mw
            if gen > 0:
                total_gen_weight += gen
                weighted_carbon += gen * s.avg_carbon_intensity
        global_carbon = weighted_carbon / total_gen_weight if total_gen_weight > 0 else 0.0

        # Compute global constraints
        constraints: Dict[str, float] = {}

        # Global carbon throttle toward target
        if global_carbon > self._config.global_carbon_target:
            excess = (global_carbon - self._config.global_carbon_target) / self._config.global_carbon_target
            constraints["global_carbon_multiplier"] = max(0.5, 1.0 - excess * 0.5)

        # Global supply/demand balance
        if total_generation > 0:
            balance = total_consumption / total_generation
            if balance > 0.9:  # Approaching limit
                constraints["load_balance_throttle"] = max(0.5, 0.9 - (balance - 0.9))

        # Kardashev trajectory incentive
        # Type I civilization target: ~174 PW, current ~18 TW
        # For now, just track growth
        total_power_tw = total_generation / 1000.0  # MW to TW
        kardashev_ratio = total_power_tw / 18.0  # relative to current civilization
        constraints["kardashev_ratio"] = kardashev_ratio

        self._global_constraints = constraints

    def get_constraints_for_rc(self, rc_id: EntityID) -> Dict[str, float]:
        """Get constraints to send to a Regional Coordinator."""
        return self._global_constraints.copy()

    def get_global_summary(self) -> Dict[str, Any]:
        """Get global system summary."""
        if not self._rc_summaries:
            return {
                "gh_id": str(self._gh_id),
                "foyer": self._config.foyer,
                "timestamp_ms": int(time.time() * 1000),
                "num_regions": 0,
                "total_lfis": 0,
                "total_compute_nodes": 0,
                "total_available_mw": 0.0,
                "total_consumption_mw": 0.0,
                "total_generation_mw": 0.0,
                "global_carbon_intensity": 0.0,
                "global_constraints": {},
            }

        total_consumption = sum(s.total_consumption_mw for s in self._rc_summaries.values())
        total_generation = sum(s.total_generation_mw for s in self._rc_summaries.values())
        total_available = sum(s.total_available_mw for s in self._rc_summaries.values())
        total_lfis = sum(s.num_lfis for s in self._rc_summaries.values())
        total_compute = sum(s.total_compute_nodes for s in self._rc_summaries.values())

        # Weighted carbon
        total_gen_weight = 0.0
        weighted_carbon = 0.0
        for s in self._rc_summaries.values():
            gen = s.total_generation_mw
            if gen > 0:
                total_gen_weight += gen
                weighted_carbon += gen * s.avg_carbon_intensity
        global_carbon = weighted_carbon / total_gen_weight if total_gen_weight > 0 else 0.0

        return {
            "gh_id": str(self._gh_id),
            "foyer": self._config.foyer,
            "timestamp_ms": int(time.time() * 1000),
            "num_regions": len(self._rc_summaries),
            "total_lfis": total_lfis,
            "total_compute_nodes": total_compute,
            "total_available_mw": total_available,
            "total_consumption_mw": total_consumption,
            "total_generation_mw": total_generation,
            "global_carbon_intensity": global_carbon,
            "global_constraints": self._global_constraints,
        }

    def get_region_rankings(self) -> List[Dict[str, Any]]:
        """Rank regions by efficiency."""
        rankings = []
        for rc_entity, summary in self._rc_summaries.items():
            carbon_score = 1.0 / (1.0 + summary.avg_carbon_intensity / 100.0)
            available_score = summary.total_available_mw / max(1.0, summary.total_consumption_mw)
            efficiency = carbon_score * 0.5 + available_score * 0.5

            rankings.append({
                "rc_id": str(rc_entity),
                "region_id": summary.region_id,
                "efficiency_score": efficiency,
                "carbon_intensity": summary.avg_carbon_intensity,
                "available_mw": summary.total_available_mw,
                "consumption_mw": summary.total_consumption_mw,
            })

        rankings.sort(key=lambda x: x["efficiency_score"], reverse=True)
        return rankings

    def recommend_load_shift(self) -> List[Dict[str, Any]]:
        """Recommend load shifts between regions."""
        rankings = self.get_region_rankings()
        if len(rankings) < 2:
            return []

        recommendations = []
        best = rankings[0]
        worst = rankings[-1]

        # If significant difference, recommend shift
        if best["efficiency_score"] - worst["efficiency_score"] > 0.2:
            recommendations.append({
                "action": "shift_load",
                "from_region": worst["region_id"],
                "to_region": best["region_id"],
                "reason": f"Efficiency gap: {best['efficiency_score']:.2f} vs {worst['efficiency_score']:.2f}",
                "carbon_saving": worst["carbon_intensity"] - best["carbon_intensity"],
            })

        return recommendations
