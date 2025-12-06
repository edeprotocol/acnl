"""
ACNL Store — Event Storage

Thread-safe in-memory store with indexing.
Future: persist to SQLite, RocksDB, or distributed store.
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from threading import Lock
import time

from ..core.ids import EntityID, entity_kind
from ..core.events import (
    Assertion, Claim, Challenge, Proof,
    EnergyEvent, ComputeEvent, CapitalEvent,
    SigEnvelope,
)


@dataclass
class EventStore:
    """
    Thread-safe local event store.

    Indexes:
      - by subject
      - by region
      - by time window
      - by challenge status
    """

    # Raw storage
    assertions: List[SigEnvelope[Assertion]] = field(default_factory=list)
    claims: List[SigEnvelope[Claim]] = field(default_factory=list)
    challenges: List[Challenge] = field(default_factory=list)
    proofs: List[Proof] = field(default_factory=list)

    energy_events: List[EnergyEvent] = field(default_factory=list)
    compute_events: List[ComputeEvent] = field(default_factory=list)
    capital_events: List[CapitalEvent] = field(default_factory=list)

    # Indexes
    _by_subject: Dict[EntityID, List[SigEnvelope[Assertion]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _by_region: Dict[str, List[SigEnvelope[Assertion]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _claims_by_subject: Dict[EntityID, List[SigEnvelope[Claim]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _challenges_by_target: Dict[EntityID, List[Challenge]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _proofs_by_challenge: Dict[str, List[Proof]] = field(
        default_factory=lambda: defaultdict(list)
    )

    _lock: Lock = field(default_factory=Lock)

    # Retention
    max_events: int = 100_000
    max_age_ms: int = 600_000  # 10 minutes

    # ──────────────────────────────────────────────────────────────────────────
    # Ingestion
    # ──────────────────────────────────────────────────────────────────────────

    def add_assertion(self, env: SigEnvelope[Assertion]) -> None:
        with self._lock:
            self.assertions.append(env)
            self._by_subject[env.payload.subject].append(env)
            self._by_region[env.payload.coord.region_id].append(env)
            self._maybe_gc()

    def add_assertions_batch(self, envs: List[SigEnvelope[Assertion]]) -> None:
        with self._lock:
            for env in envs:
                self.assertions.append(env)
                self._by_subject[env.payload.subject].append(env)
                self._by_region[env.payload.coord.region_id].append(env)
            self._maybe_gc()

    def add_claim(self, env: SigEnvelope[Claim]) -> None:
        with self._lock:
            self.claims.append(env)
            self._claims_by_subject[env.payload.subject].append(env)

    def add_challenge(self, challenge: Challenge) -> None:
        with self._lock:
            self.challenges.append(challenge)
            self._challenges_by_target[challenge.target].append(challenge)

    def add_proof(self, proof: Proof) -> None:
        with self._lock:
            self.proofs.append(proof)
            self._proofs_by_challenge[proof.challenge_id].append(proof)

    def add_energy_event(self, event: EnergyEvent) -> None:
        with self._lock:
            self.energy_events.append(event)

    def add_compute_event(self, event: ComputeEvent) -> None:
        with self._lock:
            self.compute_events.append(event)

    def add_capital_event(self, event: CapitalEvent) -> None:
        with self._lock:
            self.capital_events.append(event)

    # ──────────────────────────────────────────────────────────────────────────
    # Queries
    # ──────────────────────────────────────────────────────────────────────────

    def get_assertions_for_subject(
        self,
        subject: EntityID,
        since_ms: Optional[int] = None,
    ) -> List[Assertion]:
        with self._lock:
            envs = self._by_subject.get(subject, [])
            if since_ms:
                return [e.payload for e in envs if e.payload.coord.ts_ms >= since_ms]
            return [e.payload for e in envs]

    def get_assertions_in_region(
        self,
        region_id: str,
        start_ms: int,
        end_ms: int,
        subject_filter: Optional[Callable[[EntityID], bool]] = None,
    ) -> List[Assertion]:
        with self._lock:
            envs = self._by_region.get(region_id, [])
            results = []
            for env in envs:
                a = env.payload
                if start_ms <= a.coord.ts_ms <= end_ms:
                    if subject_filter is None or subject_filter(a.subject):
                        results.append(a)
            return results

    def get_assertions_in_window(
        self,
        region_id: str,
        window_ms: int,
        now_ms: Optional[int] = None,
    ) -> List[Assertion]:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return self.get_assertions_in_region(region_id, now_ms - window_ms, now_ms)

    def get_latest_claim(self, subject: EntityID) -> Optional[Claim]:
        with self._lock:
            claims = self._claims_by_subject.get(subject, [])
            if not claims:
                return None
            latest = max(claims, key=lambda e: e.payload.coord.ts_ms)
            return latest.payload

    def get_pending_challenges(self, target: Optional[EntityID] = None) -> List[Challenge]:
        with self._lock:
            if target:
                return [c for c in self._challenges_by_target.get(target, []) if c.status == "pending"]
            return [c for c in self.challenges if c.status == "pending"]

    def update_challenge_status(self, challenge_id: str, status: str) -> None:
        with self._lock:
            for c in self.challenges:
                if c.challenge_id == challenge_id:
                    c.status = status
                    break

    def get_proofs_for_challenge(self, challenge_id: str) -> List[Proof]:
        with self._lock:
            return list(self._proofs_by_challenge.get(challenge_id, []))

    def get_compute_events(
        self,
        pattern_id: Optional[EntityID] = None,
        since_ms: Optional[int] = None,
    ) -> List[ComputeEvent]:
        with self._lock:
            events = self.compute_events
            if pattern_id:
                events = [e for e in events if e.pattern_id == pattern_id]
            if since_ms:
                events = [e for e in events if e.coord.ts_ms >= since_ms]
            return events

    def get_all_subjects(self, region_id: str) -> List[EntityID]:
        """Get all subjects that have assertions in region."""
        with self._lock:
            subjects = set()
            for env in self._by_region.get(region_id, []):
                subjects.add(env.payload.subject)
            return list(subjects)

    def get_subjects_by_kind(self, region_id: str, kind: str) -> List[EntityID]:
        """Get subjects of specific kind in region."""
        return [s for s in self.get_all_subjects(region_id) if entity_kind(s) == kind]

    # ──────────────────────────────────────────────────────────────────────────
    # Maintenance
    # ──────────────────────────────────────────────────────────────────────────

    def _maybe_gc(self) -> None:
        """Garbage collect old events."""
        if len(self.assertions) > self.max_events:
            cutoff = int(time.time() * 1000) - self.max_age_ms
            self.assertions = [
                env for env in self.assertions
                if env.payload.coord.ts_ms > cutoff
            ][-self.max_events:]
            self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        """Rebuild indexes from assertions."""
        self._by_subject = defaultdict(list)
        self._by_region = defaultdict(list)
        for env in self.assertions:
            self._by_subject[env.payload.subject].append(env)
            self._by_region[env.payload.coord.region_id].append(env)

    def clear(self) -> None:
        """Clear all events."""
        with self._lock:
            self.assertions.clear()
            self.claims.clear()
            self.challenges.clear()
            self.proofs.clear()
            self.energy_events.clear()
            self.compute_events.clear()
            self.capital_events.clear()
            self._by_subject.clear()
            self._by_region.clear()
            self._claims_by_subject.clear()
            self._challenges_by_target.clear()
            self._proofs_by_challenge.clear()

    def stats(self) -> Dict[str, int]:
        """Get store statistics."""
        with self._lock:
            return {
                "assertions": len(self.assertions),
                "claims": len(self.claims),
                "challenges": len(self.challenges),
                "proofs": len(self.proofs),
                "energy_events": len(self.energy_events),
                "compute_events": len(self.compute_events),
                "capital_events": len(self.capital_events),
                "regions": len(self._by_region),
                "subjects": len(self._by_subject),
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Canonical API (as per ACNL spec)
    # ──────────────────────────────────────────────────────────────────────────

    def append(self, event: Assertion | Claim | Challenge | Proof) -> None:
        """
        Append any event type to the store.

        This is the primary ingestion API for ACNL events.
        """
        if isinstance(event, Assertion):
            # Wrap in SigEnvelope for consistency
            env = SigEnvelope(
                payload=event,
                signer=event.issuer,
                alg="mock",
                signature=b"",
                timestamp_ms=event.coord.ts_ms,
            )
            self.add_assertion(env)
        elif isinstance(event, Claim):
            env = SigEnvelope(
                payload=event,
                signer=event.claimant,
                alg="mock",
                signature=b"",
                timestamp_ms=event.coord.ts_ms,
            )
            self.add_claim(env)
        elif isinstance(event, Challenge):
            self.add_challenge(event)
        elif isinstance(event, Proof):
            self.add_proof(event)
        else:
            raise TypeError(f"Unknown event type: {type(event)}")

    def get_events(
        self,
        region_id: str,
        kind: type,
        since_ms: Optional[int] = None,
        until_ms: Optional[int] = None,
    ) -> List:
        """
        Query events by region, type, and time window.

        Args:
            region_id: Region to query
            kind: Event type (Assertion, Claim, Challenge, Proof)
            since_ms: Start of time window (inclusive)
            until_ms: End of time window (inclusive)

        Returns:
            List of events matching criteria
        """
        with self._lock:
            if kind == Assertion:
                envs = self._by_region.get(region_id, [])
                events = [e.payload for e in envs]
            elif kind == Claim:
                events = [
                    e.payload for e in self.claims
                    if e.payload.coord.region_id == region_id
                ]
            elif kind == Challenge:
                events = [
                    c for c in self.challenges
                    if c.coord.region_id == region_id
                ]
            elif kind == Proof:
                events = [
                    p for p in self.proofs
                    if p.coord.region_id == region_id
                ]
            else:
                return []

            # Time filtering
            if since_ms is not None:
                events = [e for e in events if e.coord.ts_ms >= since_ms]
            if until_ms is not None:
                events = [e for e in events if e.coord.ts_ms <= until_ms]

            return events

    def get_assertions_by_region(
        self,
        region_id: str,
        since_ms: Optional[int] = None,
        until_ms: Optional[int] = None,
    ) -> List[Assertion]:
        """Convenience method for assertion queries."""
        return self.get_events(region_id, Assertion, since_ms, until_ms)

    def get_claims_by_region(
        self,
        region_id: str,
        since_ms: Optional[int] = None,
        until_ms: Optional[int] = None,
    ) -> List[Claim]:
        """Convenience method for claim queries."""
        return self.get_events(region_id, Claim, since_ms, until_ms)

    def get_proofs_by_region(
        self,
        region_id: str,
        since_ms: Optional[int] = None,
        until_ms: Optional[int] = None,
    ) -> List[Proof]:
        """Convenience method for proof queries."""
        return self.get_events(region_id, Proof, since_ms, until_ms)
