"""Real solar system data."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..simulation.resources import ResourceType

if TYPE_CHECKING:
    pass


class BodyType(Enum):
    """Types of celestial bodies."""
    STAR = "star"
    PLANET = "planet"
    DWARF_PLANET = "dwarf_planet"
    MOON = "moon"
    ASTEROID = "asteroid"
    ASTEROID_BELT = "asteroid_belt"


@dataclass
class CelestialBodyData:
    """Static data for a celestial body."""
    name: str
    body_type: BodyType
    parent: str | None  # Name of parent body (None for Sun)
    semi_major_axis: float  # AU from parent
    orbital_period: float  # Earth days
    radius: float  # km
    color: tuple[int, int, int]
    resources: list[tuple[ResourceType, float]] = field(default_factory=list)  # (type, richness)


# Real solar system data (simplified)
SOLAR_SYSTEM_DATA: dict[str, CelestialBodyData] = {
    # The Sun
    "Sun": CelestialBodyData(
        name="Sun",
        body_type=BodyType.STAR,
        parent=None,
        semi_major_axis=0.0,
        orbital_period=0.0,
        radius=696340,
        color=(255, 255, 200),
        resources=[]
    ),

    # Inner planets
    "Mercury": CelestialBodyData(
        name="Mercury",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=0.387,
        orbital_period=88,
        radius=2439,
        color=(169, 169, 169),
        resources=[
            (ResourceType.IRON_ORE, 1.5),
            (ResourceType.RARE_EARTHS, 0.8),
        ]
    ),
    "Venus": CelestialBodyData(
        name="Venus",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=0.723,
        orbital_period=225,
        radius=6051,
        color=(255, 198, 73),
        resources=[
            (ResourceType.SILICATES, 1.2),
            (ResourceType.RARE_EARTHS, 0.5),
        ]
    ),
    "Earth": CelestialBodyData(
        name="Earth",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=1.0,
        orbital_period=365.25,
        radius=6371,
        color=(100, 149, 237),
        resources=[
            (ResourceType.WATER_ICE, 0.5),
            (ResourceType.IRON_ORE, 1.0),
            (ResourceType.SILICATES, 1.0),
            (ResourceType.RARE_EARTHS, 0.3),
        ]
    ),
    "Moon": CelestialBodyData(
        name="Moon",
        body_type=BodyType.MOON,
        parent="Earth",
        semi_major_axis=0.05,  # Scaled up for visibility (trails behind Earth)
        orbital_period=27.3,
        radius=1737,
        color=(200, 200, 200),
        resources=[
            (ResourceType.SILICATES, 1.0),
            (ResourceType.HELIUM3, 1.5),
        ]
    ),
    "Mars": CelestialBodyData(
        name="Mars",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=1.524,
        orbital_period=687,
        radius=3389,
        color=(193, 68, 14),
        resources=[
            (ResourceType.WATER_ICE, 0.8),
            (ResourceType.IRON_ORE, 1.3),
            (ResourceType.SILICATES, 1.1),
        ]
    ),
    "Phobos": CelestialBodyData(
        name="Phobos",
        body_type=BodyType.MOON,
        parent="Mars",
        semi_major_axis=0.04,  # Scaled up for visibility
        orbital_period=0.32,
        radius=11,
        color=(150, 120, 100),
        resources=[
            (ResourceType.IRON_ORE, 0.8),
            (ResourceType.SILICATES, 0.6),
        ]
    ),
    "Deimos": CelestialBodyData(
        name="Deimos",
        body_type=BodyType.MOON,
        parent="Mars",
        semi_major_axis=0.07,  # Scaled up for visibility
        orbital_period=1.26,
        radius=6,
        color=(160, 140, 120),
        resources=[
            (ResourceType.SILICATES, 0.5),
        ]
    ),

    # Asteroid Belt
    "Ceres": CelestialBodyData(
        name="Ceres",
        body_type=BodyType.DWARF_PLANET,
        parent="Sun",
        semi_major_axis=2.77,
        orbital_period=1682,
        radius=473,
        color=(150, 150, 150),
        resources=[
            (ResourceType.WATER_ICE, 1.5),
            (ResourceType.IRON_ORE, 1.2),
            (ResourceType.SILICATES, 1.0),
        ]
    ),
    "Vesta": CelestialBodyData(
        name="Vesta",
        body_type=BodyType.ASTEROID,
        parent="Sun",
        semi_major_axis=2.36,
        orbital_period=1325,
        radius=262,
        color=(180, 180, 170),
        resources=[
            (ResourceType.IRON_ORE, 1.8),
            (ResourceType.RARE_EARTHS, 1.0),
        ]
    ),

    # Outer planets
    "Jupiter": CelestialBodyData(
        name="Jupiter",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=5.203,
        orbital_period=4333,
        radius=69911,
        color=(255, 165, 79),
        resources=[
            (ResourceType.HELIUM3, 2.0),
        ]
    ),
    "Io": CelestialBodyData(
        name="Io",
        body_type=BodyType.MOON,
        parent="Jupiter",
        semi_major_axis=0.08,  # Scaled up for visibility
        orbital_period=1.77,
        radius=1821,
        color=(255, 255, 100),
        resources=[
            (ResourceType.RARE_EARTHS, 1.5),
            (ResourceType.SILICATES, 0.8),
        ]
    ),
    "Europa": CelestialBodyData(
        name="Europa",
        body_type=BodyType.MOON,
        parent="Jupiter",
        semi_major_axis=0.12,  # Scaled up for visibility
        orbital_period=3.55,
        radius=1560,
        color=(200, 180, 150),
        resources=[
            (ResourceType.WATER_ICE, 2.0),
        ]
    ),
    "Ganymede": CelestialBodyData(
        name="Ganymede",
        body_type=BodyType.MOON,
        parent="Jupiter",
        semi_major_axis=0.18,  # Scaled up for visibility
        orbital_period=7.15,
        radius=2634,
        color=(180, 160, 140),
        resources=[
            (ResourceType.WATER_ICE, 1.8),
            (ResourceType.SILICATES, 0.7),
        ]
    ),
    "Callisto": CelestialBodyData(
        name="Callisto",
        body_type=BodyType.MOON,
        parent="Jupiter",
        semi_major_axis=0.25,  # Scaled up for visibility
        orbital_period=16.69,
        radius=2410,
        color=(120, 100, 80),
        resources=[
            (ResourceType.WATER_ICE, 1.5),
            (ResourceType.IRON_ORE, 0.6),
        ]
    ),
    "Saturn": CelestialBodyData(
        name="Saturn",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=9.537,
        orbital_period=10759,
        radius=58232,
        color=(238, 232, 170),
        resources=[
            (ResourceType.HELIUM3, 1.8),
        ]
    ),
    "Titan": CelestialBodyData(
        name="Titan",
        body_type=BodyType.MOON,
        parent="Saturn",
        semi_major_axis=0.15,  # Scaled up for visibility
        orbital_period=15.95,
        radius=2574,
        color=(255, 180, 100),
        resources=[
            (ResourceType.WATER_ICE, 1.0),
            (ResourceType.HELIUM3, 0.5),
        ]
    ),
    "Enceladus": CelestialBodyData(
        name="Enceladus",
        body_type=BodyType.MOON,
        parent="Saturn",
        semi_major_axis=0.08,  # Scaled up for visibility
        orbital_period=1.37,
        radius=252,
        color=(255, 255, 255),
        resources=[
            (ResourceType.WATER_ICE, 2.5),
        ]
    ),
    "Uranus": CelestialBodyData(
        name="Uranus",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=19.19,
        orbital_period=30687,
        radius=25362,
        color=(173, 216, 230),
        resources=[
            (ResourceType.HELIUM3, 1.5),
        ]
    ),
    "Neptune": CelestialBodyData(
        name="Neptune",
        body_type=BodyType.PLANET,
        parent="Sun",
        semi_major_axis=30.07,
        orbital_period=60190,
        radius=24622,
        color=(100, 149, 237),
        resources=[
            (ResourceType.HELIUM3, 1.5),
        ]
    ),
    "Triton": CelestialBodyData(
        name="Triton",
        body_type=BodyType.MOON,
        parent="Neptune",
        semi_major_axis=0.1,  # Scaled up for visibility
        orbital_period=5.88,
        radius=1353,
        color=(200, 200, 220),
        resources=[
            (ResourceType.WATER_ICE, 2.0),
            (ResourceType.RARE_EARTHS, 0.8),
        ]
    ),

    # Kuiper Belt
    "Pluto": CelestialBodyData(
        name="Pluto",
        body_type=BodyType.DWARF_PLANET,
        parent="Sun",
        semi_major_axis=39.48,
        orbital_period=90560,
        radius=1188,
        color=(200, 180, 160),
        resources=[
            (ResourceType.WATER_ICE, 1.8),
            (ResourceType.RARE_EARTHS, 0.5),
        ]
    ),
}


class SolarSystemData:
    """Accessor for solar system data."""

    @staticmethod
    def get_body(name: str) -> CelestialBodyData | None:
        """Get data for a celestial body by name."""
        return SOLAR_SYSTEM_DATA.get(name)

    @staticmethod
    def get_all_bodies() -> list[CelestialBodyData]:
        """Get all celestial bodies."""
        return list(SOLAR_SYSTEM_DATA.values())

    @staticmethod
    def get_bodies_by_type(body_type: BodyType) -> list[CelestialBodyData]:
        """Get all bodies of a specific type."""
        return [b for b in SOLAR_SYSTEM_DATA.values() if b.body_type == body_type]

    @staticmethod
    def get_moons_of(parent_name: str) -> list[CelestialBodyData]:
        """Get all moons of a parent body."""
        return [
            b for b in SOLAR_SYSTEM_DATA.values()
            if b.parent == parent_name and b.body_type == BodyType.MOON
        ]

    @staticmethod
    def get_bodies_with_resource(resource: ResourceType) -> list[CelestialBodyData]:
        """Get all bodies that have a specific resource."""
        result = []
        for body in SOLAR_SYSTEM_DATA.values():
            for res_type, _ in body.resources:
                if res_type == resource:
                    result.append(body)
                    break
        return result

    @staticmethod
    def get_planetary_system(planet_name: str) -> list[CelestialBodyData]:
        """Get a planet and all its moons as a system.

        Args:
            planet_name: Name of the planet

        Returns:
            List containing the planet and its moons
        """
        result = []
        planet = SOLAR_SYSTEM_DATA.get(planet_name)
        if planet and planet.body_type in (BodyType.PLANET, BodyType.DWARF_PLANET):
            result.append(planet)
            # Add moons
            result.extend(SolarSystemData.get_moons_of(planet_name))
        return result

    @staticmethod
    def get_planetary_system_resources(planet_name: str) -> list[tuple[str, ResourceType, float]]:
        """Get all resources available in a planetary system (planet + moons).

        Args:
            planet_name: Name of the planet

        Returns:
            List of (body_name, resource_type, richness) tuples, sorted by richness
        """
        result = []
        bodies = SolarSystemData.get_planetary_system(planet_name)

        for body in bodies:
            for resource, richness in body.resources:
                result.append((body.name, resource, richness))

        # Sort by richness (highest first)
        result.sort(key=lambda x: x[2], reverse=True)
        return result

    @staticmethod
    def get_nearest_planet(body_name: str) -> str | None:
        """Get the nearest planet for a body (self if planet, parent if moon).

        Args:
            body_name: Name of the body

        Returns:
            Planet name or None
        """
        body = SOLAR_SYSTEM_DATA.get(body_name)
        if not body:
            return None

        if body.body_type in (BodyType.PLANET, BodyType.DWARF_PLANET):
            return body_name
        elif body.body_type == BodyType.MOON:
            return body.parent
        else:
            return None

    @staticmethod
    def is_in_same_system(body1: str, body2: str) -> bool:
        """Check if two bodies are in the same planetary system.

        Args:
            body1: First body name
            body2: Second body name

        Returns:
            True if both are in the same system (same planet or planet+moon)
        """
        planet1 = SolarSystemData.get_nearest_planet(body1)
        planet2 = SolarSystemData.get_nearest_planet(body2)

        if planet1 and planet2:
            return planet1 == planet2
        return False
