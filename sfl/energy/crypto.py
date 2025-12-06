from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, TypeVar, Generic
import hashlib
import json

T = TypeVar("T")


class SignatureScheme(Protocol):
    """Abstract interface for signature schemes. PQ implementation later."""

    def sign(self, payload: bytes) -> bytes:
        ...

    def verify(self, payload: bytes, signature: bytes, public_key: bytes) -> bool:
        ...

    def get_public_key(self) -> bytes:
        ...


class MockSignatureScheme:
    """Mock signature for development. Replace with Dilithium/Falcon in prod."""

    def __init__(self, secret: str = "dev-secret"):
        self._secret = secret.encode()

    def sign(self, payload: bytes) -> bytes:
        return hashlib.sha256(self._secret + payload).digest()

    def verify(self, payload: bytes, signature: bytes, public_key: bytes) -> bool:
        expected = hashlib.sha256(self._secret + payload).digest()
        return signature == expected

    def get_public_key(self) -> bytes:
        return hashlib.sha256(self._secret).digest()


@dataclass
class SigEnvelope(Generic[T]):
    """Signed envelope wrapping any payload."""
    payload: T
    signer_id: str
    signature: bytes
    timestamp_ms: int

    @staticmethod
    def wrap(payload: T, signer_id: str, scheme: SignatureScheme) -> "SigEnvelope[T]":
        import time
        ts = int(time.time() * 1000)
        # Serialize payload for signing
        payload_bytes = json.dumps(payload, default=str, sort_keys=True).encode()
        sig = scheme.sign(payload_bytes)
        return SigEnvelope(
            payload=payload,
            signer_id=signer_id,
            signature=sig,
            timestamp_ms=ts,
        )

    def verify(self, scheme: SignatureScheme) -> bool:
        payload_bytes = json.dumps(self.payload, default=str, sort_keys=True).encode()
        return scheme.verify(payload_bytes, self.signature, scheme.get_public_key())
