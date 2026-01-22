"""Base class for ship behaviors using the Strategy pattern.

Behaviors encapsulate decision-making logic for ships. Each behavior
is responsible for a specific type of activity (trading, patrol, etc.)
and produces navigation commands for the ship to follow.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from ...core.ecs import EntityManager, Entity
    from ...entities.ships import Ship
    from ...solar_system.orbits import Position


class BehaviorStatus(Enum):
    """Status returned by behavior update."""
    RUNNING = "running"      # Behavior is actively processing
    SUCCESS = "success"      # Behavior completed successfully
    FAILURE = "failure"      # Behavior failed
    WAITING = "waiting"      # Behavior is waiting (e.g., at station)


@dataclass
class BehaviorContext:
    """Context passed to behaviors during update.

    Contains all information a behavior needs to make decisions.
    """
    # Core references
    entity_manager: EntityManager
    ship_entity: Entity
    ship: Ship
    position: Position

    # Time info
    dt: float  # Delta time in seconds
    game_time: float  # Total game time in days

    # State storage (persisted between updates)
    state_data: dict[str, Any] = field(default_factory=dict)

    # Helper methods
    def get_component(self, component_type: type):
        """Get a component from the ship entity."""
        return self.entity_manager.get_component(self.ship_entity, component_type)

    def get_entity(self, entity_id: UUID):
        """Get an entity by ID."""
        return self.entity_manager.get_entity(entity_id)


@dataclass
class BehaviorResult:
    """Result returned by behavior update.

    Contains the status and any navigation commands to execute.
    """
    status: BehaviorStatus
    # Navigation target (if any)
    target_x: float | None = None
    target_y: float | None = None
    target_body: str = ""
    target_entity_id: UUID | None = None
    # Speed modifiers
    speed_multiplier: float = 1.0
    # Wait time before next update
    wait_time: float = 0.0
    # Message for debugging/logging
    message: str = ""


class ShipBehavior(ABC):
    """Abstract base class for ship behaviors.

    Subclass this to create new behavior types. Behaviors are responsible
    for making decisions about what the ship should do, returning navigation
    targets and other commands.

    Behaviors should be stateless - all state is stored in the BehaviorContext's
    state_data dict and persisted by the AI system.
    """

    @property
    def name(self) -> str:
        """Human-readable name for this behavior."""
        return self.__class__.__name__

    @abstractmethod
    def update(self, ctx: BehaviorContext) -> BehaviorResult:
        """Update the behavior and return next action.

        Called each frame when this behavior is active. Should return
        a BehaviorResult indicating what the ship should do.

        Args:
            ctx: Current context with entity manager, ship state, etc.

        Returns:
            BehaviorResult with navigation target and status
        """
        pass

    def on_enter(self, ctx: BehaviorContext) -> None:
        """Called when this behavior becomes active.

        Override to perform initialization when switching to this behavior.
        """
        pass

    def on_exit(self, ctx: BehaviorContext) -> None:
        """Called when this behavior is deactivated.

        Override to perform cleanup when switching away from this behavior.
        """
        pass

    def on_arrival(self, ctx: BehaviorContext, destination_id: UUID | None) -> BehaviorResult:
        """Called when ship arrives at its navigation target.

        Override to handle arrival logic. Default implementation returns
        SUCCESS status.

        Args:
            ctx: Current context
            destination_id: Entity ID of destination (if known)

        Returns:
            BehaviorResult for post-arrival behavior
        """
        return BehaviorResult(status=BehaviorStatus.SUCCESS)

    def can_activate(self, ctx: BehaviorContext) -> bool:
        """Check if this behavior can be activated.

        Override to add preconditions for behavior activation.
        Default returns True.
        """
        return True

    def get_priority(self, ctx: BehaviorContext) -> float:
        """Get behavior priority for behavior selection.

        Higher priority behaviors are preferred. Override to implement
        dynamic priority based on context.
        Default returns 0.
        """
        return 0.0
