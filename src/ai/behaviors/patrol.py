"""Patrol behavior for idle ships.

Ships patrol between nearby stations when they have no other tasks.
Creates visible activity in the game world.
"""
from __future__ import annotations
import random
from uuid import UUID

from .base import ShipBehavior, BehaviorContext, BehaviorResult, BehaviorStatus


class PatrolState:
    """State constants for patrol behavior."""
    SELECTING_TARGET = "selecting_target"
    TRAVELING = "traveling"
    WAITING = "waiting"


class PatrolBehavior(ShipBehavior):
    """Behavior for idle ships to patrol between stations.

    Creates the "ant farm" effect - ships constantly moving around
    even when not actively trading. This makes the game feel alive.
    """

    def __init__(self) -> None:
        self.max_patrol_distance = 3.0  # AU
        self.min_wait_time = 0.5  # seconds (reduced from 2.0 for more activity)
        self.max_wait_time = 3.0  # seconds (reduced from 8.0 for more activity)

    @property
    def name(self) -> str:
        return "Patrol"

    def on_enter(self, ctx: BehaviorContext) -> None:
        """Initialize patrol state."""
        ctx.state_data["patrol_state"] = PatrolState.SELECTING_TARGET
        ctx.state_data["patrol_target_id"] = None

    def update(self, ctx: BehaviorContext) -> BehaviorResult:
        """Update patrol behavior."""
        from ...entities.stations import Station
        from ...solar_system.orbits import Position

        state = ctx.state_data.get("patrol_state", PatrolState.SELECTING_TARGET)

        if state == PatrolState.SELECTING_TARGET:
            target = self._select_patrol_target(ctx)
            if target:
                ctx.state_data["patrol_target_id"] = target.id
                ctx.state_data["patrol_state"] = PatrolState.TRAVELING
                return self._navigate_to_target(ctx, target.id)
            else:
                # No targets - wait and try again
                return BehaviorResult(
                    status=BehaviorStatus.WAITING,
                    wait_time=5.0,
                    message="No patrol targets found"
                )

        elif state == PatrolState.TRAVELING:
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        elif state == PatrolState.WAITING:
            # Wait complete - find next target
            ctx.state_data["patrol_state"] = PatrolState.SELECTING_TARGET
            return BehaviorResult(status=BehaviorStatus.RUNNING)

        return BehaviorResult(status=BehaviorStatus.RUNNING)

    def on_arrival(self, ctx: BehaviorContext, destination_id: UUID | None) -> BehaviorResult:
        """Handle arrival at patrol destination."""
        state = ctx.state_data.get("patrol_state", PatrolState.SELECTING_TARGET)

        if state == PatrolState.TRAVELING:
            # Arrived - wait before selecting next target
            ctx.state_data["patrol_state"] = PatrolState.WAITING
            wait_time = random.uniform(self.min_wait_time, self.max_wait_time)
            return BehaviorResult(
                status=BehaviorStatus.RUNNING,
                wait_time=wait_time,
                message=f"Arrived, waiting {wait_time:.1f}s"
            )

        return BehaviorResult(status=BehaviorStatus.RUNNING)

    def _select_patrol_target(self, ctx: BehaviorContext):
        """Select a destination to patrol to.

        Includes both stations and celestial bodies for more varied movement.
        Prefers nearby targets but occasionally picks farther ones.
        """
        from ...entities.stations import Station
        from ...entities.celestial import CelestialBody
        from ...solar_system.orbits import Position

        em = ctx.entity_manager
        targets_by_dist: list[tuple] = []

        # Collect stations as targets
        for entity, station in em.get_all_components(Station):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            dist = ctx.position.distance_to(pos)
            if dist > self.max_patrol_distance:
                continue

            targets_by_dist.append((entity, dist, 'station'))

        # Also collect planets/moons as targets (30% chance to consider)
        if random.random() < 0.3:
            for entity, body in em.get_all_components(CelestialBody):
                # Only patrol to planets and moons, not the sun
                if body.body_type.value not in ('planet', 'moon', 'dwarf_planet'):
                    continue

                pos = em.get_component(entity, Position)
                if not pos:
                    continue

                dist = ctx.position.distance_to(pos)
                if dist > self.max_patrol_distance:
                    continue

                targets_by_dist.append((entity, dist, 'body'))

        if not targets_by_dist:
            return None

        # Sort by distance
        targets_by_dist.sort(key=lambda x: x[1])

        # If we're near a target (first one), pick a different one
        if targets_by_dist[0][1] < 0.1 and len(targets_by_dist) > 1:
            # Weight towards closer targets but allow farther ones
            # Take from the first 5 targets (excluding current)
            candidates = targets_by_dist[1:min(6, len(targets_by_dist))]
            if candidates:
                return random.choice(candidates)[0]

        # Not near any target - go to closest
        return targets_by_dist[0][0]

    def _navigate_to_target(self, ctx: BehaviorContext, target_id: UUID) -> BehaviorResult:
        """Create navigation result for a station or celestial body."""
        from ...solar_system.orbits import Position
        from ...entities.stations import Station
        from ...entities.celestial import CelestialBody

        target = ctx.get_entity(target_id)
        if not target:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message=f"Target {target_id} not found"
            )

        pos = ctx.entity_manager.get_component(target, Position)
        if not pos:
            return BehaviorResult(
                status=BehaviorStatus.FAILURE,
                message="Target has no position"
            )

        # Determine target body for sector navigation
        target_body = ""
        station_comp = ctx.entity_manager.get_component(target, Station)
        if station_comp:
            target_body = station_comp.parent_body
        else:
            # It's a celestial body - use its name
            body_comp = ctx.entity_manager.get_component(target, CelestialBody)
            if body_comp:
                target_body = target.name

        return BehaviorResult(
            status=BehaviorStatus.RUNNING,
            target_x=pos.x,
            target_y=pos.y,
            target_body=target_body,
            target_entity_id=target_id,
        )

    def get_priority(self, ctx: BehaviorContext) -> float:
        """Patrol has lowest priority - fallback behavior."""
        return 10.0
