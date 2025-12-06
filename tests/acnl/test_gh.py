import pytest

from acnl.control import (
    LocalFieldIntegrator,
    LFIConfig,
    RegionalCoordinator,
    RCConfig,
    GlobalHarmonizer,
    GHConfig,
)
from acnl.integration import generate_simulated_assertions


def test_gh_basic():
    """Test basic GH functionality."""
    gh = GlobalHarmonizer()

    # Create RC and get summary
    rc = RegionalCoordinator(RCConfig(region_id="test/region-1"))
    lfi = LocalFieldIntegrator(LFIConfig(region_id="test/sub-1"))
    assertions = generate_simulated_assertions("test/sub-1", 2, 1, 2)
    lfi.ingest_assertions(assertions)
    lfi.tick()
    rc.receive_lfi_summary(lfi.get_summary())
    rc.tick()

    gh.receive_rc_summary(rc.get_summary())
    gh.tick()

    summary = gh.get_global_summary()
    assert summary["num_regions"] == 1
    assert "global_carbon_intensity" in summary


def test_gh_multiple_regions():
    """Test GH with multiple regions."""
    gh = GlobalHarmonizer()

    for i in range(3):
        rc = RegionalCoordinator(RCConfig(region_id=f"test/region-{i}", rc_name=f"rc-{i}"))
        lfi = LocalFieldIntegrator(
            LFIConfig(region_id=f"test/region-{i}/sub", lfi_name=f"lfi-{i}")
        )
        assertions = generate_simulated_assertions(f"test/region-{i}/sub", 2, 1, 2)
        lfi.ingest_assertions(assertions)
        lfi.tick()
        rc.receive_lfi_summary(lfi.get_summary())
        rc.tick()
        gh.receive_rc_summary(rc.get_summary())

    gh.tick()

    summary = gh.get_global_summary()
    assert summary["num_regions"] == 3


def test_gh_region_rankings():
    """Test region ranking."""
    gh = GlobalHarmonizer()

    for i in range(3):
        rc = RegionalCoordinator(RCConfig(region_id=f"test/region-{i}", rc_name=f"rc-{i}"))
        lfi = LocalFieldIntegrator(
            LFIConfig(region_id=f"test/region-{i}/sub", lfi_name=f"lfi-{i}")
        )
        assertions = generate_simulated_assertions(
            f"test/region-{i}/sub",
            num_compute_nodes=2 + i,
            num_plants=1 + i,
            readings_per_entity=2,
        )
        lfi.ingest_assertions(assertions)
        lfi.tick()
        rc.receive_lfi_summary(lfi.get_summary())
        rc.tick()
        gh.receive_rc_summary(rc.get_summary())

    gh.tick()

    rankings = gh.get_region_rankings()
    assert len(rankings) == 3
    # Should be sorted by efficiency
    for r in rankings:
        assert "efficiency_score" in r


def test_gh_load_shift_recommendations():
    """Test load shift recommendations."""
    gh = GlobalHarmonizer()

    for i in range(2):
        rc = RegionalCoordinator(RCConfig(region_id=f"test/region-{i}", rc_name=f"rc-{i}"))
        lfi = LocalFieldIntegrator(
            LFIConfig(region_id=f"test/region-{i}/sub", lfi_name=f"lfi-{i}")
        )
        assertions = generate_simulated_assertions(f"test/region-{i}/sub", 2, 1, 2)
        lfi.ingest_assertions(assertions)
        lfi.tick()
        rc.receive_lfi_summary(lfi.get_summary())
        rc.tick()
        gh.receive_rc_summary(rc.get_summary())

    gh.tick()

    recommendations = gh.recommend_load_shift()
    # May or may not have recommendations based on generated data
    assert isinstance(recommendations, list)
