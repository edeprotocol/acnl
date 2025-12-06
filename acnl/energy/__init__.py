"""
ACNL Energy Module - Core types, events, and storage for energy-compute mesh.
"""
from .types import (
    EntityID,
    EntityKind,
    make_entity_id,
    parse_entity_id,
    Coord,
    EnergyObservableKind,
    Observable,
    Number,
)
from .events import (
    Assertion,
    Claim,
    Challenge,
    Proof,
    SigEnvelope,
)
from .crypto import (
    SignatureScheme,
    MockSignatureScheme,
    serialize_for_signing,
    wrap_with_signature,
    verify_envelope,
)
from .store import (
    StoreConfig,
    EnergyEventStore,
)

__all__ = [
    # Types
    "EntityID",
    "EntityKind",
    "make_entity_id",
    "parse_entity_id",
    "Coord",
    "EnergyObservableKind",
    "Observable",
    "Number",
    # Events
    "Assertion",
    "Claim",
    "Challenge",
    "Proof",
    "SigEnvelope",
    # Crypto
    "SignatureScheme",
    "MockSignatureScheme",
    "serialize_for_signing",
    "wrap_with_signature",
    "verify_envelope",
    # Store
    "StoreConfig",
    "EnergyEventStore",
]
