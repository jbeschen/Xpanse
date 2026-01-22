"""Trading behavior for autonomous trade ships.

Finds profitable trade routes, buys low, sells high.
"""
from __future__ import annotations
from uuid import UUID

from .base import ShipBehavior, BehaviorContext, BehaviorResult, BehaviorStatus


class TradingState:
    """State constants for trading behavior."""
    IDLE = "idle"
    FINDING_ROUTE = "finding_route"
    TRAVELING_TO_BUY = "traveling_to_buy"
    BUYING = "buying"
    TRAVELING_TO_SELL = "traveling_to_sell"
    SELLING = "selling"


class TradingBehavior(ShipBehavior):
    """Behavior for autonomous trading ships.

    Finds profitable trade routes and executes buy/sell cycles.
    Uses the TradeRouteFinder for efficient route discovery.
    """

    def __init__(self, route_finder=None) -> None:
        """Initialize trading behavior.

        Args:
            route_finder: Optional TradeRouteFinder for route discovery
        """
        self.route_finder = route_finder
        self.min_profit_threshold = 5.0  # Minimum profit per unit to consider

    @property
    def name(self) -> str:
        return "Trading"

    def on_enter(self, ctx: BehaviorContext) -> None:
        """Initialize trading state."""
        ctx.state_data["trade_state"] = TradingState.IDLE
        ctx.state_data["route_source_id"] = None
        ctx.state_data["route_dest_id"] = None
        ctx.state_data["route_resource"] = None
        ctx.state_data["route_amount"] = 0.0
        ctx.state_data["route_profit"] = 0.0

    def update(self, ctx: BehaviorContext) -> BehaviorResult:
        """Update trading behavior."""
        from ...simulation.trade import CargoHold, Trader
        from ...simulation.economy import Market
        from ...simulation.resources import Inventory
        from ...entities.stations import Station

        state = ctx.state_data.get("trade_state", TradingState.IDLE)
        cargo = ctx.get_component(CargoHold)
        trader = ctx.get_component(Trader)

        if not cargo:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="No cargo hold"
            )

        # State machine
        if state == TradingState.IDLE:
            # Find a new trade route
            route = self._find_trade_route(ctx, cargo)
            if route:
                ctx.state_data["route_source_id"] = route[0]
                ctx.state_data["route_dest_id"] = route[1]
                ctx.state_data["route_resource"] = route[2]
                ctx.state_data["route_amount"] = route[3]
                ctx.state_data["route_profit"] = route[4]
                ctx.state_data["trade_state"] = TradingState.TRAVELING_TO_BUY

                # Update trader component if exists
                if trader:
                    from ...simulation.trade import TradeRoute, TradeState
                    trader.current_route = TradeRoute(
                        source_id=route[0],
                        destination_id=route[1],
                        resource=route[2],
                        amount=route[3],
                        profit_per_unit=route[4],
                    )
                    trader.state = TradeState.TRAVELING_TO_BUY

                # Navigate to source
                return self._navigate_to_station(ctx, route[0])
            else:
                # No profitable routes - wait and try again
                return BehaviorResult(
                    status=BehaviorStatus.WAITING,
                    wait_time=5.0,
                    message="No profitable routes found"
                )

        elif state == TradingState.TRAVELING_TO_BUY:
            # Continue navigation (handled by AI system)
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        elif state == TradingState.BUYING:
            # Execute buy
            success = self._execute_buy(ctx, cargo)
            if success:
                ctx.state_data["trade_state"] = TradingState.TRAVELING_TO_SELL
                dest_id = ctx.state_data.get("route_dest_id")
                if trader:
                    from ...simulation.trade import TradeState
                    trader.state = TradeState.TRAVELING_TO_SELL
                return self._navigate_to_station(ctx, dest_id)
            else:
                # Buy failed - reset
                ctx.state_data["trade_state"] = TradingState.IDLE
                if trader:
                    trader.current_route = None
                    from ...simulation.trade import TradeState
                    trader.state = TradeState.IDLE
                return BehaviorResult(
                    status=BehaviorStatus.RUNNING,
                    wait_time=2.0,
                    message="Buy failed, finding new route"
                )

        elif state == TradingState.TRAVELING_TO_SELL:
            # Continue navigation (handled by AI system)
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        elif state == TradingState.SELLING:
            # Execute sell
            self._execute_sell(ctx, cargo)
            ctx.state_data["trade_state"] = TradingState.IDLE
            if trader:
                trader.current_route = None
                from ...simulation.trade import TradeState
                trader.state = TradeState.IDLE
            return BehaviorResult(
                status=BehaviorStatus.SUCCESS,
                wait_time=1.0,
                message="Trade complete"
            )

        return BehaviorResult(status=BehaviorStatus.RUNNING)

    def on_arrival(self, ctx: BehaviorContext, destination_id: UUID | None) -> BehaviorResult:
        """Handle arrival at destination."""
        state = ctx.state_data.get("trade_state", TradingState.IDLE)

        if state == TradingState.TRAVELING_TO_BUY:
            ctx.state_data["trade_state"] = TradingState.BUYING
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                wait_time=1.0,
                message="Arrived at source, buying"
            )

        elif state == TradingState.TRAVELING_TO_SELL:
            ctx.state_data["trade_state"] = TradingState.SELLING
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                wait_time=1.0,
                message="Arrived at destination, selling"
            )

        return BehaviorResult(status=BehaviorStatus.RUNNING)

    def _find_trade_route(self, ctx: BehaviorContext, cargo) -> tuple | None:
        """Find best trade route.

        Returns: (source_id, dest_id, resource_type, amount, profit_per_unit) or None
        """
        from ...simulation.economy import Market, find_best_trade
        from ...simulation.resources import Inventory
        from ...entities.stations import Station

        em = ctx.entity_manager
        best_route = None
        best_profit = self.min_profit_threshold

        # Get all stations with markets
        stations = list(em.get_entities_with(Market, Inventory))

        for source in stations:
            source_market = em.get_component(source, Market)
            source_inv = em.get_component(source, Inventory)
            if not source_market or not source_inv:
                continue

            for dest in stations:
                if source.id == dest.id:
                    continue

                dest_market = em.get_component(dest, Market)
                dest_inv = em.get_component(dest, Inventory)
                if not dest_market or not dest_inv:
                    continue

                trade = find_best_trade(
                    source_market, source_inv,
                    dest_market, dest_inv,
                    cargo.free_space
                )

                if trade and trade[2] > best_profit:
                    resource, amount, profit = trade
                    best_profit = profit
                    best_route = (source.id, dest.id, resource, amount, profit)

        return best_route

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

    def _execute_buy(self, ctx: BehaviorContext, cargo) -> bool:
        """Execute buy at source station."""
        from ...simulation.economy import Market
        from ...simulation.resources import Inventory

        source_id = ctx.state_data.get("route_source_id")
        resource = ctx.state_data.get("route_resource")
        amount = ctx.state_data.get("route_amount")

        if not source_id or not resource:
            return False

        source = ctx.get_entity(source_id)
        if not source:
            return False

        source_market = ctx.entity_manager.get_component(source, Market)
        source_inv = ctx.entity_manager.get_component(source, Inventory)

        if not source_market or not source_inv:
            return False

        # Get price and check availability
        price = source_market.get_sell_price(resource)
        if price is None:
            return False

        available = source_inv.get(resource)
        buy_amount = min(amount, available, cargo.free_space)

        if buy_amount <= 0:
            return False

        total_cost = price * buy_amount

        # Transfer resources
        removed = source_inv.remove(resource, buy_amount)
        cargo.add_cargo(resource, removed)
        source_market.credits += total_cost

        return True

    def _execute_sell(self, ctx: BehaviorContext, cargo) -> bool:
        """Execute sell at destination station."""
        from ...simulation.economy import Market
        from ...simulation.resources import Inventory

        dest_id = ctx.state_data.get("route_dest_id")
        resource = ctx.state_data.get("route_resource")

        if not dest_id or not resource:
            return False

        dest = ctx.get_entity(dest_id)
        if not dest:
            return False

        dest_market = ctx.entity_manager.get_component(dest, Market)
        dest_inv = ctx.entity_manager.get_component(dest, Inventory)

        if not dest_market or not dest_inv:
            return False

        # Get price
        price = dest_market.get_buy_price(resource)
        if price is None:
            return False

        sell_amount = cargo.get_cargo(resource)
        if sell_amount <= 0:
            return False

        total_value = price * sell_amount

        # Check if market can afford it
        if dest_market.credits < total_value:
            total_value = dest_market.credits
            sell_amount = total_value / price if price > 0 else 0

        if sell_amount <= 0:
            return False

        # Transfer resources
        removed = cargo.remove_cargo(resource, sell_amount)
        dest_inv.add(resource, removed)
        dest_market.credits -= total_value

        return True

    def get_priority(self, ctx: BehaviorContext) -> float:
        """Trading has medium priority."""
        return 50.0
