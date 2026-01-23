"""Station entities (outposts, colonies, factories)."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, Entity
from ..core.world import World
from ..solar_system.orbits import Position, ParentBody
from ..simulation.resources import ResourceType, Inventory
from ..simulation.economy import Market, MarketType, Population
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

    # Minimum inventory reserves - prevents auto-trading below these levels
    # Key: ResourceType, Value: minimum amount to keep
    min_reserves: dict = field(default_factory=dict)

    def get_available_for_trade(self, resource: ResourceType, current_amount: float) -> float:
        """Get amount available for auto-trading (respects min_reserves)."""
        min_keep = self.min_reserves.get(resource, 0.0)
        return max(0.0, current_amount - min_keep)

    def set_min_reserve(self, resource: ResourceType, amount: float) -> None:
        """Set minimum reserve for a resource."""
        if amount > 0:
            self.min_reserves[resource] = amount
        elif resource in self.min_reserves:
            del self.min_reserves[resource]


# Station type configurations
STATION_CONFIGS: dict[StationType, dict] = {
    StationType.OUTPOST: {
        "capacity": 500,
        "recipes": [],
        "buys": [ResourceType.WATER, ResourceType.FUEL],
        "sells": [],
        "credits": 5000,
        "market_type": MarketType.STATION,
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
        "market_type": MarketType.MINING,
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
        "market_type": MarketType.STATION,
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
        "market_type": MarketType.STATION,
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
        "market_type": MarketType.COLONY,  # Higher prices for frontier colonies
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
        "market_type": MarketType.STATION,
    },
    StationType.TRADE_HUB: {
        "capacity": 20000,
        "recipes": [],
        "buys": list(ResourceType),  # Buys everything
        "sells": list(ResourceType),  # Sells everything
        "credits": 200000,
        "market_type": MarketType.STATION,
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
    resource_type: ResourceType | None = None,
    auto_name: bool = False,
) -> Entity:
    """Create a station entity.

    Args:
        world: The game world
        name: Station name (or base name if auto_name=True)
        station_type: Type of station
        position: (x, y) position in AU
        parent_body: Name of parent celestial body
        owner_faction_id: Owning faction ID
        initial_resources: Starting inventory
        resource_type: Resource being mined/processed (for naming)
        auto_name: If True, generate a sci-fi name automatically

    Returns:
        The created entity
    """
    from .station_slots import (
        OrbitalSlotManager, get_slot_offset, generate_unique_station_name,
        MAX_STATIONS_PER_BODY
    )

    config = STATION_CONFIGS[station_type]
    em = world.entity_manager

    # Get or create slot manager
    slot_manager = None
    for _, sm in em.get_all_components(OrbitalSlotManager):
        slot_manager = sm
        break

    # Determine orbital slot
    slot_index = 0
    if parent_body and slot_manager:
        next_slot = slot_manager.get_next_available_slot(parent_body)
        if next_slot is None:
            # Body is full, cannot create station
            return None
        slot_index = next_slot

    # Generate name if auto_name is requested
    if auto_name:
        # Collect existing station names
        existing_names = set()
        for existing_entity, _ in em.get_all_components(Station):
            existing_names.add(existing_entity.name)

        resource_str = resource_type.value if resource_type else None
        name = generate_unique_station_name(
            station_type, parent_body or "Deep Space",
            existing_names, resource_str, slot_index
        )

    # Create entity
    tags = {"station", station_type.value}
    if owner_faction_id:
        tags.add("owned")

    entity = world.create_entity(name=name, tags=tags)

    # Add station component
    em.add_component(entity, Station(
        station_type=station_type,
        parent_body=parent_body,
        owner_faction_id=owner_faction_id,
    ))

    # Add position (will be updated by OrbitalSystem if parent_body is set)
    em.add_component(entity, Position(x=position[0], y=position[1]))

    # Add parent body relationship using orbital slot system
    if parent_body:
        # Get offset from slot system
        offset_x, offset_y = get_slot_offset(slot_index)

        em.add_component(entity, ParentBody(
            parent_name=parent_body,
            offset_x=offset_x,
            offset_y=offset_y,
        ))

        # Register the slot as occupied
        if slot_manager:
            slot_manager.occupy_slot(parent_body, slot_index, entity.id)

    # Add inventory
    inventory = Inventory(capacity=config["capacity"])
    if initial_resources:
        for resource, amount in initial_resources.items():
            inventory.add(resource, amount)
    em.add_component(entity, inventory)

    # Add market
    market_type = config.get("market_type", MarketType.STATION)
    market = Market(
        credits=config["credits"],
        market_type=market_type,
    )

    # Set up what this station buys/sells
    for resource in config["buys"]:
        market.buys[resource] = True
        market.target_stock[resource] = config["capacity"] / 10

    for resource in config["sells"]:
        market.sells[resource] = True
        market.target_stock[resource] = config["capacity"] / 5

    em.add_component(entity, market)

    # Add population for colonies
    if station_type == StationType.COLONY:
        em.add_component(entity, Population(
            population=10.0,  # Start with 10k population
            max_population=1000.0,
            growth_rate=0.01,
            credits_per_pop=10.0,
        ))

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
        The created entity, or None if creation failed (e.g., body full)
    """
    entity = create_station(
        world=world,
        name=name,
        station_type=StationType.MINING_STATION,
        position=position,
        parent_body=parent_body,
        owner_faction_id=owner_faction_id,
        resource_type=resource_type,
    )

    # Check if station creation failed (body might be full)
    if entity is None:
        return None

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


