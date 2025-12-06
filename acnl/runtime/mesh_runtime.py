"""
ACNL Runtime — Mesh Runtime

Full mesh orchestration: multiple LFIs → RCs → GH.
Fractal hierarchy for planetary-scale coordination.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
import threading
import time

from ..core.ids import EntityID, lfi_id, rc_id, gh_id
from ..core.fields import LocalField, RegionalField
from ..store.event_store import EventStore
from ..mesh.node import MeshNode, NodeRole
from ..mesh.graph import MeshGraph
from ..mesh.aggregator import LocalFieldBuilder, AggregatorConfig
from ..control.lfi import LocalFieldIntegrator
from ..control.rc import RegionalCoordinator
from ..control.gh import GlobalHarmonizer
from ..control.policies import TauLimitPolicy, DefaultTauLimitPolicy, KardashevPolicy


@dataclass
class MeshConfig:
    """Configuration for full mesh runtime."""
    tick_interval_ms: int = 1000
    rc_tick_interval_ms: int = 5000  # RC aggregates every 5s
    gh_tick_interval_ms: int = 10000  # GH harmonizes every 10s
    kardashev_target: float = 1.0
    auto_start: bool = False


class MeshRuntime:
    """
    Full mesh orchestration.

    Manages:
    - Multiple LFIs (local field integrators)
    - Regional Coordinators (RCs) aggregating LFI fields
    - Global Harmonizer (GH) for planetary optimization

    Fractal hierarchy: LFI → RC → GH
    """

    def __init__(self, config: MeshConfig | None = None):
        self._config = config or MeshConfig()
        self._graph = MeshGraph()

        # Controllers by region
        self._lfis: Dict[str, LocalFieldIntegrator] = {}
        self._rcs: Dict[str, RegionalCoordinator] = {}
        self._gh: Optional[GlobalHarmonizer] = None

        # Stores by region
        self._stores: Dict[str, EventStore] = {}
        self._builders: Dict[str, LocalFieldBuilder] = {}

        # Runtime state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._tick_count = 0
        self._last_rc_tick_ms = 0
        self._last_gh_tick_ms = 0

        # Callbacks
        self._on_lfi_update: Optional[Callable] = None
        self._on_rc_update: Optional[Callable] = None
        self._on_gh_update: Optional[Callable] = None

        if self._config.auto_start:
            self.start()

    @property
    def graph(self) -> MeshGraph:
        return self._graph

    @property
    def is_running(self) -> bool:
        return self._running

    def create_lfi(
        self,
        region_id: str,
        policy: TauLimitPolicy | None = None,
    ) -> LocalFieldIntegrator:
        """Create and register an LFI for a region."""
        with self._lock:
            if region_id in self._lfis:
                return self._lfis[region_id]

            store = EventStore()
            builder = LocalFieldBuilder(
                AggregatorConfig(region_id=region_id)
            )
            lfi = LocalFieldIntegrator(
                store,
                builder,
                policy or DefaultTauLimitPolicy(),
                region_id,
            )

            self._stores[region_id] = store
            self._builders[region_id] = builder
            self._lfis[region_id] = lfi

            # Register in mesh graph
            node = MeshNode(
                node_id=lfi_id(region_id),
                role=NodeRole.LFI,
                region_id=region_id,
            )
            self._graph.add_node(node)

            return lfi

    def create_rc(
        self,
        region_id: str,
        child_regions: List[str],
    ) -> RegionalCoordinator:
        """Create and register an RC for a region."""
        with self._lock:
            if region_id in self._rcs:
                return self._rcs[region_id]

            # Get child LFIs
            child_lfis = [
                self._lfis[r] for r in child_regions
                if r in self._lfis
            ]

            rc = RegionalCoordinator(region_id, child_lfis)
            self._rcs[region_id] = rc

            # Register in mesh graph
            node = MeshNode(
                node_id=rc_id(region_id),
                role=NodeRole.RC,
                region_id=region_id,
            )
            self._graph.add_node(node)

            # Connect to child LFIs
            for child_region in child_regions:
                child_node_id = lfi_id(child_region)
                if self._graph.get_node(child_node_id):
                    self._graph.add_edge(rc_id(region_id), child_node_id)

            return rc

    def create_gh(
        self,
        child_regions: List[str],
        kardashev_target: float | None = None,
    ) -> GlobalHarmonizer:
        """Create the Global Harmonizer."""
        with self._lock:
            if self._gh is not None:
                return self._gh

            # Get child RCs
            child_rcs = [
                self._rcs[r] for r in child_regions
                if r in self._rcs
            ]

            target = kardashev_target or self._config.kardashev_target
            self._gh = GlobalHarmonizer(child_rcs, kardashev_target=target)

            # Register in mesh graph
            node = MeshNode(
                node_id=gh_id("global"),
                role=NodeRole.GH,
                region_id="global",
            )
            self._graph.add_node(node)

            # Connect to child RCs
            for child_region in child_regions:
                child_node_id = rc_id(child_region)
                if self._graph.get_node(child_node_id):
                    self._graph.add_edge(gh_id("global"), child_node_id)

            return self._gh

    def get_lfi(self, region_id: str) -> Optional[LocalFieldIntegrator]:
        """Get LFI for a region."""
        return self._lfis.get(region_id)

    def get_rc(self, region_id: str) -> Optional[RegionalCoordinator]:
        """Get RC for a region."""
        return self._rcs.get(region_id)

    def get_gh(self) -> Optional[GlobalHarmonizer]:
        """Get the Global Harmonizer."""
        return self._gh

    def on_lfi_update(self, callback: Callable) -> None:
        """Register callback for LFI field updates."""
        self._on_lfi_update = callback

    def on_rc_update(self, callback: Callable) -> None:
        """Register callback for RC aggregation updates."""
        self._on_rc_update = callback

    def on_gh_update(self, callback: Callable) -> None:
        """Register callback for GH harmonization updates."""
        self._on_gh_update = callback

    def start(self) -> None:
        """Start the mesh runtime."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the mesh runtime."""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def tick(self) -> None:
        """Run one tick of the mesh."""
        now_ms = int(time.time() * 1000)

        # Tick all LFIs
        for region_id, lfi in self._lfis.items():
            lfi.rebuild_field()
            if self._on_lfi_update:
                field = lfi.get_field()
                if field:
                    self._on_lfi_update(region_id, field)

        # Maybe tick RCs
        if now_ms - self._last_rc_tick_ms >= self._config.rc_tick_interval_ms:
            for region_id, rc in self._rcs.items():
                rc.aggregate_fields()
                if self._on_rc_update:
                    regional = rc.get_regional_field()
                    if regional:
                        self._on_rc_update(region_id, regional)
            self._last_rc_tick_ms = now_ms

        # Maybe tick GH
        if now_ms - self._last_gh_tick_ms >= self._config.gh_tick_interval_ms:
            if self._gh:
                self._gh.harmonize()
                if self._on_gh_update:
                    summary = self._gh.get_global_summary()
                    self._on_gh_update(summary)
            self._last_gh_tick_ms = now_ms

        self._tick_count += 1

    def _run_loop(self) -> None:
        """Main mesh loop."""
        while self._running:
            try:
                self.tick()
            except Exception as e:
                print(f"Mesh tick error: {e}")

            time.sleep(self._config.tick_interval_ms / 1000.0)

    def get_stats(self) -> dict:
        """Get mesh statistics."""
        return {
            "tick_count": self._tick_count,
            "is_running": self._running,
            "lfi_count": len(self._lfis),
            "rc_count": len(self._rcs),
            "has_gh": self._gh is not None,
            "node_count": len(self._graph.nodes()),
            "edge_count": len(self._graph.edges()),
        }

    def setup_demo_mesh(self) -> None:
        """Set up a demo mesh with sample regions."""
        # Create LFIs for data center regions
        self.create_lfi("earth/us/west/dc-1")
        self.create_lfi("earth/us/west/dc-2")
        self.create_lfi("earth/us/east/dc-1")
        self.create_lfi("earth/eu/west/dc-1")
        self.create_lfi("earth/eu/central/dc-1")

        # Create RCs for regional aggregation
        self.create_rc("earth/us/west", [
            "earth/us/west/dc-1",
            "earth/us/west/dc-2",
        ])
        self.create_rc("earth/us/east", [
            "earth/us/east/dc-1",
        ])
        self.create_rc("earth/eu", [
            "earth/eu/west/dc-1",
            "earth/eu/central/dc-1",
        ])

        # Create continental RCs
        self.create_rc("earth/us", [
            "earth/us/west",
            "earth/us/east",
        ])

        # Create GH
        self.create_gh([
            "earth/us",
            "earth/eu",
        ])
