"""Drone behavior for local cargo transfer.

Drones orbit their home station and transfer cargo between
nearby stations in the same planetary system.
"""
from __future__ import annotations
import math
import random
from uuid import UUID

from .base import ShipBehavior, BehaviorContext, BehaviorResult, BehaviorStatus


class DroneState:
    """State constants for drone behavior."""
    IDLE = "idle"
    TRAVELING_TO_PICKUP = "traveling_to_pickup"
    PICKING_UP = "picking_up"
    TRAVELING_TO_DELIVER = "traveling_to_deliver"
    DELIVERING = "delivering"
    PATROLLING = "patrolling"


class DroneBehavior(ShipBehavior):
    """Behavior for automated cargo drones.

    Drones are restricted to local systems (single planetary area).
    They transfer resources between stations to support production.
    When idle, they patrol around their home station.
    """

    def __init__(self) -> None:
        self.patrol_radius = 0.05  # AU
        self.max_pickup_distance = 0.1  # AU - max distance for pickups

    @property
    def name(self) -> str:
        return "Drone"

    def on_enter(self, ctx: BehaviorContext) -> None:
        """Initialize drone state."""
        ctx.state_data["drone_state"] = DroneState.IDLE
        ctx.state_data["pickup_station_id"] = None
        ctx.state_data["pickup_resource"] = None

    def update(self, ctx: BehaviorContext) -> BehaviorResult:
        """Update drone behavior."""
        from ...simulation.trade import CargoHold
        from ...simulation.resources import Inventory
        from ...entities.stations import Station

        state = ctx.state_data.get("drone_state", DroneState.IDLE)
        cargo = ctx.get_component(CargoHold)

        if not cargo:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="No cargo hold"
            )

        # Get home station
        home_station_id = ctx.ship.home_station_id
        if not home_station_id:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="No home station"
            )

        home_station = ctx.get_entity(home_station_id)
        if not home_station:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="Home station not found"
            )

        # State machine
        if state == DroneState.IDLE:
            # Check if we have cargo to deliver
            if not cargo.is_empty:
                ctx.state_data["drone_state"] = DroneState.TRAVELING_TO_DELIVER
                return self._navigate_to_station(ctx, home_station_id)

            # Look for resources to pick up
            pickup = self._find_pickup_target(ctx, home_station)
            if pickup:
                station_id, resource = pickup
                ctx.state_data["pickup_station_id"] = station_id
                ctx.state_data["pickup_resource"] = resource
                ctx.state_data["drone_state"] = DroneState.TRAVELING_TO_PICKUP
                return self._navigate_to_station(ctx, station_id)

            # Nothing to do - patrol
            ctx.state_data["drone_state"] = DroneState.PATROLLING
            return self._patrol_around_home(ctx, home_station)

        elif state == DroneState.TRAVELING_TO_PICKUP:
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        elif state == DroneState.PICKING_UP:
            success = self._execute_pickup(ctx, cargo)
            if success:
                ctx.state_data["drone_state"] = DroneState.TRAVELING_TO_DELIVER
                return self._navigate_to_station(ctx, home_station_id)
            else:
                ctx.state_data["drone_state"] = DroneState.IDLE
                return BehaviorResult(
                    status=BehaviorStatus.RUNNING,
                    wait_time=2.0,
                    message="Pickup failed"
                )

        elif state == DroneState.TRAVELING_TO_DELIVER:
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        elif state == DroneState.DELIVERING:
            self._execute_delivery(ctx, cargo, home_station)
            ctx.state_data["drone_state"] = DroneState.IDLE
            return BehaviorResult(
                status=BehaviorStatus.SUCCESS,
                wait_time=1.5,
                message="Delivery complete"
            )

        elif state == DroneState.PATROLLING:
            # Check if patrol complete or if new work available
            pickup = self._find_pickup_target(ctx, home_station)
            if pickup:
                ctx.state_data["drone_state"] = DroneState.IDLE
                return BehaviorResult(
                    status=BehaviorStatus.RUNNING,
                    message="Found pickup target"
                )
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        return BehaviorResult(status=BehaviorStatus.RUNNING)

    def on_arrival(self, ctx: BehaviorContext, destination_id: UUID | None) -> BehaviorResult:
        """Handle arrival at destination."""
        state = ctx.state_data.get("drone_state", DroneState.IDLE)

        if state == DroneState.TRAVELING_TO_PICKUP:
            ctx.state_data["drone_state"] = DroneState.PICKING_UP
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                wait_time=1.0,
                message="Arrived at pickup"
            )

        elif state == DroneState.TRAVELING_TO_DELIVER:
            ctx.state_data["drone_state"] = DroneState.DELIVERING
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                wait_time=1.0,
                message="Arrived at home station"
            )

        elif state == DroneState.PATROLLING:
            # Continue patrolling
            home_station = ctx.get_entity(ctx.ship.home_station_id) if ctx.ship.home_station_id else None
            if home_station:
                return self._patrol_around_home(ctx, home_station)
            ctx.state_data["drone_state"] = DroneState.IDLE

        return BehaviorResult(status=BehaviorStatus.RUNNING, wait_time=0.5)

    def _find_pickup_target(self, ctx: BehaviorContext, home_station) -> tuple | None:
        """Find a station with resources needed by home station.

        Returns: (station_id, resource_type) or None
        """
        from ...simulation.production import get_station_input_resources
        from ...simulation.resources import Inventory
        from ...entities.stations import Station
        from ...solar_system.orbits import Position
        from ...solar_system.bodies import SolarSystemData

        home_station_comp = ctx.entity_manager.get_component(home_station, Station)
        home_inv = ctx.entity_manager.get_component(home_station, Inventory)

        if not home_station_comp or not home_inv:
            return None

        # Get what resources home station needs
        station_type_str = home_station_comp.station_type.value
        needed_input_types = get_station_input_resources(station_type_str)

        # Find resources that are low
        needed_resources = []
        for resource in needed_input_types:
            current = home_inv.get(resource)
            if current < 20:  # Need more if below threshold
                needed_resources.append(resource)

        if not needed_resources:
            return None

        # Find nearby station with these resources
        best_source = None
        best_dist = float('inf')
        best_resource = None

        for entity, station in ctx.entity_manager.get_all_components(Station):
            # Skip home station
            if entity.id == home_station.id:
                continue

            # Only consider stations in same planetary system
            if ctx.ship.local_system:
                station_planet = SolarSystemData.get_nearest_planet(station.parent_body)
                if station_planet != ctx.ship.local_system:
                    continue

            # Check distance
            station_pos = ctx.entity_manager.get_component(entity, Position)
            if not station_pos:
                continue

            dist = ctx.position.distance_to(station_pos)
            if dist > self.max_pickup_distance:
                continue

            # Check if has resources we need
            station_inv = ctx.entity_manager.get_component(entity, Inventory)
            if not station_inv:
                continue

            for resource in needed_resources:
                available = station_inv.get(resource)
                if available > 5:  # Has enough to share
                    if dist < best_dist:
                        best_dist = dist
                        best_source = entity
                        best_resource = resource

        if best_source:
            return (best_source.id, best_resource)
        return None

    def _execute_pickup(self, ctx: BehaviorContext, cargo) -> bool:
        """Pick up resources from target station."""
        from ...simulation.resources import Inventory

        station_id = ctx.state_data.get("pickup_station_id")
        resource = ctx.state_data.get("pickup_resource")

        if not station_id or not resource:
            return False

        station = ctx.get_entity(station_id)
        if not station:
            return False

        station_inv = ctx.entity_manager.get_component(station, Inventory)
        if not station_inv:
            return False

        available = station_inv.get(resource)
        space = cargo.free_space

        # Take up to half available or fill cargo, max 10 units
        take_amount = min(available * 0.5, space, 10)

        if take_amount < 1:
            return False

        taken = station_inv.remove(resource, take_amount)
        cargo.add_cargo(resource, taken)

        return True

    def _execute_delivery(self, ctx: BehaviorContext, cargo, home_station) -> None:
        """Deliver cargo to home station."""
        from ...simulation.resources import Inventory

        home_inv = ctx.entity_manager.get_component(home_station, Inventory)
        if not home_inv:
            return

        # Deliver all cargo
        for resource, amount in list(cargo.cargo.items()):
            if amount > 0:
                delivered = cargo.remove_cargo(resource, amount)
                home_inv.add(resource, delivered)

    def _navigate_to_station(self, ctx: BehaviorContext, station_id: UUID) -> BehaviorResult:
        """Create navigation result for a station."""
        from ...solar_system.orbits import Position
        from ...entities.stations import Station

        station = ctx.get_entity(station_id)
        if not station:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message=f"Station {station_id} not found"
            )

        pos = ctx.entity_manager.get_component(station, Position)
        station_comp = ctx.entity_manager.get_component(station, Station)

        if not pos:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="Station has no position"
            )

        target_body = station_comp.parent_body if station_comp else ""

        return BehaviorResult(
            status=BehaviorStatus.RUNNING,
            target_x=pos.x,
            target_y=pos.y,
            target_body=target_body,
            target_entity_id=station_id,
        )

    def _patrol_around_home(self, ctx: BehaviorContext, home_station) -> BehaviorResult:
        """Generate patrol waypoint around home station."""
        from ...solar_system.orbits import Position
        from ...entities.stations import Station

        home_pos = ctx.entity_manager.get_component(home_station, Position)
        home_comp = ctx.entity_manager.get_component(home_station, Station)

        if not home_pos:
            return BehaviorResult(status=BehaviorStatus.FAILURE)

        # Check distance to home
        dist_to_home = ctx.position.distance_to(home_pos)

        if dist_to_home > self.patrol_radius * 1.5:
            # Too far - return home
            target_body = home_comp.parent_body if home_comp else ""
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                target_x=home_pos.x,
                target_y=home_pos.y,
                target_body=target_body,
                target_entity_id=home_station.id,
            )

        # Random patrol waypoint
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(self.patrol_radius * 0.4, self.patrol_radius)
        patrol_x = home_pos.x + dist * math.cos(angle)
        patrol_y = home_pos.y + dist * math.sin(angle)

        target_body = home_comp.parent_body if home_comp else ""

        return BehaviorResult(
            status=BehaviorStatus.RUNNING,
            target_x=patrol_x,
            target_y=patrol_y,
            target_body=target_body,
            speed_multiplier=0.3,  # Slow patrol
            wait_time=0.5,
        )

    def can_activate(self, ctx: BehaviorContext) -> bool:
        """Drones must have a home station."""
        return ctx.ship.is_drone and ctx.ship.home_station_id is not None

    def get_priority(self, ctx: BehaviorContext) -> float:
        """Drones have high priority when they have a home station."""
        if ctx.ship.is_drone and ctx.ship.home_station_id:
            return 100.0
        return 0.0
