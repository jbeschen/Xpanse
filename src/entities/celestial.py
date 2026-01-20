"""Celestial body entities (planets, moons, asteroids)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.ecs import Component, Entity
from ..core.world import World
from ..solar_system.bodies import CelestialBodyData, BodyType, SOLAR_SYSTEM_DATA
from ..solar_system.orbits import Position, Orbit
from ..simulation.resources import ResourceDeposit

if TYPE_CHECKING:
    pass


@dataclass
class CelestialBody(Component):
    """Component identifying a celestial body."""
    body_type: BodyType = BodyType.PLANET
    radius: float = 1000.0  # km
    color: tuple[int, int, int] = (150, 150, 150)
    is_colonizable: bool = True
    has_atmosphere: bool = False
    gravity: float = 1.0  # Earth gravities


def create_celestial_body(
    world: World,
    data: CelestialBodyData
) -> Entity:
    """Create a celestial body entity from data.

    Args:
        world: The game world
        data: Celestial body data

    Returns:
        The created entity
    """
    # Create entity with appropriate tags
    tags = {data.body_type.value}
    if data.resources:
        tags.add("has_resources")

    entity = world.create_entity(name=data.name, tags=tags)
    em = world.entity_manager

    # Add celestial body component
    em.add_component(entity, CelestialBody(
        body_type=data.body_type,
        radius=data.radius,
        color=data.color,
        is_colonizable=data.body_type in (BodyType.PLANET, BodyType.MOON, BodyType.DWARF_PLANET),
    ))

    # Add position (will be updated by orbital system)
    em.add_component(entity, Position(x=data.semi_major_axis, y=0.0))

    # Add orbit if it has a parent
    if data.parent:
        em.add_component(entity, Orbit(
            parent_name=data.parent,
            semi_major_axis=data.semi_major_axis,
            orbital_period=data.orbital_period,
        ))

    # Add resource deposits
    for resource_type, richness in data.resources:
        # Create a separate deposit component for each resource
        # For simplicity, we'll use the first resource as primary
        em.add_component(entity, ResourceDeposit(
            resource_type=resource_type,
            richness=richness,
            remaining=1000000.0 * richness,
        ))
        break  # Only add first resource as primary deposit

    return entity


def create_solar_system(world: World) -> dict[str, Entity]:
    """Create all celestial bodies in the solar system.

    Args:
        world: The game world

    Returns:
        Dictionary mapping body names to entities
    """
    bodies: dict[str, Entity] = {}

    # Create bodies in order (parents first)
    # Sun first
    sun_data = SOLAR_SYSTEM_DATA.get("Sun")
    if sun_data:
        bodies["Sun"] = create_celestial_body(world, sun_data)

    # Then planets and their moons
    for name, data in SOLAR_SYSTEM_DATA.items():
        if name == "Sun":
            continue
        bodies[name] = create_celestial_body(world, data)

    return bodies


def get_body_display_radius(body: CelestialBody, zoom: float) -> float:
    """Get display radius for a celestial body based on zoom level.

    Uses log scale to keep bodies visible at all zoom levels.

    Args:
        body: The celestial body component
        zoom: Current camera zoom level

    Returns:
        Display radius in pixels
    """
    import math

    # Base size depends on body type
    if body.body_type == BodyType.STAR:
        base_size = 20.0
    elif body.body_type == BodyType.PLANET:
        base_size = 8.0
    elif body.body_type == BodyType.DWARF_PLANET:
        base_size = 5.0
    elif body.body_type == BodyType.MOON:
        base_size = 4.0
    else:
        base_size = 3.0

    # Scale with zoom but use log to prevent too small/large
    min_size = 3.0
    max_size = 50.0

    scaled = base_size * math.log10(zoom * 10 + 1)
    return max(min_size, min(max_size, scaled))
