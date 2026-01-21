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

# Station material requirements (tier 2+ stations need materials)
# Tier 1 (basic): just credits
# Tier 2 (intermediate): credits + tier 1 processed materials
# Tier 3 (advanced): credits + tier 2 advanced materials
STATION_MATERIAL_COSTS: dict[StationType, dict[ResourceType, float]] = {
    # Tier 1 - no materials required
    StationType.OUTPOST: {},
    StationType.MINING_STATION: {},

    # Tier 2 - requires tier 1 processed materials
    StationType.REFINERY: {
        ResourceType.REFINED_METAL: 50,
        ResourceType.SILICON: 20,
    },
    StationType.FACTORY: {
        ResourceType.REFINED_METAL: 100,
        ResourceType.ELECTRONICS: 20,
    },

    # Tier 3 - requires tier 2 advanced materials
    StationType.COLONY: {
        ResourceType.MACHINERY: 50,
        ResourceType.LIFE_SUPPORT: 100,
        ResourceType.ELECTRONICS: 50,
    },
    StationType.SHIPYARD: {
        ResourceType.MACHINERY: 100,
        ResourceType.ELECTRONICS: 50,
        ResourceType.REFINED_METAL: 200,
    },
    StationType.TRADE_HUB: {
        ResourceType.ELECTRONICS: 100,
        ResourceType.MACHINERY: 50,
        ResourceType.LIFE_SUPPORT: 50,
    },
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
        from ..simulation.resources import Inventory

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

        # Check credit cost
        cost = STATION_COSTS.get(station_type, 0)
        if faction_comp.credits < cost:
            return BuildResult(
                False,
                f"Insufficient credits: need {cost:.0f}, have {faction_comp.credits:.0f}"
            )

        # Check material requirements
        material_reqs = STATION_MATERIAL_COSTS.get(station_type, {})
        if material_reqs:
            # Get all faction's station inventories
            faction_inventories = self._get_faction_inventories(faction_id, em)

            # Check if faction has enough materials across all stations
            missing = self._check_material_availability(material_reqs, faction_inventories)
            if missing:
                missing_str = ", ".join(f"{r.value}: {a:.0f}" for r, a in missing.items())
                return BuildResult(False, f"Missing materials: {missing_str}")

        # Check distance from other stations
        valid, msg = self._validate_position(position, em)
        if not valid:
            return BuildResult(False, msg)

        # Deduct credits
        faction_comp.credits -= cost

        # Deduct materials from faction's stations
        if material_reqs:
            self._consume_materials(material_reqs, faction_inventories)

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

        # Build message with materials
        if material_reqs:
            mat_str = ", ".join(f"{r.value}: {a:.0f}" for r, a in material_reqs.items())
            return BuildResult(
                True,
                f"Built {station_type.value} for {cost:.0f} credits + {mat_str}",
                station_entity.id
            )

        return BuildResult(
            True,
            f"Built {station_type.value} for {cost:.0f} credits",
            station_entity.id
        )

    def _get_faction_inventories(
        self,
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> list:
        """Get all inventories at faction-owned stations.

        Returns:
            List of Inventory components
        """
        from ..simulation.resources import Inventory

        inventories = []
        for entity, station in entity_manager.get_all_components(Station):
            if station.owner_faction_id == faction_id:
                inv = entity_manager.get_component(entity, Inventory)
                if inv:
                    inventories.append(inv)
        return inventories

    def _check_material_availability(
        self,
        requirements: dict[ResourceType, float],
        inventories: list
    ) -> dict[ResourceType, float]:
        """Check if materials are available across inventories.

        Returns:
            Dict of missing resources and amounts (empty if all available)
        """
        # Sum up available resources across all inventories
        available: dict[ResourceType, float] = {}
        for inv in inventories:
            for resource, amount in inv.resources.items():
                available[resource] = available.get(resource, 0) + amount

        # Check what's missing
        missing: dict[ResourceType, float] = {}
        for resource, needed in requirements.items():
            have = available.get(resource, 0)
            if have < needed:
                missing[resource] = needed - have

        return missing

    def _consume_materials(
        self,
        requirements: dict[ResourceType, float],
        inventories: list
    ) -> None:
        """Consume materials from faction inventories."""
        for resource, needed in requirements.items():
            remaining = needed
            for inv in inventories:
                if remaining <= 0:
                    break
                available = inv.get(resource)
                if available > 0:
                    take = min(available, remaining)
                    inv.remove(resource, take)
                    remaining -= take

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

    def can_afford(
        self,
        faction: Faction,
        station_type: StationType,
        entity_manager: EntityManager | None = None,
        faction_id: UUID | None = None
    ) -> bool:
        """Check if a faction can afford to build a station type.

        Args:
            faction: Faction component
            station_type: Type of station to build
            entity_manager: Entity manager (needed for material checks)
            faction_id: Faction ID (needed for material checks)

        Returns:
            True if faction can afford both credits and materials
        """
        # Check credits
        if faction.credits < STATION_COSTS.get(station_type, float('inf')):
            return False

        # Check materials if entity_manager provided
        material_reqs = STATION_MATERIAL_COSTS.get(station_type, {})
        if material_reqs and entity_manager and faction_id:
            inventories = self._get_faction_inventories(faction_id, entity_manager)
            missing = self._check_material_availability(material_reqs, inventories)
            if missing:
                return False

        return True

    def get_cost(self, station_type: StationType) -> float:
        """Get the credit cost of a station type."""
        return STATION_COSTS.get(station_type, 0)

    def get_material_cost(self, station_type: StationType) -> dict[ResourceType, float]:
        """Get the material requirements for a station type."""
        return STATION_MATERIAL_COSTS.get(station_type, {})

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
