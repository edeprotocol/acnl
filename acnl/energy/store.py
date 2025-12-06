from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .types import EntityID, Coord
from .events import Assertion, Claim, Challenge, Proof, SigEnvelope


@dataclass
class StoreConfig:
    """Configuration for EnergyEventStore."""
    max_age_ms: int = 3600_000  # 1 hour
    gc_interval_ms: int = 60_000  # 1 minute
    max_assertions_per_subject: int = 1000


class EnergyEventStore:
    """
    Thread-safe store for energy assertions and claims.

    Provides:
    - Add/query assertions by subject or time range
    - Add/query claims
    - Add/query challenges and proofs
    - Automatic garbage collection of old data
    """

    def __init__(self, config: StoreConfig | None = None):
        self._config = config or StoreConfig()
        self._lock = threading.RLock()

        # Assertions indexed by subject
        self._assertions_by_subject: Dict[EntityID, List[SigEnvelope[Assertion]]] = {}

        # Claims indexed by subject
        self._claims_by_subject: Dict[EntityID, List[SigEnvelope[Claim]]] = {}

        # Challenges indexed by target
        self._challenges_by_target: Dict[EntityID, List[SigEnvelope[Challenge]]] = {}

        # Proofs indexed by challenge_id
        self._proofs_by_challenge: Dict[str, List[SigEnvelope[Proof]]] = {}

        # All subjects we've seen
        self._known_subjects: Set[EntityID] = set()

        self._last_gc_ms = int(time.time() * 1000)

    def add_assertion(self, envelope: SigEnvelope[Assertion]) -> None:
        """Add a signed assertion to the store."""
        with self._lock:
            subject = envelope.payload.subject
            self._known_subjects.add(subject)

            if subject not in self._assertions_by_subject:
                self._assertions_by_subject[subject] = []

            self._assertions_by_subject[subject].append(envelope)

            # Trim if too many
            if len(self._assertions_by_subject[subject]) > self._config.max_assertions_per_subject:
                # Keep most recent
                self._assertions_by_subject[subject] = sorted(
                    self._assertions_by_subject[subject],
                    key=lambda e: e.payload.coord.ts_ms,
                    reverse=True
                )[:self._config.max_assertions_per_subject]

            self._maybe_gc()

    def add_claim(self, envelope: SigEnvelope[Claim]) -> None:
        """Add a signed claim to the store."""
        with self._lock:
            subject = envelope.payload.subject
            self._known_subjects.add(subject)

            if subject not in self._claims_by_subject:
                self._claims_by_subject[subject] = []

            self._claims_by_subject[subject].append(envelope)

    def add_challenge(self, envelope: SigEnvelope[Challenge]) -> None:
        """Add a signed challenge to the store."""
        with self._lock:
            target = envelope.payload.target

            if target not in self._challenges_by_target:
                self._challenges_by_target[target] = []

            self._challenges_by_target[target].append(envelope)

    def add_proof(self, envelope: SigEnvelope[Proof]) -> None:
        """Add a signed proof to the store."""
        with self._lock:
            challenge_id = envelope.payload.challenge_id

            if challenge_id not in self._proofs_by_challenge:
                self._proofs_by_challenge[challenge_id] = []

            self._proofs_by_challenge[challenge_id].append(envelope)

    def get_assertions(
        self,
        subject: EntityID | None = None,
        since_ms: int | None = None,
        until_ms: int | None = None,
    ) -> List[SigEnvelope[Assertion]]:
        """Query assertions with optional filters."""
        with self._lock:
            if subject is not None:
                assertions = self._assertions_by_subject.get(subject, [])
            else:
                assertions = []
                for subj_assertions in self._assertions_by_subject.values():
                    assertions.extend(subj_assertions)

            # Apply time filters
            if since_ms is not None:
                assertions = [a for a in assertions if a.payload.coord.ts_ms >= since_ms]
            if until_ms is not None:
                assertions = [a for a in assertions if a.payload.coord.ts_ms <= until_ms]

            return assertions

    def get_claims(
        self,
        subject: EntityID | None = None,
        since_ms: int | None = None,
    ) -> List[SigEnvelope[Claim]]:
        """Query claims with optional filters."""
        with self._lock:
            if subject is not None:
                claims = self._claims_by_subject.get(subject, [])
            else:
                claims = []
                for subj_claims in self._claims_by_subject.values():
                    claims.extend(subj_claims)

            if since_ms is not None:
                claims = [c for c in claims if c.payload.coord.ts_ms >= since_ms]

            return claims

    def get_challenges(
        self,
        target: EntityID | None = None,
        status: str | None = None,
    ) -> List[SigEnvelope[Challenge]]:
        """Query challenges with optional filters."""
        with self._lock:
            if target is not None:
                challenges = self._challenges_by_target.get(target, [])
            else:
                challenges = []
                for target_challenges in self._challenges_by_target.values():
                    challenges.extend(target_challenges)

            if status is not None:
                challenges = [c for c in challenges if c.payload.status == status]

            return challenges

    def get_proofs(self, challenge_id: str) -> List[SigEnvelope[Proof]]:
        """Get proofs for a specific challenge."""
        with self._lock:
            return self._proofs_by_challenge.get(challenge_id, [])

    def get_known_subjects(self) -> Set[EntityID]:
        """Get all known subjects."""
        with self._lock:
            return self._known_subjects.copy()

    def _maybe_gc(self) -> None:
        """Run garbage collection if needed."""
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_gc_ms < self._config.gc_interval_ms:
            return

        self._gc(now_ms)
        self._last_gc_ms = now_ms

    def _gc(self, now_ms: int) -> None:
        """Remove old assertions and claims."""
        cutoff_ms = now_ms - self._config.max_age_ms

        # GC assertions
        for subject in list(self._assertions_by_subject.keys()):
            self._assertions_by_subject[subject] = [
                a for a in self._assertions_by_subject[subject]
                if a.payload.coord.ts_ms >= cutoff_ms
            ]
            if not self._assertions_by_subject[subject]:
                del self._assertions_by_subject[subject]

        # GC claims
        for subject in list(self._claims_by_subject.keys()):
            self._claims_by_subject[subject] = [
                c for c in self._claims_by_subject[subject]
                if c.payload.coord.ts_ms >= cutoff_ms
            ]
            if not self._claims_by_subject[subject]:
                del self._claims_by_subject[subject]

    def stats(self) -> Dict[str, int]:
        """Return store statistics."""
        with self._lock:
            total_assertions = sum(
                len(a) for a in self._assertions_by_subject.values()
            )
            total_claims = sum(
                len(c) for c in self._claims_by_subject.values()
            )
            total_challenges = sum(
                len(c) for c in self._challenges_by_target.values()
            )
            total_proofs = sum(
                len(p) for p in self._proofs_by_challenge.values()
            )

            return {
                "subjects": len(self._known_subjects),
                "assertions": total_assertions,
                "claims": total_claims,
                "challenges": total_challenges,
                "proofs": total_proofs,
            }
