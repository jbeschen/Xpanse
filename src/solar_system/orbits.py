"""Orbital mechanics (simplified for game)."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.ecs import Component, System, EntityManager

if TYPE_CHECKING:
    pass


@dataclass
class Position(Component):
    """2D position in space (AU from solar system center)."""
    x: float = 0.0
    y: float = 0.0

    def distance_to(self, other: Position) -> float:
        """Calculate distance to another position."""
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx * dx + dy * dy)

    def direction_to(self, other: Position) -> tuple[float, float]:
        """Get normalized direction vector to another position."""
        dx = other.x - self.x
        dy = other.y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist == 0:
            return (0.0, 0.0)
        return (dx / dist, dy / dist)


@dataclass
class Velocity(Component):
    """2D velocity (AU per game day)."""
    vx: float = 0.0
    vy: float = 0.0

    @property
    def speed(self) -> float:
        """Get speed magnitude."""
        return math.sqrt(self.vx * self.vx + self.vy * self.vy)


@dataclass
class Orbit(Component):
    """Orbital parameters for celestial bodies."""
    parent_name: str  # Name of parent body
    semi_major_axis: float  # AU
    orbital_period: float  # Earth days
    current_angle: float = 0.0  # Radians, 0 = positive x-axis
    clockwise: bool = False  # Most orbits are counter-clockwise

    def get_position_at_angle(self, angle: float) -> tuple[float, float]:
        """Get orbital position at a given angle (circular orbit)."""
        x = self.semi_major_axis * math.cos(angle)
        y = self.semi_major_axis * math.sin(angle)
        return (x, y)

    def angular_velocity(self) -> float:
        """Get angular velocity in radians per day."""
        if self.orbital_period <= 0:
            return 0.0
        return (2 * math.pi) / self.orbital_period


@dataclass
class ParentBody(Component):
    """Component for entities that stay at fixed offset from a parent body.

    Used for moons (static relative to planet) and stations (locked to parent).
    """
    parent_name: str  # Name of parent celestial body
    offset_x: float = 0.0  # Fixed offset in AU from parent
    offset_y: float = 0.0  # Fixed offset in AU from parent


class OrbitalMechanics:
    """Helper class for orbital calculations."""

    @staticmethod
    def calculate_transfer_time(
        start_pos: Position,
        end_pos: Position,
        speed: float
    ) -> float:
        """Calculate travel time between two positions at given speed.

        Args:
            start_pos: Starting position
            end_pos: Ending position
            speed: Travel speed in AU per day

        Returns:
            Travel time in days
        """
        distance = start_pos.distance_to(end_pos)
        if speed <= 0:
            return float('inf')
        return distance / speed

    @staticmethod
    def hohmann_transfer_time(
        r1: float,
        r2: float
    ) -> float:
        """Calculate Hohmann transfer orbit time between two circular orbits.

        This is more realistic but slower than direct travel.

        Args:
            r1: Radius of inner orbit (AU)
            r2: Radius of outer orbit (AU)

        Returns:
            Transfer time in days
        """
        # Semi-major axis of transfer orbit
        a_transfer = (r1 + r2) / 2
        # Kepler's third law: T^2 = a^3 (in years, AU)
        # Transfer is half an orbit
        period_years = math.sqrt(a_transfer ** 3)
        transfer_time_days = period_years * 365.25 / 2
        return transfer_time_days


class OrbitalSystem(System):
    """System that updates orbital positions."""

    priority = 0  # Run first

    def __init__(self) -> None:
        # Cache parent positions for efficiency
        self._parent_positions: dict[str, Position] = {}

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update all orbital positions."""
        # First pass: cache all positions by name
        self._parent_positions.clear()
        for entity, pos in entity_manager.get_all_components(Position):
            if entity.name:
                self._parent_positions[entity.name] = pos

        # Second pass: update orbits (for planets and other orbiting bodies)
        # Convert dt from seconds to days (1 real second = 1 game day)
        # This makes 30-60 days to Jupiter = 30-60 seconds real time
        dt_days = dt  # 1 second = 1 day (X-Drive era)

        for entity, orbit in entity_manager.get_all_components(Orbit):
            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            # Update orbital angle
            angular_vel = orbit.angular_velocity()
            if orbit.clockwise:
                angular_vel = -angular_vel
            orbit.current_angle += angular_vel * dt_days
            orbit.current_angle %= (2 * math.pi)

            # Calculate new position relative to parent
            rel_x, rel_y = orbit.get_position_at_angle(orbit.current_angle)

            # Add parent position
            parent_pos = self._parent_positions.get(orbit.parent_name)
            if parent_pos:
                pos.x = parent_pos.x + rel_x
                pos.y = parent_pos.y + rel_y
            else:
                pos.x = rel_x
                pos.y = rel_y

        # Third pass: update entities with ParentBody (moons, stations)
        # These stay at fixed offset from their parent
        for entity, parent_body in entity_manager.get_all_components(ParentBody):
            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            parent_pos = self._parent_positions.get(parent_body.parent_name)
            if parent_pos:
                pos.x = parent_pos.x + parent_body.offset_x
                pos.y = parent_pos.y + parent_body.offset_y


