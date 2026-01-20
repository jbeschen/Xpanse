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
    total_seconds: float = 0.0
    day: int = 1
    year: int = 2150

    # Time scale: 1 real second = 1 game minute at 1x speed
    SECONDS_PER_MINUTE: float = 1.0
    MINUTES_PER_HOUR: int = 60
    HOURS_PER_DAY: int = 24
    DAYS_PER_YEAR: int = 365

    def advance(self, dt: float, speed: float = 1.0) -> None:
        """Advance game time by dt real seconds."""
        game_seconds = dt * speed * 60  # Convert to game minutes
        self.total_seconds += game_seconds

        # Calculate day/year
        total_minutes = self.total_seconds
        total_hours = total_minutes / self.MINUTES_PER_HOUR
        total_days = total_hours / self.HOURS_PER_DAY

        self.day = int(total_days % self.DAYS_PER_YEAR) + 1
        self.year = 2150 + int(total_days / self.DAYS_PER_YEAR)

    @property
    def hour(self) -> int:
        """Current hour of the day."""
        total_minutes = self.total_seconds
        total_hours = total_minutes / self.MINUTES_PER_HOUR
        return int(total_hours % self.HOURS_PER_DAY)

    @property
    def minute(self) -> int:
        """Current minute of the hour."""
        return int(self.total_seconds % self.MINUTES_PER_HOUR)

    def __str__(self) -> str:
        return f"Year {self.year}, Day {self.day}, {self.hour:02d}:{self.minute:02d}"


class World:
    """Main world state container. Coordinates entities, systems, and events."""

    def __init__(self) -> None:
        self.entity_manager = EntityManager()
        self.event_bus = EventBus()
        self.game_time = GameTime()
        self._systems: list[System] = []
        self._paused: bool = False
        self._speed: float = 1.0

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
        """Set simulation speed (clamped 0.1 to 10.0)."""
        self._speed = max(0.1, min(10.0, value))

    def get_entity(self, entity_id: UUID) -> Entity | None:
        """Get an entity by ID."""
        return self.entity_manager.get_entity(entity_id)
