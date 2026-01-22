"""Camera for pan/zoom navigation."""
from __future__ import annotations
from dataclasses import dataclass
import math

from ..config import AU_TO_PIXELS, MIN_ZOOM, MAX_ZOOM, SCREEN_WIDTH, SCREEN_HEIGHT


@dataclass
class Camera:
    """Camera for viewing the solar system."""
    # Position in world coordinates (AU)
    x: float = 0.0
    y: float = 0.0

    # Zoom level (1.0 = 1 AU = AU_TO_PIXELS pixels)
    zoom: float = 1.0

    # Screen dimensions
    screen_width: int = SCREEN_WIDTH
    screen_height: int = SCREEN_HEIGHT

    # Pan state
    is_panning: bool = False
    pan_start_x: int = 0
    pan_start_y: int = 0
    pan_start_cam_x: float = 0.0
    pan_start_cam_y: float = 0.0

    # Camera lock - follows a target entity
    locked_entity_id: object = None  # UUID of entity to follow
    locked_entity_name: str = ""  # Name for display

    def world_to_screen(self, world_x: float, world_y: float) -> tuple[int, int]:
        """Convert world coordinates (AU) to screen coordinates (pixels)."""
        # Offset from camera center
        dx = world_x - self.x
        dy = world_y - self.y

        # Scale by zoom and base AU_TO_PIXELS
        screen_x = int(dx * self.zoom * AU_TO_PIXELS + self.screen_width / 2)
        screen_y = int(-dy * self.zoom * AU_TO_PIXELS + self.screen_height / 2)  # Y is inverted

        return (screen_x, screen_y)

    def screen_to_world(self, screen_x: int, screen_y: int) -> tuple[float, float]:
        """Convert screen coordinates (pixels) to world coordinates (AU)."""
        # Offset from screen center
        dx = screen_x - self.screen_width / 2
        dy = -(screen_y - self.screen_height / 2)  # Y is inverted

        # Scale by zoom and base AU_TO_PIXELS
        world_x = dx / (self.zoom * AU_TO_PIXELS) + self.x
        world_y = dy / (self.zoom * AU_TO_PIXELS) + self.y

        return (world_x, world_y)

    def zoom_at(self, screen_x: int, screen_y: int, factor: float) -> None:
        """Zoom centered on a screen position.

        Args:
            screen_x: Screen X coordinate to zoom at
            screen_y: Screen Y coordinate to zoom at
            factor: Zoom factor (>1 to zoom in, <1 to zoom out)
        """
        # Get world position before zoom
        world_x, world_y = self.screen_to_world(screen_x, screen_y)

        # Apply zoom
        new_zoom = self.zoom * factor
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))

        # Get world position after zoom
        new_world_x, new_world_y = self.screen_to_world(screen_x, screen_y)

        # Adjust camera to keep point under cursor
        self.x += world_x - new_world_x
        self.y += world_y - new_world_y

    def zoom_in(self, screen_x: int | None = None, screen_y: int | None = None) -> None:
        """Zoom in (1.2x)."""
        if screen_x is None:
            screen_x = self.screen_width // 2
        if screen_y is None:
            screen_y = self.screen_height // 2
        self.zoom_at(screen_x, screen_y, 1.2)

    def zoom_out(self, screen_x: int | None = None, screen_y: int | None = None) -> None:
        """Zoom out (0.8x)."""
        if screen_x is None:
            screen_x = self.screen_width // 2
        if screen_y is None:
            screen_y = self.screen_height // 2
        self.zoom_at(screen_x, screen_y, 1.0 / 1.2)

    def start_pan(self, screen_x: int, screen_y: int) -> None:
        """Start panning from a screen position."""
        self.is_panning = True
        self.pan_start_x = screen_x
        self.pan_start_y = screen_y
        self.pan_start_cam_x = self.x
        self.pan_start_cam_y = self.y
        # Panning unlocks the camera
        if self.is_locked:
            self.unlock()

    def update_pan(self, screen_x: int, screen_y: int) -> None:
        """Update pan position."""
        if not self.is_panning:
            return

        # Calculate screen delta
        dx = screen_x - self.pan_start_x
        dy = screen_y - self.pan_start_y

        # Convert to world delta and apply
        world_dx = -dx / (self.zoom * AU_TO_PIXELS)
        world_dy = dy / (self.zoom * AU_TO_PIXELS)  # Y is inverted

        self.x = self.pan_start_cam_x + world_dx
        self.y = self.pan_start_cam_y + world_dy

    def end_pan(self) -> None:
        """End panning."""
        self.is_panning = False

    def pan(self, dx: float, dy: float) -> None:
        """Pan the camera by a world-space delta.

        Args:
            dx: Delta X in AU
            dy: Delta Y in AU
        """
        self.x += dx
        self.y += dy

    def pan_by_screen(self, screen_dx: int, screen_dy: int) -> None:
        """Pan the camera by a screen-space delta.

        Args:
            screen_dx: Delta X in pixels
            screen_dy: Delta Y in pixels
        """
        world_dx = screen_dx / (self.zoom * AU_TO_PIXELS)
        world_dy = -screen_dy / (self.zoom * AU_TO_PIXELS)  # Y is inverted
        self.pan(world_dx, world_dy)

    def center_on(self, world_x: float, world_y: float) -> None:
        """Center the camera on a world position."""
        self.x = world_x
        self.y = world_y

    def fit_bounds(self, min_x: float, min_y: float, max_x: float, max_y: float, padding: float = 0.1) -> None:
        """Adjust camera to fit bounds with optional padding.

        Args:
            min_x: Minimum X in world coordinates
            min_y: Minimum Y in world coordinates
            max_x: Maximum X in world coordinates
            max_y: Maximum Y in world coordinates
            padding: Padding factor (0.1 = 10% padding)
        """
        # Center on bounds
        self.x = (min_x + max_x) / 2
        self.y = (min_y + max_y) / 2

        # Calculate required zoom
        width = max_x - min_x
        height = max_y - min_y

        if width == 0 and height == 0:
            return

        # Add padding
        width *= (1 + padding)
        height *= (1 + padding)

        # Calculate zoom to fit
        zoom_x = self.screen_width / (width * AU_TO_PIXELS) if width > 0 else MAX_ZOOM
        zoom_y = self.screen_height / (height * AU_TO_PIXELS) if height > 0 else MAX_ZOOM

        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, min(zoom_x, zoom_y)))

    def get_visible_bounds(self) -> tuple[float, float, float, float]:
        """Get visible world bounds.

        Returns:
            (min_x, min_y, max_x, max_y) in world coordinates
        """
        min_x, max_y = self.screen_to_world(0, 0)
        max_x, min_y = self.screen_to_world(self.screen_width, self.screen_height)
        return (min_x, min_y, max_x, max_y)

    def is_visible(self, world_x: float, world_y: float, radius: float = 0) -> bool:
        """Check if a world position is visible on screen.

        Args:
            world_x: World X coordinate
            world_y: World Y coordinate
            radius: Object radius in world units (AU)

        Returns:
            True if position is visible
        """
        min_x, min_y, max_x, max_y = self.get_visible_bounds()
        return (
            world_x + radius >= min_x and
            world_x - radius <= max_x and
            world_y + radius >= min_y and
            world_y - radius <= max_y
        )

    def lock_to_entity(self, entity_id, entity_name: str) -> None:
        """Lock camera to follow an entity.

        Args:
            entity_id: UUID of the entity to follow
            entity_name: Name of the entity (for display)
        """
        self.locked_entity_id = entity_id
        self.locked_entity_name = entity_name

    def unlock(self) -> None:
        """Unlock camera from following an entity."""
        self.locked_entity_id = None
        self.locked_entity_name = ""

    @property
    def is_locked(self) -> bool:
        """Check if camera is locked to an entity."""
        return self.locked_entity_id is not None

    def update_lock(self, entity_manager) -> None:
        """Update camera position if locked to an entity.

        Args:
            entity_manager: EntityManager to look up entity position
        """
        if not self.locked_entity_id:
            return

        from ..solar_system.orbits import Position

        entity = entity_manager.get_entity(self.locked_entity_id)
        if not entity:
            # Entity no longer exists, unlock
            self.unlock()
            return

        pos = entity_manager.get_component(entity, Position)
        if pos:
            self.x = pos.x
            self.y = pos.y
