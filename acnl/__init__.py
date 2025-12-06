"""
ACNL - Autonomous Compute/Energy Nervous Layer

A fractal energy-compute layer that constrains τ (tau) rate based on
physical energy state. Patterns don't pay - they survive or die based
on info/energy efficiency.

Architecture:
- LFI (Local Field Integrator): Ingests sensor assertions, builds energy field
- RC (Regional Coordinator): Aggregates LFI summaries, computes regional constraints
- GH (Global Harmonizer): Global optimization across regions

Core principle: Zero humans in decision loops.
"""

__version__ = "0.1.0"

from acnl.energy import (
    EntityID,
    Coord,
    Observable,
    EnergyObservableKind,
    Assertion,
    Claim,
    Challenge,
    Proof,
    SigEnvelope,
    make_entity_id,
)
from acnl.field import (
    EnergyField,
    EnergyFieldPoint,
    EnergyFieldBuilder,
    FieldConfig,
)
from acnl.control import (
    LocalFieldIntegrator,
    LFIConfig,
    RegionalCoordinator,
    RCConfig,
    GlobalHarmonizer,
    GHConfig,
    TauLimitPolicy,
    DefaultTauLimitPolicy,
    KardashevPolicy,
)

__all__ = [
    # Version
    "__version__",
    # Types
    "EntityID",
    "Coord",
    "Observable",
    "EnergyObservableKind",
    # Events
    "Assertion",
    "Claim",
    "Challenge",
    "Proof",
    "SigEnvelope",
    # Helpers
    "make_entity_id",
    # Field
    "EnergyField",
    "EnergyFieldPoint",
    "EnergyFieldBuilder",
    "FieldConfig",
    # Control hierarchy
    "LocalFieldIntegrator",
    "LFIConfig",
    "RegionalCoordinator",
    "RCConfig",
    "GlobalHarmonizer",
    "GHConfig",
    # Policies
    "TauLimitPolicy",
    "DefaultTauLimitPolicy",
    "KardashevPolicy",
]
