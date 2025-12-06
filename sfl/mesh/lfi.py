from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable, Any
import time
import threading

from sfl.energy.store import EventStore
from sfl.energy.field import EnergyFieldBuilder, FieldConfig, EnergyField
from sfl.energy.model import EntityID, Assertion, Observable, EnergyObservableKind, Coord
from sfl.energy.crypto import SigEnvelope, MockSignatureScheme
from .controllers import (
    LocalEnergyController,
    LocalComputeController,
    ChallengeController,
    TauLimitComputer,
    TauLimitConfig,
)


@dataclass
class LFIConfig:
    region_id: str
    field_horizon_ms: int = 5_000
    tick_interval_ms: int = 1_000
    tau_config: TauLimitConfig = field(default_factory=TauLimitConfig)


class LocalFieldIntegrator:
    """
    Local Field Integrator - fractal node that:
    1. Collects energy/compute assertions
    2. Builds local EnergyField
    3. Computes tau_limits for compute nodes
    4. Emits challenges for verification
    5. Reports summary to Regional Coordinator
    """

    def __init__(self, config: LFIConfig):
        self.config = config
        self.store = EventStore()
        self.signer = MockSignatureScheme(f"lfi-{config.region_id}")

        self.field_builder = EnergyFieldBuilder(
            store=self.store,
            config=FieldConfig(horizon_ms=config.field_horizon_ms),
            region_id=config.region_id,
        )

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
        )

        self._current_field: Optional[EnergyField] = None
        self._current_tau_limits: Dict[EntityID, float] = {}
        self._current_directives: Dict[str, Any] = {}
        self._regional_constraints: Dict[str, float] = {}

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[EnergyField], None]] = []

    def ingest_assertion(self, assertion: Assertion) -> None:
        """Ingest a single assertion."""
        env = SigEnvelope.wrap(assertion, assertion.issuer, self.signer)
        self.store.add_assertion(env)

    def ingest_assertions(self, assertions: List[Assertion]) -> None:
        """Ingest multiple assertions."""
        envs = [
            SigEnvelope.wrap(a, a.issuer, self.signer)
            for a in assertions
        ]
        self.store.add_assertion_batch(envs)

    def set_regional_constraints(self, constraints: Dict[str, float]) -> None:
        """Update constraints from Regional Coordinator."""
        self._regional_constraints = constraints

    def tick(self) -> None:
        """Single tick of the LFI loop."""
        now_ms = int(time.time() * 1000)

        # 1. Emit challenges
        self.challenge_controller.emit_challenges(now_ms)

        # 2. Build field
        self._current_field = self.field_builder.build(now_ms)

        # 3. Apply energy controller
        self._current_directives = self.energy_controller.apply(
            self._current_field, now_ms
        )

        # 4. Compute tau limits
        self._current_tau_limits = self.compute_controller.apply(
            self._current_field,
            now_ms,
            self._regional_constraints,
        )

        # 5. Notify callbacks
        for cb in self._callbacks:
            try:
                cb(self._current_field)
            except Exception:
                pass  # Don't let callbacks crash the loop

    def start(self) -> None:
        """Start background tick loop."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run_loop(self) -> None:
        while self._running:
            try:
                self.tick()
            except Exception as e:
                print(f"LFI tick error: {e}")
            time.sleep(self.config.tick_interval_ms / 1000.0)

    def get_field(self) -> Optional[EnergyField]:
        return self._current_field

    def get_tau_limit(self, node_id: EntityID) -> float:
        """Get tau_limit for a specific compute node."""
        return self._current_tau_limits.get(node_id, 1.0)

    def get_tau_limits(self) -> Dict[EntityID, float]:
        return self._current_tau_limits.copy()

    def get_directives(self) -> Dict[str, Any]:
        return self._current_directives.copy()

    def get_summary(self) -> Dict[str, Any]:
        """Summary for RC reporting."""
        field = self._current_field
        if not field:
            return {"region_id": self.config.region_id, "status": "no_data"}

        return {
            "region_id": self.config.region_id,
            "generated_at_ms": field.generated_at_ms,
            "num_points": len(field.points),
            "total_available_mw": field.total_available_power(),
            "avg_carbon_intensity": field.avg_carbon_intensity(),
            "num_compute_nodes": len(field.get_compute_nodes()),
            "directives": self._current_directives,
        }

    def on_field_update(self, callback: Callable[[EnergyField], None]) -> None:
        """Register callback for field updates."""
        self._callbacks.append(callback)