class MovementSystem(System):
    """System that updates positions based on velocity for non-orbital objects."""

    priority = 5  # Run after orbital system

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update positions based on velocity."""
        # Convert dt to days - same as OrbitalSystem for consistency
        dt_days = dt  # 1 second = 1 day (X-Drive era)

        for entity, vel in entity_manager.get_all_components(Velocity):
            # Skip if entity has an orbit (handled by OrbitalSystem)
            if entity_manager.has_component(entity, Orbit):
                continue

            # Skip if entity is locked to a parent body (handled by OrbitalSystem)
            if entity_manager.has_component(entity, ParentBody):
                continue

            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            pos.x += vel.vx * dt_days
            pos.y += vel.vy * dt_days


@dataclass
class NavigationTarget(Component):
    """Component for entities moving towards a target with acceleration.

    Supports tracking a moving celestial body with predictive targeting.
    """
    target_x: float = 0.0
    target_y: float = 0.0
    max_speed: float = 0.10  # AU per day (cruise speed) - X-Drive era
    current_speed: float = 0.0  # Current speed (for acceleration)
    acceleration: float = 0.03  # AU per day per day (how fast we speed up)
    arrival_threshold: float = 0.005  # AU - tight threshold for station arrival (~750,000 km)

    # Target body tracking - if set, coordinates are updated each frame
    target_body_name: str = ""  # Name of celestial body to track
    orbit_capture_distance: float = 0.02  # AU - capture orbit when very close to body

    def has_arrived(self, current_pos: Position) -> bool:
        """Check if close enough to target."""
        dx = self.target_x - current_pos.x
        dy = self.target_y - current_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        return dist <= self.arrival_threshold

    def should_capture_orbit(self, current_pos: Position) -> bool:
        """Check if close enough to capture into orbit around target body."""
        dx = self.target_x - current_pos.x
        dy = self.target_y - current_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        return dist <= self.orbit_capture_distance

    def get_stopping_distance(self) -> float:
        """Calculate distance needed to decelerate to stop."""
        # d = v^2 / (2a) - basic kinematics
        if self.acceleration <= 0:
            return 0
        return (self.current_speed * self.current_speed) / (2 * self.acceleration)


class NavigationSystem(System):
    """System that moves entities towards their navigation targets with predictive tracking."""

    priority = 3  # Run between orbital and movement systems

    def __init__(self) -> None:
        # Cache of body positions and orbits for predictive targeting
        self._body_positions: dict[str, Position] = {}
        self._body_orbits: dict[str, Orbit] = {}

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update velocities to move towards targets with predictive tracking."""
        dt_days = dt  # 1 second = 1 day (X-Drive era)

        # Cache celestial body positions and orbits
        self._update_body_cache(entity_manager)

        # Collect into list first to avoid modifying dict during iteration
        nav_entities = list(entity_manager.get_all_components(NavigationTarget))
        for entity, nav in nav_entities:
            pos = entity_manager.get_component(entity, Position)
            vel = entity_manager.get_component(entity, Velocity)

            if not pos or not vel:
                continue

            # If ship has a ParentBody, it's locked - remove it to start moving
            if entity_manager.has_component(entity, ParentBody):
                entity_manager.remove_component(entity, ParentBody)
                # Release parking slot
                from ..entities.station_slots import ShipParkingManager
                for _, pm in entity_manager.get_all_components(ShipParkingManager):
                    pm.release_parking(entity.id)
                    break

            # Update target position if tracking a body
            if nav.target_body_name:
                self._update_target_for_body(nav, pos, entity_manager)

            # Calculate direction and distance to target
            dx = nav.target_x - pos.x
            dy = nav.target_y - pos.y
            dist = math.sqrt(dx * dx + dy * dy)

            # Check for orbit capture - if close enough to target body, lock to it
            if nav.target_body_name and nav.should_capture_orbit(pos):
                # Lock to target body
                self._lock_to_body(entity, pos, nav.target_body_name, entity_manager)
                vel.vx = 0.0
                vel.vy = 0.0
                nav.current_speed = 0.0
                # Remove navigation target - we've arrived
                entity_manager.remove_component(entity, NavigationTarget)
                continue

            # Check if arrived at fixed coordinate (no body tracking)
            # Note: We don't remove NavigationTarget here - ShipAI will do that
            # after processing the arrival (advancing trade states, etc.)
            if not nav.target_body_name and (nav.has_arrived(pos) or dist <= 0.001):
                pos.x = nav.target_x
                pos.y = nav.target_y
                vel.vx = 0.0
                vel.vy = 0.0
                nav.current_speed = 0.0
                self._lock_to_nearest_body(entity, pos, entity_manager)
                continue

            # Normalize direction
            if dist < 0.001:
                continue  # Too close to determine direction
            dir_x = dx / dist
            dir_y = dy / dist

            # Calculate stopping distance
            stopping_dist = nav.get_stopping_distance()

            # Determine if we should accelerate or decelerate
            if dist <= stopping_dist + nav.orbit_capture_distance:
                # Decelerate - approaching capture zone
                nav.current_speed = max(0.01, nav.current_speed - nav.acceleration * dt_days)
            elif nav.current_speed < nav.max_speed:
                # Accelerate towards max speed
                nav.current_speed = min(nav.max_speed, nav.current_speed + nav.acceleration * dt_days)

            # Set velocity - MovementSystem will apply it
            vel.vx = dir_x * nav.current_speed
            vel.vy = dir_y * nav.current_speed

    def _update_target_for_body(
        self,
        nav: NavigationTarget,
        ship_pos: Position,
        entity_manager: EntityManager
    ) -> None:
        """Update navigation target to intercept a moving body."""
        body_name = nav.target_body_name

        # Get current body position
        body_pos = self._body_positions.get(body_name)
        body_orbit = self._body_orbits.get(body_name)

        if not body_pos:
            return  # Body not found

        if not body_orbit:
            # Body doesn't orbit (Sun, or moons with ParentBody) - just track current position
            nav.target_x = body_pos.x
            nav.target_y = body_pos.y
            return

        # Calculate distance and estimated travel time
        dx = body_pos.x - ship_pos.x
        dy = body_pos.y - ship_pos.y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 0.01:
            # Already at target
            nav.target_x = body_pos.x
            nav.target_y = body_pos.y
            return

        # Estimate travel time based on current and max speed
        avg_speed = (nav.current_speed + nav.max_speed) / 2 if nav.current_speed > 0 else nav.max_speed
        if avg_speed < 0.01:
            avg_speed = nav.max_speed

        estimated_days = dist / avg_speed

        # Calculate where the body will be when we arrive
        angular_vel = body_orbit.angular_velocity()
        if body_orbit.clockwise:
            angular_vel = -angular_vel

        future_angle = body_orbit.current_angle + (angular_vel * estimated_days)
        future_x, future_y = body_orbit.get_position_at_angle(future_angle)

        # Add parent position if body has a parent
        parent_pos = self._body_positions.get(body_orbit.parent_name)
        if parent_pos:
            future_x += parent_pos.x
            future_y += parent_pos.y

        nav.target_x = future_x
        nav.target_y = future_y

    def _update_body_cache(self, entity_manager: EntityManager) -> None:
        """Cache celestial body positions and orbits for predictive targeting."""
        from ..entities.celestial import CelestialBody

        self._body_positions.clear()
        self._body_orbits.clear()

        for entity, body in entity_manager.get_all_components(CelestialBody):
            pos = entity_manager.get_component(entity, Position)
            orbit = entity_manager.get_component(entity, Orbit)
            if pos and entity.name:
                self._body_positions[entity.name] = pos
            if orbit and entity.name:
                self._body_orbits[entity.name] = orbit

    def _lock_to_body(
        self,
        entity,
        pos: Position,
        body_name: str,
        entity_manager: EntityManager
    ) -> None:
        """Lock a ship to a specific celestial body using parking slots."""
        from ..entities.station_slots import ShipParkingManager, get_ship_parking_offset

        body_pos = self._body_positions.get(body_name)
        if not body_pos:
            return

        # Try to get parking manager and assign a slot
        parking_manager = None
        for _, pm in entity_manager.get_all_components(ShipParkingManager):
            parking_manager = pm
            break

        if parking_manager:
            # Assign a parking slot
            slot_index = parking_manager.assign_parking(body_name, entity.id)
            if slot_index is not None:
                # Use parking slot offset
                offset_x, offset_y = get_ship_parking_offset(slot_index)
            else:
                # No slots available - use fallback position
                offset_x = pos.x - body_pos.x
                offset_y = pos.y - body_pos.y
                offset_dist = math.sqrt(offset_x * offset_x + offset_y * offset_y)
                if offset_dist > 0.1:
                    offset_x = (offset_x / offset_dist) * 0.05
                    offset_y = (offset_y / offset_dist) * 0.05
        else:
            # No parking manager - use old behavior
            offset_x = pos.x - body_pos.x
            offset_y = pos.y - body_pos.y
            offset_dist = math.sqrt(offset_x * offset_x + offset_y * offset_y)
            if offset_dist > 0.1:
                offset_x = (offset_x / offset_dist) * 0.05
                offset_y = (offset_y / offset_dist) * 0.05

        # Snap position to orbit
        pos.x = body_pos.x + offset_x
        pos.y = body_pos.y + offset_y

        # Add ParentBody component
        entity_manager.add_component(entity, ParentBody(
            parent_name=body_name,
            offset_x=offset_x,
            offset_y=offset_y
        ))

    def _lock_to_nearest_body(
        self,
        entity,
        pos: Position,
        entity_manager: EntityManager
    ) -> None:
        """Lock a ship to the nearest celestial body so it moves with the planet."""
        nearest_body = None
        nearest_dist = float('inf')
        nearest_pos = None

        for body_name, body_pos in self._body_positions.items():
            dx = body_pos.x - pos.x
            dy = body_pos.y - pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_body = body_name
                nearest_pos = body_pos

        if nearest_body and nearest_pos:
            # Calculate offset from body
            offset_x = pos.x - nearest_pos.x
            offset_y = pos.y - nearest_pos.y

            # Add ParentBody component to lock ship to this body
            entity_manager.add_component(entity, ParentBody(
                parent_name=nearest_body,
                offset_x=offset_x,
                offset_y=offset_y
            ))
