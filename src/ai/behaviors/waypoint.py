"""Waypoint behavior for player-configured routes.

Ships follow player-set waypoints in sequence, executing
buy/sell orders at each stop.
"""
from __future__ import annotations
from uuid import UUID

from .base import ShipBehavior, BehaviorContext, BehaviorResult, BehaviorStatus


class WaypointState:
    """State constants for waypoint behavior."""
    IDLE = "idle"
    TRAVELING = "traveling"
    EXECUTING_ORDERS = "executing_orders"
    WAITING = "waiting"


class WaypointBehavior(ShipBehavior):
    """Behavior for following player-configured waypoint routes.

    Ships follow a sequence of waypoints, optionally buying/selling
    resources at each stop. Supports looping routes.
    """

    def __init__(self) -> None:
        self.wait_at_waypoint = 1.5  # seconds

    @property
    def name(self) -> str:
        return "Waypoint"

    def on_enter(self, ctx: BehaviorContext) -> None:
        """Initialize waypoint state."""
        ctx.state_data["waypoint_state"] = WaypointState.IDLE

    def update(self, ctx: BehaviorContext) -> BehaviorResult:
        """Update waypoint behavior."""
        from ...simulation.trade import ManualRoute, CargoHold

        manual_route = ctx.get_component(ManualRoute)
        if not manual_route or not manual_route.waypoints:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="No waypoint route configured"
            )

        state = ctx.state_data.get("waypoint_state", WaypointState.IDLE)
        cargo = ctx.get_component(CargoHold)

        if state == WaypointState.IDLE:
            waypoint = manual_route.get_current_waypoint()
            if not waypoint:
                return BehaviorResult(
                    status=BehaviorStatus.SUCCESS,
                    message="Route complete"
                )

            ctx.state_data["waypoint_state"] = WaypointState.TRAVELING
            return self._navigate_to_waypoint(ctx, waypoint.station_id)

        elif state == WaypointState.TRAVELING:
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        elif state == WaypointState.EXECUTING_ORDERS:
            if cargo:
                self._execute_waypoint_orders(ctx, manual_route, cargo)
            manual_route.advance_waypoint()
            ctx.state_data["waypoint_state"] = WaypointState.WAITING
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                wait_time=self.wait_at_waypoint,
                message="Orders executed"
            )

        elif state == WaypointState.WAITING:
            ctx.state_data["waypoint_state"] = WaypointState.IDLE
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        return BehaviorResult(status=BehaviorStatus.RUNNING)

    def on_arrival(self, ctx: BehaviorContext, destination_id: UUID | None) -> BehaviorResult:
        """Handle arrival at waypoint."""
        state = ctx.state_data.get("waypoint_state", WaypointState.IDLE)

        if state == WaypointState.TRAVELING:
            ctx.state_data["waypoint_state"] = WaypointState.EXECUTING_ORDERS
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                wait_time=1.0,
                message="Arrived at waypoint"
            )

        return BehaviorResult(status=BehaviorStatus.RUNNING)

    def _navigate_to_waypoint(self, ctx: BehaviorContext, station_id: UUID) -> BehaviorResult:
        """Create navigation result for waypoint station.

        NOTE: We intentionally DON'T set target_body here. If we did, NavigationSystem
        would track the parent body and lock the ship to that body (e.g., "Moon") when
        it gets close, rather than going to the actual station coordinates.

        Since stations have ParentBody components, OrbitalSystem keeps their Position
        updated as planets orbit. So we just navigate to the station's current Position
        and the ship will arrive at the right place.
        """
        from ...solar_system.orbits import Position
        from ...entities.stations import Station

        station = ctx.get_entity(station_id)
        if not station:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message=f"Waypoint station {station_id} not found"
            )

        pos = ctx.entity_manager.get_component(station, Position)
        station_comp = ctx.entity_manager.get_component(station, Station)

        if not pos:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="Station has no position"
            )

        # Get parent body name for parking after arrival (but don't use for tracking)
        parent_body = station_comp.parent_body if station_comp else ""

        return BehaviorResult(
            status=BehaviorStatus.RUNNING,
            target_x=pos.x,
            target_y=pos.y,
            target_body="",  # Don't track parent body - go to exact station coordinates
            target_entity_id=station_id,
            # Store parent body in message for use after arrival
            message=f"parent_body:{parent_body}",
        )

    def _execute_waypoint_orders(self, ctx: BehaviorContext, manual_route, cargo) -> None:
        """Execute buy/sell orders at current waypoint.

        If specific resources are configured, use those.
        Otherwise, automatically trade based on what's available and profitable.
        """
        from ...simulation.resources import Inventory
        from ...simulation.economy import Market

        waypoint = manual_route.get_current_waypoint()
        if not waypoint:
            return

        station = ctx.get_entity(waypoint.station_id)
        if not station:
            return

        station_inv = ctx.entity_manager.get_component(station, Inventory)
        market = ctx.entity_manager.get_component(station, Market)
        if not station_inv:
            return

        # If specific resources are configured, use those
        if waypoint.sell_resource or waypoint.buy_resource:
            # Execute sell order first (to make room for buying)
            if waypoint.sell_resource:
                sell_amount = cargo.get_cargo(waypoint.sell_resource)
                if sell_amount > 0:
                    removed = cargo.remove_cargo(waypoint.sell_resource, sell_amount)
                    station_inv.add(waypoint.sell_resource, removed)

            # Execute buy order
            if waypoint.buy_resource:
                available = station_inv.get(waypoint.buy_resource)
                buy_amount = min(available, cargo.free_space)
                if buy_amount > 0:
                    removed = station_inv.remove(waypoint.buy_resource, buy_amount)
                    cargo.add_cargo(waypoint.buy_resource, removed)
        else:
            # AUTO-TRADE MODE: Sell cargo, then buy what's available
            self._auto_trade_at_station(ctx, cargo, station, station_inv, market)

    def _auto_trade_at_station(self, ctx, cargo, station, station_inv, market) -> None:
        """Automatically trade at station - sell cargo, buy resources.

        This makes manual routes work without specifying exact resources.
        Ships will pick up whatever is plentiful and deliver wherever they go.
        Respects station min_reserves to prevent auto-selling protected resources.
        """
        from ...simulation.resources import ResourceType
        from ...entities.stations import Station as StationComp

        # Get station component to check min_reserves
        station_comp = ctx.entity_manager.get_component(station, StationComp)

        # Step 1: Sell everything we're carrying
        # (Station buys it for its own use or resale)
        for resource in list(cargo.cargo.keys()):
            amount = cargo.get_cargo(resource)
            if amount > 0:
                removed = cargo.remove_cargo(resource, amount)
                station_inv.add(resource, removed)

        # Step 2: Buy the most plentiful resource at this station
        # (to carry to the next waypoint)
        if cargo.free_space <= 0:
            return

        # Find resource with most stock (respecting min_reserves)
        best_resource = None
        best_amount = 0

        for resource in ResourceType:
            available = station_inv.get(resource)

            # Respect min_reserves if station has them set
            if station_comp:
                available = station_comp.get_available_for_trade(resource, available)

            # Only buy if station has significant stock (keeping some for local use)
            if available > 20:
                buyable = available - 10  # Leave some for station
                if buyable > best_amount:
                    best_amount = buyable
                    best_resource = resource

        if best_resource and best_amount > 0:
            buy_amount = min(best_amount, cargo.free_space)
            if buy_amount > 5:  # Minimum viable load
                removed = station_inv.remove(best_resource, buy_amount)
                cargo.add_cargo(best_resource, removed)

    def can_activate(self, ctx: BehaviorContext) -> bool:
        """Waypoint behavior requires a configured route."""
        from ...simulation.trade import ManualRoute

        route = ctx.get_component(ManualRoute)
        return route is not None and len(route.waypoints) > 0

    def get_priority(self, ctx: BehaviorContext) -> float:
        """Waypoint routes have high priority (player-configured)."""
        from ...simulation.trade import ManualRoute

        route = ctx.get_component(ManualRoute)
        if route and route.waypoints:
            return 80.0  # High priority for player routes
        return 0.0
