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
        # Convert dt from seconds to days (1 real second = 1 game minute = 1/1440 day)
        dt_days = dt / 60.0  # dt is in game-minutes, convert to days

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
        dt_days = dt / 60.0

        for entity, vel in entity_manager.get_all_components(Velocity):
            # Skip if entity has an orbit (handled by OrbitalSystem)
            if entity_manager.has_component(entity, Orbit):
                continue

            pos = entity_manager.get_component(entity, Position)
            if not pos:
                continue

            pos.x += vel.vx * dt_days
            pos.y += vel.vy * dt_days


@dataclass
class NavigationTarget(Component):
    """Component for entities moving towards a target with acceleration."""
    target_x: float = 0.0
    target_y: float = 0.0
    max_speed: float = 2.0  # AU per day (cruise speed)
    current_speed: float = 0.0  # Current speed (for acceleration)
    acceleration: float = 0.5  # AU per day per day (how fast we speed up)
    arrival_threshold: float = 0.02  # AU

    def has_arrived(self, current_pos: Position) -> bool:
        """Check if close enough to target."""
        dx = self.target_x - current_pos.x
        dy = self.target_y - current_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        return dist <= self.arrival_threshold

    def get_stopping_distance(self) -> float:
        """Calculate distance needed to decelerate to stop."""
        # d = v^2 / (2a) - basic kinematics
        if self.acceleration <= 0:
            return 0
        return (self.current_speed * self.current_speed) / (2 * self.acceleration)


class NavigationSystem(System):
    """System that moves entities towards their navigation targets with acceleration."""

    priority = 3  # Run between orbital and movement systems

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update velocities to move towards targets with acceleration/deceleration."""
        dt_days = dt / 60.0  # Same conversion as other systems

        for entity, nav in entity_manager.get_all_components(NavigationTarget):
            pos = entity_manager.get_component(entity, Position)
            vel = entity_manager.get_component(entity, Velocity)

            if not pos or not vel:
                continue

            # Calculate direction and distance to target
            dx = nav.target_x - pos.x
            dy = nav.target_y - pos.y
            dist = math.sqrt(dx * dx + dy * dy)

            # Check if arrived (use a slightly larger threshold for fast-moving ships)
            if nav.has_arrived(pos) or dist <= 0.001:
                # Snap to target position to prevent drift
                pos.x = nav.target_x
                pos.y = nav.target_y
                vel.vx = 0.0
                vel.vy = 0.0
                nav.current_speed = 0.0
                continue

            # Normalize direction
            dir_x = dx / dist
            dir_y = dy / dist

            # Calculate stopping distance
            stopping_dist = nav.get_stopping_distance()

            # Determine if we should accelerate or decelerate
            if dist <= stopping_dist + nav.arrival_threshold:
                # Decelerate - we're close enough to start slowing down
                nav.current_speed = max(0.1, nav.current_speed - nav.acceleration * dt_days)
            elif nav.current_speed < nav.max_speed:
                # Accelerate towards max speed
                nav.current_speed = min(nav.max_speed, nav.current_speed + nav.acceleration * dt_days)

            # Calculate how far we would move this frame
            frame_distance = nav.current_speed * dt_days

            # If we would overshoot, clamp to the remaining distance
            if frame_distance >= dist:
                # Move directly to target
                pos.x = nav.target_x
                pos.y = nav.target_y
                vel.vx = 0.0
                vel.vy = 0.0
                nav.current_speed = 0.0
            else:
                # Set velocity - MovementSystem will apply it
                vel.vx = dir_x * nav.current_speed
                vel.vy = dir_y * nav.current_speed
