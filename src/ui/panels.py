"""UI panels and menus."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Callable
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


class MenuId(Enum):
    """Identifiers for all menus in the game."""
    NONE = auto()
    BUILD_MENU = auto()
    RESOURCE_SELECTION = auto()
    SHIP_MENU = auto()
    UPGRADE_MENU = auto()
    TRADE_ROUTE = auto()
    TRADE_MANAGER = auto()
    HELP = auto()
    WAYPOINT_MODE = auto()  # Not a menu but a modal mode
    NEWS_FEED = auto()  # News, events, and contracts panel


class MenuManager:
    """Manages menu focus stack - only the topmost menu receives input.

    This provides a robust system for handling nested menus and modal dialogs.
    When a menu is opened, it's pushed onto the stack. When closed, it's popped.
    Only the top menu receives keyboard input.
    """

    def __init__(self) -> None:
        self._stack: list[MenuId] = []
        self._close_callbacks: dict[MenuId, Callable[[], None]] = {}

    def push(self, menu_id: MenuId) -> None:
        """Push a menu onto the focus stack."""
        if menu_id not in self._stack:
            self._stack.append(menu_id)

    def pop(self, menu_id: MenuId | None = None) -> MenuId | None:
        """Pop a menu from the stack.

        Args:
            menu_id: If provided, only pop if this is the top menu.
                    If None, pop whatever is on top.

        Returns:
            The popped menu ID, or None if nothing was popped.
        """
        if not self._stack:
            return None

        if menu_id is None:
            return self._stack.pop()

        if self._stack[-1] == menu_id:
            return self._stack.pop()

        # Menu is in stack but not on top - remove it anyway
        if menu_id in self._stack:
            self._stack.remove(menu_id)
            return menu_id

        return None

    def close_top(self) -> MenuId | None:
        """Close the topmost menu and call its close callback.

        Returns:
            The closed menu ID, or None if stack was empty.
        """
        if not self._stack:
            return None

        menu_id = self._stack.pop()
        if menu_id in self._close_callbacks:
            self._close_callbacks[menu_id]()
        return menu_id

    def close_all(self) -> None:
        """Close all menus, calling callbacks in reverse order."""
        while self._stack:
            self.close_top()

    def register_close_callback(self, menu_id: MenuId, callback: Callable[[], None]) -> None:
        """Register a callback to be called when a menu is closed."""
        self._close_callbacks[menu_id] = callback

    @property
    def active_menu(self) -> MenuId:
        """Get the currently active (topmost) menu."""
        return self._stack[-1] if self._stack else MenuId.NONE

    def is_active(self, menu_id: MenuId) -> bool:
        """Check if a specific menu is the active (topmost) one."""
        return self.active_menu == menu_id

    def is_open(self, menu_id: MenuId) -> bool:
        """Check if a menu is open (anywhere in the stack)."""
        return menu_id in self._stack

    def has_open_menu(self) -> bool:
        """Check if any menu is open."""
        return len(self._stack) > 0

    @property
    def stack_depth(self) -> int:
        """Get the number of open menus."""
        return len(self._stack)


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
        from ..solar_system.orbits import NavigationTarget
        from ..simulation.trade import Trader, ManualRoute, TradeState
        ship = em.get_component(entity, Ship)
        if ship:
            self.lines.append("")
            self.lines.append(f"Ship Type: {ship.ship_type.value}")
            self.lines.append(f"Fuel: {ship.fuel:.0f}/{ship.fuel_capacity:.0f}")
            self.lines.append(f"Crew: {ship.crew}/{ship.max_crew}")

            # Gather ship state info
            nav = em.get_component(entity, NavigationTarget)
            trader = em.get_component(entity, Trader)
            manual_route = em.get_component(entity, ManualRoute)

            # Find destination name if navigating
            dest_name = None
            if nav:
                # Check stations
                for station_entity, _ in em.get_all_components(Station):
                    station_pos = em.get_component(station_entity, Position)
                    if station_pos:
                        dist = ((station_pos.x - nav.target_x)**2 + (station_pos.y - nav.target_y)**2)**0.5
                        if dist < 0.05:
                            dest_name = station_entity.name
                            break
                # Check celestial bodies if no station found
                if not dest_name:
                    from ..entities.celestial import CelestialBody
                    for body_entity, _ in em.get_all_components(CelestialBody):
                        body_pos = em.get_component(body_entity, Position)
                        if body_pos:
                            dist = ((body_pos.x - nav.target_x)**2 + (body_pos.y - nav.target_y)**2)**0.5
                            if dist < 0.1:
                                dest_name = body_entity.name
                                break

            # Determine status based on what the ship is doing
            is_moving = nav and nav.current_speed > 0.01

            if manual_route and manual_route.waypoints:
                # Ship has a player-assigned trade route
                route_desc = " >> ".join(w.station_name or "?" for w in manual_route.waypoints)
                self.lines.append(f"Route: {route_desc}")
                if is_moving and dest_name:
                    self.lines.append(f"Status: Trading > {dest_name}")
                elif is_moving:
                    self.lines.append(f"Status: Moving > ({nav.target_x:.2f}, {nav.target_y:.2f})")
                else:
                    waypoint = manual_route.get_current_waypoint()
                    if waypoint:
                        self.lines.append(f"Status: At {waypoint.station_name or 'waypoint'}")
                    else:
                        self.lines.append("Status: Route complete")
            elif is_moving:
                # Ship is moving but not on a manual route
                if trader and trader.state in (TradeState.TRAVELING_TO_BUY, TradeState.TRAVELING_TO_SELL):
                    action = "buying" if trader.state == TradeState.TRAVELING_TO_BUY else "selling"
                    if dest_name:
                        self.lines.append(f"Status: Trading ({action}) > {dest_name}")
                    else:
                        self.lines.append(f"Status: Trading ({action})")
                else:
                    if dest_name:
                        self.lines.append(f"Status: Moving > {dest_name}")
                    else:
                        self.lines.append(f"Status: Moving > ({nav.target_x:.2f}, {nav.target_y:.2f})")
            elif trader:
                # Ship is stationary with trader component
                if trader.state == TradeState.BUYING:
                    self.lines.append("Status: Buying cargo")
                elif trader.state == TradeState.SELLING:
                    self.lines.append("Status: Selling cargo")
                else:
                    self.lines.append("Status: Idle")
            else:
                self.lines.append("Status: Idle")

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
class ResourceSelectionPanel(Panel):
    """Panel for selecting which resource to mine when building mining station."""
    options: list[tuple[str, ResourceType, float]] = field(default_factory=list)  # (body_name, resource, richness)
    selected_index: int = -1
    build_position: tuple[float, float] = (0.0, 0.0)
    parent_body: str = ""

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x, y=y, width=280, height=200, title="Select Resource to Mine"
        )
        self.visible = False
        self.options = []
        self.selected_index = -1
        self.build_position = (0.0, 0.0)
        self.parent_body = ""

    def show_options(
        self,
        planet_name: str,
        position: tuple[float, float]
    ) -> None:
        """Show resource options for a planetary system.

        Args:
            planet_name: Name of the nearest planet
            position: Build position
        """
        from ..solar_system.bodies import SolarSystemData

        self.parent_body = planet_name
        self.build_position = position
        self.selected_index = -1

        # Get all resources from planet and its moons
        self.options = SolarSystemData.get_planetary_system_resources(planet_name)

        # Calculate panel height based on options
        self.height = max(120, 60 + len(self.options) * 25 + 30)
        self.visible = True

    def select_option(self, index: int) -> tuple[str, ResourceType] | None:
        """Select a resource option by index.

        Returns:
            (body_name, resource_type) tuple if valid, None otherwise
        """
        if 0 <= index < len(self.options):
            self.selected_index = index
            body_name, resource, _ = self.options[index]
            return (body_name, resource)
        return None

    def get_selection(self) -> tuple[str, ResourceType, tuple[float, float]] | None:
        """Get the current selection.

        Returns:
            (body_name, resource_type, position) tuple if selected, None otherwise
        """
        if 0 <= self.selected_index < len(self.options):
            body_name, resource, _ = self.options[self.selected_index]
            return (body_name, resource, self.build_position)
        return None

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the resource selection menu."""
        if not self.visible:
            return

        super().draw(surface, font)

        line_height = font.get_linesize()
        y = self.y + 30

        if not self.options:
            no_res_text = "No resources available here"
            no_res_surf = font.render(no_res_text, True, (150, 150, 150))
            surface.blit(no_res_surf, (self.x + 10, y))
            return

        # Draw options
        for i, (body_name, resource, richness) in enumerate(self.options):
            is_selected = i == self.selected_index

            if is_selected:
                color = COLORS['ui_highlight']
                pygame.draw.rect(
                    surface, (50, 50, 80),
                    (self.x + 5, y - 2, self.width - 10, line_height + 2)
                )
            else:
                color = COLORS['ui_text']

            # Format: "1) Mars > Iron Ore (1.3x)"
            richness_str = f"({richness:.1f}x)" if richness != 1.0 else ""
            option_text = f"{i + 1}) {body_name} > {resource.value.replace('_', ' ').title()} {richness_str}"
            option_surf = font.render(option_text, True, color)
            surface.blit(option_surf, (self.x + 10, y))

            y += line_height + 3

        # Instructions
        y += 10
        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        hint_text = "Press number to select | ESC to cancel"
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


