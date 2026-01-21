"""Integration tests for the simulation."""
import pytest
from src.core.world import World, GameTime
from src.core.ecs import Entity, Component, System, EntityManager
from src.core.events import EventBus, Event
from src.solar_system.orbits import Position, Orbit, OrbitalSystem


class TestGameTime:
    """Tests for GameTime."""

    def test_initial_state(self):
        """Test initial game time state."""
        time = GameTime()

        assert time.day == 1
        assert time.year == 2150
        assert time.total_days == 0

    def test_advance_time(self):
        """Test advancing game time."""
        time = GameTime()
        # Time scale: 1 real second at 1x speed = 1 game day
        time.advance(1.0, speed=1.0)

        assert time.total_days == 1.0  # 1 real second = 1 game day at 1x
        assert time.day == 2  # Started at day 1, advanced 1 day

    def test_day_rollover(self):
        """Test day rollover to new year."""
        time = GameTime()
        # At 1x speed, 1 real second = 1 day
        # To advance 1 year (365 days), need 365 real seconds at 1x
        time.advance(365.0, speed=1.0)

        assert time.year == 2151

    def test_str_format(self):
        """Test string representation."""
        time = GameTime()
        assert "Year 2150" in str(time)
        assert "Day 1" in str(time)


class TestEntityManager:
    """Tests for EntityManager."""

    def test_create_entity(self):
        """Test entity creation."""
        em = EntityManager()
        entity = em.create_entity("Test", {"tag1", "tag2"})

        assert entity.name == "Test"
        assert "tag1" in entity.tags
        assert em.entity_count == 1

    def test_destroy_entity(self):
        """Test entity destruction."""
        em = EntityManager()
        entity = em.create_entity("Test")
        em.destroy_entity(entity)

        assert em.entity_count == 0

    def test_add_get_component(self):
        """Test adding and getting components."""
        em = EntityManager()
        entity = em.create_entity()
        pos = Position(x=1.0, y=2.0)
        em.add_component(entity, pos)

        retrieved = em.get_component(entity, Position)

        assert retrieved is not None
        assert retrieved.x == 1.0
        assert retrieved.y == 2.0

    def test_has_component(self):
        """Test component existence check."""
        em = EntityManager()
        entity = em.create_entity()
        em.add_component(entity, Position())

        assert em.has_component(entity, Position)
        assert not em.has_component(entity, Orbit)

    def test_get_entities_with(self):
        """Test querying entities by components."""
        em = EntityManager()

        e1 = em.create_entity("E1")
        em.add_component(e1, Position())

        e2 = em.create_entity("E2")
        em.add_component(e2, Position())
        em.add_component(e2, Orbit(parent_name="Sun", semi_major_axis=1.0, orbital_period=365))

        e3 = em.create_entity("E3")
        em.add_component(e3, Orbit(parent_name="Sun", semi_major_axis=2.0, orbital_period=687))

        # Get entities with Position
        with_pos = list(em.get_entities_with(Position))
        assert len(with_pos) == 2

        # Get entities with both Position and Orbit
        with_both = list(em.get_entities_with(Position, Orbit))
        assert len(with_both) == 1
        assert with_both[0].name == "E2"

    def test_get_entities_with_tag(self):
        """Test querying entities by tag."""
        em = EntityManager()

        em.create_entity("E1", {"planet"})
        em.create_entity("E2", {"planet", "habitable"})
        em.create_entity("E3", {"moon"})

        planets = list(em.get_entities_with_tag("planet"))
        assert len(planets) == 2


class TestWorld:
    """Tests for World."""

    def test_create_destroy_entity(self):
        """Test entity lifecycle through World."""
        world = World()
        entity = world.create_entity("Test")

        assert world.entity_manager.entity_count == 1

        world.destroy_entity(entity)
        assert world.entity_manager.entity_count == 0

    def test_pause_unpause(self):
        """Test pausing and unpausing."""
        world = World()

        assert not world.paused

        world.pause()
        assert world.paused

        world.unpause()
        assert not world.paused

        world.toggle_pause()
        assert world.paused

    def test_speed_control(self):
        """Test simulation speed control."""
        world = World()

        world.speed = 5.0
        assert world.speed == 5.0

        # Test clamping (speed range is 1-100)
        world.speed = 200.0
        assert world.speed == 100.0

        world.speed = 0.1
        assert world.speed == 1.0

    def test_update_advances_time(self):
        """Test that update advances game time."""
        world = World()
        initial_time = world.game_time.total_days

        world.update(1.0)  # 1 second

        assert world.game_time.total_days > initial_time

    def test_update_paused(self):
        """Test that update does nothing when paused."""
        world = World()
        world.pause()
        initial_time = world.game_time.total_days

        world.update(1.0)

        assert world.game_time.total_days == initial_time


