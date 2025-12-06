"""
ACNL Control — Tau Limit Policies

Policies transform EnergyFieldPoints into tau limits.
τ = rate at which a pattern can consume energy/compute.

NAIVE DESIGN (rejected):
- Fixed quotas per pattern
- Human-assigned priorities

CRITIQUE:
- Fixed quotas don't adapt to field state
- Human priorities can't scale to 10^12 patterns
- No energy-centric reasoning

FRACTAL DESIGN (implemented):
- Policies read field state
- Compute tau_limit based on energy/cost/carbon/reliability
- Patterns with high info_gain/tau survive. Others decay.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
from abc import ABC, abstractmethod

from ..core.fields import FieldPoint


class TauLimitPolicy(ABC):
    """
    Base policy: transforms FieldPoint → tau_limit.

    tau_limit = maximum τ (energy consumption rate) for patterns
    on this compute node given current field state.
    """

    base_tau_max: float = 1.0

    @abstractmethod
    def compute(
        self,
        point: FieldPoint,
        constraints: Optional[Dict[str, float]] = None,
    ) -> float:
        """Compute tau_limit for a field point."""
        ...


@dataclass
class DefaultTauLimitPolicy(TauLimitPolicy):
    """
    Default policy based on price, carbon, congestion, reliability.

    Tau is compressed when:
      - Price is high
      - Carbon intensity is high
      - Line loading (congestion) is high
      - Temperature is high
      - Reliability is low
      - Confidence is low
    """

    base_tau_max: float = 1.0

    # Thresholds
    price_high: float = 200.0       # €/MWh
    price_medium: float = 100.0
    carbon_high: float = 500.0      # gCO2/kWh
    carbon_medium: float = 200.0
    congestion_threshold: float = 0.8
    temp_warning: float = 75.0      # °C
    temp_critical: float = 85.0

    def compute(
        self,
        point: FieldPoint,
        constraints: Optional[Dict[str, float]] = None,
    ) -> float:
        tau = self.base_tau_max

        # ── Price penalty ──
        price = point.price_energy
        if price > self.price_high:
            tau *= 0.25
        elif price > self.price_medium:
            tau *= 0.5

        # ── Carbon penalty ──
        carbon = point.carbon_intensity
        if carbon > self.carbon_high:
            tau *= 0.2
        elif carbon > self.carbon_medium:
            tau *= 0.5

        # ── Congestion penalty ──
        loading = point.line_loading
        if loading > self.congestion_threshold:
            congestion_factor = 1.0 - (loading - self.congestion_threshold) / (1.0 - self.congestion_threshold)
            tau *= max(0.1, congestion_factor)

        # ── Temperature penalty ──
        temp = point.temp_celsius
        if temp > self.temp_critical:
            tau *= 0.1
        elif temp > self.temp_warning:
            tau *= max(0.3, 1.0 - (temp - self.temp_warning) / (self.temp_critical - self.temp_warning))

        # ── Reliability / Confidence ──
        tau *= point.reliability * (0.4 + 0.6 * point.confidence)

        # ── Regional constraints ──
        if constraints:
            tau *= constraints.get("carbon_throttle", 1.0)
            tau *= constraints.get("power_quota", 1.0)
            tau *= constraints.get("emergency_factor", 1.0)

        return max(0.0, min(self.base_tau_max, tau))


@dataclass
class KardashevPolicy(TauLimitPolicy):
    """
    Policy aligned with Kardashev trajectory.

    Favors:
      - Low carbon (toward Type I civilization)
      - High exergy efficiency
      - Sustainable growth

    This is a civilizational-scale policy applied by GH.
    """

    base_tau_max: float = 1.0

    # Kardashev targets
    target_exergy_tw: float = 100.0      # Type I = ~174 PW, start with 100 TW goal
    current_exergy_tw: float = 18.0
    growth_target: float = 0.02          # 2% growth per period
    carbon_ceiling: float = 50.0         # Target carbon intensity

    def compute(
        self,
        point: FieldPoint,
        constraints: Optional[Dict[str, float]] = None,
    ) -> float:
        tau = self.base_tau_max

        # ── Carbon: exponential penalty above ceiling ──
        carbon = point.carbon_intensity
        if carbon > self.carbon_ceiling:
            ratio = carbon / self.carbon_ceiling
            tau *= max(0.1, 1.0 / (ratio ** 1.5))
        else:
            # Bonus for very low carbon
            tau *= min(1.3, self.carbon_ceiling / max(carbon, 1))

        # ── Reliability is critical at civilizational scale ──
        tau *= point.reliability ** 2

        # ── Confidence weight ──
        tau *= (0.3 + 0.7 * point.confidence)

        # ── Apply global constraints ──
        if constraints:
            kardashev_ratio = constraints.get("kardashev_ratio", 1.0)
            if kardashev_ratio < 0.3:
                # Far below trajectory: encourage growth
                tau *= 1.5
            elif kardashev_ratio > 1.2:
                # Above trajectory: stabilize
                tau *= 0.8

            tau *= constraints.get("growth_incentive", 1.0)
            tau *= constraints.get("global_carbon_multiplier", 1.0)

        return max(0.0, min(self.base_tau_max * 1.5, tau))


@dataclass
class EmergencyPolicy(TauLimitPolicy):
    """
    Emergency policy for grid stability events.

    Activated when:
      - Frequency deviation > threshold
      - Voltage collapse risk
      - Cascading failure detected
    """

    base_tau_max: float = 0.1  # Very conservative

    def compute(
        self,
        point: FieldPoint,
        constraints: Optional[Dict[str, float]] = None,
    ) -> float:
        # In emergency, only essential compute continues
        if point.reliability < 0.5:
            return 0.0

        # Check grid frequency (50 Hz nominal)
        freq = point.get("grid_frequency", 50.0)
        if abs(freq - 50.0) > 0.5:
            return 0.05  # Minimal compute

        return self.base_tau_max * point.reliability
