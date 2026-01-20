"""Manufacturing and production chains."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.ecs import Component, System, EntityManager
from ..core.events import EventBus, ProductionCompleteEvent
from .resources import ResourceType, Inventory

if TYPE_CHECKING:
    pass


@dataclass
class Recipe:
    """A production recipe that transforms inputs into outputs."""
    id: str
    name: str
    inputs: dict[ResourceType, float]
    outputs: dict[ResourceType, float]
    duration: float  # Seconds to complete one cycle
    category: str = "general"

    def can_produce(self, inventory: Inventory) -> bool:
        """Check if inventory has all required inputs."""
        return inventory.has_all(self.inputs)

    def consume_inputs(self, inventory: Inventory) -> bool:
        """Consume inputs from inventory. Returns True if successful."""
        if not self.can_produce(inventory):
            return False

        for resource, amount in self.inputs.items():
            inventory.remove(resource, amount)
        return True

    def produce_outputs(self, inventory: Inventory) -> dict[ResourceType, float]:
        """Add outputs to inventory. Returns actual amounts produced."""
        produced = {}
        for resource, amount in self.outputs.items():
            actual = inventory.add(resource, amount)
            produced[resource] = actual
        return produced


# Define all production recipes
RECIPES: dict[str, Recipe] = {
    # Tier 0 -> Tier 1 (Refining)
    "refine_metal": Recipe(
        id="refine_metal",
        name="Refine Metal",
        inputs={ResourceType.IRON_ORE: 2.0},
        outputs={ResourceType.REFINED_METAL: 1.0},
        duration=10.0,
        category="refinery"
    ),
    "process_silicon": Recipe(
        id="process_silicon",
        name="Process Silicon",
        inputs={ResourceType.SILICATES: 2.0},
        outputs={ResourceType.SILICON: 1.0},
        duration=10.0,
        category="refinery"
    ),
    "purify_water": Recipe(
        id="purify_water",
        name="Purify Water",
        inputs={ResourceType.WATER_ICE: 1.5},
        outputs={ResourceType.WATER: 1.0},
        duration=5.0,
        category="refinery"
    ),
    "produce_fuel": Recipe(
        id="produce_fuel",
        name="Produce Fuel",
        inputs={ResourceType.WATER: 1.0, ResourceType.HELIUM3: 0.5},
        outputs={ResourceType.FUEL: 1.0},
        duration=15.0,
        category="refinery"
    ),

    # Tier 1 -> Tier 2 (Manufacturing)
    "manufacture_electronics": Recipe(
        id="manufacture_electronics",
        name="Manufacture Electronics",
        inputs={ResourceType.SILICON: 2.0, ResourceType.RARE_EARTHS: 0.5},
        outputs={ResourceType.ELECTRONICS: 1.0},
        duration=20.0,
        category="factory"
    ),
    "manufacture_machinery": Recipe(
        id="manufacture_machinery",
        name="Manufacture Machinery",
        inputs={ResourceType.REFINED_METAL: 3.0, ResourceType.ELECTRONICS: 0.5},
        outputs={ResourceType.MACHINERY: 1.0},
        duration=25.0,
        category="factory"
    ),
    "manufacture_life_support": Recipe(
        id="manufacture_life_support",
        name="Manufacture Life Support",
        inputs={ResourceType.WATER: 2.0, ResourceType.ELECTRONICS: 1.0},
        outputs={ResourceType.LIFE_SUPPORT: 1.0},
        duration=20.0,
        category="factory"
    ),

    # Tier 2 -> Tier 3 (Advanced Manufacturing)
    "build_habitat_module": Recipe(
        id="build_habitat_module",
        name="Build Habitat Module",
        inputs={
            ResourceType.REFINED_METAL: 5.0,
            ResourceType.LIFE_SUPPORT: 2.0,
            ResourceType.MACHINERY: 1.0
        },
        outputs={ResourceType.HABITAT_MODULES: 1.0},
        duration=60.0,
        category="advanced_factory"
    ),
    "build_ship_components": Recipe(
        id="build_ship_components",
        name="Build Ship Components",
        inputs={
            ResourceType.REFINED_METAL: 4.0,
            ResourceType.ELECTRONICS: 2.0,
            ResourceType.MACHINERY: 2.0
        },
        outputs={ResourceType.SHIP_COMPONENTS: 1.0},
        duration=45.0,
        category="shipyard"
    ),
    "research_advanced_tech": Recipe(
        id="research_advanced_tech",
        name="Research Advanced Tech",
        inputs={
            ResourceType.ELECTRONICS: 3.0,
            ResourceType.RARE_EARTHS: 2.0
        },
        outputs={ResourceType.ADVANCED_TECH: 1.0},
        duration=90.0,
        category="research"
    ),
}


@dataclass
class Producer(Component):
    """Component for entities that produce resources."""
    recipes: list[str] = field(default_factory=list)  # Recipe IDs this producer can use
    active_recipe: str | None = None
    progress: float = 0.0  # Progress towards current recipe completion
    efficiency: float = 1.0  # Production speed multiplier
    auto_produce: bool = True  # Automatically start new cycles

    def get_active_recipe(self) -> Recipe | None:
        """Get the currently active recipe."""
        if self.active_recipe and self.active_recipe in RECIPES:
            return RECIPES[self.active_recipe]
        return None

    def set_recipe(self, recipe_id: str) -> bool:
        """Set the active recipe. Returns True if valid."""
        if recipe_id in self.recipes and recipe_id in RECIPES:
            self.active_recipe = recipe_id
            self.progress = 0.0
            return True
        return False


@dataclass
class Extractor(Component):
    """Component for mining operations that extract raw resources."""
    extraction_rate: float = 1.0  # Units per second
    efficiency: float = 1.0
    active: bool = True


class ProductionSystem(System):
    """System that processes production at stations."""

    priority = 20  # Run before economy

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update all producers."""
        for entity, producer in entity_manager.get_all_components(Producer):
            inventory = entity_manager.get_component(entity, Inventory)
            if not inventory:
                continue

            self._update_producer(entity, producer, inventory, dt)

    def _update_producer(
        self,
        entity,
        producer: Producer,
        inventory: Inventory,
        dt: float
    ) -> None:
        """Update a single producer."""
        recipe = producer.get_active_recipe()

        if not recipe:
            # Try to auto-select a recipe
            if producer.auto_produce and producer.recipes:
                for recipe_id in producer.recipes:
                    if recipe_id in RECIPES:
                        test_recipe = RECIPES[recipe_id]
                        if test_recipe.can_produce(inventory):
                            producer.set_recipe(recipe_id)
                            recipe = test_recipe
                            break
            if not recipe:
                return

        # Check if we can start/continue production
        if producer.progress == 0:
            if not recipe.consume_inputs(inventory):
                return  # Not enough inputs

        # Progress production
        producer.progress += dt * producer.efficiency

        # Check for completion
        if producer.progress >= recipe.duration:
            produced = recipe.produce_outputs(inventory)
            producer.progress = 0.0

            # Fire completion event
            self.event_bus.publish(ProductionCompleteEvent(
                entity_id=entity.id,
                recipe_id=recipe.id,
                outputs={r.value: a for r, a in produced.items()}
            ))

            # If auto-produce, check if we can start another cycle
            if producer.auto_produce and recipe.can_produce(inventory):
                recipe.consume_inputs(inventory)


class ExtractionSystem(System):
    """System that handles resource extraction from deposits."""

    priority = 10  # Run first

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update all extractors."""
        from .resources import ResourceDeposit

        for entity, extractor in entity_manager.get_all_components(Extractor):
            if not extractor.active:
                continue

            inventory = entity_manager.get_component(entity, Inventory)
            deposit = entity_manager.get_component(entity, ResourceDeposit)

            if not inventory or not deposit:
                continue

            if deposit.is_depleted:
                continue

            # Calculate extraction amount
            amount = extractor.extraction_rate * extractor.efficiency * dt
            amount /= deposit.extraction_difficulty

            # Extract and add to inventory
            extracted = deposit.extract(amount)
            if extracted > 0:
                inventory.add(deposit.resource_type, extracted)