def create_earth_market(
    world: World,
    position: tuple[float, float],
    owner_faction_id: UUID | None = None,
) -> Entity:
    """Create Earth as a major consumer hub with large population and market.

    Earth has:
    - Large population generating constant demand
    - Lower prices due to competition (MarketType.EARTH)
    - Buys all processed and finished goods
    - High credits for purchasing

    Args:
        world: The game world
        position: Earth's position in AU
        owner_faction_id: Earth Coalition faction ID

    Returns:
        The created entity
    """
    # Create entity
    tags = {"station", "earth_market", "population_center"}
    if owner_faction_id:
        tags.add("owned")

    entity = world.create_entity(name="Earth Market", tags=tags)
    em = world.entity_manager

    # Add station component
    em.add_component(entity, Station(
        station_type=StationType.TRADE_HUB,
        parent_body="Earth",
        owner_faction_id=owner_faction_id,
    ))

    # Add position locked to Earth
    em.add_component(entity, Position(x=position[0], y=position[1]))
    em.add_component(entity, ParentBody(
        parent_name="Earth",
        offset_x=0.01,
        offset_y=0.01,
    ))

    # Large inventory capacity
    inventory = Inventory(capacity=100000)
    # Start with some resources for initial trades
    inventory.add(ResourceType.FUEL, 500)
    inventory.add(ResourceType.WATER, 500)
    em.add_component(entity, inventory)

    # Earth market - low prices due to competition
    market = Market(
        credits=10000000,  # 10 million credits
        market_type=MarketType.EARTH,
    )

    # Earth buys all processed goods (Tier 1+)
    earth_buys = [
        # Tier 1 - Basic materials
        ResourceType.REFINED_METAL,
        ResourceType.SILICON,
        ResourceType.WATER,
        ResourceType.FUEL,
        # Tier 2 - Components
        ResourceType.ELECTRONICS,
        ResourceType.MACHINERY,
        ResourceType.LIFE_SUPPORT,
        # Tier 3 - Complex goods
        ResourceType.HABITAT_MODULES,
        ResourceType.SHIP_COMPONENTS,
        ResourceType.ADVANCED_TECH,
    ]

    for resource in earth_buys:
        market.buys[resource] = True
        market.target_stock[resource] = 10000  # High demand

    # Earth also sells fuel and water (for ships)
    market.sells[ResourceType.FUEL] = True
    market.sells[ResourceType.WATER] = True
    market.target_stock[ResourceType.FUEL] = 1000
    market.target_stock[ResourceType.WATER] = 1000

    em.add_component(entity, market)

    # Large population - creates constant demand
    em.add_component(entity, Population(
        population=10000.0,  # 10 billion people (in thousands)
        max_population=50000.0,
        growth_rate=0.001,  # Slow growth - mature population
        credits_per_pop=5.0,  # Lower per-capita but huge volume
        consumption={
            ResourceType.LIFE_SUPPORT: 0.5,
            ResourceType.WATER: 0.2,
            ResourceType.ELECTRONICS: 0.1,
            ResourceType.MACHINERY: 0.05,
        },
    ))

    # Register Earth market with slot manager so new builds don't overlap
    from .station_slots import OrbitalSlotManager
    for _, slot_mgr in em.get_all_components(OrbitalSlotManager):
        slot_mgr.occupy_slot("Earth", 0, entity.id)
        break

    return entity
