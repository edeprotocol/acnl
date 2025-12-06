"""
ACNL Mesh — Graph Structure

Directed graph connecting mesh nodes.
Edges represent control/data flow, not physical topology.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Iterator
from threading import Lock

from ..core.ids import EntityID
from .node import MeshNode, NodeRole


@dataclass
class MeshGraph:
    """
    Graph of mesh nodes with adjacency tracking.

    Thread-safe for concurrent access.
    """

    nodes: Dict[EntityID, MeshNode] = field(default_factory=dict)
    adjacency: Dict[EntityID, Set[EntityID]] = field(default_factory=dict)
    reverse_adjacency: Dict[EntityID, Set[EntityID]] = field(default_factory=dict)

    _lock: Lock = field(default_factory=Lock)

    # ──────────────────────────────────────────────────────────────────────────
    # Node operations
    # ──────────────────────────────────────────────────────────────────────────

    def add_node(self, node: MeshNode) -> None:
        with self._lock:
            self.nodes[node.node_id] = node
            if node.node_id not in self.adjacency:
                self.adjacency[node.node_id] = set()
            if node.node_id not in self.reverse_adjacency:
                self.reverse_adjacency[node.node_id] = set()

    def get_node(self, node_id: EntityID) -> Optional[MeshNode]:
        with self._lock:
            return self.nodes.get(node_id)

    def remove_node(self, node_id: EntityID) -> None:
        with self._lock:
            if node_id in self.nodes:
                del self.nodes[node_id]
            # Remove edges
            if node_id in self.adjacency:
                for neighbor in self.adjacency[node_id]:
                    if neighbor in self.reverse_adjacency:
                        self.reverse_adjacency[neighbor].discard(node_id)
                del self.adjacency[node_id]
            if node_id in self.reverse_adjacency:
                for neighbor in self.reverse_adjacency[node_id]:
                    if neighbor in self.adjacency:
                        self.adjacency[neighbor].discard(node_id)
                del self.reverse_adjacency[node_id]

    # ──────────────────────────────────────────────────────────────────────────
    # Edge operations
    # ──────────────────────────────────────────────────────────────────────────

    def add_edge(self, from_id: EntityID, to_id: EntityID) -> None:
        with self._lock:
            if from_id not in self.adjacency:
                self.adjacency[from_id] = set()
            if to_id not in self.reverse_adjacency:
                self.reverse_adjacency[to_id] = set()
            self.adjacency[from_id].add(to_id)
            self.reverse_adjacency[to_id].add(from_id)

    def remove_edge(self, from_id: EntityID, to_id: EntityID) -> None:
        with self._lock:
            if from_id in self.adjacency:
                self.adjacency[from_id].discard(to_id)
            if to_id in self.reverse_adjacency:
                self.reverse_adjacency[to_id].discard(from_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Queries
    # ──────────────────────────────────────────────────────────────────────────

    def neighbors(self, node_id: EntityID) -> List[EntityID]:
        with self._lock:
            return list(self.adjacency.get(node_id, set()))

    def predecessors(self, node_id: EntityID) -> List[EntityID]:
        with self._lock:
            return list(self.reverse_adjacency.get(node_id, set()))

    def nodes_by_role(self, role: NodeRole) -> List[MeshNode]:
        with self._lock:
            return [n for n in self.nodes.values() if n.role == role]

    def nodes_by_kind(self, kind: str) -> List[MeshNode]:
        with self._lock:
            return [n for n in self.nodes.values() if n.kind == kind]

    def nodes_in_region(self, region_id: str) -> List[MeshNode]:
        with self._lock:
            return [n for n in self.nodes.values() if n.region_id == region_id]

    def lfis(self) -> List[MeshNode]:
        return self.nodes_by_role(NodeRole.LFI)

    def rcs(self) -> List[MeshNode]:
        return self.nodes_by_role(NodeRole.RC)

    def ghs(self) -> List[MeshNode]:
        return self.nodes_by_role(NodeRole.GH)

    # ──────────────────────────────────────────────────────────────────────────
    # Traversal
    # ──────────────────────────────────────────────────────────────────────────

    def bfs(self, start: EntityID) -> Iterator[EntityID]:
        """Breadth-first traversal from start node."""
        visited = set()
        queue = [start]
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            yield node_id
            queue.extend(self.neighbors(node_id))

    def path_to_gh(self, node_id: EntityID) -> List[EntityID]:
        """Find path from node to Global Harmonizer."""
        path = [node_id]
        current = node_id
        visited = set()

        while current and current not in visited:
            visited.add(current)
            node = self.get_node(current)
            if node and node.role == NodeRole.GH:
                return path
            if node and node.parent_id:
                path.append(node.parent_id)
                current = node.parent_id
            else:
                break

        return path
