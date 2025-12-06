"""
ACNL Control — Challenge Controller

Issues and verifies challenges to nodes.
Challenges are used to verify that nodes are:
- Actually consuming the power they claim
- Located where they claim
- Performing the compute they report
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
import time
import math

from ..core.ids import EntityID, Coord
from ..core.events import Challenge, Proof
from ..store.event_store import EventStore


@dataclass
class TrustScore:
    """Trust score for a node based on challenge history."""
    node_id: EntityID
    score: float  # 0..1
    challenges_issued: int = 0
    challenges_passed: int = 0
    challenges_failed: int = 0
    last_challenge_ms: int = 0


@dataclass
class ChallengeConfig:
    """Configuration for ChallengeController."""
    min_interval_ms: int = 60_000  # 1 minute between challenges
    timeout_ms: int = 5_000
    initial_trust: float = 0.5
    trust_decay: float = 0.99  # Per-hour decay
    pass_boost: float = 0.1
    fail_penalty: float = 0.3
    low_trust_threshold: float = 0.3


class ChallengeController:
    """
    Issues and verifies challenges to nodes.
    """

    def __init__(
        self,
        store: EventStore,
        challenger_id: EntityID,
        region_id: str,
        config: ChallengeConfig | None = None,
        verifiers: Dict[str, Callable[[Challenge, Proof], bool]] | None = None,
    ):
        self._store = store
        self._challenger_id = challenger_id
        self._region_id = region_id
        self._config = config or ChallengeConfig()
        self._verifiers = verifiers or {}

        self._trust_scores: Dict[EntityID, TrustScore] = {}
        self._pending_challenges: Dict[str, Challenge] = {}

    def issue_challenge(
        self,
        target: EntityID,
        challenge_type: str,
        payload: Dict,
    ) -> Challenge:
        """Issue a new challenge to a target node."""
        challenge = Challenge.create(
            challenger=self._challenger_id,
            target=target,
            coord=Coord.now(self._region_id),
            challenge_type=challenge_type,
            payload=payload,
            timeout_ms=self._config.timeout_ms,
        )

        self._store.add_challenge(challenge)
        self._pending_challenges[challenge.challenge_id] = challenge

        # Update trust score tracking
        if target not in self._trust_scores:
            self._trust_scores[target] = TrustScore(
                node_id=target,
                score=self._config.initial_trust,
            )

        self._trust_scores[target].challenges_issued += 1
        self._trust_scores[target].last_challenge_ms = int(time.time() * 1000)

        return challenge

    def submit_proof(
        self,
        challenge_id: str,
        responder: EntityID,
        result: Dict,
    ) -> Proof:
        """Submit a proof in response to a challenge."""
        proof = Proof.create(
            challenge_id=challenge_id,
            responder=responder,
            coord=Coord.now(self._region_id),
            result=result,
        )

        self._store.add_proof(proof)
        return proof

    def verify_proof(self, challenge_id: str) -> bool:
        """Verify a proof against its challenge."""
        if challenge_id not in self._pending_challenges:
            return False

        challenge = self._pending_challenges[challenge_id]
        proofs = self._store.get_proofs_for_challenge(challenge_id)

        if not proofs:
            return False

        proof = proofs[0]  # Take first proof
        now_ms = int(time.time() * 1000)

        # Check timeout
        if proof.coord.ts_ms - challenge.coord.ts_ms > challenge.timeout_ms:
            self._record_failure(challenge.target)
            self._store.update_challenge_status(challenge_id, "timeout")
            return False

        # Check if we have a verifier for this type
        if challenge.challenge_type in self._verifiers:
            verifier = self._verifiers[challenge.challenge_type]
            result = verifier(challenge, proof)
            if result:
                self._record_pass(challenge.target)
                self._store.update_challenge_status(challenge_id, "completed")
            else:
                self._record_failure(challenge.target)
                self._store.update_challenge_status(challenge_id, "failed")
            return result

        # Default: accept if proof came from correct responder
        if proof.responder == challenge.target:
            self._record_pass(challenge.target)
            self._store.update_challenge_status(challenge_id, "completed")
            return True

        self._record_failure(challenge.target)
        self._store.update_challenge_status(challenge_id, "failed")
        return False

    def _record_pass(self, node_id: EntityID) -> None:
        """Record a passed challenge."""
        if node_id in self._trust_scores:
            ts = self._trust_scores[node_id]
            ts.challenges_passed += 1
            ts.score = min(1.0, ts.score + self._config.pass_boost)

    def _record_failure(self, node_id: EntityID) -> None:
        """Record a failed challenge."""
        if node_id in self._trust_scores:
            ts = self._trust_scores[node_id]
            ts.challenges_failed += 1
            ts.score = max(0.0, ts.score - self._config.fail_penalty)

    def get_trust_score(self, node_id: EntityID) -> float:
        """Get current trust score for a node."""
        if node_id not in self._trust_scores:
            return self._config.initial_trust

        ts = self._trust_scores[node_id]

        # Apply time decay
        now_ms = int(time.time() * 1000)
        hours_since = (now_ms - ts.last_challenge_ms) / 3600_000
        decayed = ts.score * math.pow(self._config.trust_decay, hours_since)

        return max(0.0, min(1.0, decayed))

    def get_low_trust_nodes(self) -> List[EntityID]:
        """Get nodes with trust below threshold."""
        low_trust = []
        for node_id in self._trust_scores:
            if self.get_trust_score(node_id) < self._config.low_trust_threshold:
                low_trust.append(node_id)
        return low_trust

    def should_challenge(self, node_id: EntityID) -> bool:
        """Check if a node should be challenged."""
        if node_id not in self._trust_scores:
            return True  # Never challenged

        ts = self._trust_scores[node_id]
        now_ms = int(time.time() * 1000)

        # Check minimum interval
        if now_ms - ts.last_challenge_ms < self._config.min_interval_ms:
            return False

        # More frequent challenges for low trust
        trust = self.get_trust_score(node_id)
        if trust < self._config.low_trust_threshold:
            return True

        # Random challenge based on trust (lower trust = more challenges)
        import random
        challenge_prob = 1.0 - trust
        return random.random() < challenge_prob

    def cleanup_expired(self) -> int:
        """Clean up expired pending challenges."""
        now_ms = int(time.time() * 1000)
        expired = []

        for cid, challenge in self._pending_challenges.items():
            if now_ms - challenge.coord.ts_ms > challenge.timeout_ms * 2:
                expired.append(cid)
                # Record as failure if no proof
                if not self._store.get_proofs_for_challenge(cid):
                    self._record_failure(challenge.target)
                    self._store.update_challenge_status(cid, "timeout")

        for cid in expired:
            del self._pending_challenges[cid]

        return len(expired)


# Standard challenge types
CHALLENGE_POWER_CORRELATION = "power_correlation"
CHALLENGE_LATENCY_CHECK = "latency_check"
CHALLENGE_COMPUTE_BENCHMARK = "compute_benchmark"


def make_power_correlation_verifier(tolerance: float = 0.2):
    """Create a power correlation verifier."""
    def verify(challenge: Challenge, proof: Proof) -> bool:
        expected = challenge.payload.get("expected_power")
        measured = proof.result.get("measured_power")
        if expected is None or measured is None:
            return False
        diff = abs(expected - measured) / max(expected, 1.0)
        return diff <= tolerance
    return verify


def make_latency_verifier(max_latency_ms: int = 100):
    """Create a latency verifier."""
    def verify(challenge: Challenge, proof: Proof) -> bool:
        latency = proof.result.get("latency_ms")
        if latency is None:
            return False
        return latency <= max_latency_ms
    return verify
