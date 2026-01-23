"""Sector-local coordinate system.

Each sector uses its own grid coordinate system, completely independent of AU.
Ships in a sector use grid coordinates for movement.
Ships between sectors use AU coordinates on the system map.

Grid coordinates:
- (0, 0) is top-left of sector
- (GRID_COLS-1, GRID_ROWS-1) is bottom-right
- Bodies have fixed grid positions (e.g., Earth at 7,5)
- Stations orbit bodies at fixed grid offsets
- Ships move in grid space when in sector
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID
import math

from ..core.ecs import Component, System, EntityManager
from .sectors import SECTORS, GRID_COLS, GRID_ROWS, get_sector_id_for_body

if TYPE_CHECKING:
    pass


@dataclass
class SectorPosition(Component):
    """Position within a sector using grid coordinates.

    Ships with this component are "inside" a sector and rendered
    on the sector map. They do NOT have AU-based Position components.
    """
    sector_id: str = ""  # Which sector (e.g., "earth", "mars")
    grid_x: float = 7.0  # X position in grid units (0 to GRID_COLS)
    grid_y: float = 5.0  # Y position in grid units (0 to GRID_ROWS)

    # For entities orbiting a body (stations, parked ships)
    parent_body: str = ""  # Body name if attached
    orbit_angle: float = 0.0  # Angle around body (radians)
    orbit_distance: float = 1.0  # Distance from body center (grid units)


@dataclass
class SectorNavigation(Component):
    """Navigation target within a sector.

    Ships use this for intra-sector movement instead of NavigationTarget.
    """
    target_grid_x: float = 0.0
    target_grid_y: float = 0.0
    target_body: str = ""  # Body to orbit when arrived
    target_station_id: UUID | None = None  # Station we're heading to

    # Movement parameters (in grid units per second)
    speed: float = 2.0  # Grid cells per second
    max_speed: float = 3.0
    arrival_threshold: float = 0.3  # Grid units

    def has_arrived(self, current_x: float, current_y: float) -> bool:
        """Check if close enough to target."""
        dx = self.target_grid_x - current_x
        dy = self.target_grid_y - current_y
        return math.sqrt(dx*dx + dy*dy) <= self.arrival_threshold


class SectorMovementSystem(System):
    """Handles movement of ships within sectors using grid coordinates.

    This is completely separate from AU-based NavigationSystem.
    Ships with SectorPosition + SectorNavigation move in grid space.
    """

    priority = 10  # Run after orbital updates

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Move ships toward their sector navigation targets."""
        from ..entities.ships import Ship

        for entity, ship in entity_manager.get_all_components(Ship):
            sector_pos = entity_manager.get_component(entity, SectorPosition)
            sector_nav = entity_manager.get_component(entity, SectorNavigation)

            if not sector_pos or not sector_nav:
                continue

            # Skip if parked at a body
            if sector_pos.parent_body:
                continue

            # Calculate direction to target
            dx = sector_nav.target_grid_x - sector_pos.grid_x
            dy = sector_nav.target_grid_y - sector_pos.grid_y
            dist = math.sqrt(dx*dx + dy*dy)

            if dist <= sector_nav.arrival_threshold:
                # Arrived at target
                sector_pos.grid_x = sector_nav.target_grid_x
                sector_pos.grid_y = sector_nav.target_grid_y

                # If targeting a body, park there
                if sector_nav.target_body:
                    sector_pos.parent_body = sector_nav.target_body
                    # Calculate orbit position based on arrival angle
                    if dist > 0.01:
                        sector_pos.orbit_angle = math.atan2(dy, dx)
                    sector_pos.orbit_distance = 1.5  # Default orbit distance

                # Remove navigation - we've arrived
                entity_manager.remove_component(entity, SectorNavigation)
                continue

            # Normalize and move toward target
            dir_x = dx / dist
            dir_y = dy / dist

            move_dist = min(sector_nav.speed * dt, dist)
            sector_pos.grid_x += dir_x * move_dist
            sector_pos.grid_y += dir_y * move_dist


