"""Building system for station construction and ship purchasing."""
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
from ..entities.ships import Ship, ShipType, create_ship, create_drone, SHIP_CONFIGS
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

# Station material requirements - each tier only needs materials from LOWER tiers
# Production chain: Mining → Refinery → Factory → Advanced stations
#
# Tier 0 (Raw): Iron Ore, Silicates, Water Ice, Rare Earths, Helium-3
# Tier 1 (Basic): Refined Metal, Silicon, Water, Fuel (made by Refinery)
# Tier 2 (Advanced): Electronics, Machinery, Life Support (made by Factory)
#
STATION_MATERIAL_COSTS: dict[StationType, dict[ResourceType, float]] = {
    # Bootstrap tier - credits only (needed to start the production chain)
    StationType.OUTPOST: {},
    StationType.MINING_STATION: {},

    # Tier 1 stations - need RAW materials (from Mining Stations)
    StationType.REFINERY: {
        ResourceType.IRON_ORE: 100,
        ResourceType.SILICATES: 50,
    },

    # Tier 2 stations - need BASIC materials (from Refineries)
    StationType.FACTORY: {
        ResourceType.REFINED_METAL: 100,
        ResourceType.SILICON: 50,
    },

    # Tier 3 stations - need ADVANCED materials (from Factories)
    StationType.COLONY: {
        ResourceType.ELECTRONICS: 50,
        ResourceType.MACHINERY: 30,
        ResourceType.LIFE_SUPPORT: 50,
    },
    StationType.SHIPYARD: {
        ResourceType.REFINED_METAL: 100,
        ResourceType.ELECTRONICS: 50,
        ResourceType.MACHINERY: 50,
    },
    StationType.TRADE_HUB: {
        ResourceType.ELECTRONICS: 100,
        ResourceType.MACHINERY: 50,
        ResourceType.REFINED_METAL: 100,
    },
}

# Maximum distance from ship to allow building
MAX_BUILD_DISTANCE = 0.15  # AU

# Station upgrade paths: what each station type can upgrade to
STATION_UPGRADES: dict[StationType, list[StationType]] = {
    StationType.OUTPOST: [
        StationType.MINING_STATION,
        StationType.REFINERY,
        StationType.COLONY,
    ],
    StationType.MINING_STATION: [
        StationType.REFINERY,
    ],
    StationType.REFINERY: [
        StationType.FACTORY,
    ],
    StationType.FACTORY: [
        StationType.SHIPYARD,
        StationType.TRADE_HUB,
    ],
    StationType.COLONY: [
        StationType.TRADE_HUB,
    ],
    StationType.SHIPYARD: [],  # No upgrades
    StationType.TRADE_HUB: [],  # No upgrades
}

# Upgrade costs (percentage of full build cost)
UPGRADE_COST_MULTIPLIER = 0.6  # Upgrades cost 60% of full station price


# Ship costs (credits)
SHIP_COSTS: dict[ShipType, float] = {
    ShipType.SHUTTLE: 5000,
    ShipType.FREIGHTER: 15000,
    ShipType.TANKER: 25000,
    ShipType.BULK_HAULER: 50000,
    ShipType.MINING_SHIP: 30000,
}

