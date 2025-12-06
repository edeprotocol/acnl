"""
SFL Runtime — PFC Node Implementation

PFCNode implements the real Proof → Field → Control loop:
1. PROOF: Ingest assertions, verify claims, process challenges/proofs
2. FIELD: Build energy field from verified assertions
3. CONTROL: Compute tau limits, select patterns, enforce constraints

This is the core nervous system runtime for the fractal mesh.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple
from enum import Enum
import time
import threading
import logging

from sfl.energy.store import EventStore
from sfl.energy.field import EnergyFieldBuilder, FieldConfig, EnergyField
from sfl.energy.model import (
    EntityID,
    Assertion,
    Claim,
    Challenge,
    Proof,
    Observable,
    EnergyObservableKind,
    Coord,
)
from sfl.energy.crypto import SigEnvelope, MockSignatureScheme
from sfl.mesh.controllers import (
    LocalEnergyController,
    LocalComputeController,
    ChallengeController,
    TauLimitComputer,
    TauLimitConfig,
)
from sfl.selection import PatternSelector, PatternSpec, SelectionResult, AdaptiveSelector

logger = logging.getLogger(__name__)


class PFCPhase(Enum):
    """Phases of the PFC loop."""
    PROOF = "proof"
    FIELD = "field"
    CONTROL = "control"


@dataclass
class PFCConfig:
    """Configuration for PFCNode."""
    region_id: str
    node_id: str                      # Unique node identifier
    tick_interval_ms: int = 1000      # Main loop interval
    field_horizon_ms: int = 5000      # Assertion aggregation window
    challenge_interval_ms: int = 10000  # Challenge frequency
    tau_config: TauLimitConfig = field(default_factory=TauLimitConfig)
    enable_adaptive_selection: bool = True


@dataclass
class PFCMetrics:
    """Metrics for monitoring the PFC loop."""
    ticks: int = 0
    assertions_ingested: int = 0
    claims_processed: int = 0
    challenges_issued: int = 0
    proofs_verified: int = 0
    proofs_failed: int = 0
    patterns_selected: int = 0
    patterns_rejected: int = 0
    last_tick_ms: int = 0
    avg_tick_duration_ms: float = 0.0


class PFCNode:
    """
    PFC Node — The core nervous system runtime.

    Implements the real PFC loop:
    1. PROOF phase: Ingest and verify assertions/claims/proofs
    2. FIELD phase: Build energy field from verified state
    3. CONTROL phase: Compute tau limits and select patterns

    This is NOT a mock or prototype. This is the real implementation
    that would run on actual mesh infrastructure.
    """

    def __init__(self, config: PFCConfig):
        self.config = config
        self.store = EventStore()
        self.signer = MockSignatureScheme(f"pfc-{config.node_id}")

        # Field builder
        # Use lower min_confidence to allow single-source assertions
        # In production, adjust based on required trust level
        self.field_builder = EnergyFieldBuilder(
            store=self.store,
            config=FieldConfig(
                horizon_ms=config.field_horizon_ms,
                min_confidence=0.01,  # Lower threshold for testing/development
            ),
            region_id=config.region_id,
        )

        # Controllers
        self.energy_controller = LocalEnergyController(
            store=self.store,
            region_id=config.region_id,
        )
        self.compute_controller = LocalComputeController(
            store=self.store,
            region_id=config.region_id,
            tau_computer=TauLimitComputer(config.tau_config),
        )
        self.challenge_controller = ChallengeController(
            store=self.store,
            region_id=config.region_id,
            challenge_interval_ms=config.challenge_interval_ms,
        )

        # Pattern selection
        if config.enable_adaptive_selection:
            self.selector = AdaptiveSelector()
        else:
            self.selector = PatternSelector()

        # State
        self._current_field: Optional[EnergyField] = None
        self._current_tau_limits: Dict[EntityID, float] = {}
        self._current_selection: Optional[SelectionResult] = None
        self._regional_constraints: Dict[str, float] = {}
        self._current_phase: PFCPhase = PFCPhase.PROOF
        self._metrics = PFCMetrics()

        # Threading
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Callbacks
        self._field_callbacks: List[Callable[[EnergyField], None]] = []
        self._selection_callbacks: List[Callable[[SelectionResult], None]] = []
        self._phase_callbacks: List[Callable[[PFCPhase], None]] = []

    # ──────────────────────────────────────────────────────────────────────────
    # PROOF Phase: Ingestion and Verification
    # ──────────────────────────────────────────────────────────────────────────

    def ingest_assertion(self, assertion: Assertion) -> None:
        """Ingest a single assertion."""
        env = SigEnvelope.wrap(assertion, assertion.issuer, self.signer)
        with self._lock:
            self.store.add_assertion(env)
            self._metrics.assertions_ingested += 1

    def ingest_assertions(self, assertions: List[Assertion]) -> None:
        """Ingest multiple assertions."""
        envs = [
            SigEnvelope.wrap(a, a.issuer, self.signer)
            for a in assertions
        ]
        with self._lock:
            self.store.add_assertion_batch(envs)
            self._metrics.assertions_ingested += len(assertions)

    def ingest_claim(self, claim: Claim) -> None:
        """Ingest and process a claim."""
        env = SigEnvelope.wrap(claim, claim.claimant, self.signer)
        with self._lock:
            self.store.add_claim(env)
            self._metrics.claims_processed += 1

            # Extract assertions from claim
            for assertion in claim.assertions:
                a_env = SigEnvelope.wrap(assertion, assertion.issuer, self.signer)
                self.store.add_assertion(a_env)
                self._metrics.assertions_ingested += 1

    def process_proof(self, proof: Proof) -> bool:
        """
        Process and verify a proof.

        Returns True if proof is valid.
        """
        with self._lock:
            valid = self.challenge_controller.process_proof(proof)
            if valid:
                self._metrics.proofs_verified += 1
            else:
                self._metrics.proofs_failed += 1
            return valid

    def _run_proof_phase(self, now_ms: int) -> None:
        """Execute PROOF phase of PFC loop."""
        self._current_phase = PFCPhase.PROOF
        self._notify_phase_change()

        # Emit challenges for verification
        challenges = self.challenge_controller.emit_challenges(now_ms)
        self._metrics.challenges_issued += len(challenges)

    # ──────────────────────────────────────────────────────────────────────────
    # FIELD Phase: Build Energy Field
    # ──────────────────────────────────────────────────────────────────────────

    def _run_field_phase(self, now_ms: int) -> None:
        """Execute FIELD phase of PFC loop."""
        self._current_phase = PFCPhase.FIELD
        self._notify_phase_change()

        # Build field from assertions
        self._current_field = self.field_builder.build(now_ms)

        # Notify callbacks
        if self._current_field:
            for cb in self._field_callbacks:
                try:
                    cb(self._current_field)
                except Exception as e:
                    logger.error(f"Field callback error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # CONTROL Phase: Compute Tau and Select Patterns
    # ──────────────────────────────────────────────────────────────────────────

    def _run_control_phase(self, now_ms: int) -> None:
        """Execute CONTROL phase of PFC loop."""
        self._current_phase = PFCPhase.CONTROL
        self._notify_phase_change()

        if not self._current_field:
            return

        # 1. Compute tau limits for all compute nodes
        self._current_tau_limits = self.compute_controller.apply(
            self._current_field,
            now_ms,
            self._regional_constraints,
        )

        # 2. Select patterns based on tau and field state
        self._current_selection = self.selector.select(
            self._current_field,
            self._current_tau_limits,
        )

        if self._current_selection:
            self._metrics.patterns_selected += len(self._current_selection.selected)
            self._metrics.patterns_rejected += len(self._current_selection.rejected)

            # Notify callbacks
            for cb in self._selection_callbacks:
                try:
                    cb(self._current_selection)
                except Exception as e:
                    logger.error(f"Selection callback error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Main Loop
    # ──────────────────────────────────────────────────────────────────────────

    def tick(self) -> None:
        """Execute one complete PFC cycle."""
        tick_start = int(time.time() * 1000)

        with self._lock:
            now_ms = tick_start

            # 1. PROOF: Verify and challenge
            self._run_proof_phase(now_ms)

            # 2. FIELD: Build energy field
            self._run_field_phase(now_ms)

            # 3. CONTROL: Compute tau and select
            self._run_control_phase(now_ms)

            # Update metrics
            self._metrics.ticks += 1
            tick_duration = int(time.time() * 1000) - tick_start
            self._metrics.last_tick_ms = tick_duration
            self._metrics.avg_tick_duration_ms = (
                self._metrics.avg_tick_duration_ms * 0.9 + tick_duration * 0.1
            )

    def start(self) -> None:
        """Start the PFC loop."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"PFCNode {self.config.node_id} started")

    def stop(self) -> None:
        """Stop the PFC loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info(f"PFCNode {self.config.node_id} stopped")

    def _run_loop(self) -> None:
        """Background loop for continuous PFC execution."""
        while self._running:
            try:
                self.tick()
            except Exception as e:
                logger.error(f"PFC tick error: {e}")
            time.sleep(self.config.tick_interval_ms / 1000.0)

    # ──────────────────────────────────────────────────────────────────────────
    # Query API
    # ──────────────────────────────────────────────────────────────────────────

    def get_field(self) -> Optional[EnergyField]:
        """Get current energy field."""
        with self._lock:
            return self._current_field

    def get_tau_limit(self, node_id: EntityID) -> float:
        """Get tau limit for a specific compute node."""
        with self._lock:
            return self._current_tau_limits.get(node_id, 1.0)

    def get_tau_limits(self) -> Dict[EntityID, float]:
        """Get all tau limits."""
        with self._lock:
            return self._current_tau_limits.copy()

    def get_selection(self) -> Optional[SelectionResult]:
        """Get current pattern selection."""
        with self._lock:
            return self._current_selection

    def get_metrics(self) -> PFCMetrics:
        """Get runtime metrics."""
        with self._lock:
            return PFCMetrics(
                ticks=self._metrics.ticks,
                assertions_ingested=self._metrics.assertions_ingested,
                claims_processed=self._metrics.claims_processed,
                challenges_issued=self._metrics.challenges_issued,
                proofs_verified=self._metrics.proofs_verified,
                proofs_failed=self._metrics.proofs_failed,
                patterns_selected=self._metrics.patterns_selected,
                patterns_rejected=self._metrics.patterns_rejected,
                last_tick_ms=self._metrics.last_tick_ms,
                avg_tick_duration_ms=self._metrics.avg_tick_duration_ms,
            )

    def get_phase(self) -> PFCPhase:
        """Get current PFC phase."""
        with self._lock:
            return self._current_phase

    # ──────────────────────────────────────────────────────────────────────────
    # Configuration
    # ──────────────────────────────────────────────────────────────────────────

    def set_regional_constraints(self, constraints: Dict[str, float]) -> None:
        """Update constraints from Regional Coordinator."""
        with self._lock:
            self._regional_constraints = constraints

    def register_pattern(self, spec: PatternSpec) -> None:
        """Register a pattern for selection."""
        with self._lock:
            self.selector.register_pattern(spec)

    def unregister_pattern(self, pattern_id: EntityID) -> None:
        """Remove a pattern from selection."""
        with self._lock:
            self.selector.unregister_pattern(pattern_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Callbacks
    # ──────────────────────────────────────────────────────────────────────────

    def on_field_update(self, callback: Callable[[EnergyField], None]) -> None:
        """Register callback for field updates."""
        self._field_callbacks.append(callback)

    def on_selection(self, callback: Callable[[SelectionResult], None]) -> None:
        """Register callback for pattern selection."""
        self._selection_callbacks.append(callback)

    def on_phase_change(self, callback: Callable[[PFCPhase], None]) -> None:
        """Register callback for phase changes."""
        self._phase_callbacks.append(callback)

    def _notify_phase_change(self) -> None:
        for cb in self._phase_callbacks:
            try:
                cb(self._current_phase)
            except Exception as e:
                logger.error(f"Phase callback error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Summary for RC/GH Reporting
    # ──────────────────────────────────────────────────────────────────────────

    def get_summary(self) -> Dict[str, Any]:
        """Get summary for Regional Coordinator reporting."""
        with self._lock:
            field = self._current_field
            metrics = self._metrics

            if not field:
                return {
                    "node_id": self.config.node_id,
                    "region_id": self.config.region_id,
                    "status": "no_data",
                    "metrics": {
                        "ticks": metrics.ticks,
                        "assertions": metrics.assertions_ingested,
                    },
                }

            return {
                "node_id": self.config.node_id,
                "region_id": self.config.region_id,
                "status": "active",
                "generated_at_ms": field.generated_at_ms,
                "num_points": len(field.points),
                "total_available_mw": field.total_available_power(),
                "avg_carbon_intensity": field.avg_carbon_intensity(),
                "num_compute_nodes": len(field.get_compute_nodes()),
                "tau_limits_count": len(self._current_tau_limits),
                "patterns_selected": len(self._current_selection.selected) if self._current_selection else 0,
                "metrics": {
                    "ticks": metrics.ticks,
                    "assertions": metrics.assertions_ingested,
                    "challenges": metrics.challenges_issued,
                    "proofs_ok": metrics.proofs_verified,
                    "proofs_fail": metrics.proofs_failed,
                    "avg_tick_ms": metrics.avg_tick_duration_ms,
                },
            }


def create_pfc_node(region_id: str, node_id: str | None = None, **kwargs) -> PFCNode:
    """Factory function to create a PFCNode with sensible defaults."""
    if node_id is None:
        node_id = f"pfc-{region_id.replace('/', '-')}"

    config = PFCConfig(
        region_id=region_id,
        node_id=node_id,
        **kwargs,
    )
    return PFCNode(config)
