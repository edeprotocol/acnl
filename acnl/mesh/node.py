"""
ACNL Mesh — Node Representation

Nodes in the fractal mesh: LFIs, RCs, GHs, assets, patterns.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

from ..core.ids import EntityID, entity_kind


class NodeRole(str, Enum):
    """Role of a mesh node."""
    LFI = "lfi"           # Local Field Integrator
    RC = "rc"             # Regional Coordinator
    GH = "gh"             # Global Harmonizer
    ASSET = "asset"       # Energy/compute asset
    PATTERN = "pattern"   # AGI pattern


@dataclass
class MeshNode:
    """
    Node in the fractal mesh.

    Can be a controller (LFI/RC/GH) or an asset (plant, compute-node).
    """
    node_id: EntityID
    region_id: str
    role: NodeRole

    # Node state
    status: str = "active"  # active, degraded, offline
    last_seen_ms: int = 0

    # Metadata
    meta: Dict[str, Any] = field(default_factory=dict)

    # Hierarchy (for controllers)
    parent_id: Optional[EntityID] = None      # e.g., LFI's parent is RC
    children_ids: List[EntityID] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return entity_kind(self.node_id)

    def is_controller(self) -> bool:
        return self.role in (NodeRole.LFI, NodeRole.RC, NodeRole.GH)

    def is_asset(self) -> bool:
        return self.role == NodeRole.ASSET
