from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import uuid
import time

from sfl.energy.model import (
    EnergyField,
    EnergyFieldPoint,
    EnergyObservableKind,
    EntityID,
    Challenge,
    Proof,
    Coord,
    parse_entity_id,
)
from sfl.energy.store import EventStore


@dataclass
class TauLimitConfig:
    """Configuration for tau limit computation."""
    base_power_mw: float = 100.0          # power at which tau_limit = 1.0
    congestion_threshold: float = 0.8      # line loading above this triggers penalty
    carbon_ceiling: float = 500.0          # gCO2/kWh above which we penalize
    carbon_penalty: float = 0.5            # multiplier when above carbon ceiling
    min_tau: float = 0.01                  # never go below this
    max_tau: float = 2.0                   # cap


class TauLimitComputer:
    """
    Computes tau_limit for a compute node based on energy field state.
    This is the core policy that constrains SFL allocation by physical reality.
    """

    def __init__(self, config: TauLimitConfig | None = None):
        self.config = config or TauLimitConfig()

    def compute(
        self,
        point: EnergyFieldPoint,
        regional_constraints: Dict[str, float] | None = None,
    ) -> float:
        """
        Compute tau_limit for a single compute node.

        Args:
            point: EnergyFieldPoint for the compute node
            regional_constraints: Optional constraints from RC (e.g. carbon_throttle)

        Returns:
            tau_limit in [min_tau, max_tau]
        """
        cfg = self.config

        # Base: proportional to available power
        available_power = point.get_metric(EnergyObservableKind.AVAILABLE_POWER, 0)
        if available_power <= 0:
            # Fallback to consumption headroom
            consumption = point.get_metric(EnergyObservableKind.CONSUMPTION_POWER, 0)
            available_power = max(0, cfg.base_power_mw - consumption)

        base_tau = min(1.0, available_power / cfg.base_power_mw)

        # Congestion penalty (line loading)
        line_loading = point.get_metric(EnergyObservableKind.LINE_LOADING, 0)
        if line_loading > cfg.congestion_threshold:
            # Exponential penalty as we approach 1.0
            congestion_factor = 1.0 - (line_loading - cfg.congestion_threshold) / (1.0 - cfg.congestion_threshold)
            base_tau *= max(0.1, congestion_factor)

        # Carbon penalty
        carbon_intensity = point.get_metric(EnergyObservableKind.CARBON_INTENSITY, 0)
        if carbon_intensity > cfg.carbon_ceiling:
            base_tau *= cfg.carbon_penalty

        # Thermal margin
        thermal_margin = point.get_metric(EnergyObservableKind.THERMAL_MARGIN, 1.0)
        if thermal_margin < 0.2:
            base_tau *= thermal_margin / 0.2

        # Apply regional constraints
        if regional_constraints:
            carbon_throttle = regional_constraints.get("carbon_throttle", 1.0)
            base_tau *= carbon_throttle

            power_quota = regional_constraints.get("power_quota", 1.0)
            base_tau *= power_quota

        # Confidence weighting: low confidence = conservative
        base_tau *= (0.5 + 0.5 * point.confidence)

        return max(cfg.min_tau, min(cfg.max_tau, base_tau))

    def compute_batch(
        self,
        field: EnergyField,
        regional_constraints: Dict[str, float] | None = None,
    ) -> Dict[EntityID, float]:
        """Compute tau_limit for all compute nodes in field."""
        result = {}
        for point in field.get_compute_nodes():
            result[point.subject] = self.compute(point, regional_constraints)
        return result


@dataclass
class LocalEnergyController:
    """Monitors and shapes energy state at local level."""

    store: EventStore
    region_id: str
    congestion_threshold: float = 0.9

    def apply(self, field: EnergyField, now_ms: int) -> Dict[str, Any]:
        """
        Analyze field and return local energy directives.
        """
        directives: Dict[str, Any] = {
            "congested_lines": [],
            "overloaded_nodes": [],
            "curtailment_needed": False,
            "total_available_mw": field.total_available_power(),
        }

        for point in field.points:
            kind, _ = parse_entity_id(point.subject)

            # Check line congestion
            if kind == "line":
                loading = point.get_metric(EnergyObservableKind.LINE_LOADING, 0)
                if loading > self.congestion_threshold:
                    directives["congested_lines"].append({
                        "subject": point.subject,
                        "loading": loading,
                    })

            # Check node overload
            if kind == "compute-node":
                utilization = point.get_metric(EnergyObservableKind.COMPUTE_UTILIZATION, 0)
                temp = point.get_metric(EnergyObservableKind.TEMP_CELSIUS, 0)
                if utilization > 0.95 or temp > 85:
                    directives["overloaded_nodes"].append({
                        "subject": point.subject,
                        "utilization": utilization,
                        "temp": temp,
                    })

        # Curtailment signal
        if len(directives["congested_lines"]) > 0:
            directives["curtailment_needed"] = True

        return directives


