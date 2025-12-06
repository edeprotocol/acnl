"""
Integration test: Compute-Energy Settlement Flow

Tests the full economic flow:
1. Agent runs compute workload
2. LFI measures energy consumption
3. Settlement is created with:
   - TCU consumed
   - kWh consumed
   - Carbon footprint (gCO2)
4. Account balances are updated
5. Credit lines are enforced
"""

import pytest
import time

from sfl.econ.accounts import AccountStore, EnergyAccount, ComputeEnergyCreditLine
from sfl.econ.settlement import SettlementEngine, ComputeEnergySettlement


class TestComputeEnergySettlementFlow:
    """Test the compute-energy settlement flow."""

    def test_settlement_creation(self):
        """Verify basic settlement creation."""
        account_store = AccountStore()
        engine = SettlementEngine(account_store)

        settlement = engine.create_settlement(
            consumer_id="pattern:llm-inference",
            provider_id="compute-node:gpu-1",
            region_id="earth/us/west/dc-1",
            tcu=100.0,
            kwh=0.5,
            duration_ms=1000,
            carbon_intensity=100.0,  # gCO2/kWh
        )

        assert settlement.settlement_id is not None
        assert settlement.tcu == 100.0
        assert settlement.kwh == 0.5
        assert settlement.carbon_gco2 == 50.0  # 0.5 kWh * 100 gCO2/kWh

    def test_settlement_updates_account(self):
        """Verify settlement updates consumer account."""
        account_store = AccountStore()
        engine = SettlementEngine(account_store)

        consumer_id = "pattern:training-job"

        # Create multiple settlements
        for i in range(3):
            engine.create_settlement(
                consumer_id=consumer_id,
                provider_id=f"compute-node:gpu-{i}",
                region_id="earth/eu/de/dc-1",
                tcu=100.0,
                kwh=1.0,
                duration_ms=1000,
                carbon_intensity=50.0,
            )

        # Check account
        account = account_store.get_account(consumer_id)
        assert account is not None
        assert account.kwh_consumed_total == 3.0
        assert account.tcu_consumed_total == 300.0
        assert account.total_carbon_gco2 == 150.0  # 3 * 50

    def test_low_carbon_tracking(self):
        """Verify low-carbon energy is tracked separately."""
        account_store = AccountStore()
        engine = SettlementEngine(account_store)

        consumer_id = "pattern:green-compute"

        # Low carbon settlement (renewable)
        engine.create_settlement(
            consumer_id=consumer_id,
            provider_id="compute-node:gpu-1",
            region_id="earth/eu/no/dc-1",  # Norway - hydro
            tcu=100.0,
            kwh=1.0,
            duration_ms=1000,
            carbon_intensity=20.0,  # Very low
        )

        # High carbon settlement
        engine.create_settlement(
            consumer_id=consumer_id,
            provider_id="compute-node:gpu-2",
            region_id="earth/eu/pl/dc-1",  # Poland - coal
            tcu=100.0,
            kwh=1.0,
            duration_ms=1000,
            carbon_intensity=800.0,  # Very high
        )

        account = account_store.get_account(consumer_id)
        assert account is not None

        # Only first settlement counts as low carbon
        assert account.kwh_low_carbon_total == 1.0
        assert account.kwh_consumed_total == 2.0

    def test_credit_line_enforcement(self):
        """Verify credit line limits consumption."""
        account_store = AccountStore()

        # Set up credit line
        credit_line = ComputeEnergyCreditLine(
            entity_id="pattern:limited-job",
            max_tcu=500.0,
            max_kwh=5.0,
            valid_until_ms=int(time.time() * 1000) + 3600_000,
        )
        account_store.set_credit_line(credit_line)

        # Check initial state
        cl = account_store.get_credit_line("pattern:limited-job")
        assert cl is not None
        assert cl.remaining_tcu() == 500.0
        assert cl.remaining_kwh() == 5.0

        # Simulate consumption
        cl.used_tcu = 400.0
        cl.used_kwh = 4.0

        # Check remaining
        assert cl.remaining_tcu() == 100.0
        assert cl.remaining_kwh() == 1.0

        # Check can_consume
        assert cl.can_consume(50.0, 0.5) is True
        assert cl.can_consume(150.0, 0.5) is False  # Over TCU
        assert cl.can_consume(50.0, 1.5) is False  # Over kWh

    def test_quota_enforcement(self):
        """Verify soft/hard quotas are enforced."""
        account_store = AccountStore()
        account = account_store.get_or_create_account("pattern:quota-test")

        # Set quotas
        account.kwh_quota_soft = 10.0
        account.kwh_quota_hard = 20.0
        account.tcu_quota_soft = 1000.0
        account.tcu_quota_hard = 2000.0

        # Under soft limit
        account.record_consumption(kwh=5.0, tcu=500.0, carbon_intensity=100.0)
        assert not account.is_over_soft_limit()
        assert not account.is_over_hard_limit()

        # Over soft, under hard
        account.record_consumption(kwh=6.0, tcu=600.0, carbon_intensity=100.0)
        assert account.is_over_soft_limit()
        assert not account.is_over_hard_limit()

        # Over hard limit
        account.record_consumption(kwh=10.0, tcu=1000.0, carbon_intensity=100.0)
        assert account.is_over_soft_limit()
        assert account.is_over_hard_limit()

    def test_period_reset(self):
        """Verify period reset works correctly."""
        account_store = AccountStore()
        account = account_store.get_or_create_account("pattern:period-test")

        # Consume in period
        account.record_consumption(kwh=10.0, tcu=1000.0, carbon_intensity=100.0)
        assert account.kwh_consumed_period == 10.0
        assert account.kwh_consumed_total == 10.0

        # Reset period
        account.reset_period()
        assert account.kwh_consumed_period == 0.0
        assert account.kwh_consumed_total == 10.0  # Total preserved

        # New consumption
        account.record_consumption(kwh=5.0, tcu=500.0, carbon_intensity=100.0)
        assert account.kwh_consumed_period == 5.0
        assert account.kwh_consumed_total == 15.0

    def test_settlement_query(self):
        """Verify settlement query functionality."""
        account_store = AccountStore()
        engine = SettlementEngine(account_store)

        now_ms = int(time.time() * 1000)

        # Create settlements for different consumers
        engine.create_settlement(
            consumer_id="pattern:job-a",
            provider_id="compute-node:gpu-1",
            region_id="earth/us/west/dc-1",
            tcu=100.0,
            kwh=1.0,
            duration_ms=1000,
            carbon_intensity=100.0,
        )
        engine.create_settlement(
            consumer_id="pattern:job-b",
            provider_id="compute-node:gpu-2",
            region_id="earth/us/west/dc-1",
            tcu=200.0,
            kwh=2.0,
            duration_ms=2000,
            carbon_intensity=100.0,
        )

        # Query all
        all_settlements = engine.get_settlements()
        assert len(all_settlements) == 2

        # Query by consumer
        job_a = engine.get_settlements(consumer_id="pattern:job-a")
        assert len(job_a) == 1
        assert job_a[0].tcu == 100.0

        # Query by time
        future = engine.get_settlements(since_ms=now_ms + 10_000)
        assert len(future) == 0

    def test_utilization_ratio(self):
        """Verify utilization ratio calculation."""
        account = EnergyAccount(entity_id="pattern:test")

        # Set quotas
        account.kwh_quota_soft = 100.0
        account.tcu_quota_soft = 1000.0

        # 50% utilization on kWh
        account.record_consumption(kwh=50.0, tcu=100.0, carbon_intensity=100.0)
        ratio = account.utilization_ratio()
        assert ratio == 0.5  # kWh is limiting (50/100 > 100/1000)

        # Now TCU becomes limiting
        account.record_consumption(kwh=10.0, tcu=800.0, carbon_intensity=100.0)
        ratio = account.utilization_ratio()
        assert ratio == 0.9  # TCU is limiting (900/1000 > 60/100)

    def test_carbon_ceiling_on_credit_line(self):
        """Verify credit line can specify carbon ceiling."""
        account_store = AccountStore()

        credit_line = ComputeEnergyCreditLine(
            entity_id="pattern:green-only",
            max_tcu=1000.0,
            max_kwh=10.0,
            carbon_intensity_ceiling=100.0,  # Only allow low-carbon
        )
        account_store.set_credit_line(credit_line)

        cl = account_store.get_credit_line("pattern:green-only")
        assert cl is not None
        assert cl.carbon_intensity_ceiling == 100.0

    def test_multi_region_settlement(self):
        """Verify settlements across multiple regions."""
        account_store = AccountStore()
        engine = SettlementEngine(account_store)

        consumer_id = "pattern:global-job"

        # Settlements in different regions
        # Note: is_low_carbon threshold is < 100, so 50 is low carbon, others are not
        regions = [
            ("earth/us/west/dc-1", 50.0),   # Low carbon - renewables (< 100)
            ("earth/eu/de/dc-1", 300.0),    # Medium carbon
            ("earth/asia/cn/dc-1", 600.0),  # High carbon - coal
        ]

        for region, carbon in regions:
            engine.create_settlement(
                consumer_id=consumer_id,
                provider_id=f"compute-node:{region}",
                region_id=region,
                tcu=100.0,
                kwh=1.0,
                duration_ms=1000,
                carbon_intensity=carbon,
            )

        account = account_store.get_account(consumer_id)
        assert account is not None

        # Total carbon: 50 + 300 + 600 = 950 gCO2
        assert account.total_carbon_gco2 == 950.0

        # Only first settlement (US with 50) is low carbon (< 100 threshold)
        assert account.kwh_low_carbon_total == 1.0
