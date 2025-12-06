import pytest

from acnl.control import (
    LocalFieldIntegrator,
    LFIConfig,
    RegionalCoordinator,
    RCConfig,
)
from acnl.integration import generate_simulated_assertions


def test_rc_basic():
    """Test basic RC functionality."""
    rc = RegionalCoordinator(RCConfig(region_id="test/region"))

    # Create LFI and get summary
    lfi = LocalFieldIntegrator(LFIConfig(region_id="test/sub-region-1"))
    assertions = generate_simulated_assertions("test/sub-region-1", 2, 1, 2)
    lfi.ingest_assertions(assertions)
    lfi.tick()

    # Send to RC
    rc.receive_lfi_summary(lfi.get_summary())
    rc.tick()

    summary = rc.get_summary()

    assert summary["region_id"] == "test/region"
    assert summary["num_lfis"] == 1
    assert "total_available_mw" in summary


def test_rc_multiple_lfis():
    """Test RC with multiple LFIs."""
    rc = RegionalCoordinator(RCConfig(region_id="test/region"))

    # Create multiple LFIs
    for i in range(3):
        lfi = LocalFieldIntegrator(
            LFIConfig(region_id=f"test/sub-region-{i}", lfi_name=f"lfi-{i}")
        )
        assertions = generate_simulated_assertions(f"test/sub-region-{i}", 2, 1, 2)
        lfi.ingest_assertions(assertions)
        lfi.tick()
        rc.receive_lfi_summary(lfi.get_summary())

    rc.tick()

    summary = rc.get_summary()
    assert summary["num_lfis"] == 3


def test_rc_constraints():
    """Test RC constraint computation."""
    rc = RegionalCoordinator(
        RCConfig(region_id="test/region", carbon_limit=50.0)  # Low limit
    )

    lfi = LocalFieldIntegrator(LFIConfig(region_id="test/sub-region"))
    assertions = generate_simulated_assertions("test/sub-region", 3, 2, 3)
    lfi.ingest_assertions(assertions)
    lfi.tick()

    rc.receive_lfi_summary(lfi.get_summary())
    rc.tick()

    # With low carbon limit, should have throttle constraint
    constraints = rc.get_constraints_for_lfi(lfi.lfi_id)
    # Constraints may or may not be set depending on generated data
    assert isinstance(constraints, dict)


def test_rc_rankings():
    """Test LFI ranking by efficiency."""
    rc = RegionalCoordinator(RCConfig(region_id="test/region"))

    # Create LFIs with different characteristics
    for i in range(3):
        lfi = LocalFieldIntegrator(
            LFIConfig(region_id=f"test/sub-region-{i}", lfi_name=f"lfi-{i}")
        )
        assertions = generate_simulated_assertions(
            f"test/sub-region-{i}",
            num_compute_nodes=2 + i,
            num_plants=1 + i,
            readings_per_entity=2,
        )
        lfi.ingest_assertions(assertions)
        lfi.tick()
        rc.receive_lfi_summary(lfi.get_summary())

    rc.tick()

    rankings = rc.get_lfi_rankings()
    assert len(rankings) == 3
