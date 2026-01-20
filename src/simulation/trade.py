"""Trade route logic and cargo transport."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, System, EntityManager
from ..core.events import EventBus, TradeCompleteEvent, ResourceTransferEvent
from .resources import ResourceType, Inventory
from .economy import Market

if TYPE_CHECKING:
    pass


class TradeState(Enum):
    """State of a trade ship."""
    IDLE = "idle"
    TRAVELING_TO_BUY = "traveling_to_buy"
    BUYING = "buying"
    TRAVELING_TO_SELL = "traveling_to_sell"
    SELLING = "selling"


@dataclass
class TradeRoute:
    """A trade route between two stations."""
    source_id: UUID
    destination_id: UUID
    resource: ResourceType
    amount: float
    profit_per_unit: float


@dataclass
class Trader(Component):
    """Component for entities that can trade."""
    current_route: TradeRoute | None = None
    state: TradeState = TradeState.IDLE
    home_station_id: UUID | None = None
    preferred_resources: list[ResourceType] = field(default_factory=list)
    min_profit_threshold: float = 5.0  # Minimum profit per unit to consider a trade


@dataclass
class CargoHold(Component):
    """Component for cargo storage on ships."""
    capacity: float = 100.0
    cargo: dict[ResourceType, float] = field(default_factory=dict)

    def add_cargo(self, resource: ResourceType, amount: float) -> float:
        """Add cargo. Returns actual amount added."""
        current_total = sum(self.cargo.values())
        available = self.capacity - current_total
        actual = min(amount, available)

        if actual > 0:
            self.cargo[resource] = self.cargo.get(resource, 0.0) + actual
        return actual

    def remove_cargo(self, resource: ResourceType, amount: float) -> float:
        """Remove cargo. Returns actual amount removed."""
        current = self.cargo.get(resource, 0.0)
        actual = min(amount, current)

        if actual > 0:
            self.cargo[resource] = current - actual
            if self.cargo[resource] <= 0:
                del self.cargo[resource]
        return actual

    def get_cargo(self, resource: ResourceType) -> float:
        """Get amount of a specific cargo."""
        return self.cargo.get(resource, 0.0)

    @property
    def total_cargo(self) -> float:
        """Total cargo amount."""
        return sum(self.cargo.values())

    @property
    def free_space(self) -> float:
        """Available cargo space."""
        return max(0.0, self.capacity - self.total_cargo)

    @property
    def is_empty(self) -> bool:
        """Check if hold is empty."""
        return self.total_cargo == 0


class TradeSystem(System):
    """System that manages trade between stations."""

    priority = 40  # Run after production, before economy

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update all traders."""
        for entity, trader in entity_manager.get_all_components(Trader):
            self._update_trader(entity, trader, entity_manager, dt)

    def _update_trader(
        self,
        entity,
        trader: Trader,
        entity_manager: EntityManager,
        dt: float
    ) -> None:
        """Update a single trader."""
        cargo = entity_manager.get_component(entity, CargoHold)
        if not cargo:
            return

        if trader.state == TradeState.IDLE:
            # Find a new trade route
            route = self._find_trade_route(entity, trader, cargo, entity_manager)
            if route:
                trader.current_route = route
                trader.state = TradeState.TRAVELING_TO_BUY

        elif trader.state == TradeState.BUYING:
            # Execute buy at source
            if trader.current_route:
                success = self._execute_buy(entity, trader, cargo, entity_manager)
                if success:
                    trader.state = TradeState.TRAVELING_TO_SELL
                else:
                    # Trade failed, go idle
                    trader.current_route = None
                    trader.state = TradeState.IDLE

        elif trader.state == TradeState.SELLING:
            # Execute sell at destination
            if trader.current_route:
                self._execute_sell(entity, trader, cargo, entity_manager)
            trader.current_route = None
            trader.state = TradeState.IDLE

    def _find_trade_route(
        self,
        ship_entity,
        trader: Trader,
        cargo: CargoHold,
        entity_manager: EntityManager
    ) -> TradeRoute | None:
        """Find the best trade route for this trader."""
        from .economy import find_best_trade

        best_route: TradeRoute | None = None
        best_profit = trader.min_profit_threshold

        # Get all stations with markets
        stations = list(entity_manager.get_entities_with(Market, Inventory))

        for source in stations:
            source_market = entity_manager.get_component(source, Market)
            source_inv = entity_manager.get_component(source, Inventory)
            if not source_market or not source_inv:
                continue

            for dest in stations:
                if source.id == dest.id:
                    continue

                dest_market = entity_manager.get_component(dest, Market)
                dest_inv = entity_manager.get_component(dest, Inventory)
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
                    best_route = TradeRoute(
                        source_id=source.id,
                        destination_id=dest.id,
                        resource=resource,
                        amount=amount,
                        profit_per_unit=profit
                    )

        return best_route

    def _execute_buy(
        self,
        ship_entity,
        trader: Trader,
        cargo: CargoHold,
        entity_manager: EntityManager
    ) -> bool:
        """Execute a buy order. Returns True if successful."""
        route = trader.current_route
        if not route:
            return False

        source = entity_manager.get_entity(route.source_id)
        if not source:
            return False

        source_market = entity_manager.get_component(source, Market)
        source_inv = entity_manager.get_component(source, Inventory)

        if not source_market or not source_inv:
            return False

        # Get price and check availability
        price = source_market.get_sell_price(route.resource)
        if price is None:
            return False

        available = source_inv.get(route.resource)
        buy_amount = min(route.amount, available, cargo.free_space)

        if buy_amount <= 0:
            return False

        total_cost = price * buy_amount

        # Transfer resources
        removed = source_inv.remove(route.resource, buy_amount)
        cargo.add_cargo(route.resource, removed)
        source_market.credits += total_cost

        self.event_bus.publish(ResourceTransferEvent(
            source_id=source.id,
            target_id=ship_entity.id,
            resource_type=route.resource.value,
            amount=removed
        ))

        return True

    def _execute_sell(
        self,
        ship_entity,
        trader: Trader,
        cargo: CargoHold,
        entity_manager: EntityManager
    ) -> bool:
        """Execute a sell order. Returns True if successful."""
        route = trader.current_route
        if not route:
            return False

        dest = entity_manager.get_entity(route.destination_id)
        if not dest:
            return False

        dest_market = entity_manager.get_component(dest, Market)
        dest_inv = entity_manager.get_component(dest, Inventory)

        if not dest_market or not dest_inv:
            return False

        # Get price
        price = dest_market.get_buy_price(route.resource)
        if price is None:
            return False

        sell_amount = cargo.get_cargo(route.resource)
        if sell_amount <= 0:
            return False

        total_value = price * sell_amount

        # Check if market can afford it
        if dest_market.credits < total_value:
            total_value = dest_market.credits
            sell_amount = total_value / price

        # Transfer resources
        removed = cargo.remove_cargo(route.resource, sell_amount)
        dest_inv.add(route.resource, removed)
        dest_market.credits -= total_value

        self.event_bus.publish(TradeCompleteEvent(
            buyer_id=dest.id,
            seller_id=ship_entity.id,
            resource_type=route.resource.value,
            amount=removed,
            total_price=total_value
        ))

        return True


def notify_ship_arrived(trader: Trader) -> None:
    """Called when a ship arrives at its destination. Advances trade state."""
    if trader.state == TradeState.TRAVELING_TO_BUY:
        trader.state = TradeState.BUYING
    elif trader.state == TradeState.TRAVELING_TO_SELL:
        trader.state = TradeState.SELLING