@dataclass
class LocalComputeController:
    """Controls compute allocation based on energy state."""

    store: EventStore
    region_id: str
    tau_computer: TauLimitComputer = field(default_factory=TauLimitComputer)

    def apply(
        self,
        field: EnergyField,
        now_ms: int,
        regional_constraints: Dict[str, float] | None = None,
    ) -> Dict[EntityID, float]:
        """
        Compute tau_limit for all compute nodes.
        Returns: {node_id: tau_limit}
        """
        return self.tau_computer.compute_batch(field, regional_constraints)


@dataclass
class ChallengeController:
    """Generates and validates physical challenges."""

    store: EventStore
    region_id: str
    challenge_interval_ms: int = 10_000  # challenge each node every 10s
    challenge_timeout_ms: int = 5_000

    _last_challenge_time: Dict[EntityID, int] = field(default_factory=dict)
    _pending: Dict[str, Challenge] = field(default_factory=dict)

    def emit_challenges(
        self,
        now_ms: int,
        targets: List[EntityID] | None = None,
    ) -> List[Challenge]:
        """Generate challenges for nodes due for verification."""

        if targets is None:
            # Get all compute nodes from store's recent assertions
            targets = self._get_known_compute_nodes()

        challenges = []

        for target in targets:
            last_time = self._last_challenge_time.get(target, 0)
            if now_ms - last_time < self.challenge_interval_ms:
                continue

            challenge = Challenge(
                challenge_id=str(uuid.uuid4()),
                challenger=f"lfi:{self.region_id}",
                target=target,
                coord=Coord.now(self.region_id),
                challenge_type="power_correlation",
                payload={
                    "kernel": "matmul_benchmark_1024",
                    "expected_power_range_w_min": 800,
                    "expected_power_range_w_max": 1200,
                    "duration_ms": 1000,
                },
                timeout_ms=self.challenge_timeout_ms,
                status="pending",
            )

            self.store.add_challenge(challenge)
            self._pending[challenge.challenge_id] = challenge
            self._last_challenge_time[target] = now_ms
            challenges.append(challenge)

        return challenges

    def process_proof(self, proof: Proof) -> bool:
        """
        Validate a proof against its challenge.
        Returns True if proof is valid.
        """
        if proof.challenge_id not in self._pending:
            return False

        challenge = self._pending[proof.challenge_id]

        # Check timeout
        now_ms = int(time.time() * 1000)
        if now_ms > challenge.coord.ts_ms + challenge.timeout_ms:
            self.store.update_challenge_status(challenge.challenge_id, "timeout")
            del self._pending[challenge.challenge_id]
            return False

        # Validate proof (simplified)
        if challenge.challenge_type == "power_correlation":
            measured_power = proof.result.get("measured_power_w", 0)
            expected_min = challenge.payload.get("expected_power_range_w_min", 0)
            expected_max = challenge.payload.get("expected_power_range_w_max", float("inf"))

            valid = expected_min <= measured_power <= expected_max

            proof.verified = valid
            proof.verification_method = "power_range_check"

        self.store.add_proof(proof)
        self.store.update_challenge_status(
            challenge.challenge_id,
            "completed" if proof.verified else "failed"
        )
        del self._pending[challenge.challenge_id]

        return proof.verified

    def _get_known_compute_nodes(self) -> List[EntityID]:
        """Get compute nodes from recent assertions."""
        now_ms = int(time.time() * 1000)
        assertions = self.store.get_assertions_in_window(
            region_id=self.region_id,
            start_ms=now_ms - 60_000,  # last minute
            end_ms=now_ms,
            subject_filter=lambda s: parse_entity_id(s)[0] == "compute-node",
        )
        return list(set(a.subject for a in assertions))