# Utility functions for coordinate conversion

def get_body_grid_position(sector_id: str, body_name: str) -> tuple[float, float] | None:
    """Get grid position of a body in a sector."""
    sector = SECTORS.get(sector_id)
    if not sector:
        return None

    body = sector.get_body(body_name)
    if not body:
        return None

    return (float(body.grid_x), float(body.grid_y))


def get_station_grid_position(
    sector_id: str,
    parent_body: str,
    slot_index: int
) -> tuple[float, float] | None:
    """Get grid position of a station based on its orbital slot."""
    body_pos = get_body_grid_position(sector_id, parent_body)
    if not body_pos:
        return None

    # Station orbital rings (in grid units from body center)
    STATION_RINGS = [1.2, 1.8, 2.4]  # Grid units
    CLOCK_ANGLES = [math.pi/2, 0, -math.pi/2, math.pi]  # 12, 3, 6, 9 o'clock

    ring = slot_index // 4
    clock = slot_index % 4

    if ring >= len(STATION_RINGS):
        ring = len(STATION_RINGS) - 1

    orbit_dist = STATION_RINGS[ring]
    angle = CLOCK_ANGLES[clock]

    return (
        body_pos[0] + orbit_dist * math.cos(angle),
        body_pos[1] - orbit_dist * math.sin(angle)  # Negative for screen coords
    )


def get_sector_entry_position(
    sector_id: str,
    from_direction: str  # "inner", "outer", or specific sector_id
) -> tuple[float, float]:
    """Get grid position where ships enter a sector.

    Args:
        sector_id: Target sector
        from_direction: "inner" (from sun), "outer" (from outer system),
                       or a specific sector_id

    Returns:
        (grid_x, grid_y) entry position
    """
    sector = SECTORS.get(sector_id)
    if not sector:
        return (GRID_COLS // 2, GRID_ROWS // 2)

    # Determine direction
    if from_direction == "inner":
        # Coming from inner system - enter from left
        return (0.5, GRID_ROWS // 2)
    elif from_direction == "outer":
        # Coming from outer system - enter from right
        return (GRID_COLS - 0.5, GRID_ROWS // 2)
    else:
        # Coming from specific sector - check orbital radii
        from_sector = SECTORS.get(from_direction)
        if from_sector and from_sector.orbital_radius < sector.orbital_radius:
            return (0.5, GRID_ROWS // 2)  # From inner
        else:
            return (GRID_COLS - 0.5, GRID_ROWS // 2)  # From outer


def get_sector_exit_position(
    sector_id: str,
    to_direction: str  # "inner", "outer", or specific sector_id
) -> tuple[float, float]:
    """Get grid position where ships exit a sector."""
    sector = SECTORS.get(sector_id)
    if not sector:
        return (GRID_COLS // 2, GRID_ROWS // 2)

    if to_direction == "inner":
        return (0.5, GRID_ROWS // 2)
    elif to_direction == "outer":
        return (GRID_COLS - 0.5, GRID_ROWS // 2)
    else:
        to_sector = SECTORS.get(to_direction)
        if to_sector and to_sector.orbital_radius > sector.orbital_radius:
            return (GRID_COLS - 0.5, GRID_ROWS // 2)  # Exit right
        else:
            return (0.5, GRID_ROWS // 2)  # Exit left


def is_at_sector_edge(grid_x: float, grid_y: float, threshold: float = 0.5) -> str | None:
    """Check if position is at a sector edge.

    Returns:
        "left", "right", "top", "bottom", or None if not at edge
    """
    if grid_x <= threshold:
        return "left"
    if grid_x >= GRID_COLS - threshold:
        return "right"
    if grid_y <= threshold:
        return "top"
    if grid_y >= GRID_ROWS - threshold:
        return "bottom"
    return None
