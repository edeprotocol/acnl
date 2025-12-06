"""Tests for ACNL mesh graph."""

import pytest
from acnl.core.ids import lfi_id, rc_id
from acnl.mesh.node import MeshNode, NodeRole
from acnl.mesh.graph import MeshGraph


class TestMeshGraph:
    """Test MeshGraph."""

    def test_add_node(self):
        graph = MeshGraph()
        node = MeshNode(
            node_id=lfi_id("earth/us/west"),
            role=NodeRole.LFI,
            region_id="earth/us/west",
        )
        graph.add_node(node)
        assert graph.get_node(lfi_id("earth/us/west")) == node

    def test_add_edge(self):
        graph = MeshGraph()
        lfi_node = MeshNode(
            node_id=lfi_id("earth/us/west"),
            role=NodeRole.LFI,
            region_id="earth/us/west",
        )
        rc_node = MeshNode(
            node_id=rc_id("earth/us"),
            role=NodeRole.RC,
            region_id="earth/us",
        )
        graph.add_node(lfi_node)
        graph.add_node(rc_node)
        graph.add_edge(rc_id("earth/us"), lfi_id("earth/us/west"))

        # Check neighbors
        neighbors = graph.neighbors(rc_id("earth/us"))
        assert lfi_id("earth/us/west") in neighbors

    def test_neighbors(self):
        graph = MeshGraph()
        lfi1 = MeshNode(node_id=lfi_id("earth/us/west"), role=NodeRole.LFI, region_id="earth/us/west")
        lfi2 = MeshNode(node_id=lfi_id("earth/us/east"), role=NodeRole.LFI, region_id="earth/us/east")
        rc = MeshNode(node_id=rc_id("earth/us"), role=NodeRole.RC, region_id="earth/us")

        graph.add_node(lfi1)
        graph.add_node(lfi2)
        graph.add_node(rc)
        graph.add_edge(rc_id("earth/us"), lfi_id("earth/us/west"))
        graph.add_edge(rc_id("earth/us"), lfi_id("earth/us/east"))

        neighbors = graph.neighbors(rc_id("earth/us"))
        assert len(neighbors) == 2
        assert lfi_id("earth/us/west") in neighbors
        assert lfi_id("earth/us/east") in neighbors

    def test_predecessors(self):
        graph = MeshGraph()
        lfi = MeshNode(node_id=lfi_id("earth/us/west"), role=NodeRole.LFI, region_id="earth/us/west")
        rc = MeshNode(node_id=rc_id("earth/us"), role=NodeRole.RC, region_id="earth/us")

        graph.add_node(lfi)
        graph.add_node(rc)
        graph.add_edge(rc_id("earth/us"), lfi_id("earth/us/west"))

        predecessors = graph.predecessors(lfi_id("earth/us/west"))
        assert len(predecessors) == 1
        assert rc_id("earth/us") in predecessors

    def test_nodes_by_role(self):
        graph = MeshGraph()
        lfi1 = MeshNode(node_id=lfi_id("earth/us/west"), role=NodeRole.LFI, region_id="earth/us/west")
        lfi2 = MeshNode(node_id=lfi_id("earth/us/east"), role=NodeRole.LFI, region_id="earth/us/east")
        rc = MeshNode(node_id=rc_id("earth/us"), role=NodeRole.RC, region_id="earth/us")

        graph.add_node(lfi1)
        graph.add_node(lfi2)
        graph.add_node(rc)

        lfis = graph.nodes_by_role(NodeRole.LFI)
        assert len(lfis) == 2

        rcs = graph.nodes_by_role(NodeRole.RC)
        assert len(rcs) == 1

    def test_remove_node(self):
        graph = MeshGraph()
        node = MeshNode(node_id=lfi_id("earth/us/west"), role=NodeRole.LFI, region_id="earth/us/west")
        graph.add_node(node)
        assert graph.get_node(lfi_id("earth/us/west")) is not None

        graph.remove_node(lfi_id("earth/us/west"))
        assert graph.get_node(lfi_id("earth/us/west")) is None
