"""UI panels and menus."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import pygame

from ..config import COLORS
from ..simulation.resources import ResourceType, BASE_PRICES

if TYPE_CHECKING:
    from ..core.world import World
    from ..core.ecs import Entity


@dataclass
class Panel:
    """Base class for UI panels."""
    x: int
    y: int
    width: int
    height: int
    visible: bool = True
    title: str = ""
    bg_color: tuple[int, int, int] = COLORS['ui_bg']
    border_color: tuple[int, int, int] = COLORS['ui_border']

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the panel."""
        if not self.visible:
            return

        # Draw background
        pygame.draw.rect(surface, self.bg_color, (self.x, self.y, self.width, self.height))

        # Draw border
        pygame.draw.rect(surface, self.border_color, (self.x, self.y, self.width, self.height), 2)

        # Draw title
        if self.title:
            title_surf = font.render(self.title, True, COLORS['ui_text'])
            surface.blit(title_surf, (self.x + 10, self.y + 5))

    def contains_point(self, x: int, y: int) -> bool:
        """Check if a point is inside the panel."""
        return (
            self.x <= x <= self.x + self.width and
            self.y <= y <= self.y + self.height
        )


@dataclass
class InfoPanel(Panel):
    """Panel showing information about selected entity."""
    entity_id: object = None
    lines: list[str] = field(default_factory=list)

    def update(self, world: World, entity: Entity | None) -> None:
        """Update panel content based on selected entity."""
        self.lines.clear()

        if not entity:
            self.title = "Nothing Selected"
            self.lines.append("Click on an object to select it")
            return

        self.title = entity.name or "Unknown"
        self.lines.append(f"ID: {str(entity.id)[:8]}...")

        em = world.entity_manager

        # Show position
        from ..solar_system.orbits import Position
        pos = em.get_component(entity, Position)
        if pos:
            self.lines.append(f"Position: ({pos.x:.3f}, {pos.y:.3f}) AU")

        # Show inventory if present
        from ..simulation.resources import Inventory
        inv = em.get_component(entity, Inventory)
        if inv:
            self.lines.append("")
            self.lines.append("Inventory:")
            for resource, amount in inv.resources.items():
                if amount > 0:
                    self.lines.append(f"  {resource.value}: {amount:.1f}")
            self.lines.append(f"  Capacity: {inv.total_amount:.0f}/{inv.capacity:.0f}")

        # Show market if present
        from ..simulation.economy import Market
        market = em.get_component(entity, Market)
        if market:
            self.lines.append("")
            self.lines.append(f"Credits: {market.credits:.0f}")

        # Show station type
        from ..entities.stations import Station
        station = em.get_component(entity, Station)
        if station:
            self.lines.append("")
            self.lines.append(f"Type: {station.station_type.value}")
            if station.population > 0:
                self.lines.append(f"Population: {station.population}")

        # Show ship info
        from ..entities.ships import Ship
        ship = em.get_component(entity, Ship)
        if ship:
            self.lines.append("")
            self.lines.append(f"Ship Type: {ship.ship_type.value}")
            self.lines.append(f"Fuel: {ship.fuel:.0f}/{ship.fuel_capacity:.0f}")
            self.lines.append(f"Crew: {ship.crew}/{ship.max_crew}")

        # Show celestial body info
        from ..entities.celestial import CelestialBody
        body = em.get_component(entity, CelestialBody)
        if body:
            self.lines.append("")
            self.lines.append(f"Body Type: {body.body_type.value}")
            self.lines.append(f"Radius: {body.radius:.0f} km")

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the info panel."""
        if not self.visible:
            return

        # Calculate required height
        line_height = font.get_linesize()
        required_height = 30 + len(self.lines) * line_height + 10
        self.height = max(100, required_height)

        # Draw background and border
        super().draw(surface, font)

        # Draw content lines
        y = self.y + 25
        for line in self.lines:
            text_surf = font.render(line, True, COLORS['ui_text'])
            surface.blit(text_surf, (self.x + 10, y))
            y += line_height


@dataclass
class StatusBar(Panel):
    """Status bar showing game state."""

    def __init__(self, screen_width: int, screen_height: int) -> None:
        super().__init__(
            x=0,
            y=screen_height - 30,
            width=screen_width,
            height=30,
            title=""
        )

    def draw_status(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        world: World,
        fps: float
    ) -> None:
        """Draw status bar with game info."""
        if not self.visible:
            return

        # Draw background
        pygame.draw.rect(surface, self.bg_color, (self.x, self.y, self.width, self.height))
        pygame.draw.line(surface, self.border_color, (0, self.y), (self.width, self.y), 2)

        # Build status text
        time_str = str(world.game_time)
        speed_str = f"Speed: {world.speed:.1f}x"
        pause_str = " [PAUSED]" if world.paused else ""
        fps_str = f"FPS: {fps:.0f}"

        status = f"{time_str}  |  {speed_str}{pause_str}  |  {fps_str}"

        text_surf = font.render(status, True, COLORS['ui_text'])
        surface.blit(text_surf, (10, self.y + 7))

        # Draw entity count on right side
        entity_count = world.entity_manager.entity_count
        count_text = f"Entities: {entity_count}"
        count_surf = font.render(count_text, True, COLORS['ui_text'])
        surface.blit(count_surf, (self.width - count_surf.get_width() - 10, self.y + 7))


@dataclass
class MiniMap(Panel):
    """Minimap showing solar system overview."""

    def __init__(self, x: int, y: int, size: int = 150) -> None:
        super().__init__(x=x, y=y, width=size, height=size, title="")

    def draw_minimap(
        self,
        surface: pygame.Surface,
        world: World,
        camera_bounds: tuple[float, float, float, float]
    ) -> None:
        """Draw the minimap."""
        if not self.visible:
            return

        # Draw background
        pygame.draw.rect(surface, self.bg_color, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(surface, self.border_color, (self.x, self.y, self.width, self.height), 1)

        # Scale: show inner solar system (0-5 AU)
        scale = self.width / 10.0  # 10 AU total width
        center_x = self.x + self.width // 2
        center_y = self.y + self.height // 2

        em = world.entity_manager

        # Draw celestial bodies
        from ..solar_system.orbits import Position
        from ..entities.celestial import CelestialBody

        for entity, body in em.get_all_components(CelestialBody):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            # Convert to minimap coordinates
            mx = int(center_x + pos.x * scale)
            my = int(center_y - pos.y * scale)

            # Skip if outside minimap
            if not (self.x < mx < self.x + self.width and self.y < my < self.y + self.height):
                continue

            # Draw as small dot
            size = 2 if body.body_type.value in ('star', 'planet') else 1
            pygame.draw.circle(surface, body.color, (mx, my), size)

        # Draw camera viewport rectangle
        min_x, min_y, max_x, max_y = camera_bounds
        rect_x = int(center_x + min_x * scale)
        rect_y = int(center_y - max_y * scale)
        rect_w = int((max_x - min_x) * scale)
        rect_h = int((max_y - min_y) * scale)

        # Clamp to minimap bounds
        rect_x = max(self.x, min(self.x + self.width - 1, rect_x))
        rect_y = max(self.y, min(self.y + self.height - 1, rect_y))
        rect_w = min(rect_w, self.width)
        rect_h = min(rect_h, self.height)

        if rect_w > 0 and rect_h > 0:
            pygame.draw.rect(surface, COLORS['ui_highlight'], (rect_x, rect_y, rect_w, rect_h), 1)
