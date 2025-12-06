"""
Integration test: Local Energy-Compute Field

Tests the full flow:
1. Sensors emit assertions about power/carbon
2. LFI builds energy field
3. Field contains correct aggregated metrics
4. Compute nodes see correct tau limits
"""

import pytest
import time

from sfl.energy.model import (
    Assertion,
    Observable,
    EnergyObservableKind,
    Coord,
    EntityID,
)
from sfl.energy.field import EnergyFieldBuilder, FieldConfig
from sfl.energy.store import EventStore
from sfl.energy.crypto import SigEnvelope, MockSignatureScheme
from sfl.mesh.lfi import LocalFieldIntegrator, LFIConfig
from sfl.mesh.controllers import TauLimitConfig


def make_power_assertion(
    issuer: str,
    subject: str,
    region: str,
    power_mw: float,
    ts_offset_ms: int = 0,
) -> Assertion:
    """Create a power consumption assertion."""
    now_ms = int(time.time() * 1000) + ts_offset_ms
    return Assertion(
        assertion_id=f"assert-{now_ms}-{subject}",
        issuer=issuer,
        subject=subject,
        coord=Coord(region_id=region, ts_ms=now_ms),
        observable=Observable(
            kind=EnergyObservableKind.CONSUMPTION_POWER,
            value=power_mw,
            unit="MW",
        ),
    )


def make_carbon_assertion(
    issuer: str,
    subject: str,
    region: str,
    gco2_kwh: float,
    ts_offset_ms: int = 0,
) -> Assertion:
    """Create a carbon intensity assertion."""
    now_ms = int(time.time() * 1000) + ts_offset_ms
    return Assertion(
        assertion_id=f"assert-carbon-{now_ms}-{subject}",
        issuer=issuer,
        subject=subject,
        coord=Coord(region_id=region, ts_ms=now_ms),
        observable=Observable(
            kind=EnergyObservableKind.CARBON_INTENSITY,
            value=gco2_kwh,
            unit="gCO2/kWh",
        ),
    )


def make_available_power_assertion(
    issuer: str,
    subject: str,
    region: str,
    power_mw: float,
    ts_offset_ms: int = 0,
) -> Assertion:
    """Create an available power assertion."""
    now_ms = int(time.time() * 1000) + ts_offset_ms
    return Assertion(
        assertion_id=f"assert-avail-{now_ms}-{subject}",
        issuer=issuer,
        subject=subject,
        coord=Coord(region_id=region, ts_ms=now_ms),
        observable=Observable(
            kind=EnergyObservableKind.AVAILABLE_POWER,
            value=power_mw,
            unit="MW",
        ),
    )


