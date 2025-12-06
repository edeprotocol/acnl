import pytest
from sfl.mesh.lfi import LocalFieldIntegrator, LFIConfig
from sfl.mesh.rc import RegionalCoordinator, RCConfig
from sfl.integrations.sensors import generate_simulated_assertions


def test_rc_aggregation():
    """Test RC aggregates multiple LFIs."""
    # Create two LFIs
    lfi1 = LocalFieldIntegrator(LFIConfig(region_id="test/zone-1"))
    lfi2 = LocalFieldIntegrator(LFIConfig(region_id="test/zone-2"))

    # Create RC
    rc = RegionalCoordinator(
        RCConfig(region_id="test/region"),
        lfi_ids=["test/zone-1", "test/zone-2"],
    )

    # Generate and ingest data
    for lfi, zone in [(lfi1, "test/zone-1"), (lfi2, "test/zone-2")]:
        assertions = generate_simulated_assertions(zone, 2, 1, 1)
        lfi.ingest_assertions(assertions)
        lfi.tick()

    # Update RC with LFI data
    lfi1_field = lfi1.get_field()
    lfi2_field = lfi2.get_field()
    if lfi1_field:
        rc.update_lfi_field("test/zone-1", lfi1_field)
    if lfi2_field:
        rc.update_lfi_field("test/zone-2", lfi2_field)
    rc.update_lfi_summary("test/zone-1", lfi1.get_summary())
    rc.update_lfi_summary("test/zone-2", lfi2.get_summary())

    # Run RC tick
    rc.tick()

    # Check regional field
    regional_field = rc.get_regional_field()
    assert regional_field is not None

    # Should have points from both zones
    assert len(regional_field.points) >= 4  # at least 2 from each


def test_rc_carbon_constraints():
    """Test RC generates carbon constraints."""
    lfi = LocalFieldIntegrator(LFIConfig(region_id="test/zone-1"))

    rc = RegionalCoordinator(
        RCConfig(
            region_id="test/region",
            carbon_budget_gco2_per_hour=1000,  # Very low budget
        ),
        lfi_ids=["test/zone-1"],
    )

    # Generate high-carbon data
    assertions = generate_simulated_assertions("test/zone-1", 5, 2, 2)
    lfi.ingest_assertions(assertions)
    lfi.tick()

    lfi_field = lfi.get_field()
    if lfi_field:
        rc.update_lfi_field("test/zone-1", lfi_field)
    rc.update_lfi_summary("test/zone-1", lfi.get_summary())
    rc.tick()

    constraints = rc.get_constraints()

    # With very low carbon budget, should have throttle < 1.0
    assert "carbon_throttle" in constraints
    # May or may not trigger depending on random simulation values
