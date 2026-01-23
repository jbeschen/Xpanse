"""Trail system - records ship positions for visual trails."""
from __future__ import annotations

from ..core.ecs import System, EntityManager
from ..entities.trails import Trail, TrailPoint
from ..entities.ships import Ship
from ..solar_system.orbits import Position, Velocity, ParentBody


class TrailSystem(System):
    """System that records ship positions and manages trail data.

    Creates the visual "ant farm" effect by recording position history
    for moving ships. Trails are cleared when ships park at a body.
    """

    priority = 100  # Run after movement systems

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update trail data for all ships."""
        # Get current game time (we'll track it incrementally)
        # Since we don't have direct access to world.game_time here,
        # we'll use the trail's own timestamp tracking

        for entity, ship in entity_manager.get_all_components(Ship):
            # Get or create trail component
            trail = entity_manager.get_component(entity, Trail)
            if not trail:
                trail = Trail()
                entity_manager.add_component(entity, trail)

            # Get ship's current state
            pos = entity_manager.get_component(entity, Position)
            vel = entity_manager.get_component(entity, Velocity)
            parent = entity_manager.get_component(entity, ParentBody)

            if not pos:
                continue

            # Clear trail if ship is parked (has ParentBody)
            if parent is not None:
                if trail.points:
                    trail.points.clear()
                continue

            # Check if ship is moving
            is_moving = vel and (abs(vel.vx) > 0.001 or abs(vel.vy) > 0.001)

            if not is_moving:
                # Ship stopped - let trail fade naturally
                continue

            # Update trail timestamp tracking
            trail.last_record_time += dt

            # Record new point if enough time has passed
            if trail.last_record_time >= trail.record_interval:
                # Add new point at current position
                new_point = TrailPoint(
                    x=pos.x,
                    y=pos.y,
                    timestamp=trail.last_record_time
                )
                trail.points.append(new_point)
                trail.last_record_time = 0.0

                # Prune old points if over max
                while len(trail.points) > trail.max_points:
                    trail.points.pop(0)

            # Age all points and remove expired ones
            self._age_trail_points(trail, dt)

    def _age_trail_points(self, trail: Trail, dt: float) -> None:
        """Age trail points and remove those past max_age."""
        if not trail.points:
            return

        # Update timestamps (increase age)
        for point in trail.points:
            point.timestamp += dt

        # Remove points older than max_age
        trail.points = [
            p for p in trail.points
            if p.timestamp < trail.max_age
        ]
