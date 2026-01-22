"""Orbital slot system for station placement around celestial bodies."""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component
from .stations import StationType

if TYPE_CHECKING:
    pass


# Maximum stations per celestial body
MAX_STATIONS_PER_BODY = 12

# Orbital rings (distance from body center in AU)
ORBITAL_RINGS = [0.03, 0.05, 0.07]

# Clock positions (in radians, 12 o'clock = pi/2, clockwise)
CLOCK_POSITIONS = {
    12: math.pi / 2,      # 12 o'clock (top)
    3: 0,                  # 3 o'clock (right)
    6: -math.pi / 2,       # 6 o'clock (bottom)
    9: math.pi,            # 9 o'clock (left)
}

# All 12 slots: 4 positions x 3 rings
# Slot index maps to (ring_index, clock_position)
SLOT_LAYOUT = [
    # Ring 0 (inner) - slots 0-3
    (0, 12), (0, 3), (0, 6), (0, 9),
    # Ring 1 (middle) - slots 4-7
    (1, 12), (1, 3), (1, 6), (1, 9),
    # Ring 2 (outer) - slots 8-11
    (2, 12), (2, 3), (2, 6), (2, 9),
]


@dataclass
class OrbitalSlotManager(Component):
    """Singleton component tracking which orbital slots are occupied.

    Each celestial body can have up to 12 stations in fixed orbital slots.
    """
    # Maps body_name -> list of slot indices that are occupied (0-11)
    occupied_slots: dict[str, list[int]] = field(default_factory=dict)
    # Maps body_name -> {slot_index: station_entity_id}
    slot_assignments: dict[str, dict[int, UUID]] = field(default_factory=dict)

    def get_next_available_slot(self, body_name: str) -> int | None:
        """Get the next available slot index for a body.

        Returns:
            Slot index (0-11) or None if full
        """
        occupied = self.occupied_slots.get(body_name, [])
        for slot in range(MAX_STATIONS_PER_BODY):
            if slot not in occupied:
                return slot
        return None

    def occupy_slot(self, body_name: str, slot_index: int, station_id: UUID) -> None:
        """Mark a slot as occupied."""
        if body_name not in self.occupied_slots:
            self.occupied_slots[body_name] = []
            self.slot_assignments[body_name] = {}

        if slot_index not in self.occupied_slots[body_name]:
            self.occupied_slots[body_name].append(slot_index)
        self.slot_assignments[body_name][slot_index] = station_id

    def release_slot(self, body_name: str, station_id: UUID) -> None:
        """Release a slot when a station is destroyed."""
        if body_name not in self.slot_assignments:
            return

        for slot, sid in list(self.slot_assignments[body_name].items()):
            if sid == station_id:
                self.slot_assignments[body_name].pop(slot)
                if slot in self.occupied_slots[body_name]:
                    self.occupied_slots[body_name].remove(slot)
                break

    def get_slot_count(self, body_name: str) -> int:
        """Get number of occupied slots for a body."""
        return len(self.occupied_slots.get(body_name, []))

    def is_full(self, body_name: str) -> bool:
        """Check if a body has reached max stations."""
        return self.get_slot_count(body_name) >= MAX_STATIONS_PER_BODY


def get_slot_offset(slot_index: int) -> tuple[float, float]:
    """Get the (x, y) offset for a given slot index.

    Args:
        slot_index: Slot index (0-11)

    Returns:
        (offset_x, offset_y) in AU from body center
    """
    if slot_index < 0 or slot_index >= MAX_STATIONS_PER_BODY:
        slot_index = 0

    ring_index, clock_pos = SLOT_LAYOUT[slot_index]
    radius = ORBITAL_RINGS[ring_index]
    angle = CLOCK_POSITIONS[clock_pos]

    offset_x = radius * math.cos(angle)
    offset_y = radius * math.sin(angle)

    return (offset_x, offset_y)


# SciFi Name Generation System

# Station type prefixes
TYPE_PREFIXES = {
    StationType.OUTPOST: ["OP", "OUT", "POST"],
    StationType.MINING_STATION: ["MN", "MIN", "MINE", "EXT"],
    StationType.REFINERY: ["REF", "RF", "PROC"],
    StationType.FACTORY: ["FAC", "MFG", "IND"],
    StationType.COLONY: ["COL", "HAB", "DOME"],
    StationType.SHIPYARD: ["SY", "YARD", "DOCK"],
    StationType.TRADE_HUB: ["TH", "HUB", "PORT"],
}

