from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time
import threading

from sfl.energy.model import EnergyField, EnergyFieldPoint, Coord, EnergyObservableKind


@dataclass
class RCConfig:
    region_id: str                    # e.g. "earth/eu" covering multiple LFIs
    tick_interval_ms: int = 5_000     # slower than LFI
    carbon_budget_gco2_per_hour: float = 1_000_000
    power_budget_mw: float = 10_000


class RegionalCoordinator:
    """
    Regional Coordinator - aggregates multiple LFIs and enforces regional constraints.

    Responsibilities:
    1. Aggregate LFI fields into regional view
    2. Compute regional constraints (carbon budget, power quota)
    3. Distribute constraints back to LFIs
    4. Report summary to Global Harmonizer
    """

    def __init__(self, config: RCConfig, lfi_ids: List[str]):
        self.config = config
        self.lfi_ids = lfi_ids

        self._lfi_summaries: Dict[str, Dict[str, Any]] = {}
        self._lfi_fields: Dict[str, EnergyField] = {}
        self._regional_field: Optional[EnergyField] = None
        self._constraints: Dict[str, float] = {}
        self._global_params: Dict[str, float] = {}

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def update_lfi_field(self, lfi_id: str, field: EnergyField) -> None:
        """Receive field update from LFI."""
        self._lfi_fields[lfi_id] = field

    def update_lfi_summary(self, lfi_id: str, summary: Dict[str, Any]) -> None:
        """Receive summary update from LFI."""
        self._lfi_summaries[lfi_id] = summary

    def set_global_params(self, params: Dict[str, float]) -> None:
        """Receive parameters from Global Harmonizer."""
        self._global_params = params

    def tick(self) -> None:
        """Single tick of RC loop."""
        now_ms = int(time.time() * 1000)

        # 1. Build regional field
        self._regional_field = self._build_regional_field(now_ms)

        # 2. Compute constraints
        self._constraints = self._compute_constraints()

    def _build_regional_field(self, now_ms: int) -> EnergyField:
        """Aggregate LFI fields into regional field."""
        all_points: List[EnergyFieldPoint] = []

        for lfi_id, field in self._lfi_fields.items():
            # Add LFI's points, possibly with region prefix
            for point in field.points:
                # Adjust coord to regional
                regional_point = EnergyFieldPoint(
                    coord=Coord(region_id=self.config.region_id, ts_ms=now_ms),
                    subject=point.subject,
                    metrics=point.metrics.copy(),
                    confidence=point.confidence * 0.9,  # slight confidence decay
                )
                all_points.append(regional_point)

        return EnergyField(
            region_id=self.config.region_id,
            points=all_points,
            generated_at_ms=now_ms,
        )

    def _compute_constraints(self) -> Dict[str, float]:
        """Compute regional constraints to send to LFIs."""
        constraints = {
            "carbon_throttle": 1.0,
            "power_quota": 1.0,
        }

        if not self._regional_field:
            return constraints

        # Carbon budget check
        total_carbon = self._estimate_carbon_rate()
        carbon_ratio = total_carbon / max(self.config.carbon_budget_gco2_per_hour, 1)

        if carbon_ratio > 0.8:
            # Approaching budget - throttle
            constraints["carbon_throttle"] = max(0.2, 1.0 - (carbon_ratio - 0.8) * 2.5)

        # Power budget check
        total_consumption = sum(
            p.get_metric(EnergyObservableKind.CONSUMPTION_POWER)
            for p in self._regional_field.points
        )
        power_ratio = total_consumption / max(self.config.power_budget_mw, 1)

        if power_ratio > 0.9:
            constraints["power_quota"] = max(0.3, 1.0 - (power_ratio - 0.9) * 5)

        # Apply global params
        if "global_carbon_multiplier" in self._global_params:
            constraints["carbon_throttle"] *= self._global_params["global_carbon_multiplier"]

        return constraints

    def _estimate_carbon_rate(self) -> float:
        """Estimate gCO2/hour for region."""
        if not self._regional_field:
            return 0.0

        total = 0.0
        for point in self._regional_field.points:
            power_mw = point.get_metric(EnergyObservableKind.CONSUMPTION_POWER)
            intensity = point.get_metric(EnergyObservableKind.CARBON_INTENSITY)
            # gCO2/kWh * MW * 1000 kW/MW = gCO2/h
            total += intensity * power_mw * 1000

        return total

    def get_constraints(self) -> Dict[str, float]:
        return self._constraints.copy()

    def get_regional_field(self) -> Optional[EnergyField]:
        return self._regional_field

    def get_summary(self) -> Dict[str, Any]:
        """Summary for GH reporting."""
        field = self._regional_field
        return {
            "region_id": self.config.region_id,
            "num_lfis": len(self._lfi_fields),
            "total_points": len(field.points) if field else 0,
            "total_available_mw": field.total_available_power() if field else 0,
            "avg_carbon_intensity": field.avg_carbon_intensity() if field else 0,
            "carbon_rate_gco2_h": self._estimate_carbon_rate(),
            "constraints": self._constraints,
        }

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
                print(f"RC tick error: {e}")
            time.sleep(self.config.tick_interval_ms / 1000.0)
