"""UI panels and menus."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID
import pygame

from ..config import COLORS
from ..simulation.resources import ResourceType, BASE_PRICES
from ..entities.stations import StationType

if TYPE_CHECKING:
    from ..core.world import World
    from ..core.ecs import Entity
    from ..systems.building import BuildingSystem
    from ..entities.factions import Faction


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


# Station build options for menu - now imported from building system
from ..systems.building import STATION_COSTS, STATION_MATERIAL_COSTS

# Build options list (station_type, display_name)
BUILD_OPTIONS = [
    (StationType.OUTPOST, "Outpost"),
    (StationType.MINING_STATION, "Mining Station"),
    (StationType.REFINERY, "Refinery"),
    (StationType.FACTORY, "Factory"),
    (StationType.SHIPYARD, "Shipyard"),
    (StationType.COLONY, "Colony"),
    (StationType.TRADE_HUB, "Trade Hub"),
]


@dataclass
class BuildMenuPanel(Panel):
    """Panel for building stations."""
    selected_index: int = -1
    player_credits: float = 0.0
    player_materials: dict = field(default_factory=dict)

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x, y=y, width=280, height=320, title="Build Station [B]"
        )
        self.selected_index = -1
        self.player_credits = 0.0
        self.player_materials = {}

    def update_player_resources(self, credits: float, materials: dict) -> None:
        """Update the player's available credits and materials."""
        self.player_credits = credits
        self.player_materials = materials

    def can_afford_station(self, station_type: StationType) -> bool:
        """Check if player can afford a station (credits + materials)."""
        # Check credits
        cost = STATION_COSTS.get(station_type, float('inf'))
        if self.player_credits < cost:
            return False

        # Check materials
        material_reqs = STATION_MATERIAL_COSTS.get(station_type, {})
        for resource, needed in material_reqs.items():
            if self.player_materials.get(resource, 0) < needed:
                return False

        return True

    def select_option(self, index: int) -> StationType | None:
        """Select a build option by index.

        Returns:
            Selected station type if valid and affordable, None otherwise
        """
        if 0 <= index < len(BUILD_OPTIONS):
            station_type, name = BUILD_OPTIONS[index]
            if self.can_afford_station(station_type):
                self.selected_index = index
                return station_type
        return None

    def get_selected_type(self) -> StationType | None:
        """Get the currently selected station type."""
        if 0 <= self.selected_index < len(BUILD_OPTIONS):
            return BUILD_OPTIONS[self.selected_index][0]
        return None

    def get_selected_cost(self) -> float:
        """Get credit cost of currently selected station type."""
        if 0 <= self.selected_index < len(BUILD_OPTIONS):
            station_type = BUILD_OPTIONS[self.selected_index][0]
            return STATION_COSTS.get(station_type, 0)
        return 0.0

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the build menu."""
        if not self.visible:
            return

        # Draw background and border
        super().draw(surface, font)

        line_height = font.get_linesize()
        y = self.y + 25

        # Show credits
        credits_text = f"Credits: {self.player_credits:,.0f}"
        credits_surf = font.render(credits_text, True, COLORS['ui_highlight'])
        surface.blit(credits_surf, (self.x + 10, y))
        y += line_height + 5

        # Draw separator
        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        # Draw build options
        for i, (station_type, name) in enumerate(BUILD_OPTIONS):
            cost = STATION_COSTS.get(station_type, 0)
            material_reqs = STATION_MATERIAL_COSTS.get(station_type, {})
            can_afford = self.can_afford_station(station_type)
            is_selected = i == self.selected_index

            # Choose color based on state
            if is_selected:
                color = COLORS['ui_highlight']
                # Draw selection background
                pygame.draw.rect(
                    surface, (50, 50, 80),
                    (self.x + 5, y - 2, self.width - 10, line_height + 2)
                )
            elif can_afford:
                color = COLORS['ui_text']
            else:
                color = (100, 100, 100)  # Grayed out

            # Draw option text
            option_text = f"{i + 1}. {name}"
            option_surf = font.render(option_text, True, color)
            surface.blit(option_surf, (self.x + 10, y))

            # Draw credit cost on right side
            cost_text = f"{cost:,}c"
            cost_surf = font.render(cost_text, True, color)
            surface.blit(cost_surf, (self.x + self.width - cost_surf.get_width() - 10, y))

            y += line_height

            # Draw material requirements if any (smaller text)
            if material_reqs:
                mat_parts = []
                for resource, amount in material_reqs.items():
                    # Abbreviate resource names
                    abbrev = resource.value[:3].upper()
                    have = self.player_materials.get(resource, 0)
                    mat_color = color if have >= amount else (255, 100, 100)
                    mat_parts.append((f"{abbrev}:{amount:.0f}", mat_color))

                x_offset = self.x + 25
                for mat_text, mat_color in mat_parts:
                    mat_surf = font.render(mat_text, True, mat_color)
                    surface.blit(mat_surf, (x_offset, y))
                    x_offset += mat_surf.get_width() + 8

                y += line_height

            y += 2

        # Instructions at bottom
        y += 5
        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        hint_text = "Click to place | ESC to cancel"
        hint_surf = font.render(hint_text, True, (150, 150, 150))
        surface.blit(hint_surf, (self.x + 10, y))


@dataclass
class PlayerHUD(Panel):
    """HUD showing player corporation status."""
    faction_name: str = ""
    faction_color: tuple[int, int, int] = (255, 255, 255)
    credits: float = 0.0
    station_count: int = 0
    ship_count: int = 0

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x, y=y, width=200, height=100, title=""
        )

    def update(
        self,
        world: "World",
        player_faction_id: UUID | None
    ) -> None:
        """Update HUD with current player stats."""
        if not player_faction_id:
            return

        em = world.entity_manager

        # Find player faction
        from ..entities.factions import Faction
        for entity, faction in em.get_all_components(Faction):
            if entity.id == player_faction_id:
                self.faction_name = entity.name
                self.faction_color = faction.color
                self.credits = faction.credits
                break

        # Count owned stations
        from ..entities.stations import Station
        self.station_count = 0
        for entity, station in em.get_all_components(Station):
            if station.owner_faction_id == player_faction_id:
                self.station_count += 1

        # Count owned ships
        from ..entities.ships import Ship
        self.ship_count = 0
        for entity, ship in em.get_all_components(Ship):
            if ship.owner_faction_id == player_faction_id:
                self.ship_count += 1

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the player HUD."""
        if not self.visible:
            return

        # Draw background
        pygame.draw.rect(surface, self.bg_color, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(surface, self.border_color, (self.x, self.y, self.width, self.height), 2)

        # Draw faction color bar at top
        pygame.draw.rect(
            surface, self.faction_color,
            (self.x + 2, self.y + 2, self.width - 4, 4)
        )

        line_height = font.get_linesize()
        y = self.y + 10

        # Faction name
        name_surf = font.render(self.faction_name, True, self.faction_color)
        surface.blit(name_surf, (self.x + 10, y))
        y += line_height + 5

        # Credits
        credits_text = f"Credits: {self.credits:,.0f}"
        credits_surf = font.render(credits_text, True, COLORS['ui_text'])
        surface.blit(credits_surf, (self.x + 10, y))
        y += line_height

        # Station count
        station_text = f"Stations: {self.station_count}"
        station_surf = font.render(station_text, True, COLORS['ui_text'])
        surface.blit(station_surf, (self.x + 10, y))
        y += line_height

        # Ship count
        ship_text = f"Ships: {self.ship_count}"
        ship_surf = font.render(ship_text, True, COLORS['ui_text'])
        surface.blit(ship_surf, (self.x + 10, y))
