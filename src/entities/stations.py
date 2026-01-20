"""Station entities (outposts, colonies, factories)."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, Entity
from ..core.world import World
from ..solar_system.orbits import Position
from ..simulation.resources import ResourceType, Inventory
from ..simulation.economy import Market
from ..simulation.production import Producer, Extractor, RECIPES

if TYPE_CHECKING:
    pass


class StationType(Enum):
    """Types of stations."""
    OUTPOST = "outpost"  # Basic presence, minimal facilities
    MINING_STATION = "mining_station"  # Extracts raw resources
    REFINERY = "refinery"  # Processes raw -> basic materials
    FACTORY = "factory"  # Manufactures components
    COLONY = "colony"  # Population center, consumes goods
    SHIPYARD = "shipyard"  # Builds ships
    TRADE_HUB = "trade_hub"  # Major trading post


@dataclass
class Station(Component):
    """Component identifying a station."""
    station_type: StationType = StationType.OUTPOST
    parent_body: str = ""  # Name of celestial body it orbits
    owner_faction_id: UUID | None = None
    population: int = 0
    max_population: int = 100
    morale: float = 1.0  # 0-1, affects productivity


# Station type configurations
STATION_CONFIGS: dict[StationType, dict] = {
    StationType.OUTPOST: {
        "capacity": 500,
        "recipes": [],
        "buys": [ResourceType.WATER, ResourceType.FUEL],
        "sells": [],
        "credits": 5000,
    },
    StationType.MINING_STATION: {
        "capacity": 2000,
        "recipes": [],  # Uses extractor instead
        "buys": [ResourceType.FUEL, ResourceType.MACHINERY],
        "sells": [
            ResourceType.WATER_ICE, ResourceType.IRON_ORE,
            ResourceType.SILICATES, ResourceType.RARE_EARTHS, ResourceType.HELIUM3
        ],
        "credits": 10000,
    },
    StationType.REFINERY: {
        "capacity": 3000,
        "recipes": ["refine_metal", "process_silicon", "purify_water", "produce_fuel"],
        "buys": [
            ResourceType.WATER_ICE, ResourceType.IRON_ORE,
            ResourceType.SILICATES, ResourceType.HELIUM3
        ],
        "sells": [
            ResourceType.REFINED_METAL, ResourceType.SILICON,
            ResourceType.WATER, ResourceType.FUEL
        ],
        "credits": 20000,
    },
    StationType.FACTORY: {
        "capacity": 4000,
        "recipes": ["manufacture_electronics", "manufacture_machinery", "manufacture_life_support"],
        "buys": [
            ResourceType.REFINED_METAL, ResourceType.SILICON,
            ResourceType.RARE_EARTHS, ResourceType.WATER, ResourceType.ELECTRONICS
        ],
        "sells": [
            ResourceType.ELECTRONICS, ResourceType.MACHINERY, ResourceType.LIFE_SUPPORT
        ],
        "credits": 50000,
    },
    StationType.COLONY: {
        "capacity": 10000,
        "recipes": [],
        "buys": [
            ResourceType.WATER, ResourceType.LIFE_SUPPORT,
            ResourceType.HABITAT_MODULES, ResourceType.ELECTRONICS
        ],
        "sells": [],  # Colonies consume but produce services/labor
        "credits": 100000,
    },
    StationType.SHIPYARD: {
        "capacity": 5000,
        "recipes": ["build_ship_components"],
        "buys": [
            ResourceType.REFINED_METAL, ResourceType.ELECTRONICS,
            ResourceType.MACHINERY
        ],
        "sells": [ResourceType.SHIP_COMPONENTS],
        "credits": 75000,
    },
    StationType.TRADE_HUB: {
        "capacity": 20000,
        "recipes": [],
        "buys": list(ResourceType),  # Buys everything
        "sells": list(ResourceType),  # Sells everything
        "credits": 200000,
    },
}


def create_station(
    world: World,
    name: str,
    station_type: StationType,
    position: tuple[float, float],
    parent_body: str = "",
    owner_faction_id: UUID | None = None,
    initial_resources: dict[ResourceType, float] | None = None,
) -> Entity:
    """Create a station entity.

    Args:
        world: The game world
        name: Station name
        station_type: Type of station
        position: (x, y) position in AU
        parent_body: Name of parent celestial body
        owner_faction_id: Owning faction ID
        initial_resources: Starting inventory

    Returns:
        The created entity
    """
    config = STATION_CONFIGS[station_type]

    # Create entity
    tags = {"station", station_type.value}
    if owner_faction_id:
        tags.add("owned")

    entity = world.create_entity(name=name, tags=tags)
    em = world.entity_manager

    # Add station component
    em.add_component(entity, Station(
        station_type=station_type,
        parent_body=parent_body,
        owner_faction_id=owner_faction_id,
    ))

    # Add position
    em.add_component(entity, Position(x=position[0], y=position[1]))

    # Add inventory
    inventory = Inventory(capacity=config["capacity"])
    if initial_resources:
        for resource, amount in initial_resources.items():
            inventory.add(resource, amount)
    em.add_component(entity, inventory)

    # Add market
    market = Market(credits=config["credits"])

    # Set up what this station buys/sells
    for resource in config["buys"]:
        market.buys[resource] = True
        market.target_stock[resource] = config["capacity"] / 10

    for resource in config["sells"]:
        market.sells[resource] = True
        market.target_stock[resource] = config["capacity"] / 5

    em.add_component(entity, market)

    # Add producer if station has recipes
    if config["recipes"]:
        em.add_component(entity, Producer(
            recipes=config["recipes"],
            auto_produce=True,
        ))

    return entity


def create_mining_station(
    world: World,
    name: str,
    position: tuple[float, float],
    parent_body: str,
    resource_type: ResourceType,
    owner_faction_id: UUID | None = None,
) -> Entity:
    """Create a mining station that extracts a specific resource.

    Args:
        world: The game world
        name: Station name
        position: (x, y) position in AU
        parent_body: Name of celestial body being mined
        resource_type: Resource to extract
        owner_faction_id: Owning faction ID

    Returns:
        The created entity
    """
    entity = create_station(
        world=world,
        name=name,
        station_type=StationType.MINING_STATION,
        position=position,
        parent_body=parent_body,
        owner_faction_id=owner_faction_id,
    )

    em = world.entity_manager

    # Add extractor component
    from ..simulation.resources import ResourceDeposit

    em.add_component(entity, Extractor(
        extraction_rate=5.0,  # Units per second
        efficiency=1.0,
        active=True,
    ))

    # Add a virtual resource deposit (the actual deposit is on the celestial body)
    em.add_component(entity, ResourceDeposit(
        resource_type=resource_type,
        richness=1.0,
        remaining=float('inf'),  # Mining stations don't deplete
    ))

    return entity
