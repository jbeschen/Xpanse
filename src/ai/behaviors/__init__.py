"""Ship behavior strategies for the behavior pattern.

This package provides extensible ship behaviors using the Strategy pattern.
Adding new behaviors (mining, escort, construction) requires only creating
a new behavior class - no changes to the core AI system needed.
"""
from __future__ import annotations
from typing import Optional, Type

from .base import ShipBehavior, BehaviorContext, BehaviorResult, BehaviorStatus
from .trading import TradingBehavior
from .drone import DroneBehavior
from .patrol import PatrolBehavior
from .waypoint import WaypointBehavior

__all__ = [
    'ShipBehavior',
    'BehaviorContext',
    'BehaviorResult',
    'BehaviorStatus',
    'TradingBehavior',
    'DroneBehavior',
    'PatrolBehavior',
    'WaypointBehavior',
]


# Behavior registry for easy lookup by name
BEHAVIOR_REGISTRY: dict[str, Type[ShipBehavior]] = {
    "trading": TradingBehavior,
    "drone": DroneBehavior,
    "patrol": PatrolBehavior,
    "waypoint": WaypointBehavior,
}


def get_behavior_class(name: str) -> Optional[Type[ShipBehavior]]:
    """Get behavior class by name."""
    return BEHAVIOR_REGISTRY.get(name)


def register_behavior(name: str, behavior_class: Type[ShipBehavior]) -> None:
    """Register a new behavior type."""
    BEHAVIOR_REGISTRY[name] = behavior_class
