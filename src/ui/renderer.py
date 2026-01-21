"""Main rendering logic."""
from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID
import pygame
import math

from ..config import COLORS, SCREEN_WIDTH, SCREEN_HEIGHT
from .camera import Camera
from .panels import InfoPanel, StatusBar, MiniMap, BuildMenuPanel, PlayerHUD
from ..entities.stations import StationType

if TYPE_CHECKING:
    from ..core.world import World
    from ..core.ecs import Entity
    from ..systems.building import BuildingSystem


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
            x=10, y=120, width=250, height=200, title="Info"
        )
        self.status_bar = StatusBar(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.minimap = MiniMap(x=SCREEN_WIDTH - 160, y=10, size=150)
        self.build_menu = BuildMenuPanel(x=SCREEN_WIDTH - 240, y=170)
        self.build_menu.visible = False
        self.player_hud = PlayerHUD(x=10, y=10)

        # State
        self.selected_entity: Entity | None = None
        self.show_ui = True
        self.show_orbits = True
        self.show_labels = True

        # Build mode state
        self.build_mode_active = False
        self.build_menu_visible = False
        self.selected_station_type: StationType | None = None
        self.mouse_world_x = 0.0
        self.mouse_world_y = 0.0

        # Player faction info
        self.player_faction_id: UUID | None = None
        self.player_faction_color: tuple[int, int, int] = (255, 255, 255)
        self.building_system: "BuildingSystem | None" = None
        self._world: "World | None" = None

    def set_player_faction(self, faction_id: UUID | None, world: "World") -> None:
        """Set the player faction for highlighting."""
        self.player_faction_id = faction_id
        self._world = world

        if faction_id and world:
            from ..entities.factions import Faction
            em = world.entity_manager
            for entity, faction in em.get_all_components(Faction):
                if entity.id == faction_id:
                    self.player_faction_color = faction.color
                    break

    def set_building_system(self, building_system: "BuildingSystem") -> None:
        """Set the building system reference."""
        self.building_system = building_system

    def update_mouse_position(self, world_x: float, world_y: float) -> None:
        """Update the current mouse world position for build preview."""
        self.mouse_world_x = world_x
        self.mouse_world_y = world_y

    def toggle_build_menu(self) -> None:
        """Toggle the build menu visibility."""
        self.build_menu_visible = not self.build_menu_visible
        self.build_menu.visible = self.build_menu_visible

        if not self.build_menu_visible:
            self.cancel_build_mode()

    def select_build_option(self, index: int) -> None:
        """Select a build option from the menu."""
        if not self._world:
            return

        # Update credits in build menu
        self._update_build_menu_credits()

        station_type = self.build_menu.select_option(index)
        if station_type:
            self.selected_station_type = station_type
            self.build_mode_active = True

    def cancel_build_mode(self) -> None:
        """Cancel build mode."""
        self.build_mode_active = False
        self.selected_station_type = None
        self.build_menu.selected_index = -1

    def try_place_station(self, world_x: float, world_y: float, world: "World") -> bool:
        """Try to place a station at the given world coordinates.

        Returns:
            True if station was placed successfully
        """
        if not self.build_mode_active or not self.selected_station_type:
            return False

        if not self.building_system or not self.player_faction_id:
            return False

        # Find nearest celestial body
        parent_body, distance = self.building_system.find_nearest_body(
            (world_x, world_y), world.entity_manager
        )

        # Get resource type if building a mining station
        resource_type = None
        if self.selected_station_type == StationType.MINING_STATION:
            resources = self.building_system.get_body_resources(
                parent_body, world.entity_manager
            )
            if resources:
                resource_type = resources[0][0]  # Use first available resource

        # Request the build
        result = self.building_system.request_build(
            world=world,
            faction_id=self.player_faction_id,
            station_type=self.selected_station_type,
            position=(world_x, world_y),
            parent_body=parent_body,
            resource_type=resource_type,
        )

        if result.success:
            # Successfully built - exit build mode but keep menu open
            self.build_mode_active = False
            self.selected_station_type = None
            self.build_menu.selected_index = -1
            return True

        return False

    def _update_build_menu_credits(self) -> None:
        """Update credits and materials in the build menu."""
        if not self._world or not self.player_faction_id:
            return

        from ..entities.factions import Faction
        from ..entities.stations import Station
        from ..simulation.resources import Inventory

        em = self._world.entity_manager

        # Get player credits
        credits = 0.0
        for entity, faction in em.get_all_components(Faction):
            if entity.id == self.player_faction_id:
                credits = faction.credits
                break

        # Sum up materials across all player-owned stations
        materials: dict = {}
        for entity, station in em.get_all_components(Station):
            if station.owner_faction_id == self.player_faction_id:
                inv = em.get_component(entity, Inventory)
                if inv:
                    for resource, amount in inv.resources.items():
                        materials[resource] = materials.get(resource, 0) + amount

        self.build_menu.update_player_resources(credits, materials)

    def render(self, world: World, fps: float) -> None:
        """Render the game state."""
        # Clear screen
        self.screen.fill(COLORS['background'])

        # Render world
        self._render_orbits(world)
        self._render_celestial_bodies(world)
        self._render_stations(world)
        self._render_ships(world)

        # Render build preview if in build mode
        if self.build_mode_active:
            self._render_build_preview(world)

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

            # Determine station color based on owner
            is_player_owned = (
                self.player_faction_id and
                station.owner_faction_id == self.player_faction_id
            )

            if is_player_owned:
                station_color = self.player_faction_color
            else:
                # Get owner faction color if owned
                station_color = COLORS['station']
                if station.owner_faction_id:
                    from ..entities.factions import Faction
                    for f_entity, faction in em.get_all_components(Faction):
                        if f_entity.id == station.owner_faction_id:
                            station_color = faction.color
                            break

            # Draw station as square
            size = 6
            rect = pygame.Rect(screen_x - size//2, screen_y - size//2, size, size)
            pygame.draw.rect(self.screen, station_color, rect)

            # Draw player ownership indicator (extra border)
            if is_player_owned:
                pygame.draw.rect(
                    self.screen, self.player_faction_color,
                    rect.inflate(4, 4), 1
                )

            # Draw selection highlight
            if self.selected_entity and entity.id == self.selected_entity.id:
                pygame.draw.rect(
                    self.screen, COLORS['ui_highlight'],
                    rect.inflate(8, 8), 2
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
        # Update and draw player HUD
        self.player_hud.update(world, self.player_faction_id)
        self.player_hud.draw(self.screen, self.font)

        # Update and draw info panel
        self.info_panel.update(world, self.selected_entity)
        self.info_panel.draw(self.screen, self.font)

        # Draw status bar
        self.status_bar.draw_status(self.screen, self.font, world, fps)

        # Draw minimap
        camera_bounds = self.camera.get_visible_bounds()
        self.minimap.draw_minimap(self.screen, world, camera_bounds)

        # Update and draw build menu if visible
        if self.build_menu_visible:
            self._update_build_menu_credits()
            self.build_menu.draw(self.screen, self.font)

    def _render_build_preview(self, world: World) -> None:
        """Render the station build preview at mouse position."""
        if not self.selected_station_type:
            return

        # Convert mouse world position to screen
        screen_x, screen_y = self.camera.world_to_screen(
            self.mouse_world_x, self.mouse_world_y
        )

        # Check if position is valid
        is_valid = True
        if self.building_system:
            valid, msg = self.building_system._validate_position(
                (self.mouse_world_x, self.mouse_world_y),
                world.entity_manager
            )
            is_valid = valid

        # Choose preview color based on validity
        if is_valid:
            preview_color = (100, 255, 100, 128)  # Green for valid
            border_color = (0, 255, 0)
        else:
            preview_color = (255, 100, 100, 128)  # Red for invalid
            border_color = (255, 0, 0)

        # Draw station ghost (semi-transparent square)
        size = 10
        preview_surface = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(preview_surface, preview_color, (0, 0, size, size))
        self.screen.blit(
            preview_surface,
            (screen_x - size // 2, screen_y - size // 2)
        )

        # Draw border
        rect = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        pygame.draw.rect(self.screen, border_color, rect, 2)

        # Draw station type label
        type_names = {
            StationType.OUTPOST: "Outpost",
            StationType.MINING_STATION: "Mining",
            StationType.REFINERY: "Refinery",
            StationType.FACTORY: "Factory",
            StationType.COLONY: "Colony",
            StationType.SHIPYARD: "Shipyard",
            StationType.TRADE_HUB: "Trade Hub",
        }
        label_text = type_names.get(self.selected_station_type, "Station")
        label = self.font.render(label_text, True, border_color)
        self.screen.blit(label, (screen_x + size, screen_y - 8))

        # Draw position info
        pos_text = f"({self.mouse_world_x:.2f}, {self.mouse_world_y:.2f}) AU"
        pos_label = self.font.render(pos_text, True, COLORS['ui_text'])
        self.screen.blit(pos_label, (screen_x + size, screen_y + 8))

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
