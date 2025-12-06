"""SFL - Synthetic Field Layer with Energy-Compute Fractal Mesh.

The SFL package implements the fractal mesh architecture:
- LFI (Local Field Integrator): Local energy/compute integration
- RC (Regional Coordinator): Regional aggregation and constraints
- GH (Global Harmonizer): Civilizational-level coordination
- PFCNode: Real-time Proof → Field → Control loop

Key components:
- energy/: Energy field models and stores
- mesh/: LFI, RC, GH implementations
- econ/: Settlement and accounting
- selection: Pattern selection logic
- runtime: PFCNode implementation
"""

__version__ = "0.1.0"

from .selection import (
    PatternSelector,
    PatternSpec,
    SelectionResult,
    SelectionStrategy,
    AdaptiveSelector,
)
from .runtime import (
    PFCNode,
    PFCConfig,
    PFCPhase,
    PFCMetrics,
    create_pfc_node,
)

__all__ = [
    # Selection
    "PatternSelector",
    "PatternSpec",
    "SelectionResult",
    "SelectionStrategy",
    "AdaptiveSelector",
    # Runtime
    "PFCNode",
    "PFCConfig",
    "PFCPhase",
    "PFCMetrics",
    "create_pfc_node",
]
