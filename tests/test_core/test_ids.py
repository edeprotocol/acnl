"""Tests for ACNL core IDs and coordinates."""

import pytest
from acnl.core.ids import (
    EntityID,
    Coord,
    compute_node_id,
    plant_id,
    pattern_id,
    lfi_id,
    rc_id,
    gh_id,
    parse_entity_id,
    get_entity_kind,
)


class TestEntityIDs:
    """Test entity ID creation and parsing."""

    def test_compute_node_id(self):
        eid = compute_node_id("gpu-cluster-1")
        assert eid == "compute-node:gpu-cluster-1"
        assert get_entity_kind(eid) == "compute-node"

    def test_plant_id(self):
        eid = plant_id("solar-farm-1")
        assert eid == "plant:solar-farm-1"
        assert get_entity_kind(eid) == "plant"

    def test_pattern_id(self):
        eid = pattern_id("llm-inference")
        assert eid == "pattern:llm-inference"
        assert get_entity_kind(eid) == "pattern"

    def test_lfi_id(self):
        eid = lfi_id("earth/us/west")
        assert eid == "lfi:earth/us/west"
        assert get_entity_kind(eid) == "lfi"

    def test_rc_id(self):
        eid = rc_id("earth/us")
        assert eid == "rc:earth/us"
        assert get_entity_kind(eid) == "rc"

    def test_gh_id(self):
        eid = gh_id("global")
        assert eid == "gh:global"
        assert get_entity_kind(eid) == "gh"

    def test_parse_entity_id(self):
        kind, name = parse_entity_id("compute-node:gpu-1")
        assert kind == "compute-node"
        assert name == "gpu-1"

    def test_parse_entity_id_with_colons(self):
        kind, name = parse_entity_id("plant:solar:v2")
        assert kind == "plant"
        assert name == "solar:v2"


class TestCoord:
    """Test spatio-temporal coordinates."""

    def test_coord_creation(self):
        coord = Coord(region_id="earth/us/west", ts_ms=1000)
        assert coord.region_id == "earth/us/west"
        assert coord.ts_ms == 1000

    def test_coord_now(self):
        coord = Coord.now("earth/eu")
        assert coord.region_id == "earth/eu"
        assert coord.ts_ms > 0

    def test_coord_hierarchy(self):
        coord = Coord(region_id="earth/us/west/dc-1", ts_ms=1000)
        hierarchy = coord.region_hierarchy()
        assert hierarchy == ["earth", "us", "west", "dc-1"]

    def test_coord_parent_region(self):
        coord = Coord(region_id="earth/us/west/dc-1", ts_ms=1000)
        assert coord.parent_region() == "earth/us/west"

    def test_coord_parent_region_top_level(self):
        coord = Coord(region_id="earth", ts_ms=1000)
        assert coord.parent_region() is None

    def test_coord_frozen(self):
        coord = Coord(region_id="earth", ts_ms=1000)
        with pytest.raises(Exception):
            coord.region_id = "mars"
