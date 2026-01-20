"""Faction-level strategic AI."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import System, EntityManager
from ..core.events import EventBus
from ..entities.factions import Faction, Owned
from ..entities.stations import Station, StationType
from ..entities.ships import Ship, ShipType
from ..simulation.resources import ResourceType, Inventory
from ..simulation.economy import Market

if TYPE_CHECKING:
    pass


class FactionGoal(Enum):
    """High-level faction goals."""
    EXPAND = "expand"  # Build new stations
    CONSOLIDATE = "consolidate"  # Strengthen existing holdings
    TRADE = "trade"  # Focus on profitable trade routes
    MILITARY = "military"  # Build up military strength (future)


@dataclass
class FactionAIState:
    """AI state for a faction."""
    current_goal: FactionGoal = FactionGoal.TRADE
    goal_progress: float = 0.0
    expansion_target: str | None = None  # Body name to expand to
    ships_ordered: int = 0
    stations_ordered: int = 0


class FactionAI(System):
    """System that manages faction AI decisions."""

    priority = 60  # Run after economy

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._ai_states: dict[UUID, FactionAIState] = {}
        self._decision_interval = 30.0  # Seconds between major decisions
        self._time_since_decision = 0.0

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update faction AI."""
        self._time_since_decision += dt

        if self._time_since_decision < self._decision_interval:
            return

        self._time_since_decision = 0.0

        # Process each non-player faction
        for entity, faction in entity_manager.get_all_components(Faction):
            if "player" in entity.tags:
                continue

            if entity.id not in self._ai_states:
                self._ai_states[entity.id] = FactionAIState()

            self._update_faction(entity, faction, entity_manager)

    def _update_faction(
        self,
        faction_entity,
        faction: Faction,
        entity_manager: EntityManager
    ) -> None:
        """Update a single faction's AI."""
        state = self._ai_states[faction_entity.id]

        # Evaluate current situation
        owned_stations = self._count_owned_stations(faction_entity.id, entity_manager)
        owned_ships = self._count_owned_ships(faction_entity.id, entity_manager)
        total_wealth = self._calculate_wealth(faction_entity.id, faction, entity_manager)

        # Decide on goal based on situation
        if owned_ships < 2:
            state.current_goal = FactionGoal.TRADE
        elif owned_stations < 3 and faction.credits > 50000:
            state.current_goal = FactionGoal.EXPAND
        elif total_wealth < 20000:
            state.current_goal = FactionGoal.CONSOLIDATE
        else:
            state.current_goal = FactionGoal.TRADE

        # Execute goal
        if state.current_goal == FactionGoal.EXPAND:
            self._try_expand(faction_entity, faction, entity_manager, state)
        elif state.current_goal == FactionGoal.CONSOLIDATE:
            self._try_consolidate(faction_entity, faction, entity_manager, state)

    def _count_owned_stations(self, faction_id: UUID, entity_manager: EntityManager) -> int:
        """Count stations owned by a faction."""
        count = 0
        for entity, station in entity_manager.get_all_components(Station):
            if station.owner_faction_id == faction_id:
                count += 1
        return count

    def _count_owned_ships(self, faction_id: UUID, entity_manager: EntityManager) -> int:
        """Count ships owned by a faction."""
        count = 0
        for entity, ship in entity_manager.get_all_components(Ship):
            if ship.owner_faction_id == faction_id:
                count += 1
        return count

    def _calculate_wealth(
        self,
        faction_id: UUID,
        faction: Faction,
        entity_manager: EntityManager
    ) -> float:
        """Calculate total faction wealth (credits + inventory value)."""
        total = faction.credits

        # Add value of inventory at owned stations
        for entity, station in entity_manager.get_all_components(Station):
            if station.owner_faction_id != faction_id:
                continue

            inventory = entity_manager.get_component(entity, Inventory)
            if inventory:
                from ..simulation.resources import BASE_PRICES
                for resource, amount in inventory.resources.items():
                    total += amount * BASE_PRICES.get(resource, 10.0)

        return total

    def _try_expand(
        self,
        faction_entity,
        faction: Faction,
        entity_manager: EntityManager,
        state: FactionAIState
    ) -> None:
        """Try to expand to a new location."""
        # For now, just track the intent - actual station building
        # would require more complex logic and events
        pass

    def _try_consolidate(
        self,
        faction_entity,
        faction: Faction,
        entity_manager: EntityManager,
        state: FactionAIState
    ) -> None:
        """Try to strengthen existing holdings."""
        # For now, just track the intent
        pass


def evaluate_trade_opportunity(
    entity_manager: EntityManager,
    faction_id: UUID,
    source_station_id: UUID,
    dest_station_id: UUID,
) -> float:
    """Evaluate potential profit from a trade route.

    Args:
        entity_manager: Entity manager
        faction_id: Faction considering the trade
        source_station_id: Source station
        dest_station_id: Destination station

    Returns:
        Expected profit score (higher is better)
    """
    source = entity_manager.get_entity(source_station_id)
    dest = entity_manager.get_entity(dest_station_id)

    if not source or not dest:
        return 0.0

    source_market = entity_manager.get_component(source, Market)
    source_inv = entity_manager.get_component(source, Inventory)
    dest_market = entity_manager.get_component(dest, Market)

    if not source_market or not source_inv or not dest_market:
        return 0.0

    total_profit = 0.0

    for resource in ResourceType:
        sell_price = source_market.get_sell_price(resource)
        buy_price = dest_market.get_buy_price(resource)

        if sell_price is None or buy_price is None:
            continue

        available = source_inv.get(resource)
        if available <= 0:
            continue

        profit_per_unit = buy_price - sell_price
        if profit_per_unit > 0:
            total_profit += profit_per_unit * min(available, 100)  # Cap at 100 units

    return total_profit
