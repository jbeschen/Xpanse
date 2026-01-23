"""Market system and price calculations."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, System, EntityManager
from ..core.events import EventBus, PriceChangeEvent, DividendEvent
from .resources import ResourceType, BASE_PRICES, Inventory

if TYPE_CHECKING:
    pass


# Dividend system configuration
DIVIDEND_INTERVAL = 30.0  # Process dividends every 30 seconds of game time
DIVIDEND_THRESHOLD = 5000.0  # Station keeps this much as operating capital
DIVIDEND_PERCENTAGE = 0.5  # Transfer 50% of excess credits each interval


class MarketType(Enum):
    """Types of markets with different price behaviors."""
    EARTH = "earth"  # High competition, lower prices but guaranteed demand
    COLONY = "colony"  # Frontier market, higher prices, population-driven
    STATION = "station"  # Standard station market
    MINING = "mining"  # Sells raw materials only


# Price modifiers by market type (multiplier on base prices)
# Lower = cheaper to buy from / sells for less
# Higher = pays more for goods / charges more
MARKET_PRICE_MODIFIERS: dict[MarketType, float] = {
    MarketType.EARTH: 0.7,  # Earth has competition, pays 70% of base
    MarketType.COLONY: 1.5,  # Colonies pay premium, 150% of base
    MarketType.STATION: 1.0,  # Standard pricing
    MarketType.MINING: 0.8,  # Mining sells cheap raw materials
}


@dataclass
class Market(Component):
    """Component for entities that can buy/sell resources."""
    # Market type affects pricing
    market_type: MarketType = MarketType.STATION
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

    def get_price_modifier(self) -> float:
        """Get price modifier based on market type."""
        return MARKET_PRICE_MODIFIERS.get(self.market_type, 1.0)

    def get_buy_price(self, resource: ResourceType) -> float | None:
        """Get buy price for a resource (what the market pays)."""
        if not self.buys.get(resource, False):
            return None
        base = self.prices.get(resource, BASE_PRICES.get(resource, 100.0))
        return base * self.get_price_modifier()

    def get_sell_price(self, resource: ResourceType) -> float | None:
        """Get sell price for a resource (what a buyer pays)."""
        if not self.sells.get(resource, False):
            return None
        base = self.prices.get(resource, BASE_PRICES.get(resource, 100.0))
        # Sell price is base + 10% markup, then modified by market type
        return base * 1.1 * self.get_price_modifier()

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


@dataclass
class Population(Component):
    """Population component for colonies that drives demand and generates credits."""
    # Current population (in thousands)
    population: float = 10.0
    # Maximum population capacity
    max_population: float = 1000.0
    # Growth rate per day (when supplied)
    growth_rate: float = 0.01  # 1% per day when happy
    # Credits generated per population unit per day
    credits_per_pop: float = 10.0
    # Consumption rates per population unit per day
    consumption: dict[ResourceType, float] = field(default_factory=lambda: {
        ResourceType.LIFE_SUPPORT: 0.1,
        ResourceType.WATER: 0.05,
        ResourceType.ELECTRONICS: 0.02,  # Consumer goods
    })
    # Satisfaction level (0-1) affects growth
    satisfaction: float = 1.0
    # Time accumulator for daily ticks
    _day_accumulator: float = 0.0

    def calculate_demand(self) -> dict[ResourceType, float]:
        """Calculate daily resource demand based on population."""
        return {r: a * self.population for r, a in self.consumption.items()}

    def generate_credits(self) -> float:
        """Calculate credits generated by population."""
        return self.population * self.credits_per_pop * self.satisfaction


class PopulationSystem(System):
    """System that handles population consumption, growth, and credit generation."""

    priority = 45  # Run after production, before economy

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        # Game time: 1 real second = 1 game minute, so 60 seconds = 1 hour, 1440 seconds = 1 day
        self._day_length = 60.0  # Seconds per game-day (accelerated for gameplay)

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update population consumption, growth, and credit generation."""
        for entity, population in entity_manager.get_all_components(Population):
            inventory = entity_manager.get_component(entity, Inventory)
            market = entity_manager.get_component(entity, Market)

            if not inventory or not market:
                continue

            # Accumulate time for daily tick
            population._day_accumulator += dt
            if population._day_accumulator < self._day_length:
                continue

            # Process a day's worth of activity
            days = population._day_accumulator / self._day_length
            population._day_accumulator = 0.0

            # Calculate and consume resources
            satisfaction_sum = 0.0
            satisfaction_count = 0

            for resource, rate in population.consumption.items():
                needed = rate * population.population * days
                available = inventory.get(resource)

                if available >= needed:
                    inventory.remove(resource, needed)
                    satisfaction_sum += 1.0
                else:
                    # Partial satisfaction
                    inventory.remove(resource, available)
                    satisfaction_sum += available / needed if needed > 0 else 0
                satisfaction_count += 1

            # Update satisfaction (rolling average)
            if satisfaction_count > 0:
                new_satisfaction = satisfaction_sum / satisfaction_count
                population.satisfaction = (population.satisfaction * 0.7 +
                                          new_satisfaction * 0.3)

            # Generate credits based on population and satisfaction
            credits_generated = population.generate_credits() * days
            market.credits += credits_generated

            # Population growth/decline based on satisfaction
            if population.satisfaction > 0.8:
                # Growing - satisfied population
                growth = population.growth_rate * population.satisfaction * days
                population.population = min(
                    population.max_population,
                    population.population * (1 + growth)
                )
            elif population.satisfaction < 0.5:
                # Declining - unhappy population
                decline = (0.5 - population.satisfaction) * 0.02 * days
                population.population = max(1.0, population.population * (1 - decline))


