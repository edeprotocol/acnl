"""
ACNL Core — Event Types

Events are the atoms of reality for agents and controllers.
Not for humans — for machines reasoning about energy-compute-capital.

Event hierarchy:
  Assertion → single signed observation
  Claim → coherent set of assertions about one subject
  Challenge → active probe to verify node honesty
  Proof → response to challenge with measurements
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Generic, TypeVar, List, Dict, Any, Optional
import uuid
import time

from .ids import EntityID, Coord
from .observables import Observable, ObservableKind


# ══════════════════════════════════════════════════════════════════════════════
# ASSERTIONS AND CLAIMS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Assertion:
    """
    Atomic signed statement: "Subject X has observable Y at coord Z".

    This is the fundamental unit of reality in ACNL.
    Everything else (Claims, Fields) is aggregation.
    """
    assertion_id: str
    issuer: EntityID          # who makes the assertion (sensor, LFI, node itself)
    subject: EntityID         # what is being observed (plant, compute-node, line)
    coord: Coord              # where and when
    observable: Observable    # what is observed
    context: Optional[Dict[str, Any]] = None  # additional metadata

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
    Coherent set of assertions about one subject at one coordinate.

    A Claim bundles multiple observations (power, carbon, price, etc.)
    into a single signed package.
    """
    claim_id: str
    claimant: EntityID        # who makes the claim
    subject: EntityID         # what is being described
    coord: Coord
    assertions: List[Assertion] = field(default_factory=list)
    meta: Optional[Dict[str, Any]] = None

    @staticmethod
    def create(
        claimant: EntityID,
        subject: EntityID,
        coord: Coord,
        assertions: List[Assertion] | None = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "Claim":
        return Claim(
            claim_id=str(uuid.uuid4()),
            claimant=claimant,
            subject=subject,
            coord=coord,
            assertions=assertions or [],
            meta=meta,
        )

    def add_assertion(self, assertion: Assertion) -> None:
        self.assertions.append(assertion)

    def get_observable(self, kind: ObservableKind) -> Optional[Observable]:
        for a in self.assertions:
            if a.observable.kind == kind:
                return a.observable
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CHALLENGES AND PROOFS (VERIFICATION LAYER)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Challenge:
    """
    Active probe to verify a node's claims.

    Challenge types:
      - power_correlation: run known workload, verify power consumption
      - latency_check: measure RTT
      - compute_benchmark: run benchmark, verify TCU claims
      - generation_verify: verify claimed generation

    A node that fails challenges loses reliability score.
    """
    challenge_id: str
    challenger: EntityID      # who issues (typically LFI)
    target: EntityID          # who is challenged
    coord: Coord
    challenge_type: str
    payload: Dict[str, Any]   # test parameters
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
    result: Dict[str, Any]    # measured values
    verified: bool = False
    verification_method: str = ""

    @staticmethod
    def create(
        challenge_id: str,
        responder: EntityID,
        coord: Coord,
        result: Dict[str, Any],
    ) -> "Proof":
        return Proof(
            proof_id=str(uuid.uuid4()),
            challenge_id=challenge_id,
            responder=responder,
            coord=coord,
            result=result,
        )


# ══════════════════════════════════════════════════════════════════════════════
# COMPUTE AND ENERGY EVENTS (HIGH-LEVEL)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EnergyEvent:
    """
    High-level energy event (generation, consumption, grid state change).
    Convenience wrapper over Assertion.
    """
    event_id: str
    emitter: EntityID
    subject: EntityID
    coord: Coord
    observable: Observable

    @staticmethod
    def create(
        emitter: EntityID,
        subject: EntityID,
        coord: Coord,
        observable: Observable,
    ) -> "EnergyEvent":
        return EnergyEvent(
            event_id=str(uuid.uuid4()),
            emitter=emitter,
            subject=subject,
            coord=coord,
            observable=observable,
        )

    def to_assertion(self) -> Assertion:
        return Assertion(
            assertion_id=self.event_id,
            issuer=self.emitter,
            subject=self.subject,
            coord=self.coord,
            observable=self.observable,
        )


@dataclass
class ComputeEvent:
    """
    Compute job event (start, progress, completion).
    """
    event_id: str
    pattern_id: EntityID      # which pattern ran
    compute_node_id: EntityID # where it ran
    coord: Coord
    job_id: str
    tcu_used: float           # compute consumed
    energy_kwh: float         # energy consumed
    latency_ms: float         # wall time
    success: bool
    info_gain_bits: Optional[float] = None  # information produced

    @staticmethod
    def create(
        pattern_id: EntityID,
        compute_node_id: EntityID,
        coord: Coord,
        job_id: str,
        tcu_used: float,
        energy_kwh: float,
        latency_ms: float,
        success: bool,
        info_gain_bits: Optional[float] = None,
    ) -> "ComputeEvent":
        return ComputeEvent(
            event_id=str(uuid.uuid4()),
            pattern_id=pattern_id,
            compute_node_id=compute_node_id,
            coord=coord,
            job_id=job_id,
            tcu_used=tcu_used,
            energy_kwh=energy_kwh,
            latency_ms=latency_ms,
            success=success,
            info_gain_bits=info_gain_bits,
        )

    def efficiency(self) -> float:
        """Info gain per energy unit. The Darwinian selection metric."""
        if self.energy_kwh <= 0 or self.info_gain_bits is None:
            return 0.0
        return self.info_gain_bits / self.energy_kwh


@dataclass
class CapitalEvent:
    """
    Capital flow event (transfer, credit, settlement).
    Application layer — not core to field computation.
    """
    event_id: str
    event_type: str           # "transfer", "credit_open", "credit_close", "settlement"
    from_entity: EntityID
    to_entity: EntityID
    coord: Coord
    amount: float
    asset: str                # "EUR", "TCU", "kWh", token symbol
    meta: Optional[Dict[str, Any]] = None


# ══════════════════════════════════════════════════════════════════════════════
# SIGNATURE ENVELOPE
# ══════════════════════════════════════════════════════════════════════════════

T = TypeVar("T")


@dataclass
class SigEnvelope(Generic[T]):
    """
    Generic signed envelope for any payload.

    Crypto implementation is pluggable via SignatureScheme.
    """
    payload: T
    signer: EntityID
    alg: str                  # "mock-sha256", "ed25519", "dilithium3"
    signature: bytes
    timestamp_ms: int
    public_key_hint: Optional[str] = None
