from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
from threading import Lock

from sfl.energy.model import EntityID


@dataclass
class EnergyAccount:
    """Energy-compute account for a pattern or node."""

    entity_id: EntityID

    # Consumption totals
    kwh_consumed_total: float = 0.0
    kwh_low_carbon_total: float = 0.0
    tcu_consumed_total: float = 0.0

    # Current period
    kwh_consumed_period: float = 0.0
    tcu_consumed_period: float = 0.0

    # Quotas
    kwh_quota_soft: float = float("inf")
    kwh_quota_hard: float = float("inf")
    tcu_quota_soft: float = float("inf")
    tcu_quota_hard: float = float("inf")

    # Carbon tracking
    total_carbon_gco2: float = 0.0

    def record_consumption(
        self,
        kwh: float,
        tcu: float,
        carbon_intensity: float,
        is_low_carbon: bool = False,
    ) -> None:
        self.kwh_consumed_total += kwh
        self.kwh_consumed_period += kwh
        self.tcu_consumed_total += tcu
        self.tcu_consumed_period += tcu
        self.total_carbon_gco2 += kwh * carbon_intensity

        if is_low_carbon:
            self.kwh_low_carbon_total += kwh

    def reset_period(self) -> None:
        self.kwh_consumed_period = 0.0
        self.tcu_consumed_period = 0.0

    def is_over_hard_limit(self) -> bool:
        return (
            self.kwh_consumed_period > self.kwh_quota_hard or
            self.tcu_consumed_period > self.tcu_quota_hard
        )

    def is_over_soft_limit(self) -> bool:
        return (
            self.kwh_consumed_period > self.kwh_quota_soft or
            self.tcu_consumed_period > self.tcu_quota_soft
        )

    def utilization_ratio(self) -> float:
        """How much of soft quota is used."""
        kwh_ratio = self.kwh_consumed_period / max(self.kwh_quota_soft, 1)
        tcu_ratio = self.tcu_consumed_period / max(self.tcu_quota_soft, 1)
        return max(kwh_ratio, tcu_ratio)


@dataclass
class ComputeEnergyCreditLine:
    """Credit line for a pattern - allows consumption up to limits."""

    entity_id: EntityID
    max_tcu: float
    max_kwh: float
    carbon_intensity_ceiling: Optional[float] = None
    valid_until_ms: int = 0

    # Current usage
    used_tcu: float = 0.0
    used_kwh: float = 0.0

    def remaining_tcu(self) -> float:
        return max(0, self.max_tcu - self.used_tcu)

    def remaining_kwh(self) -> float:
        return max(0, self.max_kwh - self.used_kwh)

    def can_consume(self, tcu: float, kwh: float) -> bool:
        return tcu <= self.remaining_tcu() and kwh <= self.remaining_kwh()


class AccountStore:
    """Thread-safe store for energy accounts."""

    def __init__(self):
        self._accounts: Dict[EntityID, EnergyAccount] = {}
        self._credit_lines: Dict[EntityID, ComputeEnergyCreditLine] = {}
        self._lock = Lock()

    def get_or_create_account(self, entity_id: EntityID) -> EnergyAccount:
        with self._lock:
            if entity_id not in self._accounts:
                self._accounts[entity_id] = EnergyAccount(entity_id=entity_id)
            return self._accounts[entity_id]

    def get_account(self, entity_id: EntityID) -> Optional[EnergyAccount]:
        with self._lock:
            return self._accounts.get(entity_id)

    def set_credit_line(self, credit_line: ComputeEnergyCreditLine) -> None:
        with self._lock:
            self._credit_lines[credit_line.entity_id] = credit_line

    def get_credit_line(self, entity_id: EntityID) -> Optional[ComputeEnergyCreditLine]:
        with self._lock:
            return self._credit_lines.get(entity_id)