# Ship purchase options
from ..entities.ships import ShipType
from ..systems.building import SHIP_COSTS, SHIP_MATERIAL_COSTS

SHIP_OPTIONS = [
    (ShipType.SHUTTLE, "Shuttle"),
    (ShipType.FREIGHTER, "Freighter"),
    (ShipType.TANKER, "Tanker"),
    (ShipType.BULK_HAULER, "Bulk Hauler"),
    (ShipType.MINING_SHIP, "Mining Ship"),
]


@dataclass
class ShipPurchasePanel(Panel):
    """Panel for purchasing ships at shipyards."""
    selected_index: int = -1
    player_credits: float = 0.0
    player_materials: dict = field(default_factory=dict)
    shipyard_id: UUID | None = None
    shipyard_name: str = ""

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x, y=y, width=280, height=280, title="Purchase Ship [S]"
        )
        self.selected_index = -1
        self.player_credits = 0.0
        self.player_materials = {}
        self.shipyard_id = None

    def set_shipyard(self, shipyard_id: UUID | None, name: str = "") -> None:
        """Set the current shipyard."""
        self.shipyard_id = shipyard_id
        self.shipyard_name = name

    def update_player_resources(self, credits: float, materials: dict) -> None:
        """Update the player's available credits and materials."""
        self.player_credits = credits
        self.player_materials = materials

    def can_afford_ship(self, ship_type: ShipType) -> bool:
        """Check if player can afford a ship (credits + materials)."""
        cost = SHIP_COSTS.get(ship_type, float('inf'))
        if self.player_credits < cost:
            return False

        material_reqs = SHIP_MATERIAL_COSTS.get(ship_type, {})
        for resource, needed in material_reqs.items():
            if self.player_materials.get(resource, 0) < needed:
                return False

        return True

    def select_option(self, index: int) -> ShipType | None:
        """Select a ship option by index."""
        if 0 <= index < len(SHIP_OPTIONS):
            ship_type, name = SHIP_OPTIONS[index]
            if self.can_afford_ship(ship_type) and self.shipyard_id:
                self.selected_index = index
                return ship_type
        return None

    def get_selected_type(self) -> ShipType | None:
        """Get the currently selected ship type."""
        if 0 <= self.selected_index < len(SHIP_OPTIONS):
            return SHIP_OPTIONS[self.selected_index][0]
        return None

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the ship purchase menu."""
        if not self.visible:
            return

        super().draw(surface, font)

        line_height = font.get_linesize()
        y = self.y + 25

        # Show shipyard name
        if self.shipyard_name:
            yard_text = f"At: {self.shipyard_name}"
            yard_surf = font.render(yard_text, True, COLORS['ui_text'])
            surface.blit(yard_surf, (self.x + 10, y))
        else:
            no_yard = "No shipyard selected"
            no_yard_surf = font.render(no_yard, True, (255, 100, 100))
            surface.blit(no_yard_surf, (self.x + 10, y))
        y += line_height + 2

        # Show credits
        credits_text = f"Credits: {self.player_credits:,.0f}"
        credits_surf = font.render(credits_text, True, COLORS['ui_highlight'])
        surface.blit(credits_surf, (self.x + 10, y))
        y += line_height + 5

        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        # Draw ship options
        for i, (ship_type, name) in enumerate(SHIP_OPTIONS):
            cost = SHIP_COSTS.get(ship_type, 0)
            material_reqs = SHIP_MATERIAL_COSTS.get(ship_type, {})
            can_afford = self.can_afford_ship(ship_type) and self.shipyard_id is not None
            is_selected = i == self.selected_index

            if is_selected:
                color = COLORS['ui_highlight']
                pygame.draw.rect(
                    surface, (50, 50, 80),
                    (self.x + 5, y - 2, self.width - 10, line_height + 2)
                )
            elif can_afford:
                color = COLORS['ui_text']
            else:
                color = (100, 100, 100)

            option_text = f"{i + 1}. {name}"
            option_surf = font.render(option_text, True, color)
            surface.blit(option_surf, (self.x + 10, y))

            cost_text = f"{cost:,}c"
            cost_surf = font.render(cost_text, True, color)
            surface.blit(cost_surf, (self.x + self.width - cost_surf.get_width() - 10, y))

            y += line_height

            if material_reqs:
                mat_parts = []
                for resource, amount in material_reqs.items():
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

        y += 5
        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        hint_text = "Select station then press S"
        hint_surf = font.render(hint_text, True, (150, 150, 150))
        surface.blit(hint_surf, (self.x + 10, y))


@dataclass
class Notification:
    """A single notification message."""
    message: str
    notification_type: str
    remaining_time: float
    color: tuple[int, int, int] = (255, 255, 255)


class NotificationPanel:
    """Panel that displays notifications."""

    def __init__(self, x: int, y: int, width: int = 300) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.notifications: list[Notification] = []
        self.max_notifications = 5

        # Colors for notification types
        self.type_colors = {
            "info": (200, 200, 255),
            "success": (100, 255, 100),
            "warning": (255, 200, 100),
            "error": (255, 100, 100),
        }

    def add_notification(self, message: str, notification_type: str = "info", duration: float = 5.0) -> None:
        """Add a new notification."""
        color = self.type_colors.get(notification_type, (255, 255, 255))
        notification = Notification(
            message=message,
            notification_type=notification_type,
            remaining_time=duration,
            color=color
        )
        self.notifications.insert(0, notification)

        # Limit notifications
        if len(self.notifications) > self.max_notifications:
            self.notifications = self.notifications[:self.max_notifications]

    def update(self, dt: float) -> None:
        """Update notification timers."""
        for notif in self.notifications[:]:
            notif.remaining_time -= dt
            if notif.remaining_time <= 0:
                self.notifications.remove(notif)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw notifications."""
        if not self.notifications:
            return

        line_height = font.get_linesize() + 4
        y = self.y

        for notif in self.notifications:
            # Calculate alpha based on remaining time
            alpha = min(255, int(notif.remaining_time * 255 / 2))

            # Draw background
            bg_surface = pygame.Surface((self.width, line_height), pygame.SRCALPHA)
            bg_surface.fill((30, 30, 40, alpha))
            surface.blit(bg_surface, (self.x, y))

            # Draw text
            text_surf = font.render(notif.message, True, notif.color)
            text_surf.set_alpha(alpha)
            surface.blit(text_surf, (self.x + 5, y + 2))

            y += line_height + 2


