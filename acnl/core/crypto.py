"""
ACNL Core — Cryptographic Primitives

NAIVE DESIGN (rejected):
- Implement crypto by hand
- Use weak algorithms

CRITIQUE:
- Homegrown crypto = vulnerabilities
- Classical crypto = quantum-vulnerable

FRACTAL DESIGN (implemented):
- Abstract SignatureScheme interface
- Mock implementation for dev/test
- Ready for PQ crypto (Dilithium, Falcon, SPHINCS+)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypeVar
import hashlib
import json
import time

from .ids import EntityID
from .events import SigEnvelope

T = TypeVar("T")


class SignatureScheme(ABC):
    """
    Abstract interface for signature schemes.

    Implementations:
      - MockSignatureScheme: for development (NOT SECURE)
      - Ed25519SignatureScheme: classical (TODO)
      - DilithiumSignatureScheme: post-quantum (TODO)
    """

    @abstractmethod
    def sign(self, payload: bytes) -> bytes:
        ...

    @abstractmethod
    def verify(self, payload: bytes, signature: bytes) -> bool:
        ...

    @abstractmethod
    def get_algorithm(self) -> str:
        ...

    @abstractmethod
    def get_public_key_hint(self) -> str:
        ...


class MockSignatureScheme(SignatureScheme):
    """
    Mock signature for development.

    ⚠️ NOT SECURE — DO NOT USE IN PRODUCTION ⚠️
    """

    def __init__(self, secret: str = "dev-secret"):
        self._secret = secret.encode()
        self._alg = "mock-sha256"

    def sign(self, payload: bytes) -> bytes:
        return hashlib.sha256(self._secret + payload).digest()

    def verify(self, payload: bytes, signature: bytes) -> bool:
        expected = hashlib.sha256(self._secret + payload).digest()
        return signature == expected

    def get_algorithm(self) -> str:
        return self._alg

    def get_public_key_hint(self) -> str:
        return hashlib.sha256(self._secret).hexdigest()[:16]


def serialize_for_signing(obj) -> bytes:
    """Deterministic JSON serialization for signing."""
    return json.dumps(obj, default=str, sort_keys=True, separators=(',', ':')).encode()


def wrap_with_signature(
    payload: T,
    signer: EntityID,
    scheme: SignatureScheme,
) -> SigEnvelope[T]:
    """Create a signed envelope."""
    payload_bytes = serialize_for_signing(payload)
    sig = scheme.sign(payload_bytes)

    return SigEnvelope(
        payload=payload,
        signer=signer,
        alg=scheme.get_algorithm(),
        signature=sig,
        timestamp_ms=int(time.time() * 1000),
        public_key_hint=scheme.get_public_key_hint(),
    )


def verify_envelope(
    envelope: SigEnvelope[T],
    scheme: SignatureScheme,
) -> bool:
    """Verify a signed envelope."""
    payload_bytes = serialize_for_signing(envelope.payload)
    return scheme.verify(payload_bytes, envelope.signature)
