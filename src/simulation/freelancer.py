"""Freelancer spawning system - spawns traders when cargo needs moving."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, System, EntityManager
from ..core.events import EventBus
from ..entities.ships import create_ship, ShipType, Ship
from ..entities.stations import Station
from ..solar_system.orbits import Position, ParentBody
from .resources import ResourceType, Inventory
from .economy import Market
from .trade import Trader, TradeState

if TYPE_CHECKING:
    from ..core.world import World


@dataclass
class FreelancerManager(Component):
    """Singleton component tracking Freelancer spawning state."""
    freelancer_faction_id: UUID | None = None
    max_freelancers: int = 10  # Cap on total freelancer ships
    spawn_cooldown: float = 0.0  # Time until next spawn allowed
    spawn_interval: float = 5.0  # Minimum seconds between spawns (game time)

    # Thresholds for spawning
    inventory_threshold: float = 0.5  # Spawn if station > 50% full
    min_cargo_to_move: float = 50.0  # Minimum cargo amount to trigger spawn


class FreelancerSpawner(System):
    """System that spawns Freelancer ships when cargo needs moving.

    Monitors stations for excess inventory (resources piling up with no buyers).
    When a station is getting full, spawns a Freelancer to buy and redistribute.
    """

    priority = 75  # Run after goals, before rendering

    def __init__(self, event_bus: EventBus, world: "World") -> None:
        self.event_bus = event_bus
        self._world = world
        self._check_interval = 3.0  # Check every 3 game days
        self._time_since_check = 0.0

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Check for cargo that needs moving and spawn Freelancers."""
        self._time_since_check += dt

        if self._time_since_check < self._check_interval:
            return

        self._time_since_check = 0.0

        # Get FreelancerManager
        manager = None
        for entity, mgr in entity_manager.get_all_components(FreelancerManager):
            manager = mgr
            break

        if not manager or not manager.freelancer_faction_id:
            return

        # Update cooldown
        if manager.spawn_cooldown > 0:
            manager.spawn_cooldown -= self._check_interval
            return

        # Count existing freelancer ships
        freelancer_count = self._count_freelancer_ships(manager.freelancer_faction_id, entity_manager)
        if freelancer_count >= manager.max_freelancers:
            return

        # Find stations with excess cargo
        station_with_cargo = self._find_station_needing_pickup(manager, entity_manager)
        if not station_with_cargo:
            return

        station_entity, resource_type, amount = station_with_cargo

        # Check if there's already a freelancer heading to this station
        if self._freelancer_targeting_station(station_entity.id, manager.freelancer_faction_id, entity_manager):
            return

        # Spawn a Freelancer to handle this cargo
        self._spawn_freelancer(
            station_entity,
            resource_type,
            manager.freelancer_faction_id,
            entity_manager
        )

        # Set cooldown
        manager.spawn_cooldown = manager.spawn_interval

    def _count_freelancer_ships(self, faction_id: UUID, entity_manager: EntityManager) -> int:
        """Count ships owned by the Freelancer faction."""
        count = 0
        for entity, ship in entity_manager.get_all_components(Ship):
            if ship.owner_faction_id == faction_id:
                count += 1
        return count

    def _find_station_needing_pickup(
        self,
        manager: FreelancerManager,
        entity_manager: EntityManager
    ) -> tuple | None:
        """Find a station with excess cargo that needs pickup.

        Returns:
            (station_entity, resource_type, amount) or None
        """
        best_station = None
        best_resource = None
        best_amount = 0.0

        for entity, station in entity_manager.get_all_components(Station):
            inventory = entity_manager.get_component(entity, Inventory)
            market = entity_manager.get_component(entity, Market)

            if not inventory or not market:
                continue

            # Check if inventory is getting full
            fill_ratio = inventory.total_amount / inventory.capacity
            if fill_ratio < manager.inventory_threshold:
                continue

            # Find the resource with the most excess
            for resource, amount in inventory.resources.items():
                if amount < manager.min_cargo_to_move:
                    continue

                # Prefer resources that the station is selling (has excess of)
                sell_price = market.get_sell_price(resource)
                if sell_price is None:
                    continue

                # Weight by amount and how full the station is
                score = amount * fill_ratio
                if score > best_amount:
                    best_station = entity
                    best_resource = resource
                    best_amount = amount

        if best_station:
            return (best_station, best_resource, best_amount)
        return None

    def _freelancer_targeting_station(
        self,
        station_id: UUID,
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> bool:
        """Check if a freelancer is already heading to this station."""
        for entity, trader in entity_manager.get_all_components(Trader):
            ship = entity_manager.get_component(entity, Ship)
            if not ship or ship.owner_faction_id != faction_id:
                continue

            if trader.current_route:
                if trader.current_route.source_id == station_id:
                    return True

        return False

    def _spawn_freelancer(
        self,
        target_station,
        resource_type: ResourceType,
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> None:
        """Spawn a Freelancer ship to pick up cargo."""
        # Find spawn location - prefer shipyard, otherwise Earth
        spawn_pos = self._find_spawn_location(entity_manager)
        if not spawn_pos:
            return

        # Generate unique name
        freelancer_count = self._count_freelancer_ships(faction_id, entity_manager)
        ship_name = f"Freelancer Hauler {freelancer_count + 1}"

        # Create the ship
        ship = create_ship(
            world=self._world,
            name=ship_name,
            ship_type=ShipType.FREIGHTER,
            position=spawn_pos,
            owner_faction_id=faction_id,
            is_trader=True,
        )

        # The ship's AI will automatically find profitable trades
        # which should include the station we identified

    def _find_spawn_location(self, entity_manager: EntityManager) -> tuple[float, float] | None:
        """Find where to spawn a Freelancer (shipyard or Earth)."""
        # First, try to find Earth Public Shipyard
        for entity, station in entity_manager.get_all_components(Station):
            if entity.name == "Earth Public Shipyard":
                pos = entity_manager.get_component(entity, Position)
                if pos:
                    return (pos.x + 0.02, pos.y + 0.02)

        # Fall back to Earth position
        for entity in entity_manager.get_entities_with(Position):
            if entity.name == "Earth":
                pos = entity_manager.get_component(entity, Position)
                if pos:
                    return (pos.x + 0.05, pos.y + 0.05)

        # Last resort - spawn at (1.0, 0.1)
        return (1.0, 0.1)
