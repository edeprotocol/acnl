from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from acnl.energy.types import EntityID, make_entity_id
from acnl.energy.events import Assertion, Claim, SigEnvelope
from acnl.energy.crypto import SignatureScheme, MockSignatureScheme, wrap_with_signature
from acnl.energy.store import EnergyEventStore, StoreConfig
from acnl.field.energy_field import EnergyField, EnergyFieldBuilder, FieldConfig
from acnl.control.policies import TauLimitPolicy, DefaultTauLimitPolicy, TauLimitResult
from acnl.control.challenges import ChallengeController, ChallengeConfig


@dataclass
class LFIConfig:
    """Configuration for Local Field Integrator."""
    region_id: str
    lfi_name: str = "lfi-1"
    field_horizon_ms: int = 15 * 60 * 1000  # 15 minutes
    tick_interval_ms: int = 1000  # 1 second
    min_confidence: float = 0.1
    challenge_enabled: bool = True


class LocalFieldIntegrator:
    """
    Local Field Integrator (LFI) - lowest level of the fractal hierarchy.

    Responsibilities:
    - Ingest assertions from local sensors
    - Build energy field for local region
    - Compute tau limits for local compute nodes
    - Issue challenges to verify node claims
    - Report summary to Regional Coordinator
    """

    def __init__(
        self,
        config: LFIConfig,
        policy: TauLimitPolicy | None = None,
        signer: SignatureScheme | None = None,
    ):
        self._config = config
        self._lfi_id = make_entity_id("lfi", config.lfi_name)

        self._store = EnergyEventStore(StoreConfig())
        self._signer = signer or MockSignatureScheme(f"lfi-{config.lfi_name}")
        self._policy = policy or DefaultTauLimitPolicy()

        self._field_config = FieldConfig(
            horizon_ms=config.field_horizon_ms,
            min_confidence=config.min_confidence,
        )
        self._field_builder = EnergyFieldBuilder(
            self._store,
            self._field_config,
            config.region_id,
        )

        self._challenge_controller: Optional[ChallengeController] = None
        if config.challenge_enabled:
            self._challenge_controller = ChallengeController(
                self._store,
                self._signer,
                self._lfi_id,
                ChallengeConfig(),
            )

        self._current_field: Optional[EnergyField] = None
        self._tau_limits: Dict[EntityID, float] = {}
        self._regional_constraints: Dict[str, float] = {}

        self._last_tick_ms = 0

    @property
    def lfi_id(self) -> EntityID:
        return self._lfi_id

    @property
    def region_id(self) -> str:
        return self._config.region_id

    def ingest_assertions(self, assertions: List[SigEnvelope[Assertion]]) -> None:
        """Ingest signed assertions from sensors."""
        for env in assertions:
            self._store.add_assertion(env)

    def tick(self, now_ms: int | None = None) -> None:
        """Run one tick of the LFI."""
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        # Build field
        self._current_field = self._field_builder.build(now_ms)

        # Compute tau limits
        self._compute_tau_limits()

        # Run challenges if enabled
        if self._challenge_controller:
            self._run_challenges()

        self._last_tick_ms = now_ms

    def _compute_tau_limits(self) -> None:
        """Compute tau limits for all compute nodes."""
        if self._current_field is None:
            return

        self._tau_limits.clear()

        for point in self._current_field.get_compute_nodes():
            result = self._policy.compute(
                point,
                self._current_field,
                self._regional_constraints,
            )
            self._tau_limits[point.subject] = result.tau_limit

    def _run_challenges(self) -> None:
        """Issue and verify challenges."""
        if self._challenge_controller is None or self._current_field is None:
            return

        # Clean up expired
        self._challenge_controller.cleanup_expired()

        # Issue challenges to nodes that need them
        for point in self._current_field.get_compute_nodes():
            if self._challenge_controller.should_challenge(point.subject):
                self._challenge_controller.issue_challenge(
                    target=point.subject,
                    challenge_type="power_correlation",
                    payload={
                        "expected_power": point.consumption_power_mw,
                        "timestamp_ms": point.coord.ts_ms,
                    },
                    region_id=self._config.region_id,
                )

    def get_field(self) -> Optional[EnergyField]:
        """Get current energy field."""
        return self._current_field

    def get_tau_limits(self) -> Dict[EntityID, float]:
        """Get current tau limits for all compute nodes."""
        return self._tau_limits.copy()

    def get_tau_limit(self, node_id: EntityID) -> float:
        """Get tau limit for a specific node."""
        return self._tau_limits.get(node_id, 0.0)

    def set_regional_constraints(self, constraints: Dict[str, float]) -> None:
        """Set constraints from Regional Coordinator."""
        self._regional_constraints = constraints

    def get_summary(self) -> Dict:
        """Get summary for Regional Coordinator."""
        field = self._current_field
        if field is None:
            return {
                "region_id": self._config.region_id,
                "lfi_id": str(self._lfi_id),
                "num_points": 0,
                "total_available_mw": 0.0,
                "total_consumption_mw": 0.0,
                "total_generation_mw": 0.0,
                "avg_carbon_intensity": 0.0,
                "compute_nodes": 0,
                "tau_limits": {},
            }

        compute_nodes = field.get_compute_nodes()

        return {
            "region_id": self._config.region_id,
            "lfi_id": str(self._lfi_id),
            "timestamp_ms": field.timestamp_ms,
            "num_points": len(field.points),
            "total_available_mw": field.total_available_power(),
            "total_consumption_mw": field.total_consumption(),
            "total_generation_mw": field.total_generation(),
            "avg_carbon_intensity": field.average_carbon_intensity(),
            "compute_nodes": len(compute_nodes),
            "tau_limits": {str(k): v for k, v in self._tau_limits.items()},
        }

    def get_trust_scores(self) -> Dict[EntityID, float]:
        """Get trust scores for all known nodes."""
        if self._challenge_controller is None:
            return {}

        scores = {}
        if self._current_field:
            for point in self._current_field.get_compute_nodes():
                scores[point.subject] = self._challenge_controller.get_trust_score(
                    point.subject
                )
        return scores
