import pytest
import time
from sfl.mesh.lfi import LocalFieldIntegrator, LFIConfig
from sfl.energy.model import EnergyObservableKind
from sfl.integrations.sensors import generate_simulated_assertions


def test_lfi_basic():
    """Test basic LFI functionality."""
    config = LFIConfig(region_id="test/region-1")
    lfi = LocalFieldIntegrator(config)

    # Initially no field
    assert lfi.get_field() is None

    # Ingest some assertions
    assertions = generate_simulated_assertions("test/region-1", 2, 1, 1)
    lfi.ingest_assertions(assertions)

    # Run tick
    lfi.tick()

    # Now we should have a field
    field = lfi.get_field()
    assert field is not None
    assert field.region_id == "test/region-1"
    assert len(field.points) > 0


def test_tau_limit_computation():
    """Test tau limit computation based on energy state."""
    config = LFIConfig(region_id="test/region-1")
    lfi = LocalFieldIntegrator(config)

    # Ingest data
    assertions = generate_simulated_assertions("test/region-1", 3, 1, 2)
    lfi.ingest_assertions(assertions)
    lfi.tick()

    # Get tau limits
    tau_limits = lfi.get_tau_limits()

    # Should have limits for compute nodes
    compute_nodes = [k for k in tau_limits.keys() if "compute-node" in k]
    assert len(compute_nodes) > 0

    # All limits should be positive
    for limit in tau_limits.values():
        assert 0 < limit <= 2.0


def test_lfi_regional_constraints():
    """Test that regional constraints affect tau limits."""
    config = LFIConfig(region_id="test/region-1")
    lfi = LocalFieldIntegrator(config)

    # Ingest data
    assertions = generate_simulated_assertions("test/region-1", 2, 1, 1)
    lfi.ingest_assertions(assertions)
    lfi.tick()

    # Get baseline tau limits
    baseline_limits = lfi.get_tau_limits().copy()

    # Apply carbon throttle
    lfi.set_regional_constraints({"carbon_throttle": 0.5})
    lfi.tick()

    # Tau limits should be reduced
    throttled_limits = lfi.get_tau_limits()

    for node_id in baseline_limits:
        if node_id in throttled_limits:
            # Should be lower (or equal if already at minimum)
            assert throttled_limits[node_id] <= baseline_limits[node_id] + 0.01


def test_lfi_summary():
    """Test LFI summary generation."""
    config = LFIConfig(region_id="test/region-1")
    lfi = LocalFieldIntegrator(config)

    assertions = generate_simulated_assertions("test/region-1", 2, 1, 1)
    lfi.ingest_assertions(assertions)
    lfi.tick()

    summary = lfi.get_summary()

    assert summary["region_id"] == "test/region-1"
    assert "num_points" in summary
    assert "total_available_mw" in summary
    assert "avg_carbon_intensity" in summary
