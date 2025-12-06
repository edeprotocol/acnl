from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict

from sfl.energy.model import EnergyField, EnergyFieldPoint, Coord, EntityID

# Optional httpx import - gracefully handle if not installed
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class EnergyMeshClient:
    """
    Client for patterns/AGI to interact with Energy Mesh.
    Connects to LFI endpoint.
    """

    base_url: str
    timeout: float = 5.0
    _client: Optional["httpx.AsyncClient"] = None

    async def __aenter__(self):
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx is required for EnergyMeshClient. Install with: pip install httpx")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def get_energy_field(self, region_id: str) -> Optional[EnergyField]:
        """Get current energy field for region."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        resp = await self._client.get(f"/v1/field/{region_id}")
        if resp.status_code != 200:
            return None

        data = resp.json()
        # Deserialize
        points = [
            EnergyFieldPoint(
                coord=Coord(region_id=p["coord"]["region_id"], ts_ms=p["coord"]["ts_ms"]),
                subject=p["subject"],
                metrics=p["metrics"],
                confidence=p["confidence"],
            )
            for p in data.get("points", [])
        ]

        return EnergyField(
            region_id=data["region_id"],
            points=points,
            generated_at_ms=data["generated_at_ms"],
        )

    async def get_tau_limit(self, node_id: EntityID) -> float:
        """Get tau_limit for a compute node."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        resp = await self._client.get(f"/v1/tau_limit/{node_id}")
        if resp.status_code != 200:
            return 1.0  # default

        return resp.json().get("tau_limit", 1.0)

    async def get_tau_limits(self, region_id: str) -> Dict[EntityID, float]:
        """Get all tau_limits for region."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        resp = await self._client.get(f"/v1/tau_limits/{region_id}")
        if resp.status_code != 200:
            return {}

        return resp.json()


class EnergyMeshClientSync:
    """Synchronous wrapper around EnergyMeshClient."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx is required for EnergyMeshClientSync. Install with: pip install httpx")
        self.base_url = base_url
        self.timeout = timeout
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def get_energy_field(self, region_id: str) -> Optional[EnergyField]:
        resp = self._client.get(f"/v1/field/{region_id}")
        if resp.status_code != 200:
            return None

        data = resp.json()
        points = [
            EnergyFieldPoint(
                coord=Coord(region_id=p["coord"]["region_id"], ts_ms=p["coord"]["ts_ms"]),
                subject=p["subject"],
                metrics=p["metrics"],
                confidence=p["confidence"],
            )
            for p in data.get("points", [])
        ]

        return EnergyField(
            region_id=data["region_id"],
            points=points,
            generated_at_ms=data["generated_at_ms"],
        )

    def get_tau_limit(self, node_id: EntityID) -> float:
        resp = self._client.get(f"/v1/tau_limit/{node_id}")
        if resp.status_code != 200:
            return 1.0
        return resp.json().get("tau_limit", 1.0)

    def close(self):
        self._client.close()
