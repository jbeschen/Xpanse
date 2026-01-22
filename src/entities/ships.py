"""Ship entities (cargo ships, mining ships)."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, Entity
from ..core.world import World
from ..solar_system.orbits import Position, Velocity, NavigationTarget
from ..simulation.trade import Trader, CargoHold

if TYPE_CHECKING:
    pass


class ShipType(Enum):
    """Types of ships."""
    SHUTTLE = "shuttle"  # Small, fast, low cargo
    FREIGHTER = "freighter"  # Medium cargo hauler
    TANKER = "tanker"  # Bulk liquid transport
    BULK_HAULER = "bulk_hauler"  # Large cargo capacity
    MINING_SHIP = "mining_ship"  # Can mine asteroids
    DRONE = "drone"  # Automated local hauler, very small capacity


@dataclass
class Ship(Component):
    """Component identifying a ship."""
    ship_type: ShipType = ShipType.FREIGHTER
    owner_faction_id: UUID | None = None
    max_speed: float = 2.5  # AU per day
    acceleration: float = 0.6  # AU per day per day
    fuel_capacity: float = 100.0
    fuel: float = 100.0
    fuel_consumption: float = 0.1  # Per AU traveled
    crew: int = 5
    max_crew: int = 10
    hull_integrity: float = 1.0  # 0-1
    # Drone-specific fields
    is_drone: bool = False  # If true, restricted to local system
    home_station_id: UUID | None = None  # Station this drone serves
    local_system: str = ""  # Planet name this drone is restricted to


@dataclass
class ShipState(Component):
    """Component for ship AI state (used by ShipAISystemV2).

    Stores the current behavior and state for the ship's AI.
    This is separate from Ship to allow the AI system to manage
    state independently.
    """
    behavior_name: str = "patrol"  # Current behavior strategy name
    sub_state: str = "idle"  # Behavior-specific sub-state
    state_data: dict = field(default_factory=dict)  # Behavior-specific data
    wait_time: float = 0.0  # Time remaining before next AI update
    target_entity_id: UUID | None = None  # Current navigation target


# Ship type configurations
# X-Drive Era: Speeds in AU per day - 1 second = 1 day
# Earth to Jupiter (~4.2 AU) should take 30-60 seconds for freighters
# Speed ~0.10 AU/day = ~42 day trip = 42 seconds real-time
SHIP_CONFIGS: dict[ShipType, dict] = {
    ShipType.SHUTTLE: {
        "cargo_capacity": 50,
        "max_speed": 0.15,  # Fast courier - Jupiter in ~28 days
        "acceleration": 0.05,  # Quick to accelerate
        "fuel_capacity": 50,
        "fuel_consumption": 0.05,
        "max_crew": 4,
    },
    ShipType.FREIGHTER: {
        "cargo_capacity": 200,
        "max_speed": 0.10,  # Standard hauler - Jupiter in ~42 days
        "acceleration": 0.03,
        "fuel_capacity": 100,
        "fuel_consumption": 0.1,
        "max_crew": 10,
    },
    ShipType.TANKER: {
        "cargo_capacity": 500,
        "max_speed": 0.07,  # Heavy - Jupiter in ~60 days
        "acceleration": 0.02,
        "fuel_capacity": 150,
        "fuel_consumption": 0.15,
        "max_crew": 8,
    },
    ShipType.BULK_HAULER: {
        "cargo_capacity": 1000,
        "max_speed": 0.05,  # Slowest - Jupiter in ~84 days
        "acceleration": 0.015,
        "fuel_capacity": 200,
        "fuel_consumption": 0.2,
        "max_crew": 15,
    },
    ShipType.MINING_SHIP: {
        "cargo_capacity": 300,
        "max_speed": 0.08,  # Decent - Jupiter in ~52 days
        "acceleration": 0.025,
        "fuel_capacity": 120,
        "fuel_consumption": 0.12,
        "max_crew": 12,
    },
    ShipType.DRONE: {
        "cargo_capacity": 20,  # Very small capacity
        "max_speed": 0.12,  # Fast for local work
        "acceleration": 0.08,  # Quick to accelerate
        "fuel_capacity": 30,
        "fuel_consumption": 0.02,  # Efficient
        "max_crew": 0,  # Automated
    },
}


def create_ship(
    world: World,
    name: str,
    ship_type: ShipType,
    position: tuple[float, float],
    owner_faction_id: UUID | None = None,
    is_trader: bool = True,
) -> Entity:
    """Create a ship entity.

    Args:
        world: The game world
        name: Ship name
        ship_type: Type of ship
        position: (x, y) position in AU
        owner_faction_id: Owning faction ID
        is_trader: Whether ship should have AI trading behavior

    Returns:
        The created entity
    """
    config = SHIP_CONFIGS[ship_type]

    # Create entity
    tags = {"ship", ship_type.value}
    if is_trader:
        tags.add("trader")
    if owner_faction_id:
        tags.add("owned")

    entity = world.create_entity(name=name, tags=tags)
    em = world.entity_manager

    # Add ship component
    em.add_component(entity, Ship(
        ship_type=ship_type,
        owner_faction_id=owner_faction_id,
        max_speed=config["max_speed"],
        acceleration=config["acceleration"],
        fuel_capacity=config["fuel_capacity"],
        fuel=config["fuel_capacity"],  # Start with full fuel
        fuel_consumption=config["fuel_consumption"],
        max_crew=config["max_crew"],
        crew=config["max_crew"] // 2,  # Start half crewed
    ))

    # Add position and velocity
    em.add_component(entity, Position(x=position[0], y=position[1]))
    em.add_component(entity, Velocity(vx=0.0, vy=0.0))

    # Add cargo hold
    em.add_component(entity, CargoHold(capacity=config["cargo_capacity"]))

    # Add trader component if this is a trading ship
    if is_trader:
        em.add_component(entity, Trader(
            min_profit_threshold=5.0,
        ))

    return entity


def create_drone(
    world: World,
    name: str,
    position: tuple[float, float],
    owner_faction_id: UUID,
    home_station_id: UUID,
    local_system: str,
) -> Entity:
    """Create a drone (automated local hauler).

    Args:
        world: The game world
        name: Drone name
        position: (x, y) position in AU
        owner_faction_id: Owning faction ID
        home_station_id: Station this drone serves
        local_system: Planet name this drone is restricted to

    Returns:
        The created entity
    """
    config = SHIP_CONFIGS[ShipType.DRONE]

    # Create entity with drone tag
    tags = {"ship", "drone", "owned"}
    entity = world.create_entity(name=name, tags=tags)
    em = world.entity_manager

    # Add ship component with drone settings
    em.add_component(entity, Ship(
        ship_type=ShipType.DRONE,
        owner_faction_id=owner_faction_id,
        max_speed=config["max_speed"],
        acceleration=config["acceleration"],
        fuel_capacity=config["fuel_capacity"],
        fuel=config["fuel_capacity"],
        fuel_consumption=config["fuel_consumption"],
        max_crew=0,
        crew=0,
        is_drone=True,
        home_station_id=home_station_id,
        local_system=local_system,
    ))

    # Add position and velocity
    em.add_component(entity, Position(x=position[0], y=position[1]))
    em.add_component(entity, Velocity(vx=0.0, vy=0.0))

    # Add small cargo hold
    em.add_component(entity, CargoHold(capacity=config["cargo_capacity"]))

    # Drones have trader component for hauling
    em.add_component(entity, Trader(
        min_profit_threshold=0.0,  # Drones don't care about profit
    ))

    return entity


def set_ship_destination(
    world: World,
    ship_entity: Entity,
    destination: tuple[float, float],
    target_body: str = "",
) -> None:
    """Set a ship's navigation destination.

    Args:
        world: The game world
        ship_entity: The ship entity
        destination: (x, y) target position in AU
        target_body: Optional name of celestial body to track (for predictive navigation)
    """
    em = world.entity_manager
    ship = em.get_component(ship_entity, Ship)

    if not ship:
        return

    # Add or update navigation target
    nav = em.get_component(ship_entity, NavigationTarget)
    if nav:
        nav.target_x = destination[0]
        nav.target_y = destination[1]
        nav.target_body_name = target_body
        nav.max_speed = ship.max_speed
        nav.acceleration = ship.acceleration
        # Don't reset current_speed - let ship maintain momentum if already moving
    else:
        em.add_component(ship_entity, NavigationTarget(
            target_x=destination[0],
            target_y=destination[1],
            target_body_name=target_body,
            max_speed=ship.max_speed,
            acceleration=ship.acceleration,
            current_speed=0.0,  # Start from rest
        ))


def set_ship_destination_body(
    world: World,
    ship_entity: Entity,
    target_body_name: str,
) -> None:
    """Set a ship's navigation destination to a celestial body with predictive tracking.

    The ship will track the body's movement and intercept it.

    Args:
        world: The game world
        ship_entity: The ship entity
        target_body_name: Name of the celestial body to navigate to
    """
    em = world.entity_manager
    ship = em.get_component(ship_entity, Ship)

    if not ship:
        return

    # Find the target body's current position
    from .celestial import CelestialBody
    from ..solar_system.orbits import Position

    target_pos = None
    for entity, _ in em.get_all_components(CelestialBody):
        if entity.name == target_body_name:
            pos = em.get_component(entity, Position)
            if pos:
                target_pos = (pos.x, pos.y)
            break

    if not target_pos:
        return  # Body not found

    # Set destination with body tracking
    set_ship_destination(world, ship_entity, target_pos, target_body=target_body_name)


def get_ship_at_position(
    world: World,
    position: tuple[float, float],
    radius: float = 0.01,
) -> Entity | None:
    """Find a ship near a position.

    Args:
        world: The game world
        position: (x, y) position to check
        radius: Search radius in AU

    Returns:
        Ship entity if found, None otherwise
    """
    em = world.entity_manager

    for entity in em.get_entities_with_tag("ship"):
        pos = em.get_component(entity, Position)
        if not pos:
            continue

        dx = pos.x - position[0]
        dy = pos.y - position[1]
        dist_sq = dx * dx + dy * dy

        if dist_sq <= radius * radius:
            return entity

    return None
