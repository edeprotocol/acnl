from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, Generic
import hashlib
import json
import time

from .types import EntityID

T = TypeVar("T")


class SignatureScheme(Protocol):
    """
    Abstract interface for signature schemes.
    Replace with Dilithium/Falcon for post-quantum in production.
    """

    def sign(self, payload: bytes) -> bytes:
        ...

    def verify(self, payload: bytes, signature: bytes) -> bool:
        ...

    def get_algorithm(self) -> str:
        ...

    def get_public_key_hint(self) -> str:
        ...


class MockSignatureScheme:
    """
    Mock signature for development. NOT FOR PRODUCTION.
    Replace with real PQ crypto (Dilithium, Falcon, etc.)
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
    """Serialize object for signing."""
    return json.dumps(obj, default=str, sort_keys=True).encode()


def wrap_with_signature(
    payload: T,
    signer: EntityID,
    scheme: SignatureScheme,
) -> "SigEnvelope[T]":
    """Create a signed envelope."""
    from .events import SigEnvelope

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
    envelope: "SigEnvelope[T]",
    scheme: SignatureScheme,
) -> bool:
    """Verify a signed envelope."""
    payload_bytes = serialize_for_signing(envelope.payload)
    return scheme.verify(payload_bytes, envelope.signature)
