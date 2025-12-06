import pytest
import time
from sfl.energy.model import (
    Assertion,
    Observable,
    EnergyObservableKind,
    Coord,
    EnergyField,
    make_entity_id,
)
from sfl.energy.store import EventStore
from sfl.energy.field import EnergyFieldBuilder, FieldConfig
from sfl.energy.crypto import SigEnvelope, MockSignatureScheme


def test_field_builder_basic():
    """Test basic field building from assertions."""
    store = EventStore()
    config = FieldConfig(horizon_ms=10_000)
    builder = EnergyFieldBuilder(store, config, "test/region")

    signer = MockSignatureScheme()
    now_ms = int(time.time() * 1000)

    # Add some assertions
    node_id = make_entity_id("compute-node", "test-node-1")

    for i in range(5):
        assertion = Assertion.create(
            issuer="sensor:test",
            subject=node_id,
            coord=Coord(region_id="test/region", ts_ms=now_ms - i * 100),
            observable=Observable(
                kind=EnergyObservableKind.CONSUMPTION_POWER,
                value=50.0 + i,
                unit="MW",
            ),
        )
        env = SigEnvelope.wrap(assertion, "sensor:test", signer)
        store.add_assertion(env)

    # Build field
    field = builder.build(now_ms)

    assert field.region_id == "test/region"
    assert len(field.points) == 1

    point = field.points[0]
    assert point.subject == node_id
    assert EnergyObservableKind.CONSUMPTION_POWER.value in point.metrics
    assert point.confidence > 0


def test_field_builder_multiple_subjects():
    """Test field building with multiple subjects."""
    store = EventStore()
    # Lower min_confidence for unit tests with single issuer
    config = FieldConfig(horizon_ms=10_000, min_confidence=0.05)
    builder = EnergyFieldBuilder(store, config, "test/region")

    signer = MockSignatureScheme()
    now_ms = int(time.time() * 1000)

    # Add assertions for multiple nodes
    for node_idx in range(3):
        node_id = make_entity_id("compute-node", f"node-{node_idx}")

        for i in range(3):
            assertion = Assertion.create(
                issuer="sensor:test",
                subject=node_id,
                coord=Coord(region_id="test/region", ts_ms=now_ms - i * 100),
                observable=Observable(
                    kind=EnergyObservableKind.CONSUMPTION_POWER,
                    value=50.0 + node_idx * 10,
                    unit="MW",
                ),
            )
            env = SigEnvelope.wrap(assertion, "sensor:test", signer)
            store.add_assertion(env)

    field = builder.build(now_ms)

    assert len(field.points) == 3

    # Check we can get compute nodes
    compute_nodes = field.get_compute_nodes()
    assert len(compute_nodes) == 3


def test_field_builder_recency_weighting():
    """Test that recent assertions have more weight."""
    store = EventStore()
    # Lower min_confidence for unit tests with single issuer
    config = FieldConfig(horizon_ms=10_000, decay_factor=0.5, min_confidence=0.01)
    builder = EnergyFieldBuilder(store, config, "test/region")

    signer = MockSignatureScheme()
    now_ms = int(time.time() * 1000)

    node_id = make_entity_id("compute-node", "test-node")

    # Old assertion with high value
    old_assertion = Assertion.create(
        issuer="sensor:test",
        subject=node_id,
        coord=Coord(region_id="test/region", ts_ms=now_ms - 5000),
        observable=Observable(
            kind=EnergyObservableKind.CONSUMPTION_POWER,
            value=100.0,
            unit="MW",
        ),
    )
    store.add_assertion(SigEnvelope.wrap(old_assertion, "sensor:test", signer))

    # Recent assertion with low value
    recent_assertion = Assertion.create(
        issuer="sensor:test",
        subject=node_id,
        coord=Coord(region_id="test/region", ts_ms=now_ms - 100),
        observable=Observable(
            kind=EnergyObservableKind.CONSUMPTION_POWER,
            value=20.0,
            unit="MW",
        ),
    )
    store.add_assertion(SigEnvelope.wrap(recent_assertion, "sensor:test", signer))

    field = builder.build(now_ms)
    point = field.points[0]

    # Result should be closer to recent value (20) than old value (100)
    power = point.get_metric(EnergyObservableKind.CONSUMPTION_POWER)
    assert power < 60  # Should be weighted toward recent value
