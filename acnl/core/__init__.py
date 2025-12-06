"""
ACNL Core — Tensor Reality Language

Core types for the energy-compute field:
- EntityID: typed identifiers
- Coord: spatio-temporal coordinates
- Observable: physical/economic quantities
- Assertion, Claim, Challenge, Proof: event types
- SigEnvelope: signed payloads
- FieldPoint, LocalField: tensor views
"""
from .ids import (
    EntityID,
    EntityKind,
    Coord,
    make_entity_id,
    parse_entity_id,
    entity_kind,
    is_entity_kind,
    plant_id,
    compute_node_id,
    pattern_id,
    lfi_id,
    rc_id,
    gh_id,
    region_contains,
    region_depth,
)
from .observables import (
    ObservableCategory,
    EnergyObservableKind,
    ComputeObservableKind,
    CapitalObservableKind,
    ObservableKind,
    Observable,
    Number,
    UNIT_MW,
    UNIT_KWH,
    UNIT_HZ,
    UNIT_FRACTION,
    UNIT_GCO2_KWH,
    UNIT_EUR_MWH,
    UNIT_CELSIUS,
)
from .events import (
    Assertion,
    Claim,
    Challenge,
    Proof,
    EnergyEvent,
    ComputeEvent,
    CapitalEvent,
    SigEnvelope,
)
from .crypto import (
    SignatureScheme,
    MockSignatureScheme,
    serialize_for_signing,
    wrap_with_signature,
    verify_envelope,
)
from .fields import (
    FieldPoint,
    LocalField,
    RegionalField,
    STANDARD_ENERGY_FEATURES,
    STANDARD_COMPUTE_FEATURES,
)
from .tensors import (
    field_to_tensor,
    normalize_tensor,
    softmax,
)

__all__ = [
    # ids
    "EntityID", "EntityKind", "Coord",
    "make_entity_id", "parse_entity_id", "entity_kind", "is_entity_kind",
    "plant_id", "compute_node_id", "pattern_id", "lfi_id", "rc_id", "gh_id",
    "region_contains", "region_depth",
    # observables
    "ObservableCategory", "EnergyObservableKind", "ComputeObservableKind",
    "CapitalObservableKind", "ObservableKind", "Observable", "Number",
    "UNIT_MW", "UNIT_KWH", "UNIT_HZ", "UNIT_FRACTION", "UNIT_GCO2_KWH",
    "UNIT_EUR_MWH", "UNIT_CELSIUS",
    # events
    "Assertion", "Claim", "Challenge", "Proof",
    "EnergyEvent", "ComputeEvent", "CapitalEvent", "SigEnvelope",
    # crypto
    "SignatureScheme", "MockSignatureScheme",
    "serialize_for_signing", "wrap_with_signature", "verify_envelope",
    # fields
    "FieldPoint", "LocalField", "RegionalField",
    "STANDARD_ENERGY_FEATURES", "STANDARD_COMPUTE_FEATURES",
    # tensors
    "field_to_tensor", "normalize_tensor", "softmax",
]