# Resource-related name parts
RESOURCE_NAMES = {
    "water_ice": ["Aqua", "Frost", "Ice", "Hydro", "Cryo"],
    "iron_ore": ["Iron", "Ferrum", "Steel", "Metal", "Ore"],
    "silicates": ["Silica", "Crystal", "Quartz", "Glass", "Sand"],
    "rare_earths": ["Rare", "Noble", "Precious", "Element", "Terra"],
    "helium3": ["Helios", "Fusion", "Sol", "Plasma", "Nova"],
    "refined_metal": ["Forge", "Alloy", "Foundry", "Smelt"],
    "silicon": ["Chip", "Circuit", "Logic", "Cyber"],
    "water": ["Aqua", "Clear", "Pure", "Life"],
    "fuel": ["Propel", "Thrust", "Burn", "Ignite"],
    "electronics": ["Volt", "Spark", "Electron", "Tech"],
    "machinery": ["Gear", "Mech", "Auto", "Drive"],
    "life_support": ["Bio", "Vital", "Life", "Sustain"],
}

# Greek letters for station designations
GREEK_LETTERS = [
    "Alpha", "Beta", "Gamma", "Delta", "Epsilon",
    "Zeta", "Eta", "Theta", "Iota", "Kappa",
    "Lambda", "Mu", "Nu", "Xi", "Omicron",
    "Pi", "Rho", "Sigma", "Tau", "Upsilon",
]

# Sci-fi suffixes
SCIFI_SUFFIXES = [
    "Prime", "Station", "Base", "Point", "Hub",
    "Core", "Node", "Array", "Complex", "Nexus",
]

# Phonetic alphabet for codes
PHONETIC = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]


def generate_station_name(
    station_type: StationType,
    body_name: str,
    resource_type: str | None = None,
    slot_index: int = 0,
) -> str:
    """Generate a unique sci-fi station name.

    Args:
        station_type: Type of station
        body_name: Name of parent celestial body
        resource_type: Optional resource being processed/mined
        slot_index: Orbital slot for uniqueness

    Returns:
        Generated station name
    """
    # Use a mix of naming styles for variety
    style = random.choice(["code", "descriptive", "greek", "combined"])

    if style == "code":
        # Technical code style: "REF-A32" or "MN-MARS-07"
        prefix = random.choice(TYPE_PREFIXES.get(station_type, ["ST"]))
        body_code = body_name[:4].upper()
        num = f"{slot_index + 1:02d}"
        return f"{prefix}-{body_code}-{num}"

    elif style == "descriptive":
        # Descriptive style: "Iron Forge Alpha" or "Hydro Processing"
        if resource_type and resource_type in RESOURCE_NAMES:
            resource_part = random.choice(RESOURCE_NAMES[resource_type])
        else:
            resource_part = body_name

        if station_type == StationType.MINING_STATION:
            suffix = random.choice(["Mine", "Extraction", "Pit", "Works"])
        elif station_type == StationType.REFINERY:
            suffix = random.choice(["Refinery", "Processing", "Works", "Plant"])
        elif station_type == StationType.FACTORY:
            suffix = random.choice(["Factory", "Works", "Industrial", "Manufacturing"])
        elif station_type == StationType.COLONY:
            suffix = random.choice(["Colony", "Habitat", "Dome", "Settlement"])
        elif station_type == StationType.SHIPYARD:
            suffix = random.choice(["Shipyard", "Docks", "Yards", "Berth"])
        elif station_type == StationType.TRADE_HUB:
            suffix = random.choice(["Hub", "Port", "Exchange", "Terminal"])
        else:
            suffix = random.choice(["Station", "Outpost", "Base", "Post"])

        return f"{resource_part} {suffix}"

    elif style == "greek":
        # Greek letter style: "Mars Alpha" or "Ceres Gamma Mining"
        letter = GREEK_LETTERS[slot_index % len(GREEK_LETTERS)]
        type_word = station_type.value.replace("_", " ").title()
        return f"{body_name} {letter}"

    else:  # combined
        # Combined style: "Ferrum-7 Refinery" or "Cryo Station Delta"
        prefix = random.choice(TYPE_PREFIXES.get(station_type, ["ST"]))
        num = slot_index + 1
        letter = GREEK_LETTERS[slot_index % len(GREEK_LETTERS)]

        if resource_type and resource_type in RESOURCE_NAMES:
            resource_part = random.choice(RESOURCE_NAMES[resource_type])
            return f"{resource_part}-{num} {letter}"
        else:
            return f"{prefix}-{num} {body_name}"


def generate_unique_station_name(
    station_type: StationType,
    body_name: str,
    existing_names: set[str],
    resource_type: str | None = None,
    slot_index: int = 0,
) -> str:
    """Generate a unique station name that doesn't conflict with existing ones.

    Args:
        station_type: Type of station
        body_name: Name of parent celestial body
        existing_names: Set of existing station names to avoid
        resource_type: Optional resource being processed/mined
        slot_index: Orbital slot for uniqueness

    Returns:
        Unique generated station name
    """
    # Try up to 10 times to generate a unique name
    for attempt in range(10):
        name = generate_station_name(station_type, body_name, resource_type, slot_index + attempt)
        if name not in existing_names:
            return name

    # Fallback: use guaranteed unique format
    return f"{station_type.value.upper()}-{body_name[:3].upper()}-{slot_index:02d}-{random.randint(100, 999)}"