from ..systems.building import STATION_UPGRADES, UPGRADE_COST_MULTIPLIER


@dataclass
class UpgradePanel(Panel):
    """Panel for upgrading stations."""
    station_id: UUID | None = None
    station_type: StationType | None = None
    available_upgrades: list = field(default_factory=list)
    selected_index: int = -1
    player_credits: float = 0.0
    player_materials: dict = field(default_factory=dict)

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x, y=y, width=280, height=220, title="Upgrade Station [U]"
        )
        self.station_id = None
        self.station_type = None
        self.available_upgrades = []
        self.selected_index = -1
        self.player_credits = 0.0
        self.player_materials = {}

    def set_station(self, station_id: UUID | None, station_type: StationType | None) -> None:
        """Set the station to show upgrades for."""
        self.station_id = station_id
        self.station_type = station_type
        self.selected_index = -1

        if station_type:
            self.available_upgrades = STATION_UPGRADES.get(station_type, [])
        else:
            self.available_upgrades = []

    def update_player_resources(self, credits: float, materials: dict) -> None:
        """Update the player's available credits and materials."""
        self.player_credits = credits
        self.player_materials = materials

    def can_afford_upgrade(self, target_type: StationType) -> bool:
        """Check if player can afford an upgrade."""
        # Check credits (60% of build cost)
        base_cost = STATION_COSTS.get(target_type, float('inf'))
        cost = base_cost * UPGRADE_COST_MULTIPLIER
        if self.player_credits < cost:
            return False

        # Check materials
        material_reqs = STATION_MATERIAL_COSTS.get(target_type, {})
        for resource, needed in material_reqs.items():
            if self.player_materials.get(resource, 0) < needed:
                return False

        return True

    def select_option(self, index: int) -> StationType | None:
        """Select an upgrade option by index."""
        if 0 <= index < len(self.available_upgrades):
            target_type = self.available_upgrades[index]
            if self.can_afford_upgrade(target_type):
                self.selected_index = index
                return target_type
        return None

    def get_selected_type(self) -> StationType | None:
        """Get the currently selected upgrade type."""
        if 0 <= self.selected_index < len(self.available_upgrades):
            return self.available_upgrades[self.selected_index]
        return None

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the upgrade panel."""
        if not self.visible:
            return

        super().draw(surface, font)

        line_height = font.get_linesize()
        y = self.y + 25

        # Show current station type
        if self.station_type:
            type_text = f"Current: {self.station_type.value}"
            type_surf = font.render(type_text, True, COLORS['ui_text'])
            surface.blit(type_surf, (self.x + 10, y))
        else:
            no_station = "Select your station first"
            no_surf = font.render(no_station, True, (255, 100, 100))
            surface.blit(no_surf, (self.x + 10, y))
        y += line_height + 2

        # Show credits
        credits_text = f"Credits: {self.player_credits:,.0f}"
        credits_surf = font.render(credits_text, True, COLORS['ui_highlight'])
        surface.blit(credits_surf, (self.x + 10, y))
        y += line_height + 5

        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        if not self.available_upgrades:
            no_upgrades = "No upgrades available"
            no_surf = font.render(no_upgrades, True, (150, 150, 150))
            surface.blit(no_surf, (self.x + 10, y))
            return

        # Draw upgrade options
        for i, target_type in enumerate(self.available_upgrades):
            base_cost = STATION_COSTS.get(target_type, 0)
            cost = base_cost * UPGRADE_COST_MULTIPLIER
            material_reqs = STATION_MATERIAL_COSTS.get(target_type, {})
            can_afford = self.can_afford_upgrade(target_type)
            is_selected = i == self.selected_index

            if is_selected:
                color = COLORS['ui_highlight']
                pygame.draw.rect(
                    surface, (50, 50, 80),
                    (self.x + 5, y - 2, self.width - 10, line_height + 2)
                )
            elif can_afford:
                color = COLORS['ui_text']
            else:
                color = (100, 100, 100)

            option_text = f"{i + 1}. {target_type.value}"
            option_surf = font.render(option_text, True, color)
            surface.blit(option_surf, (self.x + 10, y))

            cost_text = f"{cost:,.0f}c"
            cost_surf = font.render(cost_text, True, color)
            surface.blit(cost_surf, (self.x + self.width - cost_surf.get_width() - 10, y))

            y += line_height

            if material_reqs:
                mat_parts = []
                for resource, amount in material_reqs.items():
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

        y += 5
        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        hint_text = "Enter to confirm | ESC to cancel"
        hint_surf = font.render(hint_text, True, (150, 150, 150))
        surface.blit(hint_surf, (self.x + 10, y))


@dataclass
class PriceHistoryGraph(Panel):
    """Panel showing price history for a resource."""
    resource_type: ResourceType | None = None
    price_history: list[float] = field(default_factory=list)
    max_points: int = 100

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x, y=y, width=250, height=150, title="Price History"
        )
        self.price_history = []
        self.resource_type = None

    def set_resource(self, resource_type: ResourceType) -> None:
        """Set the resource to track."""
        if resource_type != self.resource_type:
            self.resource_type = resource_type
            self.price_history = []

    def add_price(self, price: float) -> None:
        """Add a price point."""
        self.price_history.append(price)
        if len(self.price_history) > self.max_points:
            self.price_history.pop(0)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the price history graph."""
        if not self.visible:
            return

        super().draw(surface, font)

        if not self.price_history or not self.resource_type:
            no_data = font.render("Select a resource", True, COLORS['ui_text'])
            surface.blit(no_data, (self.x + 10, self.y + 60))
            return

        # Draw resource name
        res_text = f"Resource: {self.resource_type.value}"
        res_surf = font.render(res_text, True, COLORS['ui_highlight'])
        surface.blit(res_surf, (self.x + 10, self.y + 25))

        # Graph area
        graph_x = self.x + 10
        graph_y = self.y + 45
        graph_w = self.width - 20
        graph_h = self.height - 70

        # Draw graph background
        pygame.draw.rect(surface, (20, 20, 30), (graph_x, graph_y, graph_w, graph_h))

        if len(self.price_history) < 2:
            return

        # Find min/max for scaling
        min_price = min(self.price_history)
        max_price = max(self.price_history)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = 1

        # Draw price line
        points = []
        for i, price in enumerate(self.price_history):
            x = graph_x + (i * graph_w) / (len(self.price_history) - 1)
            y = graph_y + graph_h - ((price - min_price) / price_range) * graph_h
            points.append((x, y))

        if len(points) >= 2:
            pygame.draw.lines(surface, (100, 200, 100), False, points, 2)

        # Draw current price
        current_price = self.price_history[-1]
        price_text = f"Current: {current_price:.1f}"
        price_surf = font.render(price_text, True, COLORS['ui_text'])
        surface.blit(price_surf, (self.x + 10, self.y + self.height - 20))


