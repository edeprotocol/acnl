"""Tests for ACNL sensors integration."""

import pytest
from acnl.core.ids import plant_id, compute_node_id
from acnl.core.observables import EnergyObservableKind
from acnl.integration.sensors import (
    SimulatedSensor,
    generate_simulated_assertions,
)


class TestSimulatedSensor:
    """Test SimulatedSensor."""

    def test_sensor_creation(self):
        sensor = SimulatedSensor(
            region_id="earth/test",
            plant_ids=[plant_id("solar-1")],
            compute_node_ids=[compute_node_id("gpu-1")],
        )
        assert sensor.region_id == "earth/test"

    def test_sensor_poll(self):
        sensor = SimulatedSensor(
            region_id="earth/test",
            plant_ids=[plant_id("solar-1"), plant_id("wind-1")],
            compute_node_ids=[compute_node_id("gpu-1"), compute_node_id("gpu-2")],
        )

        assertions = sensor.poll()
        assert len(assertions) > 0

        # Check we have assertions for plants and compute nodes
        subjects = [a.subject for a in assertions]
        assert any("plant:" in s for s in subjects)
        assert any("compute-node:" in s for s in subjects)

    def test_sensor_observable_types(self):
        sensor = SimulatedSensor(
            region_id="earth/test",
            plant_ids=[plant_id("solar-1")],
            compute_node_ids=[compute_node_id("gpu-1")],
        )

        assertions = sensor.poll()
        observables = {a.observable for a in assertions}

        # Should have generation for plants
        observable_kinds = {o.kind for o in observables}
        assert EnergyObservableKind.GENERATION_POWER in observable_kinds


class TestGenerateSimulatedAssertions:
    """Test generate_simulated_assertions helper."""

    def test_generate_default(self):
        assertions = generate_simulated_assertions("earth/test")
        assert len(assertions) > 0

    def test_generate_with_counts(self):
        assertions = generate_simulated_assertions(
            region_id="earth/test",
            plant_count=5,
            compute_count=10,
        )

        # Should have assertions for 5 plants and 10 compute nodes
        plant_subjects = {a.subject for a in assertions if "plant:" in a.subject}
        compute_subjects = {a.subject for a in assertions if "compute-node:" in a.subject}

        assert len(plant_subjects) == 5
        assert len(compute_subjects) == 10

    def test_assertions_have_valid_values(self):
        assertions = generate_simulated_assertions("earth/test")

        for a in assertions:
            # Values should be non-negative
            assert a.observable.value >= 0

            # Should have valid timestamps
            assert a.coord.ts_ms > 0

            # Should have correct region
            assert a.coord.region_id == "earth/test"
