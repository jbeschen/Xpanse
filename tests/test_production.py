"""Tests for the production system."""
import pytest
from src.core.world import World
from src.core.events import EventBus
from src.simulation.resources import ResourceType, Inventory, ResourceDeposit
from src.simulation.production import (
    Recipe, Producer, Extractor, RECIPES,
    ProductionSystem, ExtractionSystem
)


class TestRecipe:
    """Tests for Recipe class."""

    def test_can_produce_with_resources(self):
        """Test checking if production is possible."""
        recipe = RECIPES["refine_metal"]
        inv = Inventory(capacity=1000)
        inv.add(ResourceType.IRON_ORE, 10)

        assert recipe.can_produce(inv)

    def test_cannot_produce_without_resources(self):
        """Test that production fails without resources."""
        recipe = RECIPES["refine_metal"]
        inv = Inventory(capacity=1000)

        assert not recipe.can_produce(inv)

    def test_consume_inputs(self):
        """Test consuming recipe inputs."""
        recipe = RECIPES["refine_metal"]
        inv = Inventory(capacity=1000)
        inv.add(ResourceType.IRON_ORE, 10)

        success = recipe.consume_inputs(inv)

        assert success
        assert inv.get(ResourceType.IRON_ORE) == 8  # 10 - 2

    def test_produce_outputs(self):
        """Test producing recipe outputs."""
        recipe = RECIPES["refine_metal"]
        inv = Inventory(capacity=1000)

        produced = recipe.produce_outputs(inv)

        assert ResourceType.REFINED_METAL in produced
        assert produced[ResourceType.REFINED_METAL] == 1.0
        assert inv.get(ResourceType.REFINED_METAL) == 1.0


class TestProducer:
    """Tests for Producer component."""

    def test_set_valid_recipe(self):
        """Test setting a valid recipe."""
        producer = Producer(recipes=["refine_metal", "process_silicon"])

        success = producer.set_recipe("refine_metal")

        assert success
        assert producer.active_recipe == "refine_metal"
        assert producer.progress == 0.0

    def test_set_invalid_recipe(self):
        """Test that invalid recipes are rejected."""
        producer = Producer(recipes=["refine_metal"])

        success = producer.set_recipe("nonexistent_recipe")

        assert not success
        assert producer.active_recipe is None

    def test_get_active_recipe(self):
        """Test getting the active recipe object."""
        producer = Producer(recipes=["refine_metal"])
        producer.set_recipe("refine_metal")

        recipe = producer.get_active_recipe()

        assert recipe is not None
        assert recipe.id == "refine_metal"


class TestResourceDeposit:
    """Tests for ResourceDeposit component."""

    def test_extract_resources(self):
        """Test extracting resources from deposit."""
        deposit = ResourceDeposit(
            resource_type=ResourceType.IRON_ORE,
            richness=1.0,
            remaining=1000
        )

        extracted = deposit.extract(10)

        assert extracted == 10
        assert deposit.remaining == 990

    def test_extract_with_richness(self):
        """Test that richness affects extraction."""
        deposit = ResourceDeposit(
            resource_type=ResourceType.IRON_ORE,
            richness=2.0,
            remaining=1000
        )

        extracted = deposit.extract(10)

        assert extracted == 20  # 10 * 2.0 richness
        assert deposit.remaining == 980

    def test_deposit_depletion(self):
        """Test deposit depletion."""
        deposit = ResourceDeposit(
            resource_type=ResourceType.IRON_ORE,
            richness=1.0,
            remaining=5
        )

        extracted = deposit.extract(10)

        assert extracted == 5
        assert deposit.is_depleted


class TestProductionSystem:
    """Tests for ProductionSystem."""

    def test_production_cycle(self):
        """Test a full production cycle."""
        world = World()
        event_bus = world.event_bus
        system = ProductionSystem(event_bus)

        # Create a producer entity
        entity = world.create_entity("Refinery")
        em = world.entity_manager

        producer = Producer(
            recipes=["refine_metal"],
            active_recipe="refine_metal",
            efficiency=1.0,
            auto_produce=True
        )
        em.add_component(entity, producer)

        inventory = Inventory(capacity=1000)
        inventory.add(ResourceType.IRON_ORE, 100)
        em.add_component(entity, inventory)

        # Simulate production over time
        recipe = RECIPES["refine_metal"]

        # First update consumes inputs
        system.update(1.0, em)
        assert inventory.get(ResourceType.IRON_ORE) == 98  # 2 consumed

        # Progress through production
        for _ in range(int(recipe.duration)):
            system.update(1.0, em)

        # Should have produced output
        assert inventory.get(ResourceType.REFINED_METAL) >= 1.0


class TestExtractionSystem:
    """Tests for ExtractionSystem."""

    def test_extraction(self):
        """Test resource extraction."""
        world = World()
        event_bus = world.event_bus
        system = ExtractionSystem(event_bus)

        # Create an extractor entity
        entity = world.create_entity("Mine")
        em = world.entity_manager

        extractor = Extractor(
            extraction_rate=10.0,
            efficiency=1.0,
            active=True
        )
        em.add_component(entity, extractor)

        deposit = ResourceDeposit(
            resource_type=ResourceType.IRON_ORE,
            richness=1.0,
            remaining=1000,
            extraction_difficulty=1.0
        )
        em.add_component(entity, deposit)

        inventory = Inventory(capacity=1000)
        em.add_component(entity, inventory)

        # Run extraction
        system.update(1.0, em)

        # Should have extracted resources
        assert inventory.get(ResourceType.IRON_ORE) == 10.0

    def test_extraction_respects_difficulty(self):
        """Test that extraction difficulty affects rate."""
        world = World()
        event_bus = world.event_bus
        system = ExtractionSystem(event_bus)

        entity = world.create_entity("Mine")
        em = world.entity_manager

        extractor = Extractor(extraction_rate=10.0, efficiency=1.0, active=True)
        em.add_component(entity, extractor)

        deposit = ResourceDeposit(
            resource_type=ResourceType.IRON_ORE,
            richness=1.0,
            remaining=1000,
            extraction_difficulty=2.0  # Twice as hard
        )
        em.add_component(entity, deposit)

        inventory = Inventory(capacity=1000)
        em.add_component(entity, inventory)

        system.update(1.0, em)

        # Should extract half due to difficulty
        assert inventory.get(ResourceType.IRON_ORE) == 5.0

    def test_inactive_extractor(self):
        """Test that inactive extractors don't work."""
        world = World()
        event_bus = world.event_bus
        system = ExtractionSystem(event_bus)

        entity = world.create_entity("Mine")
        em = world.entity_manager

        extractor = Extractor(extraction_rate=10.0, efficiency=1.0, active=False)
        em.add_component(entity, extractor)

        deposit = ResourceDeposit(
            resource_type=ResourceType.IRON_ORE,
            richness=1.0,
            remaining=1000
        )
        em.add_component(entity, deposit)

        inventory = Inventory(capacity=1000)
        em.add_component(entity, inventory)

        system.update(1.0, em)

        assert inventory.get(ResourceType.IRON_ORE) == 0
