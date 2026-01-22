"""Sector-based map system for planetary regions.

Each planet and major belt body is its own sector with a square grid layout.
The solar system map shows planets orbiting, while sector maps show the
detailed view of each planetary system.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
import math

if TYPE_CHECKING:
    pass


class ViewMode(Enum):
    """Current view mode for the game."""
    SOLAR_SYSTEM = "solar_system"  # Overview - shows all planets orbiting sun
    SECTOR = "sector"  # Zoomed into a specific planetary sector


# Grid settings for sector maps
GRID_SIZE = 60  # Pixels per grid cell
GRID_COLS = 15  # Number of columns in sector grid
GRID_ROWS = 11  # Number of rows in sector grid


@dataclass
class SectorBody:
    """A body within a sector (planet or moon)."""
    name: str
    is_primary: bool = False  # True for the main planet/body
    grid_x: int = 0  # Grid position (column)
    grid_y: int = 0  # Grid position (row)
    radius: float = 1.0  # Display radius multiplier
    color: tuple[int, int, int] = (150, 150, 150)
    max_stations: int = 12  # Station slots for this body


@dataclass
class Sector:
    """A planetary sector containing a body and its moons/features."""
    id: str  # Unique sector ID
    name: str  # Display name e.g., "Earth Sector"
    primary_body: str  # Name of the main planet/body
    bodies: list[SectorBody] = field(default_factory=list)
    description: str = ""

    # Grid settings (can be customized per sector)
    grid_cols: int = GRID_COLS
    grid_rows: int = GRID_ROWS

    # Position in solar system (AU from sun) - for entry/exit calculations
    orbital_radius: float = 1.0

    def get_body(self, name: str) -> SectorBody | None:
        """Get a body by name."""
        for body in self.bodies:
            if body.name == name:
                return body
        return None


def grid_to_pixel(
    grid_x: int,
    grid_y: int,
    center_x: float,
    center_y: float,
    zoom: float = 1.0
) -> tuple[float, float]:
    """Convert grid coordinates to pixel coordinates.

    Grid (0,0) is top-left, center of grid is at screen center.
    """
    # Calculate offset from grid center
    grid_center_x = GRID_COLS / 2
    grid_center_y = GRID_ROWS / 2

    offset_x = (grid_x - grid_center_x) * GRID_SIZE * zoom
    offset_y = (grid_y - grid_center_y) * GRID_SIZE * zoom

    return (center_x + offset_x, center_y + offset_y)


def pixel_to_grid(
    px: float,
    py: float,
    center_x: float,
    center_y: float,
    zoom: float = 1.0
) -> tuple[int, int]:
    """Convert pixel coordinates to grid coordinates."""
    grid_center_x = GRID_COLS / 2
    grid_center_y = GRID_ROWS / 2

    # Reverse the grid_to_pixel calculation
    offset_x = (px - center_x) / (GRID_SIZE * zoom)
    offset_y = (py - center_y) / (GRID_SIZE * zoom)

    grid_x = int(round(offset_x + grid_center_x))
    grid_y = int(round(offset_y + grid_center_y))

    return (grid_x, grid_y)


# Define all sectors - one per planet/major body
SECTORS: dict[str, Sector] = {
    # Inner planets
    "mercury": Sector(
        id="mercury",
        name="Mercury Sector",
        primary_body="Mercury",
        description="The closest planet to the Sun. Extreme temperatures.",
        orbital_radius=0.39,
        bodies=[
            SectorBody("Mercury", is_primary=True, grid_x=7, grid_y=5, radius=0.8,
                      color=(180, 180, 180), max_stations=6),
        ],
    ),

    "venus": Sector(
        id="venus",
        name="Venus Sector",
        primary_body="Venus",
        description="Earth's sister planet. Dense atmosphere and volcanic surface.",
        orbital_radius=0.72,
        bodies=[
            SectorBody("Venus", is_primary=True, grid_x=7, grid_y=5, radius=1.2,
                      color=(230, 200, 150), max_stations=8),
        ],
    ),

    "earth": Sector(
        id="earth",
        name="Earth Sector",
        primary_body="Earth",
        description="Humanity's homeworld. The center of human civilization.",
        orbital_radius=1.0,
        bodies=[
            SectorBody("Earth", is_primary=True, grid_x=7, grid_y=5, radius=1.5,
                      color=(100, 150, 255), max_stations=12),
            SectorBody("Moon", grid_x=10, grid_y=4, radius=0.6,
                      color=(200, 200, 200), max_stations=8),
        ],
    ),

    "mars": Sector(
        id="mars",
        name="Mars Sector",
        primary_body="Mars",
        description="The red planet. First major human colony beyond Earth.",
        orbital_radius=1.52,
        bodies=[
            SectorBody("Mars", is_primary=True, grid_x=7, grid_y=5, radius=1.0,
                      color=(200, 100, 80), max_stations=10),
            SectorBody("Phobos", grid_x=9, grid_y=4, radius=0.3,
                      color=(150, 140, 130), max_stations=4),
            SectorBody("Deimos", grid_x=10, grid_y=6, radius=0.2,
                      color=(140, 130, 120), max_stations=3),
        ],
    ),

    # Asteroid Belt bodies (each major body is its own sector)
    "ceres": Sector(
        id="ceres",
        name="Ceres Sector",
        primary_body="Ceres",
        description="The largest object in the asteroid belt. A dwarf planet.",
        orbital_radius=2.77,
        bodies=[
            SectorBody("Ceres", is_primary=True, grid_x=7, grid_y=5, radius=1.0,
                      color=(160, 140, 120), max_stations=8),
        ],
    ),

    "vesta": Sector(
        id="vesta",
        name="Vesta Sector",
        primary_body="Vesta",
        description="Second largest asteroid. Rich in minerals.",
        orbital_radius=2.36,
        bodies=[
            SectorBody("Vesta", is_primary=True, grid_x=7, grid_y=5, radius=0.8,
                      color=(180, 170, 160), max_stations=6),
        ],
    ),

    "pallas": Sector(
        id="pallas",
        name="Pallas Sector",
        primary_body="Pallas",
        description="Third largest asteroid. Highly inclined orbit.",
        orbital_radius=2.77,
        bodies=[
            SectorBody("Pallas", is_primary=True, grid_x=7, grid_y=5, radius=0.7,
                      color=(170, 160, 150), max_stations=6),
        ],
    ),

    "hygiea": Sector(
        id="hygiea",
        name="Hygiea Sector",
        primary_body="Hygiea",
        description="Fourth largest asteroid. Dark carbonaceous surface.",
        orbital_radius=3.14,
        bodies=[
            SectorBody("Hygiea", is_primary=True, grid_x=7, grid_y=5, radius=0.6,
                      color=(150, 140, 130), max_stations=4),
        ],
    ),

    # Outer planets
    "jupiter": Sector(
        id="jupiter",
        name="Jupiter Sector",
        primary_body="Jupiter",
        description="The gas giant. Four major Galilean moons.",
        orbital_radius=5.2,
        bodies=[
            SectorBody("Jupiter", is_primary=True, grid_x=7, grid_y=5, radius=2.5,
                      color=(200, 180, 150), max_stations=0),  # Gas giant
            SectorBody("Io", grid_x=3, grid_y=5, radius=0.6,
                      color=(230, 200, 100), max_stations=8),
            SectorBody("Europa", grid_x=5, grid_y=3, radius=0.6,
                      color=(200, 220, 255), max_stations=10),
            SectorBody("Ganymede", grid_x=11, grid_y=4, radius=0.8,
                      color=(180, 170, 160), max_stations=12),
            SectorBody("Callisto", grid_x=12, grid_y=7, radius=0.7,
                      color=(140, 130, 120), max_stations=10),
        ],
    ),

    "saturn": Sector(
        id="saturn",
        name="Saturn Sector",
        primary_body="Saturn",
        description="The ringed giant. Major moons including Titan.",
        orbital_radius=9.5,
        bodies=[
            SectorBody("Saturn", is_primary=True, grid_x=7, grid_y=5, radius=2.2,
                      color=(220, 200, 170), max_stations=0),  # Gas giant
            SectorBody("Titan", grid_x=3, grid_y=4, radius=0.9,
                      color=(230, 180, 100), max_stations=12),
            SectorBody("Enceladus", grid_x=10, grid_y=3, radius=0.5,
                      color=(240, 250, 255), max_stations=8),
            SectorBody("Rhea", grid_x=11, grid_y=6, radius=0.6,
                      color=(200, 200, 200), max_stations=6),
            SectorBody("Iapetus", grid_x=4, grid_y=7, radius=0.6,
                      color=(180, 180, 180), max_stations=6),
        ],
    ),

    "uranus": Sector(
        id="uranus",
        name="Uranus Sector",
        primary_body="Uranus",
        description="The ice giant. Tilted on its side.",
        orbital_radius=19.2,
        bodies=[
            SectorBody("Uranus", is_primary=True, grid_x=7, grid_y=5, radius=1.8,
                      color=(180, 220, 230), max_stations=0),  # Ice giant
            SectorBody("Miranda", grid_x=5, grid_y=3, radius=0.4,
                      color=(200, 200, 200), max_stations=4),
            SectorBody("Ariel", grid_x=9, grid_y=3, radius=0.5,
                      color=(210, 210, 210), max_stations=6),
            SectorBody("Titania", grid_x=11, grid_y=6, radius=0.6,
                      color=(190, 190, 190), max_stations=8),
            SectorBody("Oberon", grid_x=4, grid_y=7, radius=0.6,
                      color=(180, 180, 180), max_stations=8),
        ],
    ),

    "neptune": Sector(
        id="neptune",
        name="Neptune Sector",
        primary_body="Neptune",
        description="The distant ice giant. Home to Triton.",
        orbital_radius=30.1,
        bodies=[
            SectorBody("Neptune", is_primary=True, grid_x=7, grid_y=5, radius=1.7,
                      color=(100, 140, 255), max_stations=0),  # Ice giant
            SectorBody("Triton", grid_x=11, grid_y=5, radius=0.7,
                      color=(200, 220, 230), max_stations=10),
        ],
    ),
}

# Map body names to their sector ID
BODY_TO_SECTOR: dict[str, str] = {}
for sector_id, sector in SECTORS.items():
    for body in sector.bodies:
        BODY_TO_SECTOR[body.name] = sector_id


def get_sector_for_body(body_name: str) -> Sector | None:
    """Get the sector containing a body."""
    sector_id = BODY_TO_SECTOR.get(body_name)
    if sector_id:
        return SECTORS.get(sector_id)
    return None


def get_sector_id_for_body(body_name: str) -> str | None:
    """Get the sector ID containing a body."""
    return BODY_TO_SECTOR.get(body_name)


# Belt zone definition (AU range for asteroid belt)
BELT_INNER_RADIUS = 2.1  # AU
BELT_OUTER_RADIUS = 3.3  # AU

# List of belt sector IDs for special handling
BELT_SECTORS = ["ceres", "vesta", "pallas", "hygiea"]


def is_in_belt(orbital_radius: float) -> bool:
    """Check if an orbital radius is within the asteroid belt."""
    return BELT_INNER_RADIUS <= orbital_radius <= BELT_OUTER_RADIUS


def get_entry_position(
    from_sector_id: str | None,
    to_sector_id: str,
) -> tuple[int, int]:
    """Calculate grid entry position based on direction of travel.

    Returns grid coordinates for where ships should appear when entering.
    """
    to_sector = SECTORS.get(to_sector_id)
    if not to_sector:
        return (7, 5)  # Default center

    if not from_sector_id:
        return (7, 5)  # Coming from nowhere, enter center

    from_sector = SECTORS.get(from_sector_id)
    if not from_sector:
        return (7, 5)

    # Determine direction based on orbital radii
    if from_sector.orbital_radius < to_sector.orbital_radius:
        # Coming from inner system - enter from left
        return (0, 5)
    else:
        # Coming from outer system - enter from right
        return (14, 5)


def get_exit_position(
    from_sector_id: str,
    to_sector_id: str,
) -> tuple[int, int]:
    """Calculate grid exit position based on direction of travel.

    Returns grid coordinates for where ships should be when leaving.
    """
    from_sector = SECTORS.get(from_sector_id)
    to_sector = SECTORS.get(to_sector_id)

    if not from_sector or not to_sector:
        return (7, 5)

    # Determine direction based on orbital radii
    if to_sector.orbital_radius > from_sector.orbital_radius:
        # Going to outer system - exit from right
        return (14, 5)
    else:
        # Going to inner system - exit from left
        return (0, 5)
