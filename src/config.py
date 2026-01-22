"""Game constants and configuration."""
from dataclasses import dataclass

# Display settings
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 1000
FPS = 60
TITLE = "Xpanse: Solar System Economic Simulation"

# UI Layout
TOOLBAR_HEIGHT = 48  # Height of top toolbar
TOOLBAR_ICON_SIZE = 32  # Size of toolbar icons

# Simulation settings
SIMULATION_SPEED = 1.0  # Time multiplier
TICKS_PER_SECOND = 10  # Economic ticks per second

# Scale: 1 AU = 100 pixels at default zoom
AU_TO_PIXELS = 100
MIN_ZOOM = 0.01
MAX_ZOOM = 50.0  # Allow much closer zoom for station management

# Economic constants
BASE_PRICE_VOLATILITY = 0.1
MIN_PRICE_MULTIPLIER = 0.1
MAX_PRICE_MULTIPLIER = 10.0
SUPPLY_DEMAND_FACTOR = 0.05

# Production constants
PRODUCTION_TICK_RATE = 1.0  # Seconds between production cycles

# Ship constants
BASE_SHIP_SPEED = 0.1  # AU per game minute
CARGO_TRANSFER_RATE = 10  # Units per second

# Colors
COLORS = {
    'background': (10, 10, 20),
    'star': (255, 255, 200),
    'planet': (100, 150, 200),
    'moon': (150, 150, 150),
    'asteroid': (139, 119, 101),
    'station': (50, 200, 50),
    'ship': (200, 200, 50),
    'orbit': (40, 40, 60),
    'ui_bg': (20, 20, 40),
    'ui_border': (60, 60, 100),
    'ui_text': (200, 200, 220),
    'ui_highlight': (100, 150, 255),
    'player': (50, 150, 255),
    'enemy': (255, 100, 100),
    'neutral': (150, 150, 150),
}

# Resource tiers
RESOURCE_TIERS = {
    0: ['water_ice', 'iron_ore', 'silicates', 'rare_earths', 'helium3'],
    1: ['refined_metal', 'silicon', 'water', 'fuel'],
    2: ['electronics', 'machinery', 'life_support'],
    3: ['habitat_modules', 'ship_components', 'advanced_tech'],
}


@dataclass
class GameConfig:
    """Runtime game configuration."""
    screen_width: int = SCREEN_WIDTH
    screen_height: int = SCREEN_HEIGHT
    fps: int = FPS
    simulation_speed: float = SIMULATION_SPEED
    fullscreen: bool = False
    sound_enabled: bool = True
    music_volume: float = 0.7
    sfx_volume: float = 0.8
