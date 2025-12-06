"""
ACNL Core — Entity Identification and Coordinates

NAIVE DESIGN (rejected):
- UUIDs everywhere, no semantic meaning
- Flat namespace, no hierarchy

CRITIQUE:
- UUIDs don't encode entity type → requires separate lookup
- Flat namespace → no natural region hierarchy
- No support for multi-planetary addressing

FRACTAL DESIGN (implemented):
- Typed IDs: "kind:name" format
- Hierarchical regions: "foyer/continent/country/site"
- Immutable coordinates with monotonic time
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import NewType, Literal, Tuple
import time

# ══════════════════════════════════════════════════════════════════════════════
# ENTITY IDENTITY
# ══════════════════════════════════════════════════════════════════════════════

EntityID = NewType("EntityID", str)

EntityKind = Literal[
    # Energy infrastructure
    "plant",              # generation: nuclear, solar, wind, hydro, hydrogen, orbital-sbsp
    "substation",         # grid hub
    "line",               # transmission: HVDC, AC
    "storage",            # battery, H2, pumped-hydro, flywheel

    # Compute infrastructure
    "compute-node",       # GPU/TPU/CPU cluster
    "compute-cluster",    # group of compute-nodes

    # Agents and patterns
    "pattern",            # SFL pattern (AGI workload)
    "agent",              # autonomous agent

    # Controllers (fractal mesh)
    "lfi",                # Local Field Integrator
    "rc",                 # Regional Coordinator
    "gh",                 # Global Harmonizer

    # External
    "sensor",             # physical sensor
    "sovereign",          # state, central bank, regulatory body
    "operator",           # human infra operator (minimal role)
]


def make_entity_id(kind: EntityKind, name: str) -> EntityID:
    """Create typed EntityID."""
    if ":" in name:
        raise ValueError(f"Entity name cannot contain ':': {name}")
    return EntityID(f"{kind}:{name}")


def parse_entity_id(entity_id: EntityID) -> Tuple[str, str]:
    """Parse EntityID into (kind, name)."""
    parts = str(entity_id).split(":", 1)
    if len(parts) == 2:
        return (parts[0], parts[1])
    return ("unknown", str(entity_id))


def entity_kind(entity_id: EntityID) -> str:
    """Extract kind from EntityID."""
    return parse_entity_id(entity_id)[0]


# Alias for compatibility
get_entity_kind = entity_kind


def is_entity_kind(entity_id: EntityID, kind: EntityKind) -> bool:
    """Check if entity is of given kind."""
    return entity_kind(entity_id) == kind


# Convenience constructors
def plant_id(name: str) -> EntityID:
    return make_entity_id("plant", name)

def compute_node_id(name: str) -> EntityID:
    return make_entity_id("compute-node", name)

def pattern_id(name: str) -> EntityID:
    return make_entity_id("pattern", name)

def lfi_id(region: str) -> EntityID:
    return make_entity_id("lfi", region)

def rc_id(region: str) -> EntityID:
    return make_entity_id("rc", region)

def gh_id(foyer: str = "earth") -> EntityID:
    return make_entity_id("gh", foyer)


# ══════════════════════════════════════════════════════════════════════════════
# SPATIO-TEMPORAL COORDINATES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Coord:
    """
    Spatio-temporal coordinate in energy-compute graph.

    Region hierarchy:
      earth/eu/fr/idf/dc-paris-1
      earth/na/us/ca/dc-sfo-1
      orbit/leo/starlink-cluster-7
      mars/valles/base-alpha

    Time: monotonic milliseconds since epoch.
    """
    region_id: str
    ts_ms: int

    @staticmethod
    def now(region_id: str) -> "Coord":
        return Coord(region_id=region_id, ts_ms=int(time.time() * 1000))

    def age_ms(self, now_ms: int | None = None) -> int:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return now_ms - self.ts_ms

    def parent_region(self) -> str | None:
        """Get parent region (e.g., 'earth/eu/fr' → 'earth/eu')."""
        parts = self.region_id.rsplit("/", 1)
        if len(parts) > 1:
            return parts[0]
        return None

    def region_hierarchy(self) -> list[str]:
        """Get region hierarchy as list (e.g., ['earth', 'us', 'west', 'dc-1'])."""
        return self.region_id.split("/")

    def foyer(self) -> str:
        """Get top-level foyer (earth, mars, orbit)."""
        return self.region_id.split("/")[0]


def region_contains(parent: str, child: str) -> bool:
    """Check if parent region contains child region."""
    return child == parent or child.startswith(parent + "/")


def region_depth(region_id: str) -> int:
    """Return depth of region in hierarchy."""
    return region_id.count("/")
