"""Tests for the economy system."""
import pytest
from src.core.world import World
from src.core.events import EventBus
from src.simulation.resources import ResourceType, Inventory, BASE_PRICES
from src.simulation.economy import Market, EconomySystem, find_best_trade


class TestInventory:
    """Tests for Inventory component."""

    def test_add_resources(self):
        """Test adding resources to inventory."""
        inv = Inventory(capacity=100)
        added = inv.add(ResourceType.IRON_ORE, 50)

        assert added == 50
        assert inv.get(ResourceType.IRON_ORE) == 50
        assert inv.total_amount == 50

    def test_add_respects_capacity(self):
        """Test that adding resources respects capacity."""
        inv = Inventory(capacity=100)
        added = inv.add(ResourceType.IRON_ORE, 150)

        assert added == 100
        assert inv.get(ResourceType.IRON_ORE) == 100
        assert inv.is_full

    def test_remove_resources(self):
        """Test removing resources from inventory."""
        inv = Inventory(capacity=100)
        inv.add(ResourceType.IRON_ORE, 50)
        removed = inv.remove(ResourceType.IRON_ORE, 30)

        assert removed == 30
        assert inv.get(ResourceType.IRON_ORE) == 20

    def test_remove_more_than_available(self):
        """Test removing more resources than available."""
        inv = Inventory(capacity=100)
        inv.add(ResourceType.IRON_ORE, 50)
        removed = inv.remove(ResourceType.IRON_ORE, 100)

        assert removed == 50
        assert inv.get(ResourceType.IRON_ORE) == 0
        assert inv.is_empty

    def test_has_all(self):
        """Test checking for multiple resources."""
        inv = Inventory(capacity=1000)
        inv.add(ResourceType.IRON_ORE, 100)
        inv.add(ResourceType.WATER_ICE, 50)

        assert inv.has_all({ResourceType.IRON_ORE: 50, ResourceType.WATER_ICE: 25})
        assert not inv.has_all({ResourceType.IRON_ORE: 150, ResourceType.WATER_ICE: 25})

    def test_free_space(self):
        """Test free space calculation."""
        inv = Inventory(capacity=100)
        inv.add(ResourceType.IRON_ORE, 40)

        assert inv.free_space == 60


class TestMarket:
    """Tests for Market component."""

    def test_buy_sell_prices(self):
        """Test that sell prices have markup."""
        market = Market()
        market.buys[ResourceType.IRON_ORE] = True
        market.sells[ResourceType.IRON_ORE] = True
        market.prices[ResourceType.IRON_ORE] = 100

        buy_price = market.get_buy_price(ResourceType.IRON_ORE)
        sell_price = market.get_sell_price(ResourceType.IRON_ORE)

        assert buy_price == 100
        assert sell_price == pytest.approx(110, rel=1e-9)  # 10% markup

    def test_price_not_available(self):
        """Test that prices return None for unavailable resources."""
        market = Market()
        market.sells[ResourceType.IRON_ORE] = True

        # Can sell but not buy
        assert market.get_sell_price(ResourceType.IRON_ORE) is not None
        assert market.get_buy_price(ResourceType.IRON_ORE) is None

    def test_price_update_low_stock(self):
        """Test that prices increase when stock is low."""
        market = Market()
        market.target_stock[ResourceType.IRON_ORE] = 100
        market.prices[ResourceType.IRON_ORE] = BASE_PRICES[ResourceType.IRON_ORE]

        # Low stock should increase price
        new_price = market.update_price(ResourceType.IRON_ORE, 5)
        assert new_price > BASE_PRICES[ResourceType.IRON_ORE]

    def test_price_update_high_stock(self):
        """Test that prices decrease when stock is high."""
        market = Market()
        market.target_stock[ResourceType.IRON_ORE] = 100
        market.prices[ResourceType.IRON_ORE] = BASE_PRICES[ResourceType.IRON_ORE]

        # High stock should decrease price
        new_price = market.update_price(ResourceType.IRON_ORE, 300)
        assert new_price < BASE_PRICES[ResourceType.IRON_ORE]


class TestFindBestTrade:
    """Tests for trade route finding."""

    def test_find_profitable_trade(self):
        """Test finding a profitable trade between markets."""
        source_market = Market(credits=10000)
        source_market.sells[ResourceType.IRON_ORE] = True
        source_market.prices[ResourceType.IRON_ORE] = 10  # Cheap

        source_inv = Inventory(capacity=1000)
        source_inv.add(ResourceType.IRON_ORE, 100)

        dest_market = Market(credits=10000)
        dest_market.buys[ResourceType.IRON_ORE] = True
        dest_market.prices[ResourceType.IRON_ORE] = 20  # Expensive

        dest_inv = Inventory(capacity=1000)

        trade = find_best_trade(
            source_market, source_inv,
            dest_market, dest_inv,
            cargo_capacity=50
        )

        assert trade is not None
        resource, amount, profit = trade
        assert resource == ResourceType.IRON_ORE
        assert amount == 50  # Limited by cargo capacity
        assert profit > 0

    def test_no_profitable_trade(self):
        """Test that no trade is found when not profitable."""
        source_market = Market(credits=10000)
        source_market.sells[ResourceType.IRON_ORE] = True
        source_market.prices[ResourceType.IRON_ORE] = 30  # Expensive

        source_inv = Inventory(capacity=1000)
        source_inv.add(ResourceType.IRON_ORE, 100)

        dest_market = Market(credits=10000)
        dest_market.buys[ResourceType.IRON_ORE] = True
        dest_market.prices[ResourceType.IRON_ORE] = 10  # Cheap

        dest_inv = Inventory(capacity=1000)

        trade = find_best_trade(
            source_market, source_inv,
            dest_market, dest_inv,
            cargo_capacity=50
        )

        # Sell price (33) > buy price (10), so no profit
        assert trade is None


class TestEconomySystem:
    """Tests for the economy system."""

    def test_system_updates_prices(self):
        """Test that economy system updates market prices."""
        world = World()
        event_bus = world.event_bus
        system = EconomySystem(event_bus)
        system._update_interval = 0  # Update immediately

        # Create a station with market and inventory
        entity = world.create_entity("Test Station")
        em = world.entity_manager

        market = Market()
        market.buys[ResourceType.IRON_ORE] = True
        market.target_stock[ResourceType.IRON_ORE] = 100
        market.prices[ResourceType.IRON_ORE] = BASE_PRICES[ResourceType.IRON_ORE]
        em.add_component(entity, market)

        inventory = Inventory(capacity=1000)
        inventory.add(ResourceType.IRON_ORE, 10)  # Low stock
        em.add_component(entity, inventory)

        # Run system update
        system.update(1.0, em)

        # Price should have increased due to low stock
        assert market.prices[ResourceType.IRON_ORE] > BASE_PRICES[ResourceType.IRON_ORE]
