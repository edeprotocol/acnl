"""
ACNL Mesh — Fractal Mesh Topology

The mesh connects LFIs, RCs, GHs, and assets in a fractal hierarchy.
"""
from .node import MeshNode, NodeRole
from .graph import MeshGraph
from .aggregator import LocalFieldBuilder, AggregatorConfig

__all__ = [
    "MeshNode",
    "NodeRole",
    "MeshGraph",
    "LocalFieldBuilder",
    "AggregatorConfig",
]
