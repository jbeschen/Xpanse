"""Sector view renderer - shows a planetary sector with square grid layout."""
from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID
import pygame
import math

from ..config import COLORS
from ..solar_system.sectors import (
    Sector, SectorBody, SECTORS, GRID_SIZE, GRID_COLS, GRID_ROWS,
    grid_to_pixel, pixel_to_grid, get_sector_for_body
)

if TYPE_CHECKING:
    from ..core.world import World
    from ..core.ecs import Entity


class SectorView:
    """Renders a sector view with square grid and detailed entity icons."""

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height

        # Current sector being viewed
        self.current_sector: Sector | None = None
        self.current_sector_id: str = ""

        # Camera/view state (similar to main camera)
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.zoom = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 3.0

        # Panning state
        self.is_panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.pan_start_offset_x = 0.0
        self.pan_start_offset_y = 0.0

        # Selection state
        self.selected_body: str | None = None
        self.selected_station_id: UUID | None = None
        self.selected_ship_id: UUID | None = None
        self.hovered_body: str | None = None
        self.hovered_station_id: UUID | None = None

        # Build mode state (set by renderer)
        self.build_mode_active = False
        self.selected_station_type = None

        # Fonts
        pygame.font.init()
        self.font = pygame.font.Font(None, 18)
        self.font_medium = pygame.font.Font(None, 22)
        self.font_large = pygame.font.Font(None, 28)
        self.font_title = pygame.font.Font(None, 36)

    def enter_sector(self, sector_id: str) -> bool:
        """Enter a sector view.

        Args:
            sector_id: ID of the sector to view

        Returns:
            True if sector exists and was entered
        """
        if sector_id not in SECTORS:
            return False

        self.current_sector = SECTORS[sector_id]
        self.current_sector_id = sector_id
        self.offset_x = 0
        self.offset_y = 0
        self.zoom = 1.0
        self.selected_body = None
        self.selected_station_id = None
        self.selected_ship_id = None
        return True

    def exit_sector(self) -> None:
        """Exit the current sector view."""
        self.current_sector = None
        self.current_sector_id = ""

    @property
    def is_active(self) -> bool:
        """Check if sector view is active."""
        return self.current_sector is not None

    def get_center(self) -> tuple[float, float]:
        """Get the center of the view."""
        return (
            self.screen_width / 2 + self.offset_x,
            self.screen_height / 2 + self.offset_y
        )

    def handle_resize(self, new_width: int, new_height: int) -> None:
        """Handle window resize."""
        self.screen_width = new_width
        self.screen_height = new_height

    # Camera controls
    def start_pan(self, screen_x: int, screen_y: int) -> None:
        """Start panning the view (drag to move camera)."""
        self.is_panning = True
        self.pan_start_x = screen_x
        self.pan_start_y = screen_y
        self.pan_start_offset_x = self.offset_x
        self.pan_start_offset_y = self.offset_y

    def update_pan(self, screen_x: int, screen_y: int) -> None:
        """Update pan based on mouse movement.

        Dragging right moves camera right, so world appears to move left.
        """
        if self.is_panning:
            dx = screen_x - self.pan_start_x
            dy = screen_y - self.pan_start_y
            # Negate to get camera movement feel (drag right = camera moves right = world moves left)
            self.offset_x = self.pan_start_offset_x - dx
            self.offset_y = self.pan_start_offset_y - dy

    def end_pan(self) -> None:
        """End panning."""
        self.is_panning = False

    def zoom_in(self, focus_x: int, focus_y: int) -> None:
        """Zoom in centered on screen center (ignore focus point for simplicity)."""
        self.zoom = min(self.zoom * 1.15, self.max_zoom)

    def zoom_out(self, focus_x: int, focus_y: int) -> None:
        """Zoom out centered on screen center."""
        self.zoom = max(self.zoom / 1.15, self.min_zoom)

    def pan_by_screen(self, dx: int, dy: int) -> None:
        """Pan the view by screen pixels (arrow key panning).

        Pressing right arrow moves camera right, so world appears to move left.
        """
        # Negate for camera movement feel
        self.offset_x -= dx
        self.offset_y -= dy

    def grid_to_screen(self, grid_x: int, grid_y: int) -> tuple[float, float]:
        """Convert grid coordinates to screen coordinates."""
        center_x, center_y = self.get_center()
        return grid_to_pixel(grid_x, grid_y, center_x, center_y, self.zoom)

    def screen_to_grid(self, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Convert screen coordinates to grid coordinates."""
        center_x, center_y = self.get_center()
        return pixel_to_grid(screen_x, screen_y, center_x, center_y, self.zoom)

    def get_body_at_screen(self, screen_x: int, screen_y: int) -> str | None:
        """Get the body at a screen position."""
        if not self.current_sector:
            return None

        for body in self.current_sector.bodies:
            bx, by = self.grid_to_screen(body.grid_x, body.grid_y)
            radius = GRID_SIZE * body.radius * 0.4 * self.zoom
            dist = math.sqrt((screen_x - bx)**2 + (screen_y - by)**2)
            if dist < radius + 10:  # Small buffer for easier clicking
                return body.name

        return None

    def get_station_at_screen(
        self,
        screen_x: int,
        screen_y: int,
        world: "World"
    ) -> UUID | None:
        """Get the station at a screen position."""
        if not self.current_sector:
            return None

        from ..entities.stations import Station
        from ..entities.station_slots import OrbitalSlotManager, get_slot_offset

        em = world.entity_manager

        for entity, station in em.get_all_components(Station):
            body = self.current_sector.get_body(station.parent_body)
            if not body:
                continue

            bx, by = self.grid_to_screen(body.grid_x, body.grid_y)
            body_radius = GRID_SIZE * body.radius * 0.4 * self.zoom

            # Get station's orbital slot position
            slot_index = 0
            for _, slot_mgr in em.get_all_components(OrbitalSlotManager):
                if station.parent_body in slot_mgr.slot_assignments:
                    for slot, sid in slot_mgr.slot_assignments[station.parent_body].items():
                        if sid == entity.id:
                            slot_index = slot
                            break
                break

            # Calculate orbital position (same as render)
            ring = slot_index // 4
            clock_pos = slot_index % 4
            orbit_dist = body_radius + (25 + ring * 22) * self.zoom
            angles = [math.pi / 2, 0, -math.pi / 2, math.pi]
            angle = angles[clock_pos]
            sx = bx + orbit_dist * math.cos(angle)
            sy = by - orbit_dist * math.sin(angle)

            dist = math.sqrt((screen_x - sx)**2 + (screen_y - sy)**2)
            if dist < 18 * self.zoom:  # Station click radius
                return entity.id

        return None

    def get_ship_at_screen(
        self,
        screen_x: int,
        screen_y: int,
        world: "World"
    ) -> UUID | None:
        """Get the ship at a screen position."""
        if not self.current_sector:
            return None

        from ..entities.ships import Ship
        from ..solar_system.orbits import ParentBody

        em = world.entity_manager

        for entity, ship in em.get_all_components(Ship):
            parent = em.get_component(entity, ParentBody)
            if not parent:
                continue

            body = self.current_sector.get_body(parent.parent_name)
            if not body:
                continue

            bx, by = self.grid_to_screen(body.grid_x, body.grid_y)
            body_radius = GRID_SIZE * body.radius * 0.4 * self.zoom

            # Scale ship offset to be outside the planet
            # Use the angle from offset and place at body_radius + 15 pixels
            offset_dist = math.sqrt(parent.offset_x**2 + parent.offset_y**2)
            if offset_dist > 0.001:
                angle = math.atan2(parent.offset_y, parent.offset_x)
            else:
                angle = 0
            ship_orbit = body_radius + 15 * self.zoom
            sx = bx + ship_orbit * math.cos(angle)
            sy = by - ship_orbit * math.sin(angle)

            dist = math.sqrt((screen_x - sx)**2 + (screen_y - sy)**2)
            if dist < 12 * self.zoom:  # Ship click radius
                return entity.id

        return None

    def update(self, mouse_x: int, mouse_y: int) -> None:
        """Update hover state."""
        self.hovered_body = self.get_body_at_screen(mouse_x, mouse_y)

    def render(
        self,
        screen: pygame.Surface,
        world: "World",
        player_faction_id: UUID | None = None,
        mouse_x: int = 0,
        mouse_y: int = 0
    ) -> None:
        """Render the sector view."""
        if not self.current_sector:
            return

        # Background - dark space
        screen.fill((8, 10, 18))

        # Draw grid
        self._render_grid(screen)

        # Draw bodies
        self._render_bodies(screen, world, player_faction_id)

        # Draw stations around bodies
        self._render_stations(screen, world, player_faction_id)

        # Draw ships in sector
        self._render_ships(screen, world, player_faction_id)

        # Draw build preview if in build mode
        if self.build_mode_active:
            self._render_build_preview(screen, world, mouse_x, mouse_y)

        # Draw sector title and info
        self._render_title(screen)

        # Draw navigation hint
        self._render_nav_hint(screen)

    def _render_grid(self, screen: pygame.Surface) -> None:
        """Render the square grid background."""
        if not self.current_sector:
            return

        center_x, center_y = self.get_center()
        grid_color = (25, 30, 40)
        grid_color_strong = (35, 42, 55)

        # Draw grid lines
        for col in range(self.current_sector.grid_cols + 1):
            x1, y1 = grid_to_pixel(col, 0, center_x, center_y, self.zoom)
            x2, y2 = grid_to_pixel(col, self.current_sector.grid_rows, center_x, center_y, self.zoom)

            # Stronger lines every 5 cells
            color = grid_color_strong if col % 5 == 0 else grid_color
            pygame.draw.line(screen, color, (x1, y1 - GRID_SIZE * self.zoom / 2),
                           (x2, y2 - GRID_SIZE * self.zoom / 2), 1)

        for row in range(self.current_sector.grid_rows + 1):
            x1, y1 = grid_to_pixel(0, row, center_x, center_y, self.zoom)
            x2, y2 = grid_to_pixel(self.current_sector.grid_cols, row, center_x, center_y, self.zoom)

            color = grid_color_strong if row % 5 == 0 else grid_color
            pygame.draw.line(screen, color, (x1 - GRID_SIZE * self.zoom / 2, y1),
                           (x2 - GRID_SIZE * self.zoom / 2, y2), 1)

    def _render_bodies(
        self,
        screen: pygame.Surface,
        world: "World",
        player_faction_id: UUID | None
    ) -> None:
        """Render celestial bodies in the sector."""
        if not self.current_sector:
            return

        for body in self.current_sector.bodies:
            px, py = self.grid_to_screen(body.grid_x, body.grid_y)
            radius = int(GRID_SIZE * body.radius * 0.4 * self.zoom)

            # Draw body with slight gradient effect
            pygame.draw.circle(screen, body.color, (int(px), int(py)), radius)

            # Draw atmosphere/glow for primary body
            if body.is_primary:
                glow_color = tuple(min(255, c + 30) for c in body.color)
                pygame.draw.circle(screen, glow_color, (int(px), int(py)), radius + 4, 2)

            # Draw hover highlight
            if body.name == self.hovered_body:
                pygame.draw.circle(
                    screen, COLORS['ui_highlight'],
                    (int(px), int(py)), radius + 6, 2
                )

            # Draw selection highlight
            if body.name == self.selected_body:
                pygame.draw.circle(
                    screen, (255, 255, 100),
                    (int(px), int(py)), radius + 8, 3
                )

            # Draw body name
            name_surf = self.font_medium.render(body.name, True, COLORS['ui_text'])
            name_x = px - name_surf.get_width() // 2
            name_y = py + radius + 10
            screen.blit(name_surf, (name_x, name_y))

            # Draw station count if any
            station_count = self._count_stations_at_body(world, body.name)
            if station_count > 0:
                count_text = f"{station_count}/{body.max_stations}"
                count_surf = self.font.render(count_text, True, (150, 200, 150))
                count_x = px - count_surf.get_width() // 2
                count_y = py + radius + 26
                screen.blit(count_surf, (count_x, count_y))

    def _render_stations(
        self,
        screen: pygame.Surface,
        world: "World",
        player_faction_id: UUID | None
    ) -> None:
        """Render stations with detailed icons around their parent bodies."""
        if not self.current_sector:
            return

        from ..entities.stations import Station, StationType
        from ..entities.factions import Faction
        from ..entities.station_slots import OrbitalSlotManager, get_slot_offset

        em = world.entity_manager

        # Build faction color lookup
        faction_colors: dict[UUID, tuple[int, int, int]] = {}
        for f_entity, faction in em.get_all_components(Faction):
            faction_colors[f_entity.id] = faction.color

        for entity, station in em.get_all_components(Station):
            body = self.current_sector.get_body(station.parent_body)
            if not body:
                continue

            bx, by = self.grid_to_screen(body.grid_x, body.grid_y)
            body_radius = GRID_SIZE * body.radius * 0.4 * self.zoom

            # Get station's orbital slot position
            slot_index = 0
            for _, slot_mgr in em.get_all_components(OrbitalSlotManager):
                if station.parent_body in slot_mgr.slot_assignments:
                    for slot, sid in slot_mgr.slot_assignments[station.parent_body].items():
                        if sid == entity.id:
                            slot_index = slot
                            break
                break

            # Calculate orbital position based on body visual radius
            # Slots 0-3 are inner ring, 4-7 middle, 8-11 outer
            ring = slot_index // 4
            clock_pos = slot_index % 4  # 0=top, 1=right, 2=bottom, 3=left

            # Orbital distance: body_radius + base offset + ring spacing
            orbit_dist = body_radius + (25 + ring * 22) * self.zoom

            # Clock position angles (top, right, bottom, left)
            angles = [math.pi / 2, 0, -math.pi / 2, math.pi]
            angle = angles[clock_pos]

            sx = bx + orbit_dist * math.cos(angle)
            sy = by - orbit_dist * math.sin(angle)  # Negative because screen y is inverted

            # Determine station color
            station_color = COLORS['station']
            if station.owner_faction_id:
                station_color = faction_colors.get(station.owner_faction_id, station_color)

            # Draw detailed station icon based on type
            self._draw_station_icon(screen, sx, sy, station.station_type, station_color, self.zoom)

            # Player ownership indicator
            is_player_owned = player_faction_id and station.owner_faction_id == player_faction_id
            if is_player_owned:
                pygame.draw.circle(screen, station_color, (int(sx), int(sy)),
                                 int(14 * self.zoom), 1)

            # Selection highlight
            if self.selected_station_id == entity.id:
                pygame.draw.circle(screen, COLORS['ui_highlight'],
                                 (int(sx), int(sy)), int(18 * self.zoom), 2)

            # Draw station name on hover or selection
            if self.hovered_body == station.parent_body or self.selected_station_id == entity.id:
                label = self.font.render(entity.name, True, COLORS['ui_text'])
                screen.blit(label, (sx + 12 * self.zoom, sy - 8))

    def _draw_station_icon(
        self,
        screen: pygame.Surface,
        x: float,
        y: float,
        station_type: "StationType",
        color: tuple[int, int, int],
        zoom: float
    ) -> None:
        """Draw a detailed station icon based on type."""
        from ..entities.stations import StationType

        size = int(10 * zoom)
        ix, iy = int(x), int(y)

        if station_type == StationType.OUTPOST:
            # Small triangle
            points = [
                (ix, iy - size),
                (ix - size, iy + size // 2),
                (ix + size, iy + size // 2),
            ]
            pygame.draw.polygon(screen, color, points)

        elif station_type == StationType.MINING_STATION:
            # Pickaxe shape - two angled lines
            pygame.draw.line(screen, color, (ix - size, iy - size),
                           (ix + size // 2, iy + size // 2), 2)
            pygame.draw.line(screen, color, (ix + size, iy - size),
                           (ix - size // 2, iy + size // 2), 2)
            pygame.draw.circle(screen, color, (ix, iy), size // 3)

        elif station_type == StationType.REFINERY:
            # Factory with chimney
            pygame.draw.rect(screen, color,
                           (ix - size, iy - size // 2, size * 2, size))
            pygame.draw.rect(screen, color,
                           (ix + size // 2, iy - size, size // 2, size // 2))

        elif station_type == StationType.FACTORY:
            # Gear shape - octagon
            points = []
            for i in range(8):
                angle = math.pi / 4 * i
                r = size if i % 2 == 0 else size * 0.7
                points.append((ix + r * math.cos(angle), iy + r * math.sin(angle)))
            pygame.draw.polygon(screen, color, points)

        elif station_type == StationType.COLONY:
            # Dome shape
            pygame.draw.arc(screen, color,
                          (ix - size, iy - size, size * 2, size * 2),
                          math.pi, 2 * math.pi, 2)
            pygame.draw.line(screen, color, (ix - size, iy), (ix + size, iy), 2)

        elif station_type == StationType.SHIPYARD:
            # Ship cradle - brackets
            pygame.draw.line(screen, color, (ix - size, iy - size),
                           (ix - size, iy + size), 2)
            pygame.draw.line(screen, color, (ix + size, iy - size),
                           (ix + size, iy + size), 2)
            pygame.draw.line(screen, color, (ix - size, iy),
                           (ix + size, iy), 2)

        elif station_type == StationType.TRADE_HUB:
            # Star shape
            points = []
            for i in range(10):
                angle = math.pi / 5 * i - math.pi / 2
                r = size if i % 2 == 0 else size * 0.5
                points.append((ix + r * math.cos(angle), iy + r * math.sin(angle)))
            pygame.draw.polygon(screen, color, points)

        else:
            # Default square
            pygame.draw.rect(screen, color,
                           (ix - size // 2, iy - size // 2, size, size))

    def _render_ships(
        self,
        screen: pygame.Surface,
        world: "World",
        player_faction_id: UUID | None
    ) -> None:
        """Render ships with detailed icons in the sector.

        Shows ships that either:
        1. Have ParentBody matching a body in this sector
        2. Have Position near any body in this sector (for ships in transit)
        """
        if not self.current_sector:
            return

        from ..entities.ships import Ship, ShipType
        from ..entities.factions import Faction
        from ..solar_system.orbits import ParentBody, Velocity, Position

        em = world.entity_manager

        # Build faction color lookup
        faction_colors: dict[UUID, tuple[int, int, int]] = {}
        for f_entity, faction in em.get_all_components(Faction):
            faction_colors[f_entity.id] = faction.color

        # Get primary body world position for distance calculations
        primary_body_name = self.current_sector.primary_body
        primary_world_pos = None

        # Find the primary body entity and get its position
        for entity in em.get_entities_with(Position):
            if entity.name == primary_body_name:
                pos = em.get_component(entity, Position)
                if pos:
                    primary_world_pos = (pos.x, pos.y)
                break

        # Also build a lookup of body positions for this sector
        body_positions: dict[str, tuple[float, float]] = {}
        for body in self.current_sector.bodies:
            for entity in em.get_entities_with(Position):
                if entity.name == body.name:
                    pos = em.get_component(entity, Position)
                    if pos:
                        body_positions[body.name] = (pos.x, pos.y)
                    break

        # Track which ships we've rendered (to avoid duplicates)
        rendered_ships: set[UUID] = set()

        for entity, ship in em.get_all_components(Ship):
            parent = em.get_component(entity, ParentBody)
            pos = em.get_component(entity, Position)

            sx, sy = None, None  # Screen position
            angle = 0

            # Method 1: Ship has ParentBody matching a sector body
            if parent:
                body = self.current_sector.get_body(parent.parent_name)
                if body:
                    bx, by = self.grid_to_screen(body.grid_x, body.grid_y)
                    body_radius = GRID_SIZE * body.radius * 0.4 * self.zoom

                    # Position ship outside the planet based on its offset angle
                    offset_dist = math.sqrt(parent.offset_x**2 + parent.offset_y**2)
                    if offset_dist > 0.001:
                        offset_angle = math.atan2(parent.offset_y, parent.offset_x)
                    else:
                        offset_angle = 0
                    ship_orbit = body_radius + 15 * self.zoom
                    sx = bx + ship_orbit * math.cos(offset_angle)
                    sy = by - ship_orbit * math.sin(offset_angle)
                    rendered_ships.add(entity.id)

            # Method 2: Ship has Position near sector (for ships in transit)
            if sx is None and pos and primary_world_pos:
                # Check if ship is within sector range (0.5 AU for inner system, larger for outer)
                sector_range = 0.5 if self.current_sector.id in ("earth", "venus", "mercury") else 2.0
                dx = pos.x - primary_world_pos[0]
                dy = pos.y - primary_world_pos[1]
                dist = math.sqrt(dx * dx + dy * dy)

                if dist < sector_range:
                    # Ship is in range - convert world position to screen
                    # Find the nearest body to position the ship near
                    nearest_body = None
                    nearest_dist = float('inf')

                    for body in self.current_sector.bodies:
                        if body.name in body_positions:
                            body_pos = body_positions[body.name]
                            bdx = pos.x - body_pos[0]
                            bdy = pos.y - body_pos[1]
                            bdist = math.sqrt(bdx * bdx + bdy * bdy)
                            if bdist < nearest_dist:
                                nearest_dist = bdist
                                nearest_body = body

                    if nearest_body and nearest_body.name in body_positions:
                        bx, by = self.grid_to_screen(nearest_body.grid_x, nearest_body.grid_y)
                        body_radius = GRID_SIZE * nearest_body.radius * 0.4 * self.zoom

                        # Position based on actual offset from body
                        body_pos = body_positions[nearest_body.name]
                        offset_x = pos.x - body_pos[0]
                        offset_y = pos.y - body_pos[1]
                        offset_dist = math.sqrt(offset_x**2 + offset_y**2)

                        if offset_dist > 0.001:
                            offset_angle = math.atan2(offset_y, offset_x)
                            # Scale offset to screen space (map AU to pixels)
                            screen_offset = min(100 * self.zoom, offset_dist * 500 * self.zoom)
                            sx = bx + screen_offset * math.cos(offset_angle)
                            sy = by - screen_offset * math.sin(offset_angle)
                        else:
                            ship_orbit = body_radius + 15 * self.zoom
                            sx = bx + ship_orbit
                            sy = by

                        rendered_ships.add(entity.id)

            if sx is None or sy is None:
                continue

            # Ship color
            ship_color = faction_colors.get(ship.owner_faction_id, COLORS['ship'])

            # Get velocity for rotation
            vel = em.get_component(entity, Velocity)
            if vel and (vel.vx != 0 or vel.vy != 0):
                angle = math.atan2(-vel.vy, vel.vx)

            # Draw detailed ship icon
            self._draw_ship_icon(screen, sx, sy, ship.ship_type, ship_color, angle, self.zoom)

            # Selection highlight
            if self.selected_ship_id == entity.id:
                pygame.draw.circle(screen, COLORS['ui_highlight'],
                                 (int(sx), int(sy)), int(12 * self.zoom), 2)

    def _draw_ship_icon(
        self,
        screen: pygame.Surface,
        x: float,
        y: float,
        ship_type: "ShipType",
        color: tuple[int, int, int],
        angle: float,
        zoom: float
    ) -> None:
        """Draw a detailed ship icon based on type."""
        from ..entities.ships import ShipType

        size = int(8 * zoom)
        ix, iy = int(x), int(y)

        def rotate_point(px, py, a):
            """Rotate point around origin by angle."""
            cos_a, sin_a = math.cos(a), math.sin(a)
            return (px * cos_a - py * sin_a, px * sin_a + py * cos_a)

        if ship_type == ShipType.DRONE:
            # Small dot
            pygame.draw.circle(screen, color, (ix, iy), max(2, int(3 * zoom)))

        elif ship_type == ShipType.SHUTTLE:
            # Small arrow
            points = [
                rotate_point(size, 0, angle),
                rotate_point(-size * 0.6, -size * 0.5, angle),
                rotate_point(-size * 0.6, size * 0.5, angle),
            ]
            points = [(ix + p[0], iy + p[1]) for p in points]
            pygame.draw.polygon(screen, color, points)

        elif ship_type == ShipType.FREIGHTER:
            # Boxy ship
            points = [
                rotate_point(size, 0, angle),
                rotate_point(size * 0.3, -size * 0.6, angle),
                rotate_point(-size, -size * 0.6, angle),
                rotate_point(-size, size * 0.6, angle),
                rotate_point(size * 0.3, size * 0.6, angle),
            ]
            points = [(ix + p[0], iy + p[1]) for p in points]
            pygame.draw.polygon(screen, color, points)

        elif ship_type == ShipType.BULK_HAULER:
            # Large boxy ship
            size = int(10 * zoom)
            points = [
                rotate_point(size, 0, angle),
                rotate_point(size * 0.2, -size * 0.8, angle),
                rotate_point(-size, -size * 0.8, angle),
                rotate_point(-size, size * 0.8, angle),
                rotate_point(size * 0.2, size * 0.8, angle),
            ]
            points = [(ix + p[0], iy + p[1]) for p in points]
            pygame.draw.polygon(screen, color, points)

        elif ship_type == ShipType.TANKER:
            # Elongated ship
            points = [
                rotate_point(size * 1.2, 0, angle),
                rotate_point(-size, -size * 0.4, angle),
                rotate_point(-size, size * 0.4, angle),
            ]
            points = [(ix + p[0], iy + p[1]) for p in points]
            pygame.draw.polygon(screen, color, points)
            # Cargo section
            pygame.draw.circle(screen, color, (ix, iy), max(2, int(4 * zoom)))

        else:
            # Default triangle
            points = [
                rotate_point(size, 0, angle),
                rotate_point(-size, -size * 0.6, angle),
                rotate_point(-size, size * 0.6, angle),
            ]
            points = [(ix + p[0], iy + p[1]) for p in points]
            pygame.draw.polygon(screen, color, points)

    def _render_title(self, screen: pygame.Surface) -> None:
        """Render sector title."""
        if not self.current_sector:
            return

        title = self.font_title.render(self.current_sector.name, True, COLORS['ui_text'])
        screen.blit(title, (20, 60))

        desc = self.font.render(self.current_sector.description, True, (150, 150, 170))
        screen.blit(desc, (20, 95))

    def _render_nav_hint(self, screen: pygame.Surface) -> None:
        """Render navigation hint."""
        hint = self.font.render("Press M to view solar system map", True, (100, 100, 120))
        screen.blit(hint, (20, self.screen_height - 30))

    def _count_stations_at_body(self, world: "World", body_name: str) -> int:
        """Count stations at a body."""
        from ..entities.stations import Station

        count = 0
        for entity, station in world.entity_manager.get_all_components(Station):
            if station.parent_body == body_name:
                count += 1
        return count

    def _render_build_preview(
        self,
        screen: pygame.Surface,
        world: "World",
        mouse_x: int,
        mouse_y: int
    ) -> None:
        """Render build preview showing which bodies can be built on."""
        if not self.current_sector or not self.build_mode_active:
            return

        from ..entities.stations import StationType

        # Draw build indicator on each body
        for body in self.current_sector.bodies:
            px, py = self.grid_to_screen(body.grid_x, body.grid_y)
            radius = int(GRID_SIZE * body.radius * 0.4 * self.zoom)

            # Check if body has capacity
            station_count = self._count_stations_at_body(world, body.name)
            has_capacity = station_count < body.max_stations

            # Determine if this body is hovered
            is_hovered = body.name == self.hovered_body

            # Choose indicator color based on capacity and hover
            if has_capacity:
                if is_hovered:
                    indicator_color = (100, 255, 100)  # Bright green when hovered
                    ring_width = 3
                else:
                    indicator_color = (50, 150, 50)  # Dim green otherwise
                    ring_width = 2
            else:
                if is_hovered:
                    indicator_color = (255, 100, 100)  # Bright red when hovered
                    ring_width = 3
                else:
                    indicator_color = (150, 50, 50)  # Dim red otherwise
                    ring_width = 2

            # Draw build indicator ring
            build_ring_radius = radius + 15 * self.zoom
            pygame.draw.circle(
                screen, indicator_color,
                (int(px), int(py)), int(build_ring_radius), ring_width
            )

            # Draw "+" or "X" indicator
            if has_capacity:
                # Draw + sign
                plus_size = int(8 * self.zoom)
                pygame.draw.line(
                    screen, indicator_color,
                    (int(px) - plus_size, int(py + build_ring_radius + 10)),
                    (int(px) + plus_size, int(py + build_ring_radius + 10)), 2
                )
                pygame.draw.line(
                    screen, indicator_color,
                    (int(px), int(py + build_ring_radius + 10 - plus_size)),
                    (int(px), int(py + build_ring_radius + 10 + plus_size)), 2
                )
            else:
                # Draw X for full
                x_size = int(6 * self.zoom)
                cx, cy = int(px), int(py + build_ring_radius + 10)
                pygame.draw.line(
                    screen, indicator_color,
                    (cx - x_size, cy - x_size), (cx + x_size, cy + x_size), 2
                )
                pygame.draw.line(
                    screen, indicator_color,
                    (cx + x_size, cy - x_size), (cx - x_size, cy + x_size), 2
                )

            # Show capacity info when hovered
            if is_hovered:
                status_text = f"Slots: {station_count}/{body.max_stations}"
                if has_capacity:
                    status_text += " - Click to build"
                else:
                    status_text += " - FULL"
                status_surf = self.font.render(status_text, True, indicator_color)
                screen.blit(status_surf, (int(px) - status_surf.get_width() // 2,
                                         int(py + build_ring_radius + 25)))

        # Show build mode hint
        type_names = {
            StationType.OUTPOST: "Outpost",
            StationType.MINING_STATION: "Mining Station",
            StationType.REFINERY: "Refinery",
            StationType.FACTORY: "Factory",
            StationType.COLONY: "Colony",
            StationType.SHIPYARD: "Shipyard",
            StationType.TRADE_HUB: "Trade Hub",
        }
        station_name = type_names.get(self.selected_station_type, "Station")
        build_hint = f"BUILD MODE: {station_name} - Click on a body to place"
        hint_surf = self.font_medium.render(build_hint, True, (100, 255, 100))
        screen.blit(hint_surf, (self.screen_width // 2 - hint_surf.get_width() // 2, 130))
