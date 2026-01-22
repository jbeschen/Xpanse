"""Ship AI System V2 using the behavior strategy pattern.

This system manages ship AI using pluggable behavior strategies.
Adding new behaviors (mining, escort, construction) requires only
creating a new behavior class - no changes to this system needed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import System, EntityManager
from ..core.events import EventBus, ShipArrivedEvent
from ..core.system_priority import SystemPriority
from ..entities.ships import Ship
from ..solar_system.orbits import Position, NavigationTarget
from ..ai.behaviors import (
    ShipBehavior,
    BehaviorContext,
    BehaviorResult,
    BehaviorStatus,
    TradingBehavior,
    DroneBehavior,
    PatrolBehavior,
    WaypointBehavior,
    BEHAVIOR_REGISTRY,
)

if TYPE_CHECKING:
    from ..ai.trade_routes import TradeRouteFinder
    from ..core.transactions import TransactionService


@dataclass
class ShipAIStateV2:
    """AI state for a ship in the V2 system."""
    behavior_name: str = "patrol"
    sub_state: str = "idle"
    state_data: dict = field(default_factory=dict)
    wait_time: float = 0.0
    target_entity_id: UUID | None = None


class ShipAISystemV2(System):
    """Ship AI system using behavior strategies.

    Each ship has a behavior (trading, drone, patrol, waypoint) that
    determines its decision-making. Behaviors are swappable at runtime
    and new behaviors can be added without modifying this class.
    """

    priority = SystemPriority.AI_SHIP_BEHAVIOR

    def __init__(
        self,
        event_bus: EventBus,
        route_finder: "TradeRouteFinder | None" = None,
        transactions: "TransactionService | None" = None
    ) -> None:
        """Initialize the ship AI system.

        Args:
            event_bus: Event bus for ship events
            route_finder: Optional TradeRouteFinder for trading behavior
            transactions: Optional TransactionService for trade execution
        """
        self.event_bus = event_bus
        self.route_finder = route_finder
        self.transactions = transactions

        # AI states for each ship
        self._states: dict[UUID, ShipAIStateV2] = {}

        # Instantiated behaviors
        self._behaviors: dict[str, ShipBehavior] = {
            "trading": TradingBehavior(route_finder),
            "drone": DroneBehavior(),
            "patrol": PatrolBehavior(),
            "waypoint": WaypointBehavior(),
        }

        # Subscribe to events
        self.event_bus.subscribe(ShipArrivedEvent, self._on_ship_arrived)

    def register_behavior(self, name: str, behavior: ShipBehavior) -> None:
        """Register a new behavior type.

        Args:
            name: Behavior name (used in ShipAIStateV2.behavior_name)
            behavior: Behavior instance
        """
        self._behaviors[name] = behavior

    def set_ship_behavior(
        self,
        entity_manager: EntityManager,
        ship_entity,
        behavior_name: str
    ) -> bool:
        """Set a ship's behavior.

        Args:
            entity_manager: Entity manager
            ship_entity: Ship entity
            behavior_name: Name of behavior to switch to

        Returns:
            True if behavior was set successfully
        """
        if behavior_name not in self._behaviors:
            return False

        ship = entity_manager.get_component(ship_entity, Ship)
        pos = entity_manager.get_component(ship_entity, Position)

        if not ship or not pos:
            return False

        state = self._get_or_create_state(ship_entity.id)
        old_behavior = self._behaviors.get(state.behavior_name)

        # Call on_exit for old behavior
        if old_behavior:
            ctx = self._create_context(entity_manager, ship_entity, ship, pos, 0.0, state)
            old_behavior.on_exit(ctx)

        # Switch behavior
        state.behavior_name = behavior_name
        state.sub_state = "idle"
        state.state_data = {}
        state.wait_time = 0.0

        # Call on_enter for new behavior
        new_behavior = self._behaviors[behavior_name]
        ctx = self._create_context(entity_manager, ship_entity, ship, pos, 0.0, state)
        new_behavior.on_enter(ctx)

        return True

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update all ship AI."""
        for entity, ship in entity_manager.get_all_components(Ship):
            # Skip player-controlled ships
            if "player_controlled" in entity.tags:
                continue

            self._update_ship(entity, ship, entity_manager, dt)

    def _update_ship(
        self,
        ship_entity,
        ship: Ship,
        entity_manager: EntityManager,
        dt: float
    ) -> None:
        """Update a single ship's AI."""
        pos = entity_manager.get_component(ship_entity, Position)
        nav = entity_manager.get_component(ship_entity, NavigationTarget)

        if not pos:
            return

        state = self._get_or_create_state(ship_entity.id)

        # Handle waiting
        if state.wait_time > 0:
            state.wait_time -= dt
            return

        # Check for arrival
        if nav and nav.has_arrived(pos):
            self._handle_arrival(ship_entity, ship, entity_manager, state, pos)
            entity_manager.remove_component(ship_entity, NavigationTarget)
            return

        # If navigating, let it continue
        if nav:
            return

        # Select appropriate behavior
        behavior = self._select_behavior(entity_manager, ship_entity, ship, pos, state)
        if not behavior:
            return

        # Create context and update behavior
        ctx = self._create_context(entity_manager, ship_entity, ship, pos, dt, state)
        result = behavior.update(ctx)

        # Process result
        self._process_result(entity_manager, ship_entity, ship, state, result)

    def _get_or_create_state(self, ship_id: UUID) -> ShipAIStateV2:
        """Get or create AI state for a ship."""
        if ship_id not in self._states:
            self._states[ship_id] = ShipAIStateV2()
        return self._states[ship_id]

    def _select_behavior(
        self,
        entity_manager: EntityManager,
        ship_entity,
        ship: Ship,
        pos: Position,
        state: ShipAIStateV2
    ) -> ShipBehavior | None:
        """Select the best behavior for a ship.

        Checks current behavior first, then falls back based on priority.
        """
        # If current behavior is valid, use it
        current = self._behaviors.get(state.behavior_name)
        if current:
            ctx = self._create_context(entity_manager, ship_entity, ship, pos, 0.0, state)
            if current.can_activate(ctx):
                return current

        # Auto-select based on ship type and components
        if ship.is_drone and ship.home_station_id:
            state.behavior_name = "drone"
            return self._behaviors.get("drone")

        # Check for manual route
        from ..simulation.trade import ManualRoute
        route = entity_manager.get_component(ship_entity, ManualRoute)
        if route and route.waypoints:
            state.behavior_name = "waypoint"
            return self._behaviors.get("waypoint")

        # Check for trader component
        from ..simulation.trade import Trader
        trader = entity_manager.get_component(ship_entity, Trader)
        if trader:
            state.behavior_name = "trading"
            return self._behaviors.get("trading")

        # Default to patrol
        state.behavior_name = "patrol"
        return self._behaviors.get("patrol")

    def _create_context(
        self,
        entity_manager: EntityManager,
        ship_entity,
        ship: Ship,
        pos: Position,
        dt: float,
        state: ShipAIStateV2
    ) -> BehaviorContext:
        """Create behavior context."""
        return BehaviorContext(
            entity_manager=entity_manager,
            ship_entity=ship_entity,
            ship=ship,
            position=pos,
            dt=dt,
            game_time=0.0,  # TODO: Get from GameTime
            state_data=state.state_data,
        )

    def _process_result(
        self,
        entity_manager: EntityManager,
        ship_entity,
        ship: Ship,
        state: ShipAIStateV2,
        result: BehaviorResult
    ) -> None:
        """Process behavior result and update ship state."""
        # Set wait time
        state.wait_time = result.wait_time
        state.target_entity_id = result.target_entity_id

        # Set navigation if target provided
        if result.target_x is not None and result.target_y is not None:
            speed_mult = result.speed_multiplier
            entity_manager.add_component(ship_entity, NavigationTarget(
                target_x=result.target_x,
                target_y=result.target_y,
                target_body_name=result.target_body,
                max_speed=ship.max_speed * speed_mult,
                acceleration=ship.acceleration * speed_mult,
            ))

    def _handle_arrival(
        self,
        ship_entity,
        ship: Ship,
        entity_manager: EntityManager,
        state: ShipAIStateV2,
        pos: Position
    ) -> None:
        """Handle ship arrival at destination."""
        behavior = self._behaviors.get(state.behavior_name)
        if not behavior:
            return

        # Fire arrival event
        self.event_bus.publish(ShipArrivedEvent(
            ship_id=ship_entity.id,
            destination_id=state.target_entity_id
        ))

        # Let behavior handle arrival
        ctx = self._create_context(entity_manager, ship_entity, ship, pos, 0.0, state)
        result = behavior.on_arrival(ctx, state.target_entity_id)

        # Process arrival result
        self._process_result(entity_manager, ship_entity, ship, state, result)

    def _on_ship_arrived(self, event: ShipArrivedEvent) -> None:
        """Handle external ship arrival events."""
        if event.ship_id in self._states:
            state = self._states[event.ship_id]
            state.wait_time = 1.5  # Brief wait on arrival

    def on_entity_destroyed(self, entity, entity_manager: EntityManager) -> None:
        """Clean up when a ship is destroyed."""
        self._states.pop(entity.id, None)

    def get_ship_state(self, ship_id: UUID) -> ShipAIStateV2 | None:
        """Get AI state for a ship (for debugging/UI)."""
        return self._states.get(ship_id)

    def get_behavior_name(self, ship_id: UUID) -> str:
        """Get current behavior name for a ship."""
        state = self._states.get(ship_id)
        return state.behavior_name if state else "unknown"
