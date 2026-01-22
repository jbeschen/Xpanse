"""Efficient trade route finding with spatial indexing.

Provides O(1) nearby entity lookup and cached trade route discovery.
Scales well to hundreds of stations and ships.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator
from uuid import UUID
import math
import time

if TYPE_CHECKING:
    from ..core.ecs import EntityManager


@dataclass
class TradeOpportunity:
    """A discovered trade opportunity."""
    source_id: UUID
    destination_id: UUID
    resource_id: str  # String resource ID
    amount: float
    buy_price: float  # Price to buy at source
    sell_price: float  # Price to sell at destination
    profit_per_unit: float
    total_profit: float
    distance: float  # AU between source and destination
    profit_per_distance: float  # Efficiency score

    @property
    def score(self) -> float:
        """Combined score for route ranking."""
        # Balance total profit and efficiency
        return self.total_profit * 0.7 + self.profit_per_distance * 0.3


class SpatialIndex:
    """Grid-based spatial index for O(1) nearby entity lookup.

    Divides space into cells and tracks which entities are in each cell.
    Lookups only need to check cells within the search radius.
    """

    def __init__(self, cell_size: float = 0.5) -> None:
        """Initialize spatial index.

        Args:
            cell_size: Size of each cell in AU (default 0.5 AU)
        """
        self.cell_size = cell_size
        self._cells: dict[tuple[int, int], set[UUID]] = {}
        self._positions: dict[UUID, tuple[float, float]] = {}

    def _cell_key(self, x: float, y: float) -> tuple[int, int]:
        """Get cell key for a position."""
        return (int(x / self.cell_size), int(y / self.cell_size))

    def update(self, entity_id: UUID, x: float, y: float) -> None:
        """Update entity position in the index."""
        # Remove from old cell if exists
        if entity_id in self._positions:
            old_x, old_y = self._positions[entity_id]
            old_key = self._cell_key(old_x, old_y)
            if old_key in self._cells:
                self._cells[old_key].discard(entity_id)

        # Add to new cell
        new_key = self._cell_key(x, y)
        if new_key not in self._cells:
            self._cells[new_key] = set()
        self._cells[new_key].add(entity_id)
        self._positions[entity_id] = (x, y)

    def remove(self, entity_id: UUID) -> None:
        """Remove entity from the index."""
        if entity_id in self._positions:
            x, y = self._positions[entity_id]
            key = self._cell_key(x, y)
            if key in self._cells:
                self._cells[key].discard(entity_id)
            del self._positions[entity_id]

    def get_nearby(self, x: float, y: float, radius: float) -> Iterator[UUID]:
        """Get entities within radius of a position.

        Yields entity IDs that are within the specified radius.
        Average case O(1) for sparse distributions.
        """
        # Calculate cell range to check
        cells_to_check = int(math.ceil(radius / self.cell_size)) + 1
        center_cell = self._cell_key(x, y)
        radius_sq = radius * radius

        for dx in range(-cells_to_check, cells_to_check + 1):
            for dy in range(-cells_to_check, cells_to_check + 1):
                cell_key = (center_cell[0] + dx, center_cell[1] + dy)
                if cell_key not in self._cells:
                    continue

                for entity_id in self._cells[cell_key]:
                    if entity_id not in self._positions:
                        continue
                    ex, ey = self._positions[entity_id]
                    dist_sq = (ex - x) ** 2 + (ey - y) ** 2
                    if dist_sq <= radius_sq:
                        yield entity_id

    def get_position(self, entity_id: UUID) -> tuple[float, float] | None:
        """Get cached position of an entity."""
        return self._positions.get(entity_id)

    def clear(self) -> None:
        """Clear the index."""
        self._cells.clear()
        self._positions.clear()


@dataclass
class CachedRoute:
    """Cached trade route with expiration."""
    opportunity: TradeOpportunity
    timestamp: float  # When cached
    ttl: float = 10.0  # Time to live in seconds

    def is_expired(self, current_time: float) -> bool:
        """Check if cache entry has expired."""
        return current_time - self.timestamp > self.ttl


class TradeRouteFinder:
    """Efficient trade route discovery with caching.

    Uses spatial indexing for O(n) route finding instead of O(n²).
    Caches results to avoid repeated calculations.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        spatial_index: SpatialIndex | None = None,
        cache_ttl: float = 10.0
    ) -> None:
        """Initialize route finder.

        Args:
            entity_manager: Entity manager for component access
            spatial_index: Optional spatial index (creates new if None)
            cache_ttl: How long to cache routes (seconds)
        """
        self.entity_manager = entity_manager
        self.spatial_index = spatial_index or SpatialIndex()
        self.cache_ttl = cache_ttl
        self._route_cache: dict[UUID, list[CachedRoute]] = {}
        self._last_index_update = 0.0
        self._index_update_interval = 1.0  # seconds

    def update_index(self, force: bool = False) -> None:
        """Update spatial index with current station positions.

        Args:
            force: Force update even if interval hasn't passed
        """
        current_time = time.time()
        if not force and current_time - self._last_index_update < self._index_update_interval:
            return

        from ..entities.stations import Station
        from ..solar_system.orbits import Position

        for entity, station in self.entity_manager.get_all_components(Station):
            pos = self.entity_manager.get_component(entity, Position)
            if pos:
                self.spatial_index.update(entity.id, pos.x, pos.y)

        self._last_index_update = current_time

    def find_best_route(
        self,
        ship_id: UUID,
        ship_position: tuple[float, float],
        cargo_space: float,
        max_distance: float = 10.0,
        min_profit: float = 5.0
    ) -> TradeOpportunity | None:
        """Find the best trade route for a ship.

        Args:
            ship_id: Ship entity ID (for caching)
            ship_position: Current ship position (x, y) in AU
            cargo_space: Available cargo space
            max_distance: Maximum route distance in AU
            min_profit: Minimum profit per unit to consider

        Returns:
            Best TradeOpportunity or None if no profitable routes
        """
        # Check cache first
        current_time = time.time()
        if ship_id in self._route_cache:
            cached = self._route_cache[ship_id]
            valid_routes = [r for r in cached if not r.is_expired(current_time)]
            if valid_routes:
                # Return best cached route that's still valid
                best = max(valid_routes, key=lambda r: r.opportunity.score)
                return best.opportunity

        # Find new routes
        routes = list(self.find_all_routes(
            ship_position, cargo_space, max_distance, min_profit, limit=10
        ))

        if not routes:
            return None

        # Cache results
        self._route_cache[ship_id] = [
            CachedRoute(r, current_time, self.cache_ttl) for r in routes
        ]

        return routes[0]  # Best route (already sorted)

    def find_all_routes(
        self,
        ship_position: tuple[float, float],
        cargo_space: float,
        max_distance: float = 10.0,
        min_profit: float = 5.0,
        limit: int = 20
    ) -> Iterator[TradeOpportunity]:
        """Find all profitable trade routes, sorted by score.

        Args:
            ship_position: Current ship position (x, y) in AU
            cargo_space: Available cargo space
            max_distance: Maximum route distance in AU
            min_profit: Minimum profit per unit to consider
            limit: Maximum routes to return

        Yields:
            TradeOpportunity objects sorted by score (best first)
        """
        from ..entities.stations import Station
        from ..simulation.economy import Market
        from ..simulation.resources import Inventory, ResourceType
        from ..solar_system.orbits import Position

        # Ensure index is updated
        self.update_index()

        # Find nearby stations
        nearby_stations = list(self.spatial_index.get_nearby(
            ship_position[0], ship_position[1], max_distance
        ))

        if len(nearby_stations) < 2:
            return

        # Find all trade opportunities
        opportunities: list[TradeOpportunity] = []

        for source_id in nearby_stations:
            source = self.entity_manager.get_entity(source_id)
            if not source:
                continue

            source_market = self.entity_manager.get_component(source, Market)
            source_inv = self.entity_manager.get_component(source, Inventory)
            source_pos = self.spatial_index.get_position(source_id)

            if not source_market or not source_inv or not source_pos:
                continue

            for dest_id in nearby_stations:
                if source_id == dest_id:
                    continue

                dest = self.entity_manager.get_entity(dest_id)
                if not dest:
                    continue

                dest_market = self.entity_manager.get_component(dest, Market)
                dest_inv = self.entity_manager.get_component(dest, Inventory)
                dest_pos = self.spatial_index.get_position(dest_id)

                if not dest_market or not dest_inv or not dest_pos:
                    continue

                # Calculate distance
                distance = math.sqrt(
                    (dest_pos[0] - source_pos[0]) ** 2 +
                    (dest_pos[1] - source_pos[1]) ** 2
                )

                # Find profitable resources
                for resource in ResourceType:
                    sell_price = source_market.get_sell_price(resource)
                    buy_price = dest_market.get_buy_price(resource)

                    if sell_price is None or buy_price is None:
                        continue

                    profit_per_unit = buy_price - sell_price
                    if profit_per_unit < min_profit:
                        continue

                    # Calculate tradeable amount
                    available = source_inv.get(resource)
                    dest_space = dest_inv.free_space
                    affordable = dest_market.credits / buy_price if buy_price > 0 else 0

                    amount = min(available, cargo_space, dest_space, affordable)
                    if amount <= 0:
                        continue

                    total_profit = profit_per_unit * amount
                    profit_per_distance = total_profit / max(distance, 0.01)

                    opportunities.append(TradeOpportunity(
                        source_id=source_id,
                        destination_id=dest_id,
                        resource_id=resource.value,
                        amount=amount,
                        buy_price=sell_price,  # What ship pays at source
                        sell_price=buy_price,  # What ship receives at dest
                        profit_per_unit=profit_per_unit,
                        total_profit=total_profit,
                        distance=distance,
                        profit_per_distance=profit_per_distance,
                    ))

        # Sort by score and yield top results
        opportunities.sort(key=lambda o: o.score, reverse=True)
        for i, opp in enumerate(opportunities):
            if i >= limit:
                break
            yield opp

    def invalidate_cache(self, ship_id: UUID | None = None) -> None:
        """Invalidate cached routes.

        Args:
            ship_id: Specific ship to invalidate, or None for all
        """
        if ship_id:
            self._route_cache.pop(ship_id, None)
        else:
            self._route_cache.clear()

    def get_route_count(self, ship_position: tuple[float, float], radius: float = 5.0) -> int:
        """Get count of potential trade partners within radius."""
        self.update_index()
        return sum(1 for _ in self.spatial_index.get_nearby(
            ship_position[0], ship_position[1], radius
        ))
