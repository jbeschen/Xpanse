"""Market system and price calculations."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, System, EntityManager
from ..core.events import EventBus, PriceChangeEvent
from .resources import ResourceType, BASE_PRICES, Inventory

if TYPE_CHECKING:
    pass


@dataclass
class Market(Component):
    """Component for entities that can buy/sell resources."""
    # Current prices (buy/sell)
    prices: dict[ResourceType, float] = field(default_factory=dict)
    # Target inventory levels (for price calculation)
    target_stock: dict[ResourceType, float] = field(default_factory=dict)
    # What this market buys (True) or sells (False) for each resource
    buys: dict[ResourceType, bool] = field(default_factory=dict)
    sells: dict[ResourceType, bool] = field(default_factory=dict)
    # Price volatility (how fast prices change)
    volatility: float = 0.1
    # Credits available for purchases
    credits: float = 10000.0

    def get_buy_price(self, resource: ResourceType) -> float | None:
        """Get buy price for a resource (what the market pays)."""
        if not self.buys.get(resource, False):
            return None
        return self.prices.get(resource, BASE_PRICES.get(resource, 100.0))

    def get_sell_price(self, resource: ResourceType) -> float | None:
        """Get sell price for a resource (what a buyer pays)."""
        if not self.sells.get(resource, False):
            return None
        base = self.prices.get(resource, BASE_PRICES.get(resource, 100.0))
        return base * 1.1  # 10% markup

    def update_price(self, resource: ResourceType, current_stock: float) -> float:
        """Update price based on current vs target stock. Returns new price."""
        target = self.target_stock.get(resource, 100.0)
        base = BASE_PRICES.get(resource, 100.0)

        if target <= 0:
            target = 100.0

        # Price increases when stock is low, decreases when high
        stock_ratio = current_stock / target
        # Inverse relationship: low stock = high price
        if stock_ratio < 0.1:
            price_multiplier = 3.0
        elif stock_ratio < 0.5:
            price_multiplier = 1.5 + (0.5 - stock_ratio)
        elif stock_ratio > 2.0:
            price_multiplier = 0.5
        elif stock_ratio > 1.0:
            price_multiplier = 1.0 - (stock_ratio - 1.0) * 0.25
        else:
            price_multiplier = 1.0

        new_price = base * price_multiplier

        # Gradual adjustment based on volatility
        old_price = self.prices.get(resource, base)
        adjusted_price = old_price + (new_price - old_price) * self.volatility

        # Clamp to reasonable bounds
        adjusted_price = max(base * 0.1, min(base * 10.0, adjusted_price))
        self.prices[resource] = adjusted_price

        return adjusted_price


class EconomySystem(System):
    """System that updates market prices based on supply/demand."""

    priority = 50  # Run after production

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._update_interval = 5.0  # Update prices every 5 seconds
        self._time_since_update = 0.0

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update market prices."""
        self._time_since_update += dt

        if self._time_since_update < self._update_interval:
            return

        self._time_since_update = 0.0

        # Update prices for all markets
        for entity, market in entity_manager.get_all_components(Market):
            inventory = entity_manager.get_component(entity, Inventory)
            if not inventory:
                continue

            for resource in ResourceType:
                if resource not in market.buys and resource not in market.sells:
                    continue

                current_stock = inventory.get(resource)
                old_price = market.prices.get(resource, BASE_PRICES.get(resource, 100.0))
                new_price = market.update_price(resource, current_stock)

                # Fire event if price changed significantly
                if abs(new_price - old_price) / old_price > 0.05:
                    self.event_bus.publish(PriceChangeEvent(
                        station_id=entity.id,
                        resource_type=resource.value,
                        old_price=old_price,
                        new_price=new_price
                    ))


def find_best_trade(
    source_market: Market,
    source_inventory: Inventory,
    dest_market: Market,
    dest_inventory: Inventory,
    cargo_capacity: float
) -> tuple[ResourceType, float, float] | None:
    """Find the most profitable trade between two markets.

    Returns: (resource, amount, profit_per_unit) or None if no profitable trade.
    """
    best_trade: tuple[ResourceType, float, float] | None = None
    best_profit = 0.0

    for resource in ResourceType:
        # Check if source sells and dest buys this resource
        sell_price = source_market.get_sell_price(resource)
        buy_price = dest_market.get_buy_price(resource)

        if sell_price is None or buy_price is None:
            continue

        # Calculate profit per unit
        profit_per_unit = buy_price - sell_price

        if profit_per_unit <= 0:
            continue

        # Calculate max tradeable amount
        available = source_inventory.get(resource)
        dest_space = dest_inventory.free_space
        affordable = dest_market.credits / buy_price if buy_price > 0 else 0

        max_amount = min(available, cargo_capacity, dest_space, affordable)

        if max_amount <= 0:
            continue

        total_profit = profit_per_unit * max_amount

        if total_profit > best_profit:
            best_profit = total_profit
            best_trade = (resource, max_amount, profit_per_unit)

    return best_trade
