"""Individual ship AI behaviors."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID
import math

from ..core.ecs import System, EntityManager, Entity
from ..core.events import EventBus, ShipArrivedEvent
from ..entities.ships import Ship
from ..entities.stations import Station
from ..solar_system.orbits import Position, NavigationTarget
from ..simulation.trade import Trader, TradeState, CargoHold, ManualRoute, notify_ship_arrived
from ..simulation.economy import Market
from ..simulation.resources import Inventory

if TYPE_CHECKING:
    pass


class ShipBehavior(Enum):
    """Ship behavior modes."""
    IDLE = "idle"
    TRADING = "trading"
    MINING = "mining"
    PATROL = "patrol"
    DOCKING = "docking"


@dataclass
class ShipAIState:
    """AI state for a ship."""
    behavior: ShipBehavior = ShipBehavior.IDLE
    target_entity_id: UUID | None = None
    wait_time: float = 0.0  # Time to wait at current location


class ShipAI(System):
    """System that manages individual ship AI."""

    priority = 35  # Run before trade system

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._ai_states: dict[UUID, ShipAIState] = {}

        # Subscribe to arrival events
        self.event_bus.subscribe(ShipArrivedEvent, self._on_ship_arrived)

    def _on_ship_arrived(self, event: ShipArrivedEvent) -> None:
        """Handle ship arrival at destination."""
        if event.ship_id in self._ai_states:
            state = self._ai_states[event.ship_id]
            state.wait_time = 5.0  # Wait 5 seconds at destination

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update ship AI."""
        for entity, ship in entity_manager.get_all_components(Ship):
            # Skip player-controlled ships (for future player interaction)
            if "player_controlled" in entity.tags:
                continue

            if entity.id not in self._ai_states:
                self._ai_states[entity.id] = ShipAIState()

            self._update_ship(entity, ship, entity_manager, dt)

    def _update_ship(
        self,
        ship_entity: Entity,
        ship: Ship,
        entity_manager: EntityManager,
        dt: float
    ) -> None:
        """Update a single ship's AI."""
        state = self._ai_states[ship_entity.id]
        pos = entity_manager.get_component(ship_entity, Position)
        nav = entity_manager.get_component(ship_entity, NavigationTarget)
        trader = entity_manager.get_component(ship_entity, Trader)
        manual_route = entity_manager.get_component(ship_entity, ManualRoute)

        if not pos:
            return

        # Handle waiting
        if state.wait_time > 0:
            state.wait_time -= dt
            return

        # Check if we've arrived at destination
        if nav and nav.has_arrived(pos):
            self._handle_arrival(ship_entity, ship, entity_manager, state)
            # Remove navigation target once arrived
            entity_manager.remove_component(ship_entity, NavigationTarget)

            # If following manual route, advance to next waypoint
            if manual_route and manual_route.waypoints:
                self._handle_manual_route_arrival(ship_entity, manual_route, entity_manager)
            # Handle drone arrival (cargo pickup/delivery)
            elif ship.is_drone:
                self._handle_drone_arrival(ship_entity, ship, entity_manager, state)
            # Notify trader of arrival
            elif trader:
                notify_ship_arrived(trader)
            return

        # If we have a navigation target, we're traveling - no decisions needed
        if nav:
            return

        # Check for manual route first
        if manual_route and manual_route.waypoints:
            self._handle_manual_route(ship_entity, ship, manual_route, entity_manager, state)
        # Drones have special local-only behavior
        elif ship.is_drone:
            self._handle_drone_behavior(ship_entity, ship, entity_manager, state)
        # Otherwise use automatic trading behavior
        elif trader:
            self._handle_trading_behavior(ship_entity, ship, trader, entity_manager, state)
        else:
            self._handle_idle_behavior(ship_entity, ship, entity_manager, state)

    def _handle_arrival(
        self,
        ship_entity: Entity,
        ship: Ship,
        entity_manager: EntityManager,
        state: ShipAIState
    ) -> None:
        """Handle ship arriving at destination."""
        # Fire arrival event
        if state.target_entity_id:
            self.event_bus.publish(ShipArrivedEvent(
                ship_id=ship_entity.id,
                destination_id=state.target_entity_id
            ))

        # Small wait before next action
        state.wait_time = 2.0

    def _handle_manual_route(
        self,
        ship_entity: Entity,
        ship: Ship,
        manual_route: ManualRoute,
        entity_manager: EntityManager,
        state: ShipAIState
    ) -> None:
        """Handle ship following a manual route."""
        waypoint = manual_route.get_current_waypoint()
        if not waypoint:
            return

        # Find the target station
        target = entity_manager.get_entity(waypoint.station_id)
        if not target:
            # Station no longer exists, skip to next waypoint
            manual_route.advance_waypoint()
            return

        target_pos = entity_manager.get_component(target, Position)
        if not target_pos:
            return

        # Navigate to waypoint
        state.target_entity_id = target.id
        entity_manager.add_component(ship_entity, NavigationTarget(
            target_x=target_pos.x,
            target_y=target_pos.y,
            max_speed=ship.max_speed,
            acceleration=ship.acceleration,
        ))

    def _handle_manual_route_arrival(
        self,
        ship_entity: Entity,
        manual_route: ManualRoute,
        entity_manager: EntityManager
    ) -> None:
        """Handle arrival at a manual route waypoint."""
        waypoint = manual_route.get_current_waypoint()
        if not waypoint:
            return

        cargo = entity_manager.get_component(ship_entity, CargoHold)
        if cargo:
            station = entity_manager.get_entity(waypoint.station_id)
            if station:
                station_inv = entity_manager.get_component(station, Inventory)
                station_market = entity_manager.get_component(station, Market)

                # Execute sell order if configured
                if waypoint.sell_resource and station_inv:
                    sell_amount = cargo.get_cargo(waypoint.sell_resource)
                    if sell_amount > 0:
                        removed = cargo.remove_cargo(waypoint.sell_resource, sell_amount)
                        station_inv.add(waypoint.sell_resource, removed)

                # Execute buy order if configured
                if waypoint.buy_resource and station_inv:
                    available = station_inv.get(waypoint.buy_resource)
                    buy_amount = min(available, cargo.free_space)
                    if buy_amount > 0:
                        removed = station_inv.remove(waypoint.buy_resource, buy_amount)
                        cargo.add_cargo(waypoint.buy_resource, removed)

        # Advance to next waypoint
        manual_route.advance_waypoint()

    def _handle_trading_behavior(
        self,
        ship_entity: Entity,
        ship: Ship,
        trader: Trader,
        entity_manager: EntityManager,
        state: ShipAIState
    ) -> None:
        """Handle trading ship behavior."""
        state.behavior = ShipBehavior.TRADING
        pos = entity_manager.get_component(ship_entity, Position)

        if not pos:
            return

        route = trader.current_route

        if not route:
            # No route - handled by TradeSystem
            return

        # Navigate to appropriate destination based on trade state
        if trader.state == TradeState.TRAVELING_TO_BUY:
            target = entity_manager.get_entity(route.source_id)
        elif trader.state == TradeState.TRAVELING_TO_SELL:
            target = entity_manager.get_entity(route.destination_id)
        else:
            return

        if not target:
            return

        target_pos = entity_manager.get_component(target, Position)
        if not target_pos:
            return

        # Set navigation target
        state.target_entity_id = target.id
        entity_manager.add_component(ship_entity, NavigationTarget(
            target_x=target_pos.x,
            target_y=target_pos.y,
            max_speed=ship.max_speed,
            acceleration=ship.acceleration,
        ))

    def _handle_drone_behavior(
        self,
        ship_entity: Entity,
        ship: Ship,
        entity_manager: EntityManager,
        state: ShipAIState
    ) -> None:
        """Handle drone ship behavior - local hauling for home station."""
        from ..solar_system.bodies import SolarSystemData

        state.behavior = ShipBehavior.TRADING
        pos = entity_manager.get_component(ship_entity, Position)
        cargo = entity_manager.get_component(ship_entity, CargoHold)

        if not pos or not cargo:
            return

        # Get home station
        if not ship.home_station_id:
            return

        home_station = entity_manager.get_entity(ship.home_station_id)
        if not home_station:
            return

        home_pos = entity_manager.get_component(home_station, Position)
        home_station_comp = entity_manager.get_component(home_station, Station)
        home_inv = entity_manager.get_component(home_station, Inventory)

        if not home_pos or not home_station_comp or not home_inv:
            return

        # Get what resources the home station's production needs
        from ..simulation.production import get_station_input_resources
        station_type_str = home_station_comp.station_type.value
        needed_input_types = get_station_input_resources(station_type_str)
        needed_resources = []

        for resource in needed_input_types:
            current = home_inv.get(resource)
            if current < 20:  # Need more if below threshold
                needed_resources.append(resource)

        # If cargo is not empty, deliver to home station
        if not cargo.is_empty:
            # Navigate to home station to deliver
            state.target_entity_id = home_station.id
            entity_manager.add_component(ship_entity, NavigationTarget(
                target_x=home_pos.x,
                target_y=home_pos.y,
                max_speed=ship.max_speed,
                acceleration=ship.acceleration,
            ))
            return

        # If we need resources, find a local station that has them
        if needed_resources:
            best_source = None
            best_dist = float('inf')
            best_resource = None

            for entity, station in entity_manager.get_all_components(Station):
                # Skip home station
                if entity.id == home_station.id:
                    continue

                # Only consider stations in same planetary system
                station_body = station.parent_body
                if ship.local_system:
                    station_planet = SolarSystemData.get_nearest_planet(station_body)
                    if station_planet != ship.local_system:
                        continue

                # Check if this station has resources we need
                station_inv = entity_manager.get_component(entity, Inventory)
                station_pos = entity_manager.get_component(entity, Position)

                if not station_inv or not station_pos:
                    continue

                for resource in needed_resources:
                    available = station_inv.get(resource)
                    if available > 5:  # Has enough to share
                        dist = pos.distance_to(station_pos)
                        if dist < best_dist:
                            best_dist = dist
                            best_source = entity
                            best_resource = resource

            if best_source:
                source_pos = entity_manager.get_component(best_source, Position)
                if source_pos:
                    state.target_entity_id = best_source.id
                    entity_manager.add_component(ship_entity, NavigationTarget(
                        target_x=source_pos.x,
                        target_y=source_pos.y,
                        max_speed=ship.max_speed,
                        acceleration=ship.acceleration,
                    ))
                    return

        # Nothing to do - hang around home station
        dist_to_home = pos.distance_to(home_pos)
        if dist_to_home > 0.05:
            state.target_entity_id = home_station.id
            entity_manager.add_component(ship_entity, NavigationTarget(
                target_x=home_pos.x,
                target_y=home_pos.y,
                max_speed=ship.max_speed,
                acceleration=ship.acceleration,
            ))

    def _handle_drone_arrival(
        self,
        ship_entity: Entity,
        ship: Ship,
        entity_manager: EntityManager,
        state: ShipAIState
    ) -> None:
        """Handle drone arriving at a station - pickup or deliver cargo."""
        cargo = entity_manager.get_component(ship_entity, CargoHold)
        if not cargo:
            return

        # Get the station we arrived at
        if not state.target_entity_id:
            return

        target_station = entity_manager.get_entity(state.target_entity_id)
        if not target_station:
            return

        target_inv = entity_manager.get_component(target_station, Inventory)
        if not target_inv:
            return

        # Check if this is our home station
        is_home = state.target_entity_id == ship.home_station_id

        if is_home:
            # Deliver all cargo to home station
            for resource, amount in list(cargo.cargo.items()):
                if amount > 0:
                    delivered = cargo.remove_cargo(resource, amount)
                    target_inv.add(resource, delivered)
        else:
            # Pick up resources from this station
            # Get what the home station needs
            if ship.home_station_id:
                home_station = entity_manager.get_entity(ship.home_station_id)
                if home_station:
                    home_comp = entity_manager.get_component(home_station, Station)
                    home_inv = entity_manager.get_component(home_station, Inventory)

                    if home_comp and home_inv:
                        from ..simulation.production import get_station_input_resources
                        station_type_str = home_comp.station_type.value
                        needed_resources = get_station_input_resources(station_type_str)

                        # Pick up resources the home station needs
                        for resource in needed_resources:
                            available = target_inv.get(resource)
                            space = cargo.free_space
                            # Take up to half of what's available or fill cargo
                            take_amount = min(available * 0.5, space, 10)
                            if take_amount > 1:
                                taken = target_inv.remove(resource, take_amount)
                                cargo.add_cargo(resource, taken)

        # Small wait before next action
        state.wait_time = 3.0

    def _handle_idle_behavior(
        self,
        ship_entity: Entity,
        ship: Ship,
        entity_manager: EntityManager,
        state: ShipAIState
    ) -> None:
        """Handle idle ship behavior."""
        state.behavior = ShipBehavior.IDLE
        pos = entity_manager.get_component(ship_entity, Position)

        if not pos:
            return

        # Find nearest station to hang around
        nearest_station: Entity | None = None
        nearest_dist = float('inf')

        for entity, station in entity_manager.get_all_components(Station):
            station_pos = entity_manager.get_component(entity, Position)
            if not station_pos:
                continue

            dist = pos.distance_to(station_pos)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_station = entity

        if nearest_station and nearest_dist > 0.05:  # If not already near a station
            station_pos = entity_manager.get_component(nearest_station, Position)
            if station_pos:
                state.target_entity_id = nearest_station.id
                entity_manager.add_component(ship_entity, NavigationTarget(
                    target_x=station_pos.x,
                    target_y=station_pos.y,
                    max_speed=ship.max_speed,
                    acceleration=ship.acceleration,
                ))


