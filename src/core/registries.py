"""Data-driven registries for resources and recipes.

Load game data from JSON files, providing a centralized way to access
resource and recipe definitions. Adding new resources/recipes requires
only changes to the JSON files, no code changes needed.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# Path to data directory
DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass(frozen=True)
class ResourceInfo:
    """Immutable resource definition loaded from JSON."""
    id: str
    name: str
    tier: int
    base_price: float
    category: str
    description: str = ""
    unit: str = "units"


@dataclass(frozen=True)
class RecipeInfo:
    """Immutable recipe definition loaded from JSON."""
    id: str
    name: str
    category: str
    duration: float
    inputs: dict[str, float]
    outputs: dict[str, float]
    station_types: tuple[str, ...]


class ResourceRegistry:
    """Singleton registry for resource definitions.

    Load resources from JSON and provide query methods.
    Thread-safe for reads after initialization.
    """
    _instance: ResourceRegistry | None = None
    _initialized: bool = False

    def __new__(cls) -> ResourceRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if ResourceRegistry._initialized:
            return

        self._resources: dict[str, ResourceInfo] = {}
        self._by_tier: dict[int, list[str]] = {}
        self._by_category: dict[str, list[str]] = {}
        self._categories: dict[str, dict] = {}
        self._tiers: dict[int, dict] = {}

        self._load_from_json()
        ResourceRegistry._initialized = True

    def _load_from_json(self) -> None:
        """Load resource definitions from JSON file."""
        json_path = DATA_DIR / "resources.json"
        if not json_path.exists():
            return

        with open(json_path, "r") as f:
            data = json.load(f)

        # Load resources
        for res_id, res_data in data.get("resources", {}).items():
            info = ResourceInfo(
                id=res_id,
                name=res_data.get("name", res_id),
                tier=res_data.get("tier", 0),
                base_price=res_data.get("base_price", 100.0),
                category=res_data.get("category", "raw"),
                description=res_data.get("description", ""),
                unit=res_data.get("unit", "units"),
            )
            self._resources[res_id] = info

            # Index by tier
            if info.tier not in self._by_tier:
                self._by_tier[info.tier] = []
            self._by_tier[info.tier].append(res_id)

            # Index by category
            if info.category not in self._by_category:
                self._by_category[info.category] = []
            self._by_category[info.category].append(res_id)

        # Load category metadata
        self._categories = data.get("categories", {})

        # Load tier metadata
        for tier_str, tier_data in data.get("tiers", {}).items():
            self._tiers[int(tier_str)] = tier_data

    def get(self, resource_id: str) -> ResourceInfo | None:
        """Get resource info by ID."""
        return self._resources.get(resource_id)

    def get_tier(self, resource_id: str) -> int:
        """Get resource tier by ID. Returns -1 if not found."""
        info = self._resources.get(resource_id)
        return info.tier if info else -1

    def get_base_price(self, resource_id: str) -> float:
        """Get resource base price. Returns 100.0 if not found."""
        info = self._resources.get(resource_id)
        return info.base_price if info else 100.0

    def get_by_tier(self, tier: int) -> list[str]:
        """Get all resource IDs of a specific tier."""
        return self._by_tier.get(tier, []).copy()

    def get_by_category(self, category: str) -> list[str]:
        """Get all resource IDs in a category."""
        return self._by_category.get(category, []).copy()

    def get_all_ids(self) -> list[str]:
        """Get all resource IDs."""
        return list(self._resources.keys())

    def get_all(self) -> Iterator[ResourceInfo]:
        """Iterate over all resource definitions."""
        return iter(self._resources.values())

    def exists(self, resource_id: str) -> bool:
        """Check if a resource ID exists."""
        return resource_id in self._resources

    def get_tier_info(self, tier: int) -> dict | None:
        """Get tier metadata (name, color, etc.)."""
        return self._tiers.get(tier)

    def get_category_info(self, category: str) -> dict | None:
        """Get category metadata."""
        return self._categories.get(category)

    @classmethod
    def reload(cls) -> None:
        """Force reload from JSON (for development/testing)."""
        cls._initialized = False
        if cls._instance:
            cls._instance.__init__()


class RecipeRegistry:
    """Singleton registry for recipe definitions.

    Load recipes from JSON and provide query methods.
    Thread-safe for reads after initialization.
    """
    _instance: RecipeRegistry | None = None
    _initialized: bool = False

    def __new__(cls) -> RecipeRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if RecipeRegistry._initialized:
            return

        self._recipes: dict[str, RecipeInfo] = {}
        self._by_category: dict[str, list[str]] = {}
        self._by_station_type: dict[str, list[str]] = {}
        self._station_type_categories: dict[str, list[str]] = {}

        self._load_from_json()
        RecipeRegistry._initialized = True

    def _load_from_json(self) -> None:
        """Load recipe definitions from JSON file."""
        json_path = DATA_DIR / "recipes.json"
        if not json_path.exists():
            return

        with open(json_path, "r") as f:
            data = json.load(f)

        # Load recipes
        for recipe_id, recipe_data in data.get("recipes", {}).items():
            station_types = tuple(recipe_data.get("station_types", []))

            info = RecipeInfo(
                id=recipe_id,
                name=recipe_data.get("name", recipe_id),
                category=recipe_data.get("category", "general"),
                duration=recipe_data.get("duration", 10.0),
                inputs=dict(recipe_data.get("inputs", {})),
                outputs=dict(recipe_data.get("outputs", {})),
                station_types=station_types,
            )
            self._recipes[recipe_id] = info

            # Index by category
            if info.category not in self._by_category:
                self._by_category[info.category] = []
            self._by_category[info.category].append(recipe_id)

            # Index by station type
            for station_type in station_types:
                if station_type not in self._by_station_type:
                    self._by_station_type[station_type] = []
                self._by_station_type[station_type].append(recipe_id)

        # Load station type to category mappings
        self._station_type_categories = data.get("station_type_categories", {})

    def get(self, recipe_id: str) -> RecipeInfo | None:
        """Get recipe info by ID."""
        return self._recipes.get(recipe_id)

    def get_for_station(self, station_type: str) -> list[str]:
        """Get all recipe IDs valid for a station type."""
        return self._by_station_type.get(station_type, []).copy()

    def get_by_category(self, category: str) -> list[str]:
        """Get all recipe IDs in a category."""
        return self._by_category.get(category, []).copy()

    def get_all_ids(self) -> list[str]:
        """Get all recipe IDs."""
        return list(self._recipes.keys())

    def get_all(self) -> Iterator[RecipeInfo]:
        """Iterate over all recipe definitions."""
        return iter(self._recipes.values())

    def exists(self, recipe_id: str) -> bool:
        """Check if a recipe ID exists."""
        return recipe_id in self._recipes

    def get_station_categories(self, station_type: str) -> list[str]:
        """Get recipe categories available at a station type."""
        return self._station_type_categories.get(station_type, []).copy()

    def get_input_resources(self, station_type: str) -> set[str]:
        """Get all input resources needed by recipes at a station type."""
        inputs = set()
        for recipe_id in self.get_for_station(station_type):
            recipe = self._recipes.get(recipe_id)
            if recipe:
                inputs.update(recipe.inputs.keys())
        return inputs

    def get_output_resources(self, station_type: str) -> set[str]:
        """Get all output resources produced by recipes at a station type."""
        outputs = set()
        for recipe_id in self.get_for_station(station_type):
            recipe = self._recipes.get(recipe_id)
            if recipe:
                outputs.update(recipe.outputs.keys())
        return outputs

    @classmethod
    def reload(cls) -> None:
        """Force reload from JSON (for development/testing)."""
        cls._initialized = False
        if cls._instance:
            cls._instance.__init__()


# Convenience functions for quick access
def get_resource_registry() -> ResourceRegistry:
    """Get the singleton ResourceRegistry instance."""
    return ResourceRegistry()


def get_recipe_registry() -> RecipeRegistry:
    """Get the singleton RecipeRegistry instance."""
    return RecipeRegistry()
