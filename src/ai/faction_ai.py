"""Faction-level strategic AI."""
from __future__ import annotations
import math
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
from ..solar_system.orbits import Position

if TYPE_CHECKING:
    from ..systems.building import BuildingSystem
    from ..core.world import World


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
        self._building_system: "BuildingSystem | None" = None
        self._world: "World | None" = None

    def set_building_system(self, building_system: "BuildingSystem", world: "World") -> None:
        """Set the building system reference for AI building."""
        self._building_system = building_system
        self._world = world

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
        if not self._building_system or not self._world:
            return

        # Determine what to build based on current holdings
        owned_stations = self._get_owned_station_types(faction_entity.id, entity_manager)

        # Prioritize: Mining → Refinery → Factory chain
        station_type = self._decide_station_type(owned_stations, faction)
        if station_type is None:
            return

        # Find best location for this station type
        location = self._find_best_location(
            faction_entity.id, station_type, entity_manager
        )
        if location is None:
            return

        position, parent_body, resource_type = location

        # Attempt to build
        result = self._building_system.request_build(
            world=self._world,
            faction_id=faction_entity.id,
            station_type=station_type,
            position=position,
            parent_body=parent_body,
            resource_type=resource_type,
        )

        if result.success:
            state.stations_ordered += 1

    def _get_owned_station_types(
        self,
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> dict[StationType, int]:
        """Count station types owned by faction."""
        counts: dict[StationType, int] = {}
        for entity, station in entity_manager.get_all_components(Station):
            if station.owner_faction_id == faction_id:
                counts[station.station_type] = counts.get(station.station_type, 0) + 1
        return counts

    def _decide_station_type(
        self,
        owned_types: dict[StationType, int],
        faction: Faction
    ) -> StationType | None:
        """Decide what type of station to build next."""
        from ..systems.building import STATION_COSTS

        # Build priority order for economic chain
        # Start with mining, then refinery, then factory
        mining_count = owned_types.get(StationType.MINING_STATION, 0)
        refinery_count = owned_types.get(StationType.REFINERY, 0)
        factory_count = owned_types.get(StationType.FACTORY, 0)
        outpost_count = owned_types.get(StationType.OUTPOST, 0)

        # If no stations at all, start with an outpost (cheapest)
        if sum(owned_types.values()) == 0:
            if faction.credits >= STATION_COSTS[StationType.OUTPOST]:
                return StationType.OUTPOST
            return None

        # Need mining to fuel economy
        if mining_count < 2 and faction.credits >= STATION_COSTS[StationType.MINING_STATION]:
            return StationType.MINING_STATION

        # Need refinery to process raw materials
        if refinery_count < 1 and mining_count >= 1:
            if faction.credits >= STATION_COSTS[StationType.REFINERY]:
                return StationType.REFINERY

        # Need factory for advanced goods
        if factory_count < 1 and refinery_count >= 1:
            if faction.credits >= STATION_COSTS[StationType.FACTORY]:
                return StationType.FACTORY

        # More mining for more resources
        if mining_count < 4 and faction.credits >= STATION_COSTS[StationType.MINING_STATION]:
            return StationType.MINING_STATION

        # More outposts for presence
        if outpost_count < 3 and faction.credits >= STATION_COSTS[StationType.OUTPOST]:
            return StationType.OUTPOST

        return None

    def _find_best_location(
        self,
        faction_id: UUID,
        station_type: StationType,
        entity_manager: EntityManager
    ) -> tuple[tuple[float, float], str, ResourceType | None] | None:
        """Find the best location for a new station.

        Returns:
            (position, parent_body, resource_type) or None
        """
        from ..entities.celestial import CelestialBody
        from ..solar_system.bodies import SOLAR_SYSTEM_DATA

        best_score = -float('inf')
        best_location = None

        # Evaluate each celestial body
        for entity, body in entity_manager.get_all_components(CelestialBody):
            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            body_name = entity.name
            body_data = SOLAR_SYSTEM_DATA.get(body_name)
            if not body_data:
                continue

            # Skip the Sun
            if body.body_type.value == "star":
                continue

            # Offset slightly from body center
            test_position = (pos.x + 0.05, pos.y + 0.05)

            # Score this location
            score = self._score_location(
                body_name, body_data, station_type, faction_id, entity_manager
            )

            if score > best_score:
                best_score = score
                # Determine resource type for mining stations
                resource_type = None
                if station_type == StationType.MINING_STATION and body_data.resources:
                    # Pick the richest resource
                    resource_type = max(body_data.resources, key=lambda x: x[1])[0]

                best_location = (test_position, body_name, resource_type)

        return best_location

    def _score_location(
        self,
        body_name: str,
        body_data,
        station_type: StationType,
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> float:
        """Score a location for building a specific station type."""
        score = 0.0

        # Prefer closer bodies (less travel time)
        distance_from_sun = body_data.semi_major_axis
        score -= distance_from_sun * 5  # Penalty for distance

        # For mining stations, prioritize resource-rich bodies
        if station_type == StationType.MINING_STATION:
            for resource, richness in body_data.resources:
                score += richness * 20

        # For refineries/factories, prefer locations near mining
        if station_type in (StationType.REFINERY, StationType.FACTORY):
            nearby_mining = self._count_nearby_stations(
                body_name, StationType.MINING_STATION, entity_manager
            )
            score += nearby_mining * 15

        # Bonus for bodies we already have presence at
        own_stations_at_body = self._count_faction_stations_at_body(
            body_name, faction_id, entity_manager
        )
        if own_stations_at_body > 0:
            score += 10

        # Slight randomness to avoid all AIs picking same locations
        import random
        score += random.uniform(-5, 5)

        return score

    def _count_nearby_stations(
        self,
        body_name: str,
        station_type: StationType,
        entity_manager: EntityManager
    ) -> int:
        """Count stations of a type near a body."""
        count = 0
        for entity, station in entity_manager.get_all_components(Station):
            if station.station_type == station_type and station.parent_body == body_name:
                count += 1
        return count

    def _count_faction_stations_at_body(
        self,
        body_name: str,
        faction_id: UUID,
        entity_manager: EntityManager
    ) -> int:
        """Count faction's stations at a body."""
        count = 0
        for entity, station in entity_manager.get_all_components(Station):
            if station.owner_faction_id == faction_id and station.parent_body == body_name:
                count += 1
        return count

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
