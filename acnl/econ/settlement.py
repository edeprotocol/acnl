"""
ACNL Econ — Settlement Engine

Settles energy consumption against generation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time

from ..core.ids import EntityID
from ..core.fields import LocalField
from .accounts import AccountLedger, Transaction


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


class SettlementEngine:
    """Settles energy consumption against generation."""

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
        field: LocalField,
        duration_ms: int,
    ) -> None:
        """Record consumption and generation from a field snapshot."""
        for point in field.plants():
            self.record_generation(
                point.subject,
                point.generation_power_mw,
                duration_ms,
            )

        for point in field.compute_nodes():
            self.record_consumption(
                point.subject,
                point.consumption_power_mw,
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

    def tick(self, now_ms: int | None = None) -> List[Transaction]:
        """Check if settlement is due and run if needed."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        if self._current_period is None:
            return []

        if now_ms >= self._current_period.end_ms + self._config.settlement_delay_ms:
            txs = self.settle_period(self._current_period.period_id)
            self.start_period(
                self._current_period.region_id,
                self._current_period.end_ms,
            )
            return txs

        return []
