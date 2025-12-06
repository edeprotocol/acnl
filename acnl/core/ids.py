"""
ACNL Core — Entity Identification

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
from typing import NewType, Literal, Tuple

# Re-export Coord and RegionID for backwards compatibility
from .coord import Coord, RegionID, region_contains, region_depth, common_ancestor

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


def sensor_id(name: str) -> EntityID:
    return make_entity_id("sensor", name)


def agent_id(name: str) -> EntityID:
    return make_entity_id("agent", name)


def sovereign_id(name: str) -> EntityID:
    return make_entity_id("sovereign", name)


def substation_id(name: str) -> EntityID:
    return make_entity_id("substation", name)


def line_id(name: str) -> EntityID:
    return make_entity_id("line", name)


def storage_id(name: str) -> EntityID:
    return make_entity_id("storage", name)
