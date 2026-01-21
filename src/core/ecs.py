"""Entity-Component-System base classes."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar, Generic, Iterator
from uuid import UUID, uuid4


@dataclass
class Component:
    """Base class for all components. Components are pure data containers."""
    pass


C = TypeVar('C', bound=Component)


@dataclass
class Entity:
    """An entity is a unique identifier that groups components together."""
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    tags: set[str] = field(default_factory=set)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Entity):
            return self.id == other.id
        return False


class EntityManager:
    """Manages entities and their components."""

    def __init__(self) -> None:
        self._entities: dict[UUID, Entity] = {}
        self._components: dict[type[Component], dict[UUID, Component]] = {}
        self._entity_components: dict[UUID, set[type[Component]]] = {}

    def create_entity(
        self,
        name: str = "",
        tags: set[str] | None = None,
        entity_id: UUID | None = None
    ) -> Entity:
        """Create a new entity.

        Args:
            name: Optional name for the entity
            tags: Optional set of tags
            entity_id: Optional specific ID (used when loading saves)
        """
        if entity_id:
            entity = Entity(id=entity_id, name=name, tags=tags or set())
        else:
            entity = Entity(name=name, tags=tags or set())
        self._entities[entity.id] = entity
        self._entity_components[entity.id] = set()
        return entity

    def clear(self) -> None:
        """Clear all entities and components."""
        self._entities.clear()
        self._components.clear()
        self._entity_components.clear()

    def destroy_entity(self, entity: Entity) -> None:
        """Remove an entity and all its components."""
        if entity.id not in self._entities:
            return

        # Remove all components
        for component_type in self._entity_components.get(entity.id, set()).copy():
            self.remove_component(entity, component_type)

        del self._entities[entity.id]
        del self._entity_components[entity.id]

    def add_component(self, entity: Entity, component: Component) -> None:
        """Add a component to an entity."""
        component_type = type(component)

        if component_type not in self._components:
            self._components[component_type] = {}

        self._components[component_type][entity.id] = component
        self._entity_components[entity.id].add(component_type)

    def remove_component(self, entity: Entity, component_type: type[Component]) -> None:
        """Remove a component from an entity."""
        if component_type in self._components:
            self._components[component_type].pop(entity.id, None)
        self._entity_components[entity.id].discard(component_type)

    def get_component(self, entity: Entity, component_type: type[C]) -> C | None:
        """Get a specific component from an entity."""
        if component_type not in self._components:
            return None
        return self._components[component_type].get(entity.id)  # type: ignore

    def has_component(self, entity: Entity, component_type: type[Component]) -> bool:
        """Check if an entity has a specific component."""
        return component_type in self._entity_components.get(entity.id, set())

    def get_entities_with(self, *component_types: type[Component]) -> Iterator[Entity]:
        """Get all entities that have all specified component types."""
        if not component_types:
            yield from self._entities.values()
            return

        for entity_id, entity in self._entities.items():
            entity_comps = self._entity_components.get(entity_id, set())
            if all(ct in entity_comps for ct in component_types):
                yield entity

    def get_entities_with_tag(self, tag: str) -> Iterator[Entity]:
        """Get all entities with a specific tag."""
        for entity in self._entities.values():
            if tag in entity.tags:
                yield entity

    def get_all_components(self, component_type: type[C]) -> Iterator[tuple[Entity, C]]:
        """Get all components of a specific type with their entities."""
        if component_type not in self._components:
            return

        for entity_id, component in self._components[component_type].items():
            entity = self._entities.get(entity_id)
            if entity:
                yield entity, component  # type: ignore

    def get_entity(self, entity_id: UUID) -> Entity | None:
        """Get an entity by its ID."""
        return self._entities.get(entity_id)

    def get_entity_by_name(self, name: str) -> Entity | None:
        """Get the first entity with a specific name."""
        for entity in self._entities.values():
            if entity.name == name:
                return entity
        return None

    @property
    def entity_count(self) -> int:
        """Return the number of entities."""
        return len(self._entities)


class System(ABC):
    """Base class for all systems. Systems contain logic that operates on components."""

    priority: int = 0  # Lower numbers run first

    @abstractmethod
    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update the system. Called every simulation tick.

        Args:
            dt: Delta time since last update in seconds
            entity_manager: The entity manager to query for entities/components
        """
        pass

    def on_entity_created(self, entity: Entity, entity_manager: EntityManager) -> None:
        """Called when a new entity is created. Override for reactive behavior."""
        pass

    def on_entity_destroyed(self, entity: Entity, entity_manager: EntityManager) -> None:
        """Called when an entity is destroyed. Override for cleanup."""
        pass
