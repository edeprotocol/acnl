"""
ACNL Integration — External Integrations

Sensors, SFL hooks, and external adapters.
"""
from .sensors import SimulatedSensor, SensorInterface, generate_simulated_assertions
from .sfl_hook import SFLEnergyHook, EnergyConstrainedAllocator

__all__ = [
    "SimulatedSensor",
    "SensorInterface",
    "generate_simulated_assertions",
    "SFLEnergyHook",
    "EnergyConstrainedAllocator",
]
