from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from threading import Lock
import time

from .model import Assertion, Claim, Challenge, Proof, Coord
from .crypto import SigEnvelope


@dataclass
class EventStore:
    """
    Thread-safe event store for RFL-E objects.
    In production, back with Redis/Postgres/etc.
    """
    assertions: List[SigEnvelope[Assertion]] = field(default_factory=list)
    claims: List[SigEnvelope[Claim]] = field(default_factory=list)
    challenges: List[Challenge] = field(default_factory=list)
    proofs: List[Proof] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    # Retention config
    max_assertions: int = 100_000
    max_age_ms: int = 300_000  # 5 minutes default

    def add_assertion(self, env: SigEnvelope[Assertion]) -> None:
        with self._lock:
            self.assertions.append(env)
            self._maybe_gc()

    def add_assertion_batch(self, envs: List[SigEnvelope[Assertion]]) -> None:
        with self._lock:
            self.assertions.extend(envs)
            self._maybe_gc()

    def add_claim(self, env: SigEnvelope[Claim]) -> None:
        with self._lock:
            self.claims.append(env)

    def add_challenge(self, challenge: Challenge) -> None:
        with self._lock:
            self.challenges.append(challenge)

    def add_proof(self, proof: Proof) -> None:
        with self._lock:
            self.proofs.append(proof)

    def get_assertions_in_window(
        self,
        region_id: str,
        start_ms: int,
        end_ms: int,
        subject_filter: Optional[Callable[[str], bool]] = None,
    ) -> List[Assertion]:
        with self._lock:
            results = []
            for env in self.assertions:
                a = env.payload
                if a.coord.region_id != region_id:
                    continue
                if not (start_ms <= a.coord.ts_ms <= end_ms):
                    continue
                if subject_filter and not subject_filter(a.subject):
                    continue
                results.append(a)
            return results

    def get_pending_challenges(self, target: Optional[str] = None) -> List[Challenge]:
        with self._lock:
            return [
                c for c in self.challenges
                if c.status == "pending"
                and (target is None or c.target == target)
            ]

    def update_challenge_status(self, challenge_id: str, status: str) -> None:
        with self._lock:
            for c in self.challenges:
                if c.challenge_id == challenge_id:
                    c.status = status
                    break

    def _maybe_gc(self) -> None:
        """Garbage collect old assertions."""
        if len(self.assertions) > self.max_assertions:
            cutoff = int(time.time() * 1000) - self.max_age_ms
            self.assertions = [
                env for env in self.assertions
                if env.payload.coord.ts_ms > cutoff
            ][-self.max_assertions:]
