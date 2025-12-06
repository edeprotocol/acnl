from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, List, Optional, TypeVar, Any, Dict
import uuid

from .types import EntityID, Coord, Observable


@dataclass
class Assertion:
    """
    Atomic: single signed observation from an issuer about a subject.
    """
    assertion_id: str
    issuer: EntityID          # sensor, compute-node, lfi...
    subject: EntityID         # what is being observed
    coord: Coord
    observable: Observable
    context: Optional[Dict[str, Any]] = None  # e.g. {"window_ms": 900000}

    @staticmethod
    def create(
        issuer: EntityID,
        subject: EntityID,
        coord: Coord,
        observable: Observable,
        context: Optional[Dict[str, Any]] = None,
    ) -> "Assertion":
        return Assertion(
            assertion_id=str(uuid.uuid4()),
            issuer=issuer,
            subject=subject,
            coord=coord,
            observable=observable,
            context=context,
        )


@dataclass
class Claim:
    """
    Aggregated claim about a subject from multiple assertions.
    """
    claim_id: str
    subject: EntityID         # plant, line, compute-node...
    coord: Coord
    assertions: List[Assertion] = field(default_factory=list)
    meta: Optional[Dict[str, Any]] = None

    @staticmethod
    def create(
        subject: EntityID,
        coord: Coord,
        assertions: List[Assertion] | None = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "Claim":
        return Claim(
            claim_id=str(uuid.uuid4()),
            subject=subject,
            coord=coord,
            assertions=assertions or [],
            meta=meta,
        )


@dataclass
class Challenge:
    """
    Active probe to verify a node isn't lying about its state.
    """
    challenge_id: str
    challenger: EntityID      # who issues the challenge (typically LFI)
    target: EntityID          # node being challenged
    coord: Coord
    challenge_type: str       # "power_correlation", "latency_check", "compute_benchmark"
    payload: Dict[str, Any]   # test pattern, setpoint, etc.
    timeout_ms: int
    status: str = "pending"   # pending, completed, failed, timeout

    @staticmethod
    def create(
        challenger: EntityID,
        target: EntityID,
        coord: Coord,
        challenge_type: str,
        payload: Dict[str, Any],
        timeout_ms: int = 5000,
    ) -> "Challenge":
        return Challenge(
            challenge_id=str(uuid.uuid4()),
            challenger=challenger,
            target=target,
            coord=coord,
            challenge_type=challenge_type,
            payload=payload,
            timeout_ms=timeout_ms,
        )


@dataclass
class Proof:
    """
    Response to a Challenge with measured results.
    """
    proof_id: str
    challenge_id: str
    responder: EntityID
    coord: Coord
    result: Dict[str, Any]    # time series, derived metrics, etc.
    verified: bool = False
    verification_method: str = ""
    verify_hint: Optional[Dict[str, Any]] = None

    @staticmethod
    def create(
        challenge_id: str,
        responder: EntityID,
        coord: Coord,
        result: Dict[str, Any],
        verify_hint: Optional[Dict[str, Any]] = None,
    ) -> "Proof":
        return Proof(
            proof_id=str(uuid.uuid4()),
            challenge_id=challenge_id,
            responder=responder,
            coord=coord,
            result=result,
            verify_hint=verify_hint,
        )


T = TypeVar("T")


@dataclass
class SigEnvelope(Generic[T]):
    """
    Generic signed envelope.

    Actual crypto (post-quantum, hardware-bound) is plugged in
    via SignatureScheme. This is the neutral wrapper.
    """
    payload: T
    signer: EntityID
    alg: str                   # e.g. "pq-dilithium3", "hw-attest-v1", "mock-sha256"
    signature: bytes
    timestamp_ms: int
    public_key_hint: Optional[str] = None
