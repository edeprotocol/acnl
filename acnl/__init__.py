"""
ACNL — Autonomous Compute/Energy Nervous Layer

Tensor-native energy/compute nervous layer for AGI/ASI.
Zero humans in the loop. Patterns survive or die based on efficiency.

Fractal hierarchy:
  LFI (Local Field Integrator) → RC (Regional Coordinator) → GH (Global Harmonizer)

Primary control variable:
  τ (tau) = permitted energy consumption rate (MW)

Core principle:
  Patterns don't pay — they survive or die based on efficiency(info_gain / energy)
"""

__version__ = "0.2.0"

# Core types
from .core.ids import (
    EntityID,
    EntityKind,
    Coord,
    compute_node_id,
    plant_id,
    pattern_id,
    lfi_id,
    rc_id,
    gh_id,
)
from .core.observables import (
    EnergyObservableKind,
    ComputeObservableKind,
    CapitalObservableKind,
)
from .core.events import (
    Assertion,
    Claim,
    Challenge,
    Proof,
    SigEnvelope,
)
from .core.fields import (
    FieldPoint,
    LocalField,
    RegionalField,
    STANDARD_COMPUTE_FEATURES,
)
from .core.crypto import SignatureScheme, MockSignatureScheme

# Store
from .store.event_store import EventStore

# Mesh
from .mesh.node import MeshNode, NodeRole
from .mesh.graph import MeshGraph
from .mesh.aggregator import LocalFieldBuilder, AggregatorConfig

# Control
from .control.policies import (
    TauLimitPolicy,
    DefaultTauLimitPolicy,
    KardashevPolicy,
    EmergencyPolicy,
)
from .control.challenges import ChallengeController, ChallengeConfig
from .control.lfi import LocalFieldIntegrator
from .control.rc import RegionalCoordinator
from .control.gh import GlobalHarmonizer

# Agent API
from .agent.client import AgentClient, AllocationResult

# Integration
from .integration.sensors import SensorInterface, SimulatedSensor
from .integration.sfl_hook import SFLEnergyHook, EnergyConstrainedAllocator

# Econ (application layer)
from .econ.accounts import EnergyAccount, AccountLedger, AccountStatus, Transaction
from .econ.settlement import SettlementEngine, SettlementConfig, SettlementPeriod

# Runtime
from .runtime.lfi_runtime import LFIRuntime, LFIConfig
from .runtime.mesh_runtime import MeshRuntime, MeshConfig

__all__ = [
    # Version
    "__version__",
    # Core IDs
    "EntityID",
    "EntityKind",
    "Coord",
    "compute_node_id",
    "plant_id",
    "pattern_id",
    "lfi_id",
    "rc_id",
    "gh_id",
    # Observables
    "EnergyObservableKind",
    "ComputeObservableKind",
    "CapitalObservableKind",
    # Events
    "Assertion",
    "Claim",
    "Challenge",
    "Proof",
    "SigEnvelope",
    # Fields
    "FieldPoint",
    "LocalField",
    "RegionalField",
    "STANDARD_COMPUTE_FEATURES",
    # Crypto
    "SignatureScheme",
    "MockSignatureScheme",
    # Store
    "EventStore",
    # Mesh
    "MeshNode",
    "NodeRole",
    "MeshGraph",
    "LocalFieldBuilder",
    "AggregatorConfig",
    # Control
    "TauLimitPolicy",
    "DefaultTauLimitPolicy",
    "KardashevPolicy",
    "EmergencyPolicy",
    "ChallengeController",
    "ChallengeConfig",
    "LocalFieldIntegrator",
    "RegionalCoordinator",
    "GlobalHarmonizer",
    # Agent
    "AgentClient",
    "AllocationResult",
    # Integration
    "SensorInterface",
    "SimulatedSensor",
    "SFLEnergyHook",
    "EnergyConstrainedAllocator",
    # Econ
    "EnergyAccount",
    "AccountLedger",
    "AccountStatus",
    "Transaction",
    "SettlementEngine",
    "SettlementConfig",
    "SettlementPeriod",
    # Runtime
    "LFIRuntime",
    "LFIConfig",
    "MeshRuntime",
    "MeshConfig",
]
