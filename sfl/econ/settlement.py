from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid
import time

from sfl.energy.model import EntityID
from .accounts import AccountStore, EnergyAccount


@dataclass
class ComputeEnergySettlement:
    """Record of compute-energy consumption."""

    settlement_id: str
    consumer_id: EntityID       # pattern/agent
    provider_id: EntityID       # compute-node
    region_id: str

    tcu: float                  # compute units consumed
    kwh: float                  # energy consumed
    duration_ms: int            # duration of work

    carbon_intensity: float     # gCO2/kWh at time of consumption
    carbon_gco2: float          # total carbon

    ts_ms: int                  # timestamp

    # Optional pricing (for external settlement)
    price_per_tcu: Optional[float] = None
    price_per_kwh: Optional[float] = None
    total_amount: Optional[float] = None


class SettlementEngine:
    """Creates and processes settlements."""

    def __init__(self, account_store: AccountStore):
        self.account_store = account_store
        self._settlements: List[ComputeEnergySettlement] = []

    def create_settlement(
        self,
        consumer_id: EntityID,
        provider_id: EntityID,
        region_id: str,
        tcu: float,
        kwh: float,
        duration_ms: int,
        carbon_intensity: float,
    ) -> ComputeEnergySettlement:
        """Create and record a settlement."""

        settlement = ComputeEnergySettlement(
            settlement_id=str(uuid.uuid4()),
            consumer_id=consumer_id,
            provider_id=provider_id,
            region_id=region_id,
            tcu=tcu,
            kwh=kwh,
            duration_ms=duration_ms,
            carbon_intensity=carbon_intensity,
            carbon_gco2=kwh * carbon_intensity,
            ts_ms=int(time.time() * 1000),
        )

        # Update consumer account
        account = self.account_store.get_or_create_account(consumer_id)
        is_low_carbon = carbon_intensity < 100  # arbitrary threshold
        account.record_consumption(kwh, tcu, carbon_intensity, is_low_carbon)

        self._settlements.append(settlement)

        return settlement

    def get_settlements(
        self,
        consumer_id: Optional[EntityID] = None,
        since_ms: Optional[int] = None,
    ) -> List[ComputeEnergySettlement]:
        """Query settlements."""
        results = self._settlements

        if consumer_id:
            results = [s for s in results if s.consumer_id == consumer_id]

        if since_ms:
            results = [s for s in results if s.ts_ms >= since_ms]

        return results
