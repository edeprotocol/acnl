"""
ACNL Core — Spatio-Temporal Coordinates

Coord = where and when something happens in the energy-compute graph.
Region hierarchy enables fractal aggregation: site → country → continent → planet → solar system.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import time


# Type alias for region identifiers
RegionID = str


@dataclass(frozen=True)
class Coord:
    """
    Spatio-temporal coordinate in energy-compute graph.

    Region hierarchy examples:
        earth/eu/fr/idf/dc-paris-1
        earth/na/us/ca/dc-sfo-1
        orbit/leo/starlink-cluster-7
        mars/valles/base-alpha

    Time: monotonic milliseconds since Unix epoch.
    """
    region_id: RegionID
    ts_ms: int

    @staticmethod
    def now(region_id: RegionID) -> "Coord":
        """Create coordinate at current time."""
        return Coord(region_id=region_id, ts_ms=int(time.time() * 1000))

    def age_ms(self, now_ms: Optional[int] = None) -> int:
        """Age of this coordinate in milliseconds."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return now_ms - self.ts_ms

    def parent_region(self) -> Optional[RegionID]:
        """
        Get parent region.

        Example: 'earth/eu/fr' → 'earth/eu'
        """
        parts = self.region_id.rsplit("/", 1)
        if len(parts) > 1:
            return parts[0]
        return None

    def region_hierarchy(self) -> List[str]:
        """
        Get region hierarchy as list.

        Example: 'earth/us/west/dc-1' → ['earth', 'us', 'west', 'dc-1']
        """
        return self.region_id.split("/")

    def foyer(self) -> str:
        """
        Get top-level foyer (earth, mars, orbit, etc.).

        Example: 'earth/eu/fr/idf/dc-1' → 'earth'
        """
        return self.region_id.split("/")[0]

    def depth(self) -> int:
        """Region depth in hierarchy."""
        return self.region_id.count("/")

    def is_ancestor_of(self, other: "Coord") -> bool:
        """Check if this coord's region is an ancestor of other's region."""
        return region_contains(self.region_id, other.region_id)


def region_contains(parent: RegionID, child: RegionID) -> bool:
    """Check if parent region contains child region."""
    return child == parent or child.startswith(parent + "/")


def region_depth(region_id: RegionID) -> int:
    """Return depth of region in hierarchy."""
    return region_id.count("/")


def common_ancestor(region_a: RegionID, region_b: RegionID) -> RegionID:
    """Find common ancestor region of two regions."""
    parts_a = region_a.split("/")
    parts_b = region_b.split("/")

    common = []
    for a, b in zip(parts_a, parts_b):
        if a == b:
            common.append(a)
        else:
            break

    return "/".join(common) if common else ""
