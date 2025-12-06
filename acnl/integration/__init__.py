"""
ACNL Integration Module - Hooks for SFL and sensor simulation.
"""
from .sensors import (
    SensorConfig,
    SimulatedSensor,
    SensorRegistry,
    generate_simulated_assertions,
)
from .sfl_hook import (
    TauAllocation,
    SFLEnergyHook,
    EnergyConstrainedAllocator,
)

__all__ = [
    # Sensors
    "SensorConfig",
    "SimulatedSensor",
    "SensorRegistry",
    "generate_simulated_assertions",
    # SFL Hook
    "TauAllocation",
    "SFLEnergyHook",
    "EnergyConstrainedAllocator",
]
