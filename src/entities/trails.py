"""Trail components for ship path visualization."""
from __future__ import annotations
from dataclasses import dataclass, field

from ..core.ecs import Component


@dataclass
class TrailPoint:
    """A single point in a ship's trail."""
    x: float
    y: float
    timestamp: float  # Game time when point was recorded


@dataclass
class Trail(Component):
    """Component that stores a ship's position history for trail rendering.

    Creates the visual "ant farm" effect by showing where ships have been.
    """
    points: list[TrailPoint] = field(default_factory=list)
    max_points: int = 30  # Maximum number of trail points to store
    max_age: float = 5.0  # Seconds before trail points fade completely
    record_interval: float = 0.1  # Time between recording points
    last_record_time: float = 0.0  # Last time a point was recorded
