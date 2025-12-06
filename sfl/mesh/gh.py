from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time
import threading


@dataclass
class GHConfig:
    tick_interval_ms: int = 30_000    # much slower - global level
    global_carbon_budget_gco2_per_hour: float = 100_000_000  # 100 Mt/h
    kardashev_target_tw: float = 100  # target total power in TW
    exergy_growth_rate: float = 0.01  # 1% per period target


class GlobalHarmonizer:
    """
    Global Harmonizer - top of fractal hierarchy.

    Responsibilities:
    1. Aggregate RC summaries into global view
    2. Set civilizational parameters (Kardashev trajectory, carbon budget)
    3. Distribute parameters to RCs
    4. NO job-level scheduling - only policy parameters

    NOTE: In a real multi-foyer system (Earth + Mars), there would be
    multiple GHs with asynchronous reconciliation. This is a single-GH
    implementation for now.
    """

    def __init__(self, config: GHConfig, rc_ids: List[str]):
        self.config = config
        self.rc_ids = rc_ids

        self._rc_summaries: Dict[str, Dict[str, Any]] = {}
        self._global_params: Dict[str, float] = {}
        self._global_state: Dict[str, float] = {}

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def update_rc_summary(self, rc_id: str, summary: Dict[str, Any]) -> None:
        """Receive summary from Regional Coordinator."""
        self._rc_summaries[rc_id] = summary

    def tick(self) -> None:
        """Single tick of GH loop."""
        now_ms = int(time.time() * 1000)

        # 1. Compute global state
        self._global_state = self._compute_global_state()

        # 2. Compute parameters for RCs
        self._global_params = self._compute_global_params()

    def _compute_global_state(self) -> Dict[str, float]:
        """Aggregate RC summaries into global metrics."""
        total_available_mw = 0.0
        total_carbon_rate = 0.0
        num_compute_nodes = 0

        for summary in self._rc_summaries.values():
            total_available_mw += summary.get("total_available_mw", 0)
            total_carbon_rate += summary.get("carbon_rate_gco2_h", 0)
            num_compute_nodes += summary.get("total_points", 0)

        return {
            "total_available_mw": total_available_mw,
            "total_available_tw": total_available_mw / 1_000_000,
            "total_carbon_rate_gco2_h": total_carbon_rate,
            "num_compute_nodes": num_compute_nodes,
            "num_regions": len(self._rc_summaries),
        }

    def _compute_global_params(self) -> Dict[str, float]:
        """Compute parameters to distribute to RCs."""
        params = {
            "global_carbon_multiplier": 1.0,
            "exergy_target_tw": self.config.kardashev_target_tw,
        }

        # Carbon budget enforcement
        current_carbon = self._global_state.get("total_carbon_rate_gco2_h", 0)
        carbon_ratio = current_carbon / max(self.config.global_carbon_budget_gco2_per_hour, 1)

        if carbon_ratio > 0.9:
            # Emergency throttle
            params["global_carbon_multiplier"] = max(0.1, 1.0 - (carbon_ratio - 0.9) * 5)
        elif carbon_ratio > 0.7:
            # Warning throttle
            params["global_carbon_multiplier"] = max(0.5, 1.0 - (carbon_ratio - 0.7) * 1.5)

        # Kardashev trajectory
        current_tw = self._global_state.get("total_available_tw", 0)
        if current_tw > 0:
            kardashev_ratio = current_tw / self.config.kardashev_target_tw
            params["kardashev_ratio"] = kardashev_ratio

            if kardashev_ratio < 0.5:
                # Below target - encourage growth
                params["growth_incentive"] = 1.5
            else:
                params["growth_incentive"] = 1.0

        return params

    def get_global_params(self) -> Dict[str, float]:
        return self._global_params.copy()

    def get_global_state(self) -> Dict[str, float]:
        return self._global_state.copy()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        while self._running:
            try:
                self.tick()
            except Exception as e:
                print(f"GH tick error: {e}")
            time.sleep(self.config.tick_interval_ms / 1000.0)