def find_nearest_station(
    entity_manager: EntityManager,
    position: Position
) -> tuple[Entity, float] | None:
    """Find the nearest station to a position.

    Args:
        entity_manager: Entity manager
        position: Current position

    Returns:
        Tuple of (station entity, distance) or None
    """
    nearest: tuple[Entity, float] | None = None

    for entity, station in entity_manager.get_all_components(Station):
        station_pos = entity_manager.get_component(entity, Position)
        if not station_pos:
            continue

        dist = position.distance_to(station_pos)
        if nearest is None or dist < nearest[1]:
            nearest = (entity, dist)

    return nearest


def find_stations_with_resource(
    entity_manager: EntityManager,
    resource,
    selling: bool = True
) -> list[tuple[Entity, float]]:
    """Find stations selling/buying a specific resource.

    Args:
        entity_manager: Entity manager
        resource: Resource type to find
        selling: If True, find sellers; if False, find buyers

    Returns:
        List of (station entity, price) tuples
    """
    results: list[tuple[Entity, float]] = []

    for entity, market in entity_manager.get_all_components(Market):
        if selling:
            price = market.get_sell_price(resource)
        else:
            price = market.get_buy_price(resource)

        if price is not None:
            results.append((entity, price))

    # Sort by price (ascending for buying, descending for selling)
    results.sort(key=lambda x: x[1], reverse=selling)
    return results