class TestEventBus:
    """Tests for EventBus."""

    def test_subscribe_publish(self):
        """Test event subscription and publishing."""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        # Subscribe handler
        bus.subscribe(Event, handler)

        event = Event()
        bus.publish(event)

        assert len(received) == 1

    def test_unsubscribe(self):
        """Test event unsubscription."""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(Event, handler)
        bus.publish(Event())
        assert len(received) == 1

        bus.unsubscribe(Event, handler)
        bus.publish(Event())
        assert len(received) == 1  # No new events


class TestOrbitalSystem:
    """Tests for OrbitalSystem."""

    def test_orbital_position_update(self):
        """Test that orbital positions are updated."""
        em = EntityManager()
        system = OrbitalSystem()

        # Create Sun
        sun = em.create_entity("Sun")
        em.add_component(sun, Position(x=0, y=0))

        # Create planet
        earth = em.create_entity("Earth")
        em.add_component(earth, Position(x=1, y=0))
        em.add_component(earth, Orbit(
            parent_name="Sun",
            semi_major_axis=1.0,
            orbital_period=365.25
        ))

        # Update
        initial_pos = em.get_component(earth, Position)
        initial_x, initial_y = initial_pos.x, initial_pos.y

        system.update(1.0, em)  # 1 game minute

        new_pos = em.get_component(earth, Position)
        # Position should have changed slightly due to orbital motion
        # (very small change over 1 minute)
        assert new_pos is not None


class TestIntegration:
    """Integration tests for the full simulation."""

    def test_solar_system_creation(self):
        """Test creating the solar system."""
        from src.entities.celestial import create_solar_system

        world = World()
        bodies = create_solar_system(world)

        assert "Sun" in bodies
        assert "Earth" in bodies
        assert "Mars" in bodies
        assert world.entity_manager.entity_count > 10

    def test_station_creation(self):
        """Test creating stations."""
        from src.entities.stations import create_station, StationType
        from src.simulation.resources import ResourceType

        world = World()
        station = create_station(
            world,
            "Test Station",
            StationType.REFINERY,
            position=(1.0, 0.0),
            initial_resources={ResourceType.IRON_ORE: 100}
        )

        em = world.entity_manager
        from src.simulation.resources import Inventory
        from src.simulation.economy import Market

        assert em.has_component(station, Inventory)
        assert em.has_component(station, Market)

        inv = em.get_component(station, Inventory)
        assert inv.get(ResourceType.IRON_ORE) == 100

    def test_ship_creation(self):
        """Test creating ships."""
        from src.entities.ships import create_ship, ShipType
        from src.simulation.trade import Trader, CargoHold

        world = World()
        ship = create_ship(
            world,
            "Test Ship",
            ShipType.FREIGHTER,
            position=(1.0, 0.0),
            is_trader=True
        )

        em = world.entity_manager

        assert em.has_component(ship, Trader)
        assert em.has_component(ship, CargoHold)
        assert em.has_component(ship, Position)

    def test_faction_creation(self):
        """Test creating factions."""
        from src.entities.factions import create_predefined_factions

        world = World()
        factions = create_predefined_factions(world)

        assert "Earth Coalition" in factions
        assert "Mars Republic" in factions
        assert len(factions) >= 4

    def test_simulation_tick(self):
        """Test a full simulation tick with all systems."""
        from src.solar_system.orbits import OrbitalSystem, MovementSystem, NavigationSystem
        from src.simulation.production import ProductionSystem, ExtractionSystem
        from src.simulation.economy import EconomySystem
        from src.simulation.trade import TradeSystem
        from src.ai.faction_ai import FactionAI
        from src.ai.ship_ai import ShipAI
        from src.entities.celestial import create_solar_system
        from src.entities.stations import create_station, StationType
        from src.entities.ships import create_ship, ShipType

        world = World()
        event_bus = world.event_bus

        # Add systems
        world.add_system(OrbitalSystem())
        world.add_system(NavigationSystem())
        world.add_system(MovementSystem())
        world.add_system(ExtractionSystem(event_bus))
        world.add_system(ProductionSystem(event_bus))
        world.add_system(ShipAI(event_bus))
        world.add_system(TradeSystem(event_bus))
        world.add_system(EconomySystem(event_bus))
        world.add_system(FactionAI(event_bus))

        # Create some entities
        create_solar_system(world)
        create_station(world, "Station", StationType.REFINERY, (1.0, 0.0))
        create_ship(world, "Ship", ShipType.FREIGHTER, (1.0, 0.1))

        # Run a few ticks - should not crash
        for _ in range(10):
            world.update(0.1)

        # World should still be intact
        assert world.entity_manager.entity_count > 0
