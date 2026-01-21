"""Mouse/keyboard input handling."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable
import pygame

if TYPE_CHECKING:
    from .camera import Camera
    from ..core.world import World


class InputAction(Enum):
    """Input actions that can be triggered."""
    SELECT = "select"
    CONTEXT_MENU = "context_menu"
    DESELECT = "deselect"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN = "pan"
    PAUSE = "pause"
    SPEED_UP = "speed_up"
    SPEED_DOWN = "speed_down"
    TOGGLE_UI = "toggle_ui"
    QUIT = "quit"
    BUILD_MODE = "build_mode"  # Toggle build placement mode
    CONFIRM_BUILD = "confirm_build"  # Place station at cursor


@dataclass
class InputState:
    """Current input state."""
    mouse_x: int = 0
    mouse_y: int = 0
    mouse_world_x: float = 0.0
    mouse_world_y: float = 0.0
    left_click: bool = False
    right_click: bool = False
    middle_click: bool = False
    scroll_delta: int = 0
    keys_pressed: set[int] = field(default_factory=set)
    keys_just_pressed: set[int] = field(default_factory=set)


class InputHandler:
    """Handles input events and converts them to game actions."""

    def __init__(self, camera: Camera) -> None:
        self.camera = camera
        self.state = InputState()
        self._callbacks: dict[InputAction, list[Callable]] = {}
        self._selected_entity_id = None

    def register_callback(self, action: InputAction, callback: Callable) -> None:
        """Register a callback for an input action."""
        if action not in self._callbacks:
            self._callbacks[action] = []
        self._callbacks[action].append(callback)

    def _fire_action(self, action: InputAction, *args) -> None:
        """Fire callbacks for an action."""
        for callback in self._callbacks.get(action, []):
            callback(*args)

    def process_events(self, events: list[pygame.event.Event]) -> bool:
        """Process pygame events and update input state.

        Returns:
            False if quit was requested, True otherwise
        """
        # Reset per-frame state
        self.state.left_click = False
        self.state.right_click = False
        self.state.scroll_delta = 0
        self.state.keys_just_pressed.clear()

        for event in events:
            if event.type == pygame.QUIT:
                self._fire_action(InputAction.QUIT)
                return False

            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_button_down(event)

            elif event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_button_up(event)

            elif event.type == pygame.MOUSEWHEEL:
                self._handle_mouse_wheel(event)

            elif event.type == pygame.KEYDOWN:
                self._handle_key_down(event)

            elif event.type == pygame.KEYUP:
                self._handle_key_up(event)

        return True

    def _handle_mouse_motion(self, event: pygame.event.Event) -> None:
        """Handle mouse movement."""
        self.state.mouse_x = event.pos[0]
        self.state.mouse_y = event.pos[1]

        # Update world coordinates
        wx, wy = self.camera.screen_to_world(event.pos[0], event.pos[1])
        self.state.mouse_world_x = wx
        self.state.mouse_world_y = wy

        # Handle camera panning
        if self.camera.is_panning:
            self.camera.update_pan(event.pos[0], event.pos[1])

    def _handle_mouse_button_down(self, event: pygame.event.Event) -> None:
        """Handle mouse button press."""
        if event.button == 1:  # Left click
            self.state.left_click = True
            self._fire_action(InputAction.SELECT, self.state.mouse_world_x, self.state.mouse_world_y)

        elif event.button == 2:  # Middle click - start pan
            self.state.middle_click = True
            self.camera.start_pan(event.pos[0], event.pos[1])
            self._fire_action(InputAction.PAN)

        elif event.button == 3:  # Right click
            self.state.right_click = True
            self._fire_action(InputAction.CONTEXT_MENU, self.state.mouse_world_x, self.state.mouse_world_y)

    def _handle_mouse_button_up(self, event: pygame.event.Event) -> None:
        """Handle mouse button release."""
        if event.button == 2:  # Middle click - end pan
            self.state.middle_click = False
            self.camera.end_pan()

    def _handle_mouse_wheel(self, event: pygame.event.Event) -> None:
        """Handle mouse wheel scroll."""
        self.state.scroll_delta = event.y

        if event.y > 0:
            self.camera.zoom_in(self.state.mouse_x, self.state.mouse_y)
            self._fire_action(InputAction.ZOOM_IN)
        elif event.y < 0:
            self.camera.zoom_out(self.state.mouse_x, self.state.mouse_y)
            self._fire_action(InputAction.ZOOM_OUT)

    def _handle_key_down(self, event: pygame.event.Event) -> None:
        """Handle key press."""
        self.state.keys_pressed.add(event.key)
        self.state.keys_just_pressed.add(event.key)

        # Handle specific keys
        if event.key == pygame.K_ESCAPE:
            self._fire_action(InputAction.DESELECT)

        elif event.key == pygame.K_SPACE:
            self._fire_action(InputAction.PAUSE)

        elif event.key == pygame.K_PLUS or event.key == pygame.K_EQUALS:
            self._fire_action(InputAction.SPEED_UP)

        elif event.key == pygame.K_MINUS:
            self._fire_action(InputAction.SPEED_DOWN)

        elif event.key == pygame.K_TAB:
            self._fire_action(InputAction.TOGGLE_UI)

        elif event.key == pygame.K_b:
            self._fire_action(InputAction.BUILD_MODE)

        elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            self._fire_action(InputAction.CONFIRM_BUILD)

        elif event.key == pygame.K_q:
            self._fire_action(InputAction.QUIT)

    def _handle_key_up(self, event: pygame.event.Event) -> None:
        """Handle key release."""
        self.state.keys_pressed.discard(event.key)

    def is_key_pressed(self, key: int) -> bool:
        """Check if a key is currently pressed."""
        return key in self.state.keys_pressed

    def is_key_just_pressed(self, key: int) -> bool:
        """Check if a key was just pressed this frame."""
        return key in self.state.keys_just_pressed

    @property
    def selected_entity_id(self):
        """Get currently selected entity ID."""
        return self._selected_entity_id

    @selected_entity_id.setter
    def selected_entity_id(self, value):
        """Set selected entity ID."""
        self._selected_entity_id = value