@dataclass
class TradeRoutePanel(Panel):
    """Panel for setting up trade routes on ships."""
    ship_id: UUID | None = None
    ship_name: str = ""
    waypoints: list = field(default_factory=list)  # List of (station_id, station_name, buy, sell)
    selected_index: int = -1
    available_stations: list = field(default_factory=list)  # For adding new waypoints
    add_mode: bool = False  # True when selecting a station to add

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x, y=y, width=320, height=300, title="Trade Route [T]"
        )
        self.ship_id = None
        self.ship_name = ""
        self.waypoints = []
        self.selected_index = -1
        self.available_stations = []
        self.add_mode = False

    def set_ship(self, ship_id: UUID | None, ship_name: str = "") -> None:
        """Set the ship to configure routes for."""
        self.ship_id = ship_id
        self.ship_name = ship_name
        self.waypoints = []
        self.selected_index = -1
        self.add_mode = False

    def set_waypoints(self, waypoints: list) -> None:
        """Set the current waypoints list."""
        self.waypoints = waypoints

    def set_available_stations(self, stations: list) -> None:
        """Set available stations for adding waypoints."""
        self.available_stations = stations

    def select_waypoint(self, index: int) -> None:
        """Select a waypoint by index."""
        if 0 <= index < len(self.waypoints):
            self.selected_index = index
            self.add_mode = False
        elif self.add_mode and 0 <= index < len(self.available_stations):
            self.selected_index = index

    def toggle_add_mode(self) -> None:
        """Toggle add waypoint mode."""
        self.add_mode = not self.add_mode
        self.selected_index = -1

    def get_selected_station_to_add(self) -> tuple | None:
        """Get the selected station when in add mode."""
        if self.add_mode and 0 <= self.selected_index < len(self.available_stations):
            return self.available_stations[self.selected_index]
        return None

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the trade route panel."""
        if not self.visible:
            return

        super().draw(surface, font)

        line_height = font.get_linesize()
        y = self.y + 25

        # Ship name
        if self.ship_name:
            ship_text = f"Ship: {self.ship_name}"
            ship_surf = font.render(ship_text, True, COLORS['ui_highlight'])
            surface.blit(ship_surf, (self.x + 10, y))
        else:
            no_ship = "Select your ship first"
            no_surf = font.render(no_ship, True, (255, 100, 100))
            surface.blit(no_surf, (self.x + 10, y))
        y += line_height + 5

        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y), (self.x + self.width - 5, y), 1
        )
        y += 5

        if self.add_mode:
            # Show available stations to add
            add_text = "Select station to add:"
            add_surf = font.render(add_text, True, COLORS['ui_text'])
            surface.blit(add_surf, (self.x + 10, y))
            y += line_height + 2

            for i, (station_id, station_name) in enumerate(self.available_stations[:6]):
                is_selected = i == self.selected_index
                color = COLORS['ui_highlight'] if is_selected else COLORS['ui_text']
                if is_selected:
                    pygame.draw.rect(
                        surface, (50, 50, 80),
                        (self.x + 5, y - 2, self.width - 10, line_height + 2)
                    )

                opt_text = f"{i + 1}. {station_name}"
                opt_surf = font.render(opt_text, True, color)
                surface.blit(opt_surf, (self.x + 10, y))
                y += line_height + 1

            y += 5
            hint_text = "Enter to add | ESC to cancel"
            hint_surf = font.render(hint_text, True, (150, 150, 150))
            surface.blit(hint_surf, (self.x + 10, y))

        else:
            # Show current waypoints
            waypoints_text = f"Waypoints ({len(self.waypoints)}):"
            wp_surf = font.render(waypoints_text, True, COLORS['ui_text'])
            surface.blit(wp_surf, (self.x + 10, y))
            y += line_height + 2

            if not self.waypoints:
                empty_text = "No waypoints set"
                empty_surf = font.render(empty_text, True, (150, 150, 150))
                surface.blit(empty_surf, (self.x + 20, y))
                y += line_height
            else:
                for i, wp in enumerate(self.waypoints[:5]):
                    station_name = wp.get('name', 'Unknown')
                    is_selected = i == self.selected_index
                    color = COLORS['ui_highlight'] if is_selected else COLORS['ui_text']

                    if is_selected:
                        pygame.draw.rect(
                            surface, (50, 50, 80),
                            (self.x + 5, y - 2, self.width - 10, line_height + 2)
                        )

                    wp_text = f"{i + 1}. {station_name[:20]}"
                    wp_surf = font.render(wp_text, True, color)
                    surface.blit(wp_surf, (self.x + 10, y))
                    y += line_height + 1

            y += 10
            pygame.draw.line(
                surface, self.border_color,
                (self.x + 5, y), (self.x + self.width - 5, y), 1
            )
            y += 8

            # Controls hint
            controls = [
                "A - Add waypoint",
                "D - Delete selected",
                "C - Clear all",
            ]
            for ctrl in controls:
                ctrl_surf = font.render(ctrl, True, (150, 150, 150))
                surface.blit(ctrl_surf, (self.x + 10, y))
                y += line_height


@dataclass
class HelpPanel(Panel):
    """Panel showing keyboard controls and help information."""
    width: int = 400
    height: int = 480
    title: str = "Help - Keyboard Controls"

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the help panel."""
        if not self.visible:
            return

        # Draw background with slight transparency effect
        pygame.draw.rect(surface, self.bg_color, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(surface, self.border_color, (self.x, self.y, self.width, self.height), 2)

        # Draw title
        title_surf = font.render(self.title, True, COLORS['ui_highlight'])
        surface.blit(title_surf, (self.x + 10, self.y + 8))

        y = self.y + 35
        line_height = 18

        # Help sections
        sections = [
            ("CAMERA", [
                ("W/A/S/D or Arrows", "Pan camera"),
                ("Mouse Wheel", "Zoom in/out"),
                ("Right Click + Drag", "Pan camera"),
            ]),
            ("SIMULATION", [
                ("Space", "Pause/Resume"),
                ("+/-", "Speed up/Slow down"),
                ("Q", "Quit game"),
            ]),
            ("SELECTION", [
                ("Left Click", "Select object"),
                ("Escape", "Deselect / Cancel"),
                ("Tab", "Toggle UI"),
            ]),
            ("BUILDING", [
                ("B", "Open build menu"),
                ("1-7", "Select station type"),
                ("Left Click", "Place station"),
                ("1-9", "Select resource (mining)"),
            ]),
            ("SHIPS", [
                ("S", "Open ship purchase menu"),
                ("1-5", "Select ship type"),
                ("Enter", "Purchase ship"),
            ]),
            ("SHIPS & NAVIGATION", [
                ("W", "Set waypoint (ship selected)"),
                ("Click", "Choose destination"),
            ]),
            ("TRADE ROUTES", [
                ("T", "Open trade manager"),
                ("T (in menu)", "Create new route"),
                ("1-8", "Select route & assign ship"),
                ("D", "Delete selected route"),
            ]),
            ("OTHER", [
                ("U", "Upgrade selected station"),
                ("R", "Toggle trade route lines"),
                ("F5", "Quick save"),
                ("F9", "Quick load"),
                ("H or F1", "Toggle this help"),
            ]),
        ]

        for section_name, controls in sections:
            # Section header
            header_surf = font.render(section_name, True, COLORS['ui_highlight'])
            surface.blit(header_surf, (self.x + 10, y))
            y += line_height + 2

            # Controls in section
            for key, description in controls:
                key_text = f"  {key}"
                key_surf = font.render(key_text, True, (200, 200, 100))
                surface.blit(key_surf, (self.x + 10, y))

                desc_surf = font.render(description, True, COLORS['ui_text'])
                surface.blit(desc_surf, (self.x + 160, y))
                y += line_height

            y += 5  # Space between sections

        # Footer
        y = self.y + self.height - 25
        pygame.draw.line(
            surface, self.border_color,
            (self.x + 5, y - 5), (self.x + self.width - 5, y - 5), 1
        )
        footer_surf = font.render("Press H or F1 to close", True, (150, 150, 150))
        surface.blit(footer_surf, (self.x + self.width // 2 - 70, y))


@dataclass
class ContextPrompt(Panel):
    """Small contextual prompt panel that appears during modes."""
    width: int = 300
    height: int = 60
    message: str = ""
    hint: str = ""

    def set_prompt(self, message: str, hint: str = "") -> None:
        """Set the prompt message and hint."""
        self.message = message
        self.hint = hint

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the context prompt."""
        if not self.visible or not self.message:
            return

        # Draw semi-transparent background
        pygame.draw.rect(surface, (30, 30, 50), (self.x, self.y, self.width, self.height))
        pygame.draw.rect(surface, COLORS['ui_highlight'], (self.x, self.y, self.width, self.height), 2)

        # Draw message
        msg_surf = font.render(self.message, True, COLORS['ui_highlight'])
        surface.blit(msg_surf, (self.x + 10, self.y + 10))

        # Draw hint
        if self.hint:
            hint_surf = font.render(self.hint, True, (150, 150, 150))
            surface.blit(hint_surf, (self.x + 10, self.y + 35))


@dataclass
class TradeRouteManagerPanel(Panel):
    """Panel for creating and managing trade routes between stations."""
    width: int = 350
    height: int = 400
    title: str = "Trade Routes"

    # Trade route creation state
    routes: list[dict] = field(default_factory=list)  # [{id, name, station1, station2, ship_id}]
    selected_route_index: int = -1

    # Route creation mode
    creating_route: bool = False
    first_station_id: UUID | None = None
    first_station_name: str = ""

    # Ship assignment mode
    assigning_ship: bool = False
    route_to_assign: int = -1

    # Available stations and ships
    available_stations: list[tuple[UUID, str]] = field(default_factory=list)
    available_ships: list[tuple[UUID, str]] = field(default_factory=list)

    def start_route_creation(self) -> None:
        """Start creating a new route - waiting for first station."""
        self.creating_route = True
        self.first_station_id = None
        self.first_station_name = ""
        self.assigning_ship = False

    def set_first_station(self, station_id: UUID, station_name: str) -> None:
        """Set the first station of the route being created."""
        self.first_station_id = station_id
        self.first_station_name = station_name

    def complete_route(self, station_id: UUID, station_name: str) -> dict | None:
        """Complete route creation with second station."""
        if not self.first_station_id:
            return None

        route = {
            'id': len(self.routes),
            'name': f"{self.first_station_name} >> {station_name}",
            'station1_id': self.first_station_id,
            'station1_name': self.first_station_name,
            'station2_id': station_id,
            'station2_name': station_name,
            'ship_id': None,
            'ship_name': None,
        }
        self.routes.append(route)
        self.creating_route = False
        self.first_station_id = None
        self.first_station_name = ""
        return route

    def cancel_creation(self) -> None:
        """Cancel route creation."""
        self.creating_route = False
        self.first_station_id = None
        self.first_station_name = ""
        self.assigning_ship = False
        self.route_to_assign = -1

    def select_route(self, index: int) -> None:
        """Select a route by index."""
        if 0 <= index < len(self.routes):
            self.selected_route_index = index
            # Start ship assignment mode
            self.assigning_ship = True
            self.route_to_assign = index

    def assign_ship(self, ship_id: UUID, ship_name: str) -> bool:
        """Assign a ship to the selected route."""
        if 0 <= self.route_to_assign < len(self.routes):
            self.routes[self.route_to_assign]['ship_id'] = ship_id
            self.routes[self.route_to_assign]['ship_name'] = ship_name
            self.assigning_ship = False
            self.route_to_assign = -1
            return True
        return False

    def delete_selected_route(self) -> None:
        """Delete the selected route."""
        if 0 <= self.selected_route_index < len(self.routes):
            del self.routes[self.selected_route_index]
            self.selected_route_index = -1
            # Renumber remaining routes
            for i, route in enumerate(self.routes):
                route['id'] = i

    def set_available_stations(self, stations: list[tuple[UUID, str]]) -> None:
        """Set available stations for route creation."""
        self.available_stations = stations

    def set_available_ships(self, ships: list[tuple[UUID, str]]) -> None:
        """Set available ships for assignment."""
        self.available_ships = ships

    def get_current_prompt(self) -> tuple[str, str]:
        """Get current mode's prompt message and hint."""
        if self.assigning_ship:
            route = self.routes[self.route_to_assign] if 0 <= self.route_to_assign < len(self.routes) else None
            if route:
                return f"Assign ship to: {route['name']}", "Click a ship or press 1-5 to select"
        elif self.creating_route:
            if self.first_station_id:
                return f"Select destination: {self.first_station_name} >> ?", "Click second station or press Escape to cancel"
            else:
                return "Select first station for route", "Click a station or press Escape to cancel"
        return "", ""

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the trade route manager panel."""
        if not self.visible:
            return

        # Draw background
        pygame.draw.rect(surface, self.bg_color, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(surface, self.border_color, (self.x, self.y, self.width, self.height), 2)

        # Draw title
        title_surf = font.render(self.title, True, COLORS['ui_highlight'])
        surface.blit(title_surf, (self.x + 10, self.y + 8))

        y = self.y + 35
        line_height = 20

        if self.assigning_ship:
            # Ship assignment mode
            prompt = f"Assign ship to route:"
            prompt_surf = font.render(prompt, True, COLORS['ui_text'])
            surface.blit(prompt_surf, (self.x + 10, y))
            y += line_height + 5

            if 0 <= self.route_to_assign < len(self.routes):
                route = self.routes[self.route_to_assign]
                route_surf = font.render(route['name'], True, COLORS['ui_highlight'])
                surface.blit(route_surf, (self.x + 20, y))
                y += line_height + 10

            # Show available ships
            ships_header = font.render("Available Ships:", True, COLORS['ui_text'])
            surface.blit(ships_header, (self.x + 10, y))
            y += line_height + 2

            for i, (ship_id, ship_name) in enumerate(self.available_ships[:5]):
                ship_text = f"{i + 1}. {ship_name[:25]}"
                ship_surf = font.render(ship_text, True, COLORS['ui_text'])
                surface.blit(ship_surf, (self.x + 20, y))
                y += line_height

            y += 10
            hint = font.render("Press 1-5 to select, Escape to cancel", True, (150, 150, 150))
            surface.blit(hint, (self.x + 10, y))

        elif self.creating_route:
            # Route creation mode
            if self.first_station_id:
                msg = f"First station: {self.first_station_name}"
                msg_surf = font.render(msg, True, COLORS['ui_text'])
                surface.blit(msg_surf, (self.x + 10, y))
                y += line_height + 5

                hint = font.render("Press T + click second station", True, COLORS['ui_highlight'])
                surface.blit(hint, (self.x + 10, y))
            else:
                hint = font.render("Press T + click first station", True, COLORS['ui_highlight'])
                surface.blit(hint, (self.x + 10, y))

            y += line_height + 10
            cancel = font.render("Press Escape to cancel", True, (150, 150, 150))
            surface.blit(cancel, (self.x + 10, y))

        else:
            # Normal mode - show existing routes
            if not self.routes:
                no_routes = font.render("No trade routes defined", True, (150, 150, 150))
                surface.blit(no_routes, (self.x + 10, y))
                y += line_height + 10
            else:
                routes_header = font.render("Routes:", True, COLORS['ui_text'])
                surface.blit(routes_header, (self.x + 10, y))
                y += line_height + 2

                for i, route in enumerate(self.routes[:8]):
                    is_selected = i == self.selected_route_index
                    color = COLORS['ui_highlight'] if is_selected else COLORS['ui_text']

                    if is_selected:
                        pygame.draw.rect(
                            surface, (50, 50, 80),
                            (self.x + 5, y - 2, self.width - 10, line_height + 2)
                        )

                    # Route number and name
                    route_text = f"{i + 1}. {route['name'][:30]}"
                    route_surf = font.render(route_text, True, color)
                    surface.blit(route_surf, (self.x + 10, y))
                    y += line_height

                    # Show assigned ship if any
                    if route.get('ship_name'):
                        ship_text = f"   Ship: {route['ship_name'][:25]}"
                        ship_surf = font.render(ship_text, True, (100, 200, 100))
                        surface.blit(ship_surf, (self.x + 10, y))
                    else:
                        ship_text = "   No ship assigned"
                        ship_surf = font.render(ship_text, True, (150, 100, 100))
                        surface.blit(ship_surf, (self.x + 10, y))
                    y += line_height + 5

            # Controls
            y = self.y + self.height - 80
            pygame.draw.line(
                surface, self.border_color,
                (self.x + 5, y), (self.x + self.width - 5, y), 1
            )
            y += 8

            controls = [
                "T - Create new route",
                "1-8 - Select route & assign ship",
                "D - Delete selected route",
                "Escape - Close",
            ]
            for ctrl in controls:
                ctrl_surf = font.render(ctrl, True, (150, 150, 150))
                surface.blit(ctrl_surf, (self.x + 10, y))
                y += line_height - 2


class NewsFeedPanel:
    """Panel showing news, events, contracts, and discoveries."""

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.visible = False
        self.bg_color = (20, 25, 35, 230)
        self.border_color = (80, 100, 140)

        # Tabs: News, Events, Contracts, Discoveries
        self.tabs = ["News", "Events", "Contracts", "Discoveries"]
        self.active_tab = 0

        # Scrolling
        self.scroll_offset = 0
        self.max_scroll = 0

        # Selection for contracts
        self.selected_contract = 0

    def handle_key(self, key: int) -> str | None:
        """Handle keyboard input. Returns action if any."""
        if key == pygame.K_TAB:
            # Cycle tabs
            self.active_tab = (self.active_tab + 1) % len(self.tabs)
            self.scroll_offset = 0
            return "tab_changed"

        elif key == pygame.K_UP:
            if self.active_tab == 2:  # Contracts
                self.selected_contract = max(0, self.selected_contract - 1)
            else:
                self.scroll_offset = max(0, self.scroll_offset - 1)
            return "scroll"

        elif key == pygame.K_DOWN:
            if self.active_tab == 2:  # Contracts
                self.selected_contract += 1
            else:
                self.scroll_offset = min(self.max_scroll, self.scroll_offset + 1)
            return "scroll"

        elif key == pygame.K_RETURN and self.active_tab == 2:
            return "accept_contract"

        elif key == pygame.K_ESCAPE:
            return "close"

        return None

    def render(self, surface: pygame.Surface, world: "World") -> None:
        """Render the news feed panel."""
        if not self.visible:
            return

        font = pygame.font.Font(None, 22)
        small_font = pygame.font.Font(None, 18)
        title_font = pygame.font.Font(None, 28)

        # Background
        panel_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        panel_surface.fill(self.bg_color)
        surface.blit(panel_surface, (self.x, self.y))

        # Border
        pygame.draw.rect(
            surface, self.border_color,
            (self.x, self.y, self.width, self.height), 2
        )

        # Title
        title = title_font.render("GALACTIC NEWS NETWORK", True, (200, 220, 255))
        surface.blit(title, (self.x + 10, self.y + 8))

        # Tabs
        tab_y = self.y + 40
        tab_width = (self.width - 20) // len(self.tabs)
        for i, tab_name in enumerate(self.tabs):
            tab_x = self.x + 10 + i * tab_width
            is_active = i == self.active_tab

            # Tab background
            tab_color = (60, 80, 120) if is_active else (40, 50, 70)
            pygame.draw.rect(surface, tab_color, (tab_x, tab_y, tab_width - 5, 25))

            # Tab text
            text_color = (255, 255, 255) if is_active else (150, 150, 150)
            tab_text = font.render(tab_name, True, text_color)
            surface.blit(tab_text, (tab_x + 5, tab_y + 4))

        # Content area
        content_y = tab_y + 35
        content_height = self.height - 90

        # Get data from event manager
        from ..simulation.events import get_news_feed, get_active_events, get_available_contracts, EventManager

        news = []
        events = []
        contracts = []
        discoveries = []

        for entity, em in world.entity_manager.get_all_components(EventManager):
            news = em.news_feed[:15]
            events = em.active_events
            contracts = [c for c in em.available_contracts if not c.accepted]
            discoveries = em.pending_discoveries
            break

        line_height = 20

        if self.active_tab == 0:
            # News tab
            self._render_news(surface, font, small_font, news, content_y, content_height, line_height)

        elif self.active_tab == 1:
            # Events tab
            self._render_events(surface, font, small_font, events, content_y, content_height, line_height)

        elif self.active_tab == 2:
            # Contracts tab
            self._render_contracts(surface, font, small_font, contracts, content_y, content_height, line_height)

        elif self.active_tab == 3:
            # Discoveries tab
            self._render_discoveries(surface, font, small_font, discoveries, content_y, content_height, line_height)

        # Footer with controls
        footer_y = self.y + self.height - 25
        pygame.draw.line(surface, self.border_color, (self.x + 5, footer_y - 5), (self.x + self.width - 5, footer_y - 5), 1)
        controls = small_font.render("Tab: Switch | ↑↓: Scroll | Enter: Accept | N/Esc: Close", True, (120, 120, 140))
        surface.blit(controls, (self.x + 10, footer_y))

    def _render_news(self, surface, font, small_font, news, y, height, line_height):
        """Render news items."""
        if not news:
            no_news = font.render("No recent news", True, (100, 100, 100))
            surface.blit(no_news, (self.x + 20, y + 20))
            return

        # Importance colors
        importance_colors = {
            1: (150, 150, 150),
            2: (200, 200, 200),
            3: (255, 200, 100),
            4: (255, 150, 100),
            5: (255, 100, 100),
        }

        # Category icons
        category_symbols = {
            "economic": "$",
            "disaster": "!",
            "political": "⚑",
            "discovery": "★",
            "crime": "⚠",
            "technology": "⚙",
        }

        current_y = y
        for i, item in enumerate(news[self.scroll_offset:]):
            if current_y > y + height - line_height * 2:
                break

            color = importance_colors.get(item.importance, (150, 150, 150))
            symbol = category_symbols.get(item.category.value, "•")

            # Headline
            headline = f"{symbol} {item.headline[:45]}"
            headline_surf = font.render(headline, True, color)
            surface.blit(headline_surf, (self.x + 15, current_y))
            current_y += line_height

            # Body (truncated)
            if item.body:
                body = item.body[:60] + "..." if len(item.body) > 60 else item.body
                body_surf = small_font.render(body, True, (120, 120, 140))
                surface.blit(body_surf, (self.x + 25, current_y))
                current_y += line_height

            current_y += 5  # Spacing

        self.max_scroll = max(0, len(news) - 5)

    def _render_events(self, surface, font, small_font, events, y, height, line_height):
        """Render active events."""
        if not events:
            no_events = font.render("No active events", True, (100, 100, 100))
            surface.blit(no_events, (self.x + 20, y + 20))
            return

        # Severity colors
        severity_colors = {
            "minor": (150, 200, 150),
            "moderate": (200, 200, 100),
            "major": (255, 150, 100),
            "critical": (255, 100, 100),
        }

        current_y = y
        for event in events[self.scroll_offset:]:
            if current_y > y + height - line_height * 3:
                break

            color = severity_colors.get(event.severity.value, (150, 150, 150))

            # Title
            title_surf = font.render(event.title[:40], True, color)
            surface.blit(title_surf, (self.x + 15, current_y))
            current_y += line_height

            # Duration remaining
            if event.duration > 0:
                mins = int(event.duration // 60)
                secs = int(event.duration % 60)
                duration_text = f"Time remaining: {mins}m {secs}s"
                duration_surf = small_font.render(duration_text, True, (100, 100, 100))
                surface.blit(duration_surf, (self.x + 25, current_y))
                current_y += line_height

            # Effects
            effects = []
            if event.price_modifier != 1.0:
                change = int((event.price_modifier - 1.0) * 100)
                sign = "+" if change > 0 else ""
                effects.append(f"Price: {sign}{change}%")
            if event.supply_modifier != 1.0:
                change = int((event.supply_modifier - 1.0) * 100)
                sign = "+" if change > 0 else ""
                effects.append(f"Supply: {sign}{change}%")

            if effects:
                effects_text = " | ".join(effects)
                effects_surf = small_font.render(effects_text, True, (150, 150, 200))
                surface.blit(effects_surf, (self.x + 25, current_y))
                current_y += line_height

            current_y += 8

        self.max_scroll = max(0, len(events) - 3)

    def _render_contracts(self, surface, font, small_font, contracts, y, height, line_height):
        """Render available contracts."""
        if not contracts:
            no_contracts = font.render("No contracts available", True, (100, 100, 100))
            surface.blit(no_contracts, (self.x + 20, y + 20))

            hint = small_font.render("Contracts appear when stations need supplies", True, (80, 80, 80))
            surface.blit(hint, (self.x + 20, y + 45))
            return

        current_y = y
        self.selected_contract = min(self.selected_contract, len(contracts) - 1)

        for i, contract in enumerate(contracts):
            if current_y > y + height - line_height * 4:
                break

            is_selected = i == self.selected_contract
            bg_color = (50, 60, 80) if is_selected else None

            if bg_color:
                pygame.draw.rect(surface, bg_color, (self.x + 10, current_y - 2, self.width - 20, line_height * 3 + 10))

            # Title
            color = (255, 220, 100) if is_selected else (200, 200, 200)
            title_surf = font.render(contract.title[:40], True, color)
            surface.blit(title_surf, (self.x + 15, current_y))
            current_y += line_height

            # Details
            resource_name = contract.resource.value.replace("_", " ").title()
            details = f"{contract.amount:.0f} {resource_name} → {contract.client_name[:20]}"
            details_surf = small_font.render(details, True, (150, 150, 150))
            surface.blit(details_surf, (self.x + 25, current_y))
            current_y += line_height

            # Reward and deadline
            reward_text = f"Reward: {contract.reward:,.0f}cr"
            if contract.bonus_reward > 0:
                reward_text += f" (+{contract.bonus_reward:,.0f} bonus)"
            reward_surf = small_font.render(reward_text, True, (100, 200, 100))
            surface.blit(reward_surf, (self.x + 25, current_y))

            # Deadline
            mins = int(contract.deadline // 60)
            deadline_color = (255, 100, 100) if mins < 3 else (150, 150, 150)
            deadline_surf = small_font.render(f"Deadline: {mins}m", True, deadline_color)
            surface.blit(deadline_surf, (self.x + self.width - 100, current_y))

            current_y += line_height + 10

        # Selection hint
        if contracts:
            hint = small_font.render("Press Enter to accept selected contract", True, (100, 150, 100))
            surface.blit(hint, (self.x + 15, y + height - line_height))

    def _render_discoveries(self, surface, font, small_font, discoveries, y, height, line_height):
        """Render pending discoveries."""
        if not discoveries:
            no_disc = font.render("No pending discoveries", True, (100, 100, 100))
            surface.blit(no_disc, (self.x + 20, y + 20))

            hint = small_font.render("Ships may discover anomalies while traveling", True, (80, 80, 80))
            surface.blit(hint, (self.x + 20, y + 45))
            return

        # Discovery type colors
        type_colors = {
            "derelict": (200, 150, 100),
            "anomaly": (150, 150, 255),
            "debris": (150, 150, 150),
            "signal": (255, 200, 100),
        }

        current_y = y
        for discovery in discoveries[self.scroll_offset:]:
            if current_y > y + height - line_height * 3:
                break

            color = type_colors.get(discovery.discovery_type, (150, 150, 150))

            # Title
            title_surf = font.render(discovery.title, True, color)
            surface.blit(title_surf, (self.x + 15, current_y))
            current_y += line_height

            # Description
            desc_surf = small_font.render(discovery.description[:50], True, (120, 120, 140))
            surface.blit(desc_surf, (self.x + 25, current_y))
            current_y += line_height

            # Rewards
            rewards = []
            if discovery.reward_credits > 0:
                rewards.append(f"{discovery.reward_credits:,.0f}cr")
            for res, amt in discovery.reward_resources.items():
                rewards.append(f"{amt:.0f} {res.value.replace('_', ' ')}")

            if rewards:
                reward_text = "Rewards: " + ", ".join(rewards[:3])
                reward_surf = small_font.render(reward_text, True, (100, 200, 100))
                surface.blit(reward_surf, (self.x + 25, current_y))
                current_y += line_height

            current_y += 8

        self.max_scroll = max(0, len(discoveries) - 3)