class EconomySystem(System):
    """System that updates market prices and processes station dividends."""

    priority = 50  # Run after production and population

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._update_interval = 5.0  # Update prices every 5 seconds
        self._time_since_update = 0.0
        self._dividend_timer = 0.0  # Timer for dividend processing

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update market prices and process dividends."""
        self._time_since_update += dt
        self._dividend_timer += dt

        # Process dividends on a separate timer
        if self._dividend_timer >= DIVIDEND_INTERVAL:
            self._dividend_timer = 0.0
            self._process_dividends(entity_manager)

        if self._time_since_update < self._update_interval:
            return

        self._time_since_update = 0.0

        # Update prices for all markets
        for entity, market in entity_manager.get_all_components(Market):
            inventory = entity_manager.get_component(entity, Inventory)
            if not inventory:
                continue

            # For population centers, adjust target stock based on population
            population = entity_manager.get_component(entity, Population)
            if population:
                for resource, rate in population.consumption.items():
                    # Target stock = 10 days worth of consumption
                    market.target_stock[resource] = rate * population.population * 10

            for resource in ResourceType:
                if resource not in market.buys and resource not in market.sells:
                    continue

                current_stock = inventory.get(resource)
                old_price = market.prices.get(resource, BASE_PRICES.get(resource, 100.0))
                new_price = market.update_price(resource, current_stock)

                # Fire event if price changed significantly
                if abs(new_price - old_price) / max(old_price, 0.01) > 0.05:
                    self.event_bus.publish(PriceChangeEvent(
                        station_id=entity.id,
                        resource_type=resource.value,
                        old_price=old_price,
                        new_price=new_price
                    ))

    def _process_dividends(self, entity_manager: EntityManager) -> None:
        """Transfer excess credits from owned stations to their owner factions."""
        from ..entities.stations import Station
        from ..entities.factions import Faction

        # Build faction lookup
        factions: dict[UUID, Faction] = {}
        for entity, faction in entity_manager.get_all_components(Faction):
            factions[entity.id] = faction

        # Process each station with a market
        for entity, station in entity_manager.get_all_components(Station):
            # Skip stations without owners
            if not station.owner_faction_id:
                continue

            # Get owner faction
            owner_faction = factions.get(station.owner_faction_id)
            if not owner_faction:
                continue

            # Get station's market
            market = entity_manager.get_component(entity, Market)
            if not market:
                continue

            # Calculate excess credits above operating threshold
            excess = market.credits - DIVIDEND_THRESHOLD
            if excess <= 0:
                continue

            # Transfer percentage of excess to owner
            dividend = excess * DIVIDEND_PERCENTAGE
            if dividend < 1.0:  # Skip tiny amounts
                continue

            # Transfer credits
            market.credits -= dividend
            owner_faction.credits += dividend

            # Get station name for event
            station_name = entity.name or "Station"

            # Fire dividend event
            self.event_bus.publish(DividendEvent(
                station_id=entity.id,
                faction_id=station.owner_faction_id,
                amount=dividend,
                station_name=station_name
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
