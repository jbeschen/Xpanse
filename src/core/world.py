"""World state container."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .ecs import EntityManager, System, Entity
from .events import EventBus, EntityCreatedEvent, EntityDestroyedEvent

if TYPE_CHECKING:
    from uuid import UUID


@dataclass
class GameTime:
    """Tracks simulation time."""
    total_days: float = 0.0
    day: int = 1
    year: int = 2150

    # Time scale: base rate that gets multiplied by speed setting
    # At 1x speed: 1 real second = 1 game day
    # At default 10x speed: 1 real second = 10 game days (~1/3 month)
    # Can go up to 100x for fast-forward
    DAYS_PER_REAL_SECOND: float = 1.0  # Base rate, multiplied by speed
    DAYS_PER_YEAR: int = 365

    def advance(self, dt: float, speed: float = 1.0) -> None:
        """Advance game time by dt real seconds."""
        game_days = dt * speed * self.DAYS_PER_REAL_SECOND
        self.total_days += game_days

        # Calculate day/year
        self.day = int(self.total_days % self.DAYS_PER_YEAR) + 1
        self.year = 2150 + int(self.total_days / self.DAYS_PER_YEAR)

    @property
    def month(self) -> int:
        """Approximate month (1-12)."""
        return ((self.day - 1) // 30) + 1

    @property
    def total_years(self) -> float:
        """Total years elapsed."""
        return self.total_days / self.DAYS_PER_YEAR

    def __str__(self) -> str:
        return f"Year {self.year}, Day {self.day}"


class World:
    """Main world state container. Coordinates entities, systems, and events."""

    def __init__(self) -> None:
        self.entity_manager = EntityManager()
        self.event_bus = EventBus()
        self.game_time = GameTime()
        self._systems: list[System] = []
        self._paused: bool = False
        self._speed: float = 1.0  # Default to 1x speed (1 day/second)

    def add_system(self, system: System) -> None:
        """Add a system to the world."""
        self._systems.append(system)
        self._systems.sort(key=lambda s: s.priority)

    def remove_system(self, system: System) -> None:
        """Remove a system from the world."""
        self._systems.remove(system)

    def create_entity(self, name: str = "", tags: set[str] | None = None) -> Entity:
        """Create a new entity and fire creation event."""
        entity = self.entity_manager.create_entity(name, tags)

        # Notify systems
        for system in self._systems:
            system.on_entity_created(entity, self.entity_manager)

        # Fire event
        self.event_bus.publish(EntityCreatedEvent(
            entity_id=entity.id,
            entity_name=entity.name
        ))

        return entity

    def destroy_entity(self, entity: Entity) -> None:
        """Destroy an entity and fire destruction event."""
        entity_id = entity.id

        # Notify systems first
        for system in self._systems:
            system.on_entity_destroyed(entity, self.entity_manager)

        # Fire event before actual destruction
        self.event_bus.publish(EntityDestroyedEvent(entity_id=entity_id))

        # Actually destroy
        self.entity_manager.destroy_entity(entity)

    def update(self, dt: float) -> None:
        """Update all systems."""
        if self._paused:
            return

        # Advance game time
        self.game_time.advance(dt, self._speed)

        # Update all systems
        for system in self._systems:
            system.update(dt * self._speed, self.entity_manager)

        # Process any queued events
        self.event_bus.process_queue()

    def pause(self) -> None:
        """Pause the simulation."""
        self._paused = True

    def unpause(self) -> None:
        """Unpause the simulation."""
        self._paused = False

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        self._paused = not self._paused

    @property
    def paused(self) -> bool:
        """Check if simulation is paused."""
        return self._paused

    @property
    def speed(self) -> float:
        """Get simulation speed."""
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        """Set simulation speed (clamped 1 to 100)."""
        self._speed = max(1.0, min(100.0, value))

    def get_entity(self, entity_id: UUID) -> Entity | None:
        """Get an entity by ID."""
        return self.entity_manager.get_entity(entity_id)
