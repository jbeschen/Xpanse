"""Building system for station construction."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import System, EntityManager
from ..core.events import EventBus
from ..entities.stations import (
    Station, StationType, STATION_CONFIGS,
    create_station, create_mining_station
)
from ..entities.factions import Faction
from ..solar_system.orbits import Position
from ..simulation.resources import ResourceType

if TYPE_CHECKING:
    from ..core.world import World


# Station costs (credits)
STATION_COSTS: dict[StationType, float] = {
    StationType.OUTPOST: 5000,
    StationType.MINING_STATION: 10000,
    StationType.REFINERY: 20000,
    StationType.FACTORY: 50000,
    StationType.COLONY: 100000,
    StationType.SHIPYARD: 75000,
    StationType.TRADE_HUB: 200000,
}

# Minimum distance between stations in AU
MIN_STATION_DISTANCE = 0.1


@dataclass
class BuildRequest:
    """A request to build a station."""
    faction_id: UUID
    station_type: StationType
    position: tuple[float, float]
    parent_body: str
    resource_type: ResourceType | None = None  # For mining stations


@dataclass
class BuildResult:
    """Result of a build attempt."""
    success: bool
    message: str
    station_id: UUID | None = None


class BuildingSystem(System):
    """System that processes station construction requests."""

    priority = 55  # Run after economy, before faction AI

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._pending_builds: list[BuildRequest] = []

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Process pending build requests."""
        # Building is processed via direct calls, not in update loop
        pass

    def request_build(
        self,
        world: "World",
        faction_id: UUID,
        station_type: StationType,
        position: tuple[float, float],
        parent_body: str = "",
        resource_type: ResourceType | None = None,
    ) -> BuildResult:
        """Request to build a new station.

        Args:
            world: The game world
            faction_id: ID of the faction requesting the build
            station_type: Type of station to build
            position: (x, y) position in AU
            parent_body: Name of celestial body to orbit
            resource_type: Resource to mine (for mining stations)

        Returns:
            BuildResult indicating success/failure
        """
        em = world.entity_manager

        # Find faction entity and get credits
        faction_entity = None
        faction_comp = None
        for entity, faction in em.get_all_components(Faction):
            if entity.id == faction_id:
                faction_entity = entity
                faction_comp = faction
                break

        if not faction_comp:
            return BuildResult(False, "Faction not found")

        # Check cost
        cost = STATION_COSTS.get(station_type, 0)
        if faction_comp.credits < cost:
            return BuildResult(
                False,
                f"Insufficient credits: need {cost:.0f}, have {faction_comp.credits:.0f}"
            )

        # Check distance from other stations
        valid, msg = self._validate_position(position, em)
        if not valid:
            return BuildResult(False, msg)

        # Deduct credits
        faction_comp.credits -= cost

        # Create the station
        station_name = self._generate_station_name(station_type, parent_body, faction_entity.name)

        if station_type == StationType.MINING_STATION and resource_type:
            station_entity = create_mining_station(
                world=world,
                name=station_name,
                position=position,
                parent_body=parent_body,
                resource_type=resource_type,
                owner_faction_id=faction_id,
            )
        else:
            station_entity = create_station(
                world=world,
                name=station_name,
                station_type=station_type,
                position=position,
                parent_body=parent_body,
                owner_faction_id=faction_id,
            )

        # Fire event
        from ..core.events import StationBuiltEvent
        self.event_bus.publish(StationBuiltEvent(
            station_id=station_entity.id,
            faction_id=faction_id,
            station_type=station_type,
            position=position,
            cost=cost,
        ))

        return BuildResult(
            True,
            f"Built {station_type.value} for {cost:.0f} credits",
            station_entity.id
        )

    def _validate_position(
        self,
        position: tuple[float, float],
        entity_manager: EntityManager
    ) -> tuple[bool, str]:
        """Validate a building position.

        Args:
            position: (x, y) position to validate
            entity_manager: Entity manager

        Returns:
            (valid, message) tuple
        """
        px, py = position

        # Check distance from all existing stations
        for entity, station in entity_manager.get_all_components(Station):
            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            dx = pos.x - px
            dy = pos.y - py
            distance = math.sqrt(dx * dx + dy * dy)

            if distance < MIN_STATION_DISTANCE:
                return False, f"Too close to {entity.name} ({distance:.3f} AU, minimum {MIN_STATION_DISTANCE} AU)"

        return True, "Valid position"

    def _generate_station_name(
        self,
        station_type: StationType,
        parent_body: str,
        faction_name: str
    ) -> str:
        """Generate a name for a new station."""
        type_names = {
            StationType.OUTPOST: "Outpost",
            StationType.MINING_STATION: "Mining Station",
            StationType.REFINERY: "Refinery",
            StationType.FACTORY: "Factory",
            StationType.COLONY: "Colony",
            StationType.SHIPYARD: "Shipyard",
            StationType.TRADE_HUB: "Trade Hub",
        }

        type_name = type_names.get(station_type, "Station")

        if parent_body:
            return f"{parent_body} {type_name}"
        else:
            # Use faction name abbreviation
            abbrev = "".join(word[0] for word in faction_name.split()[:2])
            return f"{abbrev} {type_name}"

    def can_afford(self, faction: Faction, station_type: StationType) -> bool:
        """Check if a faction can afford to build a station type."""
        return faction.credits >= STATION_COSTS.get(station_type, float('inf'))

    def get_cost(self, station_type: StationType) -> float:
        """Get the cost of a station type."""
        return STATION_COSTS.get(station_type, 0)

    def find_nearest_body(
        self,
        position: tuple[float, float],
        entity_manager: EntityManager,
    ) -> tuple[str, float]:
        """Find the nearest celestial body to a position.

        Args:
            position: (x, y) position in AU
            entity_manager: Entity manager

        Returns:
            (body_name, distance) tuple
        """
        from ..entities.celestial import CelestialBody

        px, py = position
        nearest_name = ""
        nearest_dist = float('inf')

        for entity, body in entity_manager.get_all_components(CelestialBody):
            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            dx = pos.x - px
            dy = pos.y - py
            distance = math.sqrt(dx * dx + dy * dy)

            if distance < nearest_dist:
                nearest_dist = distance
                nearest_name = entity.name

        return nearest_name, nearest_dist

    def get_body_resources(
        self,
        body_name: str,
        entity_manager: EntityManager,
    ) -> list[tuple[ResourceType, float]]:
        """Get resources available at a celestial body.

        Args:
            body_name: Name of the body
            entity_manager: Entity manager

        Returns:
            List of (resource_type, richness) tuples
        """
        from ..solar_system.bodies import SOLAR_SYSTEM_DATA

        body_data = SOLAR_SYSTEM_DATA.get(body_name)
        if body_data:
            return body_data.resources
        return []