# Ship material requirements
SHIP_MATERIAL_COSTS: dict[ShipType, dict[ResourceType, float]] = {
    ShipType.SHUTTLE: {
        ResourceType.REFINED_METAL: 20,
    },
    ShipType.FREIGHTER: {
        ResourceType.REFINED_METAL: 50,
        ResourceType.ELECTRONICS: 10,
    },
    ShipType.TANKER: {
        ResourceType.REFINED_METAL: 80,
        ResourceType.ELECTRONICS: 15,
    },
    ShipType.BULK_HAULER: {
        ResourceType.REFINED_METAL: 150,
        ResourceType.ELECTRONICS: 30,
        ResourceType.MACHINERY: 20,
    },
    ShipType.MINING_SHIP: {
        ResourceType.REFINED_METAL: 60,
        ResourceType.ELECTRONICS: 20,
        ResourceType.MACHINERY: 30,
    },
}


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

        # Check for nearby ship owned by faction
        ship_nearby, ship_msg = self._check_ship_nearby(position, faction_id, em)
        if not ship_nearby:
            return BuildResult(False, ship_msg)

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

        # Spawn a drone for refineries and higher-tier stations
        # These automated haulers help get the station operational
        drone_stations = {
            StationType.REFINERY,
            StationType.FACTORY,
            StationType.COLONY,
            StationType.SHIPYARD,
            StationType.TRADE_HUB,
        }
        if station_type in drone_stations:
            # Find the planetary system this station is in
            from ..solar_system.bodies import SolarSystemData
            local_system = SolarSystemData.get_nearest_planet(parent_body) or parent_body

            # Get faction name for drone naming
            faction_name = faction_entity.name if faction_entity else "Unknown"
            drone_name = f"{faction_name} Drone"

            # Spawn drone slightly offset from station
            drone_pos = (position[0] + 0.01, position[1] + 0.01)
            create_drone(
                world=world,
                name=drone_name,
                position=drone_pos,
                owner_faction_id=faction_id,
                home_station_id=station_entity.id,
                local_system=local_system,
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
        # Stations can be built anywhere - they will be organized as menu items under planetary bodies
        return True, "Valid position"

    def _check_ship_nearby(
        self,
        position: tuple[float, float],
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> tuple[bool, str]:
        """Check if a faction-owned ship is near the build position.

        Args:
            position: (x, y) position to check
            faction_id: Faction ID that must own the ship
            entity_manager: Entity manager

        Returns:
            (valid, message) tuple
        """
        px, py = position

        for entity, ship in entity_manager.get_all_components(Ship):
            # Check if ship belongs to faction
            if ship.owner_faction_id != faction_id:
                continue

            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            dx = pos.x - px
            dy = pos.y - py
            distance = math.sqrt(dx * dx + dy * dy)

            if distance <= MAX_BUILD_DISTANCE:
                return True, f"Ship {entity.name} is nearby"

        return False, f"No ship nearby - send a ship to this location first (within {MAX_BUILD_DISTANCE} AU)"

    def find_nearest_faction_ship(
        self,
        position: tuple[float, float],
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> tuple[str | None, float]:
        """Find the nearest faction-owned ship to a position.

        Args:
            position: (x, y) position in AU
            faction_id: Faction to check
            entity_manager: Entity manager

        Returns:
            (ship_name, distance) tuple, or (None, inf) if no ships
        """
        px, py = position
        nearest_name = None
        nearest_dist = float('inf')

        for entity, ship in entity_manager.get_all_components(Ship):
            if ship.owner_faction_id != faction_id:
                continue

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

    def purchase_ship(
        self,
        world: "World",
        faction_id: UUID,
        ship_type: ShipType,
        shipyard_id: UUID,
    ) -> BuildResult:
        """Purchase a ship from a shipyard.

        Args:
            world: The game world
            faction_id: ID of the faction purchasing
            ship_type: Type of ship to purchase
            shipyard_id: ID of the shipyard to build at

        Returns:
            BuildResult indicating success/failure
        """
        from ..simulation.resources import Inventory

        em = world.entity_manager

        # Find faction
        faction_entity = None
        faction_comp = None
        for entity, faction in em.get_all_components(Faction):
            if entity.id == faction_id:
                faction_entity = entity
                faction_comp = faction
                break

        if not faction_comp:
            return BuildResult(False, "Faction not found")

        # Find shipyard and verify it's owned by faction
        shipyard_entity = em.get_entity(shipyard_id)
        if not shipyard_entity:
            return BuildResult(False, "Shipyard not found")

        station = em.get_component(shipyard_entity, Station)
        if not station or station.station_type != StationType.SHIPYARD:
            return BuildResult(False, "Not a shipyard")

        if station.owner_faction_id != faction_id:
            return BuildResult(False, "You don't own this shipyard")

        # Check credit cost
        cost = SHIP_COSTS.get(ship_type, 0)
        if faction_comp.credits < cost:
            return BuildResult(
                False,
                f"Insufficient credits: need {cost:.0f}, have {faction_comp.credits:.0f}"
            )

        # Check material requirements
        material_reqs = SHIP_MATERIAL_COSTS.get(ship_type, {})
        if material_reqs:
            faction_inventories = self._get_faction_inventories(faction_id, em)
            missing = self._check_material_availability(material_reqs, faction_inventories)
            if missing:
                missing_str = ", ".join(f"{r.value}: {a:.0f}" for r, a in missing.items())
                return BuildResult(False, f"Missing materials: {missing_str}")

        # Get shipyard position for ship spawn
        shipyard_pos = em.get_component(shipyard_entity, Position)
        if not shipyard_pos:
            return BuildResult(False, "Shipyard has no position")

        # Deduct credits
        faction_comp.credits -= cost

        # Deduct materials
        if material_reqs:
            faction_inventories = self._get_faction_inventories(faction_id, em)
            self._consume_materials(material_reqs, faction_inventories)

        # Create ship near shipyard
        ship_position = (shipyard_pos.x + 0.02, shipyard_pos.y + 0.02)
        ship_name = f"{faction_entity.name} {ship_type.value.replace('_', ' ').title()}"

        ship_entity = create_ship(
            world=world,
            name=ship_name,
            ship_type=ship_type,
            position=ship_position,
            owner_faction_id=faction_id,
            is_trader=True,
        )

        # Fire event
        from ..core.events import ShipPurchasedEvent
        self.event_bus.publish(ShipPurchasedEvent(
            ship_id=ship_entity.id,
            faction_id=faction_id,
            ship_type=ship_type.value,
            shipyard_id=shipyard_id,
            cost=cost,
        ))

        if material_reqs:
            mat_str = ", ".join(f"{r.value}: {a:.0f}" for r, a in material_reqs.items())
            return BuildResult(
                True,
                f"Purchased {ship_type.value} for {cost:.0f} credits + {mat_str}",
                ship_entity.id
            )

        return BuildResult(
            True,
            f"Purchased {ship_type.value} for {cost:.0f} credits",
            ship_entity.id
        )

    def get_ship_cost(self, ship_type: ShipType) -> float:
        """Get the credit cost of a ship type."""
        return SHIP_COSTS.get(ship_type, 0)

    def get_ship_material_cost(self, ship_type: ShipType) -> dict[ResourceType, float]:
        """Get the material requirements for a ship type."""
        return SHIP_MATERIAL_COSTS.get(ship_type, {})

    def get_available_upgrades(self, station_type: StationType) -> list[StationType]:
        """Get list of station types this station can upgrade to."""
        return STATION_UPGRADES.get(station_type, [])

    def get_upgrade_cost(self, target_type: StationType) -> float:
        """Get the credit cost to upgrade to a station type."""
        base_cost = STATION_COSTS.get(target_type, 0)
        return base_cost * UPGRADE_COST_MULTIPLIER

    def get_upgrade_material_cost(self, target_type: StationType) -> dict[ResourceType, float]:
        """Get the material cost to upgrade to a station type (same as building)."""
        return STATION_MATERIAL_COSTS.get(target_type, {})

    def upgrade_station(
        self,
        world: "World",
        faction_id: UUID,
        station_id: UUID,
        target_type: StationType,
    ) -> BuildResult:
        """Upgrade a station to a new type.

        Args:
            world: The game world
            faction_id: ID of the faction requesting the upgrade
            station_id: ID of the station to upgrade
            target_type: Station type to upgrade to

        Returns:
            BuildResult indicating success/failure
        """
        from ..simulation.resources import Inventory
        from ..core.events import StationBuiltEvent

        em = world.entity_manager

        # Find faction
        faction_entity = None
        faction_comp = None
        for entity, faction in em.get_all_components(Faction):
            if entity.id == faction_id:
                faction_entity = entity
                faction_comp = faction
                break

        if not faction_comp:
            return BuildResult(False, "Faction not found")

        # Find station
        station_entity = em.get_entity(station_id)
        if not station_entity:
            return BuildResult(False, "Station not found")

        station = em.get_component(station_entity, Station)
        if not station:
            return BuildResult(False, "Not a station")

        # Verify ownership
        if station.owner_faction_id != faction_id:
            return BuildResult(False, "You don't own this station")

        # Check if upgrade is valid
        available_upgrades = self.get_available_upgrades(station.station_type)
        if target_type not in available_upgrades:
            return BuildResult(
                False,
                f"Cannot upgrade {station.station_type.value} to {target_type.value}"
            )

        # Check credits
        cost = self.get_upgrade_cost(target_type)
        if faction_comp.credits < cost:
            return BuildResult(
                False,
                f"Insufficient credits: need {cost:.0f}, have {faction_comp.credits:.0f}"
            )

        # Check materials
        material_reqs = self.get_upgrade_material_cost(target_type)
        if material_reqs:
            faction_inventories = self._get_faction_inventories(faction_id, em)
            missing = self._check_material_availability(material_reqs, faction_inventories)
            if missing:
                missing_str = ", ".join(f"{r.value}: {a:.0f}" for r, a in missing.items())
                return BuildResult(False, f"Missing materials: {missing_str}")

        # Deduct credits
        faction_comp.credits -= cost

        # Deduct materials
        if material_reqs:
            faction_inventories = self._get_faction_inventories(faction_id, em)
            self._consume_materials(material_reqs, faction_inventories)

        # Update station type
        old_type = station.station_type
        station.station_type = target_type

        # Update station name
        station_pos = em.get_component(station_entity, Position)
        if station_pos:
            body_name, _ = self.find_nearest_body((station_pos.x, station_pos.y), em)
            station_entity.name = self._generate_station_name(target_type, body_name, faction_entity.name)

        # Update config values for new station type
        config = STATION_CONFIGS.get(target_type)
        if config:
            station.production_multiplier = config.get("production_multiplier", 1.0)
            station.storage_capacity = config.get("storage_capacity", 1000)

            # Update inventory capacity
            inv = em.get_component(station_entity, Inventory)
            if inv:
                inv.capacity = station.storage_capacity

        # Fire event
        self.event_bus.publish(StationBuiltEvent(
            station_id=station_id,
            faction_id=faction_id,
            station_type=target_type.value,
            position=(station_pos.x, station_pos.y) if station_pos else (0, 0),
            cost=cost,
        ))

        if material_reqs:
            mat_str = ", ".join(f"{r.value}: {a:.0f}" for r, a in material_reqs.items())
            return BuildResult(
                True,
                f"Upgraded {old_type.value} to {target_type.value} for {cost:.0f} credits + {mat_str}",
                station_id
            )

        return BuildResult(
            True,
            f"Upgraded {old_type.value} to {target_type.value} for {cost:.0f} credits",
            station_id
        )

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
