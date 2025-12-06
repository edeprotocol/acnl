"""
Integration test: PFC Node Tau Throttling

Tests the real PFC (Proof → Field → Control) loop:
1. PFCNode receives energy assertions
2. Builds field and computes tau limits
3. Tau limits correctly throttle compute based on:
   - Available power
   - Carbon intensity
   - Line congestion
   - Regional constraints
"""

import pytest
import time

from sfl.energy.model import (
    Assertion,
    Observable,
    EnergyObservableKind,
    Coord,
)
from sfl.runtime import PFCNode, PFCConfig, PFCPhase, create_pfc_node
from sfl.selection import PatternSpec
from sfl.mesh.controllers import TauLimitConfig


def make_assertion(
    issuer: str,
    subject: str,
    region: str,
    kind: EnergyObservableKind,
    value: float,
    unit: str = "",
) -> Assertion:
    """Create a generic assertion."""
    now_ms = int(time.time() * 1000)
    return Assertion(
        assertion_id=f"assert-{now_ms}-{subject}-{kind.value}",
        issuer=issuer,
        subject=subject,
        coord=Coord(region_id=region, ts_ms=now_ms),
        observable=Observable(kind=kind, value=value, unit=unit),
    )


class TestPFCNodeTauThrottling:
    """Test PFCNode tau throttling behavior."""

    def test_pfc_loop_phases(self):
        """Verify PFC executes all three phases."""
        region = "earth/us/west/dc-1"
        node = create_pfc_node(region, "test-node")

        phases_seen = []
        node.on_phase_change(lambda phase: phases_seen.append(phase))

        # Add some assertions
        assertions = [
            make_assertion(
                "sensor:meter-1",
                "compute-node:gpu-1",
                region,
                EnergyObservableKind.CONSUMPTION_POWER,
                50.0,
                "MW",
            ),
            make_assertion(
                "sensor:meter-1",
                "compute-node:gpu-1",
                region,
                EnergyObservableKind.AVAILABLE_POWER,
                100.0,
                "MW",
            ),
        ]
        node.ingest_assertions(assertions)

        # Run one tick
        node.tick()

        # Verify all phases executed
        assert PFCPhase.PROOF in phases_seen
        assert PFCPhase.FIELD in phases_seen
        assert PFCPhase.CONTROL in phases_seen

    def test_tau_throttling_on_low_power(self):
        """Verify tau is reduced when available power is low."""
        region = "earth/us/west/dc-1"

        config = PFCConfig(
            region_id=region,
            node_id="test-node",
            tau_config=TauLimitConfig(
                base_power_mw=100.0,
                min_tau=0.01,
                max_tau=2.0,
            ),
        )
        node = PFCNode(config)

        # High power node
        high_power = [
            make_assertion("sensor:meter", "compute-node:gpu-high", region,
                          EnergyObservableKind.AVAILABLE_POWER, 100.0, "MW"),
            make_assertion("sensor:meter", "compute-node:gpu-high", region,
                          EnergyObservableKind.CARBON_INTENSITY, 50.0, "gCO2/kWh"),
        ]

        # Low power node
        low_power = [
            make_assertion("sensor:meter", "compute-node:gpu-low", region,
                          EnergyObservableKind.AVAILABLE_POWER, 10.0, "MW"),
            make_assertion("sensor:meter", "compute-node:gpu-low", region,
                          EnergyObservableKind.CARBON_INTENSITY, 50.0, "gCO2/kWh"),
        ]

        node.ingest_assertions(high_power + low_power)
        node.tick()

        tau_high = node.get_tau_limit("compute-node:gpu-high")
        tau_low = node.get_tau_limit("compute-node:gpu-low")

        # Low power node should have lower tau
        assert tau_high > tau_low
        assert tau_low < 0.5  # Significantly throttled

    def test_tau_throttling_on_high_carbon(self):
        """Verify tau is reduced when carbon intensity is high."""
        region = "earth/eu/de/dc-1"

        config = PFCConfig(
            region_id=region,
            node_id="test-node",
            tau_config=TauLimitConfig(
                base_power_mw=100.0,
                carbon_ceiling=500.0,
                carbon_penalty=0.5,
                min_tau=0.01,
                max_tau=2.0,
            ),
        )
        node = PFCNode(config)

        # Clean node (low carbon)
        clean = [
            make_assertion("sensor:grid", "compute-node:gpu-clean", region,
                          EnergyObservableKind.AVAILABLE_POWER, 100.0, "MW"),
            make_assertion("sensor:grid", "compute-node:gpu-clean", region,
                          EnergyObservableKind.CARBON_INTENSITY, 50.0, "gCO2/kWh"),
        ]

        # Dirty node (high carbon)
        dirty = [
            make_assertion("sensor:grid", "compute-node:gpu-dirty", region,
                          EnergyObservableKind.AVAILABLE_POWER, 100.0, "MW"),
            make_assertion("sensor:grid", "compute-node:gpu-dirty", region,
                          EnergyObservableKind.CARBON_INTENSITY, 600.0, "gCO2/kWh"),
        ]

        node.ingest_assertions(clean + dirty)
        node.tick()

        tau_clean = node.get_tau_limit("compute-node:gpu-clean")
        tau_dirty = node.get_tau_limit("compute-node:gpu-dirty")

        # Dirty node should be throttled
        assert tau_clean > tau_dirty
        # Carbon penalty should reduce tau by ~50%
        assert tau_dirty < tau_clean * 0.6

    def test_tau_throttling_on_congestion(self):
        """Verify tau is reduced when line congestion is high."""
        region = "earth/us/ca/dc-1"

        config = PFCConfig(
            region_id=region,
            node_id="test-node",
            tau_config=TauLimitConfig(
                base_power_mw=100.0,
                congestion_threshold=0.8,
                min_tau=0.01,
                max_tau=2.0,
            ),
        )
        node = PFCNode(config)

        # Uncongested node
        uncongested = [
            make_assertion("sensor:grid", "compute-node:gpu-1", region,
                          EnergyObservableKind.AVAILABLE_POWER, 100.0, "MW"),
            make_assertion("sensor:grid", "compute-node:gpu-1", region,
                          EnergyObservableKind.LINE_LOADING, 0.3, ""),
            make_assertion("sensor:grid", "compute-node:gpu-1", region,
                          EnergyObservableKind.CARBON_INTENSITY, 100.0, "gCO2/kWh"),
        ]

        # Congested node
        congested = [
            make_assertion("sensor:grid", "compute-node:gpu-2", region,
                          EnergyObservableKind.AVAILABLE_POWER, 100.0, "MW"),
            make_assertion("sensor:grid", "compute-node:gpu-2", region,
                          EnergyObservableKind.LINE_LOADING, 0.95, ""),
            make_assertion("sensor:grid", "compute-node:gpu-2", region,
                          EnergyObservableKind.CARBON_INTENSITY, 100.0, "gCO2/kWh"),
        ]

        node.ingest_assertions(uncongested + congested)
        node.tick()

        tau_1 = node.get_tau_limit("compute-node:gpu-1")
        tau_2 = node.get_tau_limit("compute-node:gpu-2")

        # Congested node should be heavily throttled
        assert tau_1 > tau_2
        assert tau_2 < tau_1 * 0.5

    def test_regional_constraints_propagate(self):
        """Verify regional constraints affect tau limits."""
        region = "earth/eu/fr/dc-1"
        node = create_pfc_node(region, "test-node")

        assertions = [
            make_assertion("sensor:meter", "compute-node:gpu-1", region,
                          EnergyObservableKind.AVAILABLE_POWER, 100.0, "MW"),
            make_assertion("sensor:meter", "compute-node:gpu-1", region,
                          EnergyObservableKind.CARBON_INTENSITY, 50.0, "gCO2/kWh"),
        ]
        node.ingest_assertions(assertions)

        # First tick without constraints
        node.tick()
        tau_unconstrained = node.get_tau_limit("compute-node:gpu-1")

        # Apply regional constraint (50% throttle)
        node.set_regional_constraints({
            "carbon_throttle": 0.5,
            "power_quota": 1.0,
        })

        node.tick()
        tau_constrained = node.get_tau_limit("compute-node:gpu-1")

        # Constrained tau should be about half
        assert tau_constrained < tau_unconstrained * 0.6

    def test_pattern_selection_respects_tau(self):
        """Verify pattern selection respects tau limits."""
        region = "earth/us/west/dc-1"
        node = create_pfc_node(region, "test-node")

        # Register patterns with different tau requirements
        node.register_pattern(PatternSpec(
            pattern_id="pattern:llm-inference",
            priority=100,
            min_tau=0.5,
            max_tau=2.0,
        ))
        node.register_pattern(PatternSpec(
            pattern_id="pattern:batch-training",
            priority=50,
            min_tau=0.8,  # Requires more tau
            max_tau=2.0,
        ))
        node.register_pattern(PatternSpec(
            pattern_id="pattern:monitoring",
            priority=200,
            min_tau=0.01,  # Very low requirement
            max_tau=0.1,
        ))

        # Create low-power scenario
        assertions = [
            make_assertion("sensor:grid", "compute-node:gpu-1", region,
                          EnergyObservableKind.AVAILABLE_POWER, 30.0, "MW"),
            make_assertion("sensor:grid", "compute-node:gpu-1", region,
                          EnergyObservableKind.CARBON_INTENSITY, 100.0, "gCO2/kWh"),
        ]
        node.ingest_assertions(assertions)
        node.tick()

        selection = node.get_selection()
        assert selection is not None

        # Low tau should reject high-requirement patterns
        # monitoring should always be selected (low min_tau, high priority)
        assert "pattern:monitoring" in selection.selected

    def test_metrics_track_operations(self):
        """Verify PFCNode metrics are correctly tracked."""
        region = "earth/us/west/dc-1"
        node = create_pfc_node(region, "test-node")

        # Ingest some assertions
        assertions = [
            make_assertion("sensor:meter", f"compute-node:gpu-{i}", region,
                          EnergyObservableKind.AVAILABLE_POWER, 50.0 + i * 10, "MW")
            for i in range(5)
        ]
        node.ingest_assertions(assertions)

        # Run multiple ticks
        for _ in range(3):
            node.tick()

        metrics = node.get_metrics()

        assert metrics.ticks == 3
        assert metrics.assertions_ingested == 5
        assert metrics.avg_tick_duration_ms >= 0

    def test_field_callback_invoked(self):
        """Verify field update callbacks are invoked."""
        region = "earth/eu/nl/dc-1"
        node = create_pfc_node(region, "test-node")

        fields_received = []
        node.on_field_update(lambda f: fields_received.append(f))

        assertions = [
            make_assertion("sensor:meter", "compute-node:gpu-1", region,
                          EnergyObservableKind.AVAILABLE_POWER, 100.0, "MW"),
        ]
        node.ingest_assertions(assertions)
        node.tick()

        assert len(fields_received) == 1
        assert fields_received[0] is not None
        assert len(fields_received[0].points) == 1
