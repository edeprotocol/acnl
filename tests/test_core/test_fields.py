"""Tests for ACNL core fields."""

import pytest
import time
from acnl.core.ids import compute_node_id, plant_id, Coord
from acnl.core.fields import (
    FieldPoint,
    LocalField,
    RegionalField,
    STANDARD_COMPUTE_FEATURES,
)


class TestFieldPoint:
    """Test FieldPoint dataclass."""

    def test_field_point_creation(self):
        coord = Coord.now("earth/test")
        point = FieldPoint(
            coord=coord,
            subject=compute_node_id("gpu-1"),
            metrics={
                "consumption_power_mw": 50.0,
                "available_power_mw": 100.0,
                "carbon_intensity": 100.0,
            },
            confidence=0.9,
            reliability=0.95,
        )
        assert point.subject == "compute-node:gpu-1"
        assert point.consumption_power_mw == 50.0
        assert point.available_power_mw == 100.0

    def test_field_point_get_set(self):
        coord = Coord.now("earth/test")
        point = FieldPoint(coord=coord, subject=plant_id("solar-1"))
        point.set("generation_power_mw", 100.0)
        assert point.get("generation_power_mw") == 100.0
        assert point.generation_power_mw == 100.0


class TestLocalField:
    """Test LocalField."""

    def create_test_field(self) -> LocalField:
        now_ms = int(time.time() * 1000)
        coord = Coord(region_id="earth/test", ts_ms=now_ms)

        field = LocalField(region_id="earth/test", generated_at_ms=now_ms)

        # Add a plant
        plant_point = FieldPoint(
            coord=coord,
            subject=plant_id("solar-1"),
            metrics={
                "generation_power_mw": 100.0,
                "carbon_intensity": 0.0,
            },
            confidence=0.95,
            reliability=0.99,
        )
        field.points[plant_point.subject] = plant_point

        # Add compute nodes
        for i in range(2):
            node_point = FieldPoint(
                coord=coord,
                subject=compute_node_id(f"gpu-{i+1}"),
                metrics={
                    "consumption_power_mw": 30.0 + i * 20,
                    "available_power_mw": 50.0,
                    "carbon_intensity": 50.0 + i * 50,
                },
                confidence=0.9,
                reliability=0.95 + i * 0.03,
            )
            field.points[node_point.subject] = node_point

        return field

    def test_local_field_creation(self):
        field = self.create_test_field()
        assert field.region_id == "earth/test"
        assert len(field.all_points()) == 3

    def test_plants_filter(self):
        field = self.create_test_field()
        plants = field.plants()
        assert len(plants) == 1
        assert plants[0].subject == "plant:solar-1"

    def test_compute_nodes_filter(self):
        field = self.create_test_field()
        nodes = field.compute_nodes()
        assert len(nodes) == 2

    def test_total_generation(self):
        field = self.create_test_field()
        assert field.total_generation() == 100.0

    def test_total_consumption(self):
        field = self.create_test_field()
        # 30 + 50 = 80
        assert field.total_consumption() == 80.0

    def test_avg_carbon_intensity(self):
        field = self.create_test_field()
        # (0 + 50 + 100) / 3 = 50
        assert field.avg_carbon_intensity() == 50.0

    def test_get_point(self):
        field = self.create_test_field()
        point = field.get_point(compute_node_id("gpu-1"))
        assert point is not None
        assert point.consumption_power_mw == 30.0

    def test_get_point_not_found(self):
        field = self.create_test_field()
        point = field.get_point(compute_node_id("nonexistent"))
        assert point is None

    def test_sorted_by_efficiency(self):
        field = self.create_test_field()
        sorted_points = field.sorted_by_efficiency()
        # gpu-1 has lower carbon (50) than gpu-2 (100)
        assert len(sorted_points) == 2
        assert sorted_points[0].carbon_intensity <= sorted_points[1].carbon_intensity


class TestRegionalField:
    """Test RegionalField."""

    def test_regional_field_creation(self):
        now_ms = int(time.time() * 1000)

        local1 = LocalField(region_id="earth/us/west", generated_at_ms=now_ms)
        local1.points[plant_id("solar-1")] = FieldPoint(
            coord=Coord.now("earth/us/west"),
            subject=plant_id("solar-1"),
            metrics={"generation_power_mw": 100.0},
            confidence=0.9,
        )

        local2 = LocalField(region_id="earth/us/east", generated_at_ms=now_ms)
        local2.points[plant_id("wind-1")] = FieldPoint(
            coord=Coord.now("earth/us/east"),
            subject=plant_id("wind-1"),
            metrics={"generation_power_mw": 50.0},
            confidence=0.85,
        )

        regional = RegionalField(region_id="earth/us", generated_at_ms=now_ms)
        regional.add_lfi_field("lfi-west", local1)
        regional.add_lfi_field("lfi-east", local2)

        assert regional.region_id == "earth/us"
        assert len(regional.lfi_fields) == 2

    def test_regional_aggregate(self):
        now_ms = int(time.time() * 1000)

        local1 = LocalField(region_id="earth/us/west", generated_at_ms=now_ms)
        local1.points[plant_id("solar-1")] = FieldPoint(
            coord=Coord.now("earth/us/west"),
            subject=plant_id("solar-1"),
            metrics={"generation_power_mw": 100.0},
            confidence=0.9,
        )

        regional = RegionalField(region_id="earth/us", generated_at_ms=now_ms)
        regional.add_lfi_field("lfi-west", local1)

        agg = regional.aggregate()
        assert agg is not None
        assert len(agg.all_points()) == 1
        assert agg.total_generation() == 100.0
