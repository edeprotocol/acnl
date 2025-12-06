"""
ACNL Runtime — LFI Runtime

Main loop for Local Field Integrator.
Reads sensors, builds field, computes tau limits, issues challenges.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Callable, List
import threading
import time

from ..core.ids import EntityID
from ..core.events import Assertion
from ..store.event_store import EventStore
from ..mesh.aggregator import LocalFieldBuilder, AggregatorConfig
from ..control.lfi import LocalFieldIntegrator
from ..control.policies import TauLimitPolicy, DefaultTauLimitPolicy
from ..control.challenges import ChallengeController, ChallengeConfig
from ..integration.sensors import SensorInterface


@dataclass
class LFIConfig:
    """Configuration for LFI runtime."""
    region_id: str = "earth/default"
    tick_interval_ms: int = 1000  # 1 second
    field_window_ms: int = 60_000  # 1 minute
    challenge_interval_ms: int = 30_000  # 30 seconds
    min_trust_threshold: float = 0.5
    auto_start: bool = False


class LFIRuntime:
    """
    Main loop for Local Field Integrator.

    Responsibilities:
    - Poll sensors for assertions
    - Build local field from assertions
    - Compute tau limits using policy
    - Issue challenges to verify assertions
    - Publish field snapshots to parent RC
    """

    def __init__(
        self,
        config: LFIConfig,
        policy: TauLimitPolicy | None = None,
        sensors: List[SensorInterface] | None = None,
    ):
        self._config = config
        self._store = EventStore()
        self._builder = LocalFieldBuilder(
            AggregatorConfig(
                region_id=config.region_id,
                window_ms=config.field_window_ms,
            )
        )
        self._policy = policy or DefaultTauLimitPolicy()
        self._challenge_ctrl = ChallengeController(
            self._store,
            ChallengeConfig(
                challenge_interval_ms=config.challenge_interval_ms,
                min_trust_threshold=config.min_trust_threshold,
            ),
        )
        self._lfi = LocalFieldIntegrator(
            self._store,
            self._builder,
            self._policy,
            config.region_id,
        )

        self._sensors: List[SensorInterface] = sensors or []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._tick_count = 0
        self._last_challenge_ms = 0

        # Callbacks
        self._on_field_update: Optional[Callable] = None
        self._on_challenge_issued: Optional[Callable] = None

        if config.auto_start:
            self.start()

    @property
    def lfi(self) -> LocalFieldIntegrator:
        """Get the underlying LFI controller."""
        return self._lfi

    @property
    def store(self) -> EventStore:
        """Get the event store."""
        return self._store

    @property
    def region_id(self) -> str:
        return self._config.region_id

    @property
    def is_running(self) -> bool:
        return self._running

    def add_sensor(self, sensor: SensorInterface) -> None:
        """Add a sensor to poll."""
        with self._lock:
            self._sensors.append(sensor)

    def on_field_update(self, callback: Callable) -> None:
        """Register callback for field updates."""
        self._on_field_update = callback

    def on_challenge_issued(self, callback: Callable) -> None:
        """Register callback for challenges."""
        self._on_challenge_issued = callback

    def start(self) -> None:
        """Start the runtime loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the runtime loop."""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def tick(self) -> None:
        """Run one tick of the main loop."""
        now_ms = int(time.time() * 1000)

        # Poll sensors
        for sensor in self._sensors:
            assertions = sensor.poll()
            for assertion in assertions:
                self._store.add_assertion(assertion)
                self._builder.ingest(assertion)

        # Rebuild field
        self._lfi.rebuild_field()

        # Maybe issue challenges
        if now_ms - self._last_challenge_ms >= self._config.challenge_interval_ms:
            self._issue_challenges()
            self._last_challenge_ms = now_ms

        self._tick_count += 1

        # Notify callback
        if self._on_field_update:
            field = self._lfi.get_field()
            if field:
                self._on_field_update(field)

    def _run_loop(self) -> None:
        """Main runtime loop."""
        while self._running:
            try:
                self.tick()
            except Exception as e:
                # Log error but keep running
                print(f"LFI tick error: {e}")

            time.sleep(self._config.tick_interval_ms / 1000.0)

    def _issue_challenges(self) -> None:
        """Issue challenges to entities with low trust."""
        field = self._lfi.get_field()
        if field is None:
            return

        for point in field.all_points():
            if point.trust_score < self._config.min_trust_threshold:
                challenge = self._challenge_ctrl.issue_challenge(point.subject)
                if challenge and self._on_challenge_issued:
                    self._on_challenge_issued(challenge)

    def ingest_assertion(self, assertion: Assertion) -> None:
        """Manually ingest an assertion."""
        self._store.add_assertion(assertion)
        self._builder.ingest(assertion)

    def get_stats(self) -> dict:
        """Get runtime statistics."""
        return {
            "region_id": self._config.region_id,
            "tick_count": self._tick_count,
            "is_running": self._running,
            "sensor_count": len(self._sensors),
            "assertion_count": len(self._store.get_assertions()),
            "field_points": len(self._lfi.get_field().all_points()) if self._lfi.get_field() else 0,
        }
