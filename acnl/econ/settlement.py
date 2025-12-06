from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from acnl.energy.types import EntityID
from acnl.field.energy_field import EnergyField
from acnl.econ.accounts import AccountLedger, Transaction


@dataclass
class SettlementPeriod:
    """A settlement period with consumption and generation totals."""
    period_id: str
    start_ms: int
    end_ms: int
    region_id: str
    consumption_mwh: Dict[EntityID, float] = field(default_factory=dict)
    generation_mwh: Dict[EntityID, float] = field(default_factory=dict)
    settled: bool = False
    settlement_ms: int = 0


@dataclass
class SettlementConfig:
    """Configuration for settlement engine."""
    period_ms: int = 15 * 60 * 1000  # 15 minutes
    settlement_delay_ms: int = 60_000  # 1 minute after period ends
    mwh_per_tcu: float = 0.001  # 1 TCU = 0.001 MWh


class SettlementEngine:
    """
    Settles energy consumption against generation.

    Runs periodically to:
    1. Aggregate consumption by entity
    2. Aggregate generation by entity
    3. Credit/debit accounts accordingly
    4. Record settlement transactions
    """

    def __init__(
        self,
        ledger: AccountLedger,
        config: SettlementConfig | None = None,
    ):
        self._ledger = ledger
        self._config = config or SettlementConfig()
        self._periods: Dict[str, SettlementPeriod] = {}
        self._current_period: Optional[SettlementPeriod] = None
        self._period_counter = 0

    def start_period(self, region_id: str, start_ms: int | None = None) -> SettlementPeriod:
        """Start a new settlement period."""
        if start_ms is None:
            start_ms = int(time.time() * 1000)

        self._period_counter += 1
        period_id = f"period-{self._period_counter:06d}"

        period = SettlementPeriod(
            period_id=period_id,
            start_ms=start_ms,
            end_ms=start_ms + self._config.period_ms,
            region_id=region_id,
        )

        self._periods[period_id] = period
        self._current_period = period

        return period

    def record_consumption(
        self,
        entity_id: EntityID,
        power_mw: float,
        duration_ms: int,
    ) -> None:
        """Record consumption during current period."""
        if self._current_period is None:
            return

        # Convert MW * ms to MWh
        hours = duration_ms / 3600_000
        mwh = power_mw * hours

        current = self._current_period.consumption_mwh.get(entity_id, 0.0)
        self._current_period.consumption_mwh[entity_id] = current + mwh

    def record_generation(
        self,
        entity_id: EntityID,
        power_mw: float,
        duration_ms: int,
    ) -> None:
        """Record generation during current period."""
        if self._current_period is None:
            return

        hours = duration_ms / 3600_000
        mwh = power_mw * hours

        current = self._current_period.generation_mwh.get(entity_id, 0.0)
        self._current_period.generation_mwh[entity_id] = current + mwh

    def record_from_field(
        self,
        field: EnergyField,
        duration_ms: int,
    ) -> None:
        """Record consumption and generation from an energy field snapshot."""
        for point in field.points:
            kind = point.get_entity_kind()

            if kind == "compute-node":
                self.record_consumption(
                    point.subject,
                    point.consumption_power_mw,
                    duration_ms,
                )
            elif kind == "plant":
                self.record_generation(
                    point.subject,
                    point.generation_power_mw,
                    duration_ms,
                )

    def settle_period(self, period_id: str) -> List[Transaction]:
        """Settle a period and return transactions."""
        if period_id not in self._periods:
            return []

        period = self._periods[period_id]
        if period.settled:
            return []

        transactions = []

        # Credit generators
        for entity_id, mwh in period.generation_mwh.items():
            tx = self._ledger.record_generation(
                entity_id,
                mwh,
                period.region_id,
            )
            if tx:
                transactions.append(tx)

        # Debit consumers
        for entity_id, mwh in period.consumption_mwh.items():
            # Ensure account exists
            self._ledger.get_or_create_account(entity_id)
            tx = self._ledger.record_consumption(
                entity_id,
                mwh,
                period.region_id,
            )
            if tx:
                transactions.append(tx)

        period.settled = True
        period.settlement_ms = int(time.time() * 1000)

        return transactions

    def settle_current(self) -> List[Transaction]:
        """Settle current period and start new one."""
        if self._current_period is None:
            return []

        transactions = self.settle_period(self._current_period.period_id)

        # Start new period
        self.start_period(
            self._current_period.region_id,
            self._current_period.end_ms,
        )

        return transactions

    def tick(self, now_ms: int | None = None) -> List[Transaction]:
        """Check if settlement is due and run if needed."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        if self._current_period is None:
            return []

        # Check if period ended
        if now_ms >= self._current_period.end_ms + self._config.settlement_delay_ms:
            return self.settle_current()

        return []

    def get_period(self, period_id: str) -> Optional[SettlementPeriod]:
        """Get a settlement period by ID."""
        return self._periods.get(period_id)

    def get_current_period(self) -> Optional[SettlementPeriod]:
        """Get current period."""
        return self._current_period

    def get_unsettled_periods(self) -> List[SettlementPeriod]:
        """Get all unsettled periods."""
        return [p for p in self._periods.values() if not p.settled]

    def compute_settlement_summary(self, period_id: str) -> Dict:
        """Compute summary for a settlement period."""
        period = self._periods.get(period_id)
        if period is None:
            return {}

        total_consumption = sum(period.consumption_mwh.values())
        total_generation = sum(period.generation_mwh.values())

        return {
            "period_id": period_id,
            "region_id": period.region_id,
            "start_ms": period.start_ms,
            "end_ms": period.end_ms,
            "settled": period.settled,
            "num_consumers": len(period.consumption_mwh),
            "num_generators": len(period.generation_mwh),
            "total_consumption_mwh": total_consumption,
            "total_generation_mwh": total_generation,
            "net_mwh": total_generation - total_consumption,
        }
