"""Main rendering logic."""
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
import math

from ..config import COLORS, SCREEN_WIDTH, SCREEN_HEIGHT
from .camera import Camera
from .panels import InfoPanel, StatusBar, MiniMap

if TYPE_CHECKING:
    from ..core.world import World
    from ..core.ecs import Entity


class Renderer:
    """Main renderer for the game."""

    def __init__(self, screen: pygame.Surface, camera: Camera) -> None:
        self.screen = screen
        self.camera = camera

        # Initialize font
        pygame.font.init()
        self.font = pygame.font.Font(None, 20)
        self.font_large = pygame.font.Font(None, 28)

        # UI panels
        self.info_panel = InfoPanel(
            x=10, y=10, width=250, height=200, title="Info"
        )
        self.status_bar = StatusBar(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.minimap = MiniMap(x=SCREEN_WIDTH - 160, y=10, size=150)

        # State
        self.selected_entity: Entity | None = None
        self.show_ui = True
        self.show_orbits = True
        self.show_labels = True

    def render(self, world: World, fps: float) -> None:
        """Render the game state."""
        # Clear screen
        self.screen.fill(COLORS['background'])

        # Render world
        self._render_orbits(world)
        self._render_celestial_bodies(world)
        self._render_stations(world)
        self._render_ships(world)

        # Render UI
        if self.show_ui:
            self._render_ui(world, fps)

    def _render_orbits(self, world: World) -> None:
        """Render orbital paths."""
        if not self.show_orbits:
            return

        from ..solar_system.orbits import Orbit, Position

        em = world.entity_manager

        for entity, orbit in em.get_all_components(Orbit):
            # Get parent position
            parent_pos = Position(x=0, y=0)
            for e in em.get_entities_with(Position):
                if e.name == orbit.parent_name:
                    p = em.get_component(e, Position)
                    if p:
                        parent_pos = p
                    break

            # Calculate orbit center on screen
            center_x, center_y = self.camera.world_to_screen(parent_pos.x, parent_pos.y)

            # Calculate orbit radius in pixels
            radius = int(orbit.semi_major_axis * self.camera.zoom * 100)

            # Only draw if orbit is visible
            if radius > 2 and radius < 10000:
                pygame.draw.circle(
                    self.screen, COLORS['orbit'],
                    (center_x, center_y), radius, 1
                )

    def _render_celestial_bodies(self, world: World) -> None:
        """Render planets, moons, etc."""
        from ..solar_system.orbits import Position
        from ..entities.celestial import CelestialBody, get_body_display_radius

        em = world.entity_manager

        for entity, body in em.get_all_components(CelestialBody):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            # Convert to screen coordinates
            screen_x, screen_y = self.camera.world_to_screen(pos.x, pos.y)

            # Skip if off screen
            if not (-100 < screen_x < SCREEN_WIDTH + 100 and -100 < screen_y < SCREEN_HEIGHT + 100):
                continue

            # Get display radius
            radius = int(get_body_display_radius(body, self.camera.zoom))

            # Draw body
            pygame.draw.circle(self.screen, body.color, (screen_x, screen_y), radius)

            # Draw selection highlight
            if self.selected_entity and entity.id == self.selected_entity.id:
                pygame.draw.circle(
                    self.screen, COLORS['ui_highlight'],
                    (screen_x, screen_y), radius + 3, 2
                )

            # Draw label
            if self.show_labels and radius > 3:
                label = self.font.render(entity.name, True, COLORS['ui_text'])
                self.screen.blit(label, (screen_x + radius + 5, screen_y - 8))

    def _render_stations(self, world: World) -> None:
        """Render stations."""
        from ..solar_system.orbits import Position
        from ..entities.stations import Station

        em = world.entity_manager

        for entity, station in em.get_all_components(Station):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            screen_x, screen_y = self.camera.world_to_screen(pos.x, pos.y)

            # Skip if off screen
            if not (-50 < screen_x < SCREEN_WIDTH + 50 and -50 < screen_y < SCREEN_HEIGHT + 50):
                continue

            # Draw station as square
            size = 6
            rect = pygame.Rect(screen_x - size//2, screen_y - size//2, size, size)
            pygame.draw.rect(self.screen, COLORS['station'], rect)

            # Draw selection highlight
            if self.selected_entity and entity.id == self.selected_entity.id:
                pygame.draw.rect(
                    self.screen, COLORS['ui_highlight'],
                    rect.inflate(6, 6), 2
                )

            # Draw label
            if self.show_labels and self.camera.zoom > 0.5:
                label = self.font.render(entity.name, True, COLORS['ui_text'])
                self.screen.blit(label, (screen_x + size + 3, screen_y - 8))

    def _render_ships(self, world: World) -> None:
        """Render ships."""
        from ..solar_system.orbits import Position, Velocity
        from ..entities.ships import Ship

        em = world.entity_manager

        for entity, ship in em.get_all_components(Ship):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            screen_x, screen_y = self.camera.world_to_screen(pos.x, pos.y)

            # Skip if off screen
            if not (-50 < screen_x < SCREEN_WIDTH + 50 and -50 < screen_y < SCREEN_HEIGHT + 50):
                continue

            # Draw ship as triangle
            size = 5
            vel = em.get_component(entity, Velocity)

            # Calculate rotation based on velocity
            if vel and (vel.vx != 0 or vel.vy != 0):
                angle = math.atan2(-vel.vy, vel.vx)  # Negative vy due to screen coords
            else:
                angle = 0

            # Triangle points
            points = [
                (screen_x + size * math.cos(angle),
                 screen_y + size * math.sin(angle)),
                (screen_x + size * math.cos(angle + 2.5),
                 screen_y + size * math.sin(angle + 2.5)),
                (screen_x + size * math.cos(angle - 2.5),
                 screen_y + size * math.sin(angle - 2.5)),
            ]

            pygame.draw.polygon(self.screen, COLORS['ship'], points)

            # Draw selection highlight
            if self.selected_entity and entity.id == self.selected_entity.id:
                pygame.draw.circle(
                    self.screen, COLORS['ui_highlight'],
                    (screen_x, screen_y), size + 4, 2
                )

    def _render_ui(self, world: World, fps: float) -> None:
        """Render UI elements."""
        # Update and draw info panel
        self.info_panel.update(world, self.selected_entity)
        self.info_panel.draw(self.screen, self.font)

        # Draw status bar
        self.status_bar.draw_status(self.screen, self.font, world, fps)

        # Draw minimap
        camera_bounds = self.camera.get_visible_bounds()
        self.minimap.draw_minimap(self.screen, world, camera_bounds)

    def select_at(self, world_x: float, world_y: float, world: World) -> Entity | None:
        """Try to select an entity at world coordinates.

        Args:
            world_x: World X coordinate
            world_y: World Y coordinate
            world: The game world

        Returns:
            Selected entity or None
        """
        from ..solar_system.orbits import Position
        from ..entities.celestial import CelestialBody, get_body_display_radius
        from ..entities.stations import Station
        from ..entities.ships import Ship

        em = world.entity_manager
        best_entity: Entity | None = None
        best_dist = float('inf')

        # Selection radius in AU (adjust based on zoom)
        select_radius = 0.1 / self.camera.zoom

        # Check all positionable entities
        for entity, pos in em.get_all_components(Position):
            dx = pos.x - world_x
            dy = pos.y - world_y
            dist = math.sqrt(dx * dx + dy * dy)

            # Adjust selection radius based on entity type
            entity_radius = select_radius
            body = em.get_component(entity, CelestialBody)
            if body:
                # Larger selection area for celestial bodies
                screen_radius = get_body_display_radius(body, self.camera.zoom)
                entity_radius = max(select_radius, screen_radius / (self.camera.zoom * 100))

            if dist < entity_radius and dist < best_dist:
                best_dist = dist
                best_entity = entity

        self.selected_entity = best_entity
        return best_entity

    def deselect(self) -> None:
        """Clear selection."""
        self.selected_entity = None

    def toggle_ui(self) -> None:
        """Toggle UI visibility."""
        self.show_ui = not self.show_ui

    def toggle_orbits(self) -> None:
        """Toggle orbit display."""
        self.show_orbits = not self.show_orbits

    def toggle_labels(self) -> None:
        """Toggle label display."""
        self.show_labels = not self.show_labels
