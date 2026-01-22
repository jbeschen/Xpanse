"""Resource definitions and inventory management."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class ResourceType(Enum):
    """All resource types in the game, organized by tier."""
    # Tier 0 - Raw materials (extracted from celestial bodies)
    WATER_ICE = "water_ice"
    IRON_ORE = "iron_ore"
    SILICATES = "silicates"
    RARE_EARTHS = "rare_earths"
    HELIUM3 = "helium3"

    # Tier 1 - Basic processed materials
    REFINED_METAL = "refined_metal"
    SILICON = "silicon"
    WATER = "water"
    FUEL = "fuel"

    # Tier 2 - Advanced components
    ELECTRONICS = "electronics"
    MACHINERY = "machinery"
    LIFE_SUPPORT = "life_support"

    # Tier 3 - Complex products
    HABITAT_MODULES = "habitat_modules"
    SHIP_COMPONENTS = "ship_components"
    ADVANCED_TECH = "advanced_tech"


# Resource tier mapping
RESOURCE_TIER: dict[ResourceType, int] = {
    ResourceType.WATER_ICE: 0,
    ResourceType.IRON_ORE: 0,
    ResourceType.SILICATES: 0,
    ResourceType.RARE_EARTHS: 0,
    ResourceType.HELIUM3: 0,
    ResourceType.REFINED_METAL: 1,
    ResourceType.SILICON: 1,
    ResourceType.WATER: 1,
    ResourceType.FUEL: 1,
    ResourceType.ELECTRONICS: 2,
    ResourceType.MACHINERY: 2,
    ResourceType.LIFE_SUPPORT: 2,
    ResourceType.HABITAT_MODULES: 3,
    ResourceType.SHIP_COMPONENTS: 3,
    ResourceType.ADVANCED_TECH: 3,
}

# Base prices (in credits) by resource
BASE_PRICES: dict[ResourceType, float] = {
    ResourceType.WATER_ICE: 10,
    ResourceType.IRON_ORE: 15,
    ResourceType.SILICATES: 8,
    ResourceType.RARE_EARTHS: 50,
    ResourceType.HELIUM3: 100,
    ResourceType.REFINED_METAL: 40,
    ResourceType.SILICON: 35,
    ResourceType.WATER: 25,
    ResourceType.FUEL: 60,
    ResourceType.ELECTRONICS: 150,
    ResourceType.MACHINERY: 200,
    ResourceType.LIFE_SUPPORT: 180,
    ResourceType.HABITAT_MODULES: 500,
    ResourceType.SHIP_COMPONENTS: 800,
    ResourceType.ADVANCED_TECH: 1000,
}


@dataclass
class Inventory:
    """Component that stores resources."""
    resources: dict[ResourceType, float] = field(default_factory=dict)
    capacity: float = 1000.0  # Maximum total storage

    def add(self, resource: ResourceType, amount: float) -> float:
        """Add resources. Returns actual amount added (limited by capacity)."""
        current_total = self.total_amount
        available_space = self.capacity - current_total
        actual_add = min(amount, available_space)

        if actual_add > 0:
            self.resources[resource] = self.resources.get(resource, 0.0) + actual_add

        return actual_add

    def remove(self, resource: ResourceType, amount: float) -> float:
        """Remove resources. Returns actual amount removed."""
        current = self.resources.get(resource, 0.0)
        actual_remove = min(amount, current)

        if actual_remove > 0:
            self.resources[resource] = current - actual_remove
            if self.resources[resource] <= 0:
                del self.resources[resource]

        return actual_remove

    def get(self, resource: ResourceType) -> float:
        """Get amount of a specific resource."""
        return self.resources.get(resource, 0.0)

    def has(self, resource: ResourceType, amount: float) -> bool:
        """Check if inventory has at least the specified amount."""
        return self.get(resource) >= amount

    def has_all(self, requirements: dict[ResourceType, float]) -> bool:
        """Check if inventory has all required resources."""
        return all(self.has(r, a) for r, a in requirements.items())

    @property
    def total_amount(self) -> float:
        """Total amount of all resources."""
        return sum(self.resources.values())

    @property
    def free_space(self) -> float:
        """Available storage space."""
        return max(0.0, self.capacity - self.total_amount)

    @property
    def is_full(self) -> bool:
        """Check if inventory is at capacity."""
        return self.total_amount >= self.capacity

    @property
    def is_empty(self) -> bool:
        """Check if inventory is empty."""
        return self.total_amount == 0


@dataclass
class ResourceDeposit:
    """Component for celestial bodies with extractable resources."""
    resource_type: ResourceType
    richness: float = 1.0  # Multiplier for extraction rate
    remaining: float = 1000000.0  # Total extractable amount (very large)
    extraction_difficulty: float = 1.0  # Cost multiplier for extraction

    def extract(self, amount: float) -> float:
        """Extract resources from deposit. Returns actual extracted amount."""
        actual = min(amount * self.richness, self.remaining)
        self.remaining -= actual
        return actual

    @property
    def is_depleted(self) -> bool:
        """Check if deposit is depleted."""
        return self.remaining <= 0


@dataclass
class ResourceKnowledge:
    """Singleton component tracking which celestial bodies have been surveyed.

    In the X-Drive era, only Earth-local bodies (Moon, Mars) have public resource data.
    Other bodies must be probed/surveyed before their resources are known.
    """
    surveyed_bodies: set[str] = field(default_factory=set)
    # Bodies with public data available from the start
    PUBLIC_DATA_BODIES: tuple[str, ...] = ("Moon", "Mars", "Earth")

    def is_known(self, body_name: str) -> bool:
        """Check if a body's resources are known."""
        return body_name in self.PUBLIC_DATA_BODIES or body_name in self.surveyed_bodies

    def survey(self, body_name: str) -> bool:
        """Mark a body as surveyed. Returns True if newly discovered."""
        if body_name in self.PUBLIC_DATA_BODIES:
            return False  # Already public
        if body_name in self.surveyed_bodies:
            return False  # Already surveyed
        self.surveyed_bodies.add(body_name)
        return True

    def get_all_known(self) -> set[str]:
        """Get all known body names."""
        return set(self.PUBLIC_DATA_BODIES) | self.surveyed_bodies