class TestLocalEnergyComputeField:
    """Test local energy-compute field integration."""

    def test_field_builds_from_assertions(self):
        """Verify field is correctly built from assertions."""
        region = "earth/us/west/dc-1"
        store = EventStore()
        signer = MockSignatureScheme("test-sensor")

        # Create assertions for compute nodes
        assertions = [
            make_power_assertion("sensor:meter-1", "compute-node:gpu-1", region, 50.0),
            make_power_assertion("sensor:meter-1", "compute-node:gpu-2", region, 75.0),
            make_carbon_assertion("sensor:grid-1", "compute-node:gpu-1", region, 100.0),
            make_carbon_assertion("sensor:grid-1", "compute-node:gpu-2", region, 100.0),
            make_available_power_assertion("sensor:grid-1", "compute-node:gpu-1", region, 100.0),
            make_available_power_assertion("sensor:grid-1", "compute-node:gpu-2", region, 150.0),
        ]

        # Ingest assertions
        for a in assertions:
            env = SigEnvelope.wrap(a, a.issuer, signer)
            store.add_assertion(env)

        # Build field
        builder = EnergyFieldBuilder(
            store=store,
            config=FieldConfig(horizon_ms=10_000),
            region_id=region,
        )
        field = builder.build()

        # Verify field
        assert field is not None
        assert len(field.points) == 2  # Two compute nodes

        # Check gpu-1 metrics
        gpu1 = field.get_point("compute-node:gpu-1")
        assert gpu1 is not None
        assert gpu1.get_metric(EnergyObservableKind.CONSUMPTION_POWER) == pytest.approx(50.0, rel=0.1)
        assert gpu1.get_metric(EnergyObservableKind.CARBON_INTENSITY) == pytest.approx(100.0, rel=0.1)

        # Check gpu-2 metrics
        gpu2 = field.get_point("compute-node:gpu-2")
        assert gpu2 is not None
        assert gpu2.get_metric(EnergyObservableKind.CONSUMPTION_POWER) == pytest.approx(75.0, rel=0.1)

    def test_lfi_computes_tau_limits(self):
        """Verify LFI correctly computes tau limits from field."""
        region = "earth/us/west/dc-1"

        lfi = LocalFieldIntegrator(LFIConfig(
            region_id=region,
            field_horizon_ms=10_000,
            tau_config=TauLimitConfig(
                base_power_mw=100.0,
                min_tau=0.01,
                max_tau=2.0,
            ),
        ))

        # Ingest assertions
        assertions = [
            make_power_assertion("sensor:meter-1", "compute-node:gpu-1", region, 30.0),
            make_available_power_assertion("sensor:grid-1", "compute-node:gpu-1", region, 80.0),
            make_carbon_assertion("sensor:grid-1", "compute-node:gpu-1", region, 50.0),
            make_power_assertion("sensor:meter-1", "compute-node:gpu-2", region, 90.0),
            make_available_power_assertion("sensor:grid-1", "compute-node:gpu-2", region, 20.0),
            make_carbon_assertion("sensor:grid-1", "compute-node:gpu-2", region, 400.0),
        ]

        lfi.ingest_assertions(assertions)

        # Run tick
        lfi.tick()

        # Check tau limits
        tau_limits = lfi.get_tau_limits()

        # gpu-1 has good power (80 MW) and low carbon → higher tau
        # gpu-2 has low power (20 MW) and high carbon → lower tau
        assert "compute-node:gpu-1" in tau_limits
        assert "compute-node:gpu-2" in tau_limits
        assert tau_limits["compute-node:gpu-1"] > tau_limits["compute-node:gpu-2"]

    def test_field_confidence_from_multiple_sources(self):
        """Verify field confidence increases with multiple assertion sources."""
        region = "earth/eu/de/dc-1"
        signer = MockSignatureScheme("test")

        # Single source - lower confidence
        # Note: confidence = count/10 * recency * diversity/3 = 0.1 * ~1.0 * 0.33 ≈ 0.033
        # So we need min_confidence=0.01 to include single-assertion points
        store_single = EventStore()
        a1 = make_power_assertion("sensor:meter-1", "compute-node:gpu-1", region, 50.0)
        env1 = SigEnvelope.wrap(a1, a1.issuer, signer)
        store_single.add_assertion(env1)

        builder_single = EnergyFieldBuilder(
            store=store_single,
            config=FieldConfig(horizon_ms=10_000, min_confidence=0.01),
            region_id=region,
        )
        field_single = builder_single.build()

        # Multiple sources - higher confidence
        store_multi = EventStore()
        assertions = [
            make_power_assertion("sensor:meter-1", "compute-node:gpu-1", region, 50.0),
            make_power_assertion("sensor:meter-2", "compute-node:gpu-1", region, 51.0),
            make_power_assertion("sensor:meter-3", "compute-node:gpu-1", region, 49.0),
        ]
        for a in assertions:
            env = SigEnvelope.wrap(a, a.issuer, signer)
            store_multi.add_assertion(env)

        builder_multi = EnergyFieldBuilder(
            store=store_multi,
            config=FieldConfig(horizon_ms=10_000, min_confidence=0.01),
            region_id=region,
        )
        field_multi = builder_multi.build()

        # Multi-source should have higher confidence
        point_single = field_single.get_point("compute-node:gpu-1")
        point_multi = field_multi.get_point("compute-node:gpu-1")

        assert point_single is not None, f"Single-source field has {len(field_single.points)} points"
        assert point_multi is not None, f"Multi-source field has {len(field_multi.points)} points"
        # More diverse sources = higher confidence
        assert point_multi.confidence > point_single.confidence

    def test_stale_assertions_decay(self):
        """Verify old assertions are weighted less than recent ones."""
        region = "earth/us/east/dc-1"
        store = EventStore()
        signer = MockSignatureScheme("test")

        # Old assertion
        old = make_power_assertion(
            "sensor:meter-1",
            "compute-node:gpu-1",
            region,
            100.0,
            ts_offset_ms=-5000,  # 5 seconds ago
        )

        # Recent assertion with different value
        recent = make_power_assertion(
            "sensor:meter-1",
            "compute-node:gpu-1",
            region,
            50.0,
            ts_offset_ms=0,  # now
        )

        for a in [old, recent]:
            env = SigEnvelope.wrap(a, a.issuer, signer)
            store.add_assertion(env)

        # Use min_confidence=0.01 to include points with few assertions
        builder = EnergyFieldBuilder(
            store=store,
            config=FieldConfig(horizon_ms=10_000, decay_factor=0.5, min_confidence=0.01),
            region_id=region,
        )
        field = builder.build()

        point = field.get_point("compute-node:gpu-1")
        assert point is not None, f"Field has {len(field.points)} points"

        # Value should be closer to 50 (recent) than 100 (old)
        power = point.get_metric(EnergyObservableKind.CONSUMPTION_POWER)
        assert power < 75  # Weighted toward recent value
