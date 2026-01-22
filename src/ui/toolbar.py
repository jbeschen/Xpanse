"""Top toolbar with icon buttons for game features."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
import pygame

from ..config import TOOLBAR_HEIGHT, TOOLBAR_ICON_SIZE, COLORS


class ToolbarAction(Enum):
    """Actions that can be triggered from the toolbar."""
    BUILD = "build"
    SHIPS = "ships"
    FLEET = "fleet"
    TRADE = "trade"
    NEWS = "news"
    HELP = "help"
    PAUSE = "pause"
    SPEED_DOWN = "speed_down"
    SPEED_UP = "speed_up"


@dataclass
class ToolbarButton:
    """A button in the toolbar."""
    action: ToolbarAction
    icon_char: str  # Unicode character to display
    tooltip: str
    shortcut: str  # Keyboard shortcut hint
    x: int = 0  # Position set during layout
    width: int = TOOLBAR_ICON_SIZE + 16
    enabled: bool = True
    highlighted: bool = False


class Toolbar:
    """Top toolbar with icon buttons for accessing game features."""

    def __init__(self, screen_width: int) -> None:
        self.screen_width = screen_width
        self.height = TOOLBAR_HEIGHT
        self.visible = True

        # Callbacks for button actions
        self._callbacks: dict[ToolbarAction, Callable] = {}

        # Hover state
        self.hovered_button: ToolbarButton | None = None
        self.tooltip_timer = 0.0

        # Define buttons
        self.buttons = [
            ToolbarButton(
                ToolbarAction.BUILD,
                icon_char="\u2302",  # House symbol
                tooltip="Build Station",
                shortcut="B",
            ),
            ToolbarButton(
                ToolbarAction.SHIPS,
                icon_char="\u2708",  # Airplane symbol
                tooltip="Ship Menu",
                shortcut="S",
            ),
            ToolbarButton(
                ToolbarAction.FLEET,
                icon_char="\u2630",  # Trigram (list icon)
                tooltip="Fleet List",
                shortcut="F",
            ),
            ToolbarButton(
                ToolbarAction.TRADE,
                icon_char="\u2194",  # Left-right arrow
                tooltip="Trade Routes",
                shortcut="T",
            ),
            ToolbarButton(
                ToolbarAction.NEWS,
                icon_char="\u2709",  # Envelope
                tooltip="News & Contracts",
                shortcut="N",
            ),
            ToolbarButton(
                ToolbarAction.HELP,
                icon_char="?",
                tooltip="Help",
                shortcut="H",
            ),
        ]

        # Speed control buttons (right side)
        self.speed_buttons = [
            ToolbarButton(
                ToolbarAction.SPEED_DOWN,
                icon_char="\u25C0",  # Left triangle
                tooltip="Slow Down",
                shortcut="-",
            ),
            ToolbarButton(
                ToolbarAction.PAUSE,
                icon_char="\u25AE\u25AE",  # Pause bars
                tooltip="Pause/Resume",
                shortcut="Space",
            ),
            ToolbarButton(
                ToolbarAction.SPEED_UP,
                icon_char="\u25B6",  # Right triangle
                tooltip="Speed Up",
                shortcut="+",
            ),
        ]

        self._layout_buttons()

    def _layout_buttons(self) -> None:
        """Calculate button positions."""
        # Left side buttons
        x = 10
        for button in self.buttons:
            button.x = x
            x += button.width + 5

        # Right side buttons (speed controls)
        x = self.screen_width - 10
        for button in reversed(self.speed_buttons):
            button.width = TOOLBAR_ICON_SIZE + 8
            x -= button.width
            button.x = x
            x -= 5

    def register_callback(self, action: ToolbarAction, callback: Callable) -> None:
        """Register a callback for a toolbar action."""
        self._callbacks[action] = callback

    def update(self, dt: float, mouse_x: int, mouse_y: int) -> None:
        """Update toolbar state."""
        if not self.visible:
            return

        # Check for hover
        old_hovered = self.hovered_button
        self.hovered_button = None

        if mouse_y < self.height:
            for button in self.buttons + self.speed_buttons:
                if button.x <= mouse_x < button.x + button.width:
                    self.hovered_button = button
                    break

        # Reset tooltip timer if hover changed
        if self.hovered_button != old_hovered:
            self.tooltip_timer = 0.0
        elif self.hovered_button:
            self.tooltip_timer += dt

    def handle_click(self, mouse_x: int, mouse_y: int) -> bool:
        """Handle mouse click.

        Returns:
            True if click was handled by toolbar
        """
        if not self.visible or mouse_y >= self.height:
            return False

        for button in self.buttons + self.speed_buttons:
            if button.x <= mouse_x < button.x + button.width:
                if button.enabled and button.action in self._callbacks:
                    self._callbacks[button.action]()
                return True

        return False

    def set_paused(self, paused: bool) -> None:
        """Update pause button appearance."""
        for button in self.speed_buttons:
            if button.action == ToolbarAction.PAUSE:
                button.icon_char = "\u25B6" if paused else "\u25AE\u25AE"
                break

    def render(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
        game_speed: float,
        game_paused: bool,
        credits: float,
    ) -> None:
        """Render the toolbar."""
        if not self.visible:
            return

        # Background
        toolbar_rect = pygame.Rect(0, 0, self.screen_width, self.height)
        pygame.draw.rect(screen, (20, 25, 35), toolbar_rect)
        pygame.draw.line(
            screen,
            COLORS['ui_border'],
            (0, self.height - 1),
            (self.screen_width, self.height - 1)
        )

        # Render buttons
        for button in self.buttons + self.speed_buttons:
            self._render_button(screen, font, button)

        # Game status in center
        status_text = f"Speed: {game_speed:.0f}x" if not game_paused else "PAUSED"
        status_color = (200, 200, 100) if not game_paused else (255, 100, 100)
        status_surf = font.render(status_text, True, status_color)
        status_x = self.screen_width // 2 - status_surf.get_width() // 2
        screen.blit(status_surf, (status_x, (self.height - status_surf.get_height()) // 2))

        # Credits display
        credits_text = f"Credits: {credits:,.0f}"
        credits_surf = font.render(credits_text, True, (100, 200, 100))
        credits_x = self.screen_width // 2 + 100
        screen.blit(credits_surf, (credits_x, (self.height - credits_surf.get_height()) // 2))

        # Tooltip
        if self.hovered_button and self.tooltip_timer > 0.3:
            self._render_tooltip(screen, small_font, self.hovered_button)

    def _render_button(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        button: ToolbarButton
    ) -> None:
        """Render a single toolbar button."""
        is_hovered = button == self.hovered_button

        # Button background
        btn_rect = pygame.Rect(
            button.x, 4,
            button.width, self.height - 8
        )

        if is_hovered:
            bg_color = (50, 60, 80)
            border_color = COLORS['ui_highlight']
        else:
            bg_color = (30, 35, 50)
            border_color = (50, 55, 70)

        pygame.draw.rect(screen, bg_color, btn_rect, border_radius=4)
        pygame.draw.rect(screen, border_color, btn_rect, 1, border_radius=4)

        # Icon
        icon_color = COLORS['ui_highlight'] if is_hovered else COLORS['ui_text']
        icon_surf = font.render(button.icon_char, True, icon_color)
        icon_x = button.x + (button.width - icon_surf.get_width()) // 2
        icon_y = (self.height - icon_surf.get_height()) // 2
        screen.blit(icon_surf, (icon_x, icon_y))

    def _render_tooltip(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        button: ToolbarButton
    ) -> None:
        """Render tooltip for a button."""
        text = f"{button.tooltip} ({button.shortcut})"
        text_surf = font.render(text, True, COLORS['ui_text'])

        # Position below button
        padding = 4
        width = text_surf.get_width() + padding * 2
        height = text_surf.get_height() + padding * 2
        x = button.x + button.width // 2 - width // 2
        y = self.height + 4

        # Keep on screen
        if x < 0:
            x = 0
        if x + width > self.screen_width:
            x = self.screen_width - width

        # Background
        bg_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(screen, (30, 35, 50), bg_rect, border_radius=3)
        pygame.draw.rect(screen, COLORS['ui_border'], bg_rect, 1, border_radius=3)

        # Text
        screen.blit(text_surf, (x + padding, y + padding))
