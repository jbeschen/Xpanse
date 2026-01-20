"""Faction entities and ownership."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, Entity
from ..core.world import World

if TYPE_CHECKING:
    pass


class FactionType(Enum):
    """Types of factions."""
    PLAYER = "player"
    CORPORATION = "corporation"
    GOVERNMENT = "government"
    INDEPENDENT = "independent"


@dataclass
class Faction(Component):
    """Component representing a faction."""
    faction_type: FactionType = FactionType.CORPORATION
    color: tuple[int, int, int] = (150, 150, 150)
    credits: float = 100000.0
    reputation: dict[UUID, float] = field(default_factory=dict)  # Reputation with other factions
    home_station_id: UUID | None = None

    def get_reputation(self, other_faction_id: UUID) -> float:
        """Get reputation with another faction. Default is neutral (0.5)."""
        return self.reputation.get(other_faction_id, 0.5)

    def modify_reputation(self, other_faction_id: UUID, delta: float) -> None:
        """Modify reputation with another faction."""
        current = self.get_reputation(other_faction_id)
        new_rep = max(0.0, min(1.0, current + delta))
        self.reputation[other_faction_id] = new_rep


@dataclass
class Owned(Component):
    """Component indicating entity ownership."""
    faction_id: UUID
    acquired_time: float = 0.0  # Game time when acquired


# Predefined factions
PREDEFINED_FACTIONS: dict[str, dict] = {
    "Earth Coalition": {
        "type": FactionType.GOVERNMENT,
        "color": (50, 150, 255),
        "credits": 1000000,
        "description": "United Earth government, controls Earth and Luna.",
    },
    "Mars Republic": {
        "type": FactionType.GOVERNMENT,
        "color": (200, 100, 50),
        "credits": 500000,
        "description": "Independent Martian government.",
    },
    "Belt Alliance": {
        "type": FactionType.INDEPENDENT,
        "color": (150, 150, 100),
        "credits": 300000,
        "description": "Loose confederation of asteroid belt miners.",
    },
    "Outer Planets Consortium": {
        "type": FactionType.CORPORATION,
        "color": (100, 200, 150),
        "credits": 750000,
        "description": "Corporate alliance controlling outer system resources.",
    },
    "TransSolar Mining": {
        "type": FactionType.CORPORATION,
        "color": (200, 200, 50),
        "credits": 400000,
        "description": "Major mining corporation with operations throughout the system.",
    },
    "Titan Industries": {
        "type": FactionType.CORPORATION,
        "color": (255, 180, 100),
        "credits": 350000,
        "description": "Manufacturing giant based on Titan.",
    },
}


def create_faction(
    world: World,
    name: str,
    faction_type: FactionType = FactionType.CORPORATION,
    color: tuple[int, int, int] = (150, 150, 150),
    credits: float = 100000.0,
    is_player: bool = False,
) -> Entity:
    """Create a faction entity.

    Args:
        world: The game world
        name: Faction name
        faction_type: Type of faction
        color: Display color
        credits: Starting credits
        is_player: Whether this is the player faction

    Returns:
        The created entity
    """
    tags = {"faction", faction_type.value}
    if is_player:
        tags.add("player")

    entity = world.create_entity(name=name, tags=tags)
    em = world.entity_manager

    em.add_component(entity, Faction(
        faction_type=faction_type,
        color=color,
        credits=credits,
    ))

    return entity


def create_predefined_factions(world: World) -> dict[str, Entity]:
    """Create all predefined factions.

    Args:
        world: The game world

    Returns:
        Dictionary mapping faction names to entities
    """
    factions: dict[str, Entity] = {}

    for name, config in PREDEFINED_FACTIONS.items():
        factions[name] = create_faction(
            world=world,
            name=name,
            faction_type=config["type"],
            color=config["color"],
            credits=config["credits"],
        )

    return factions


def get_faction_by_name(world: World, name: str) -> Entity | None:
    """Get a faction by its name.

    Args:
        world: The game world
        name: Faction name

    Returns:
        Faction entity or None
    """
    return world.entity_manager.get_entity_by_name(name)


def transfer_ownership(
    world: World,
    entity: Entity,
    new_owner_id: UUID | None,
) -> None:
    """Transfer ownership of an entity to a new faction.

    Args:
        world: The game world
        entity: Entity to transfer
        new_owner_id: New owner faction ID (None for unowned)
    """
    em = world.entity_manager
    owned = em.get_component(entity, Owned)

    if new_owner_id is None:
        # Remove ownership
        if owned:
            em.remove_component(entity, Owned)
        entity.tags.discard("owned")
    else:
        # Add or update ownership
        if owned:
            owned.faction_id = new_owner_id
            owned.acquired_time = world.game_time.total_seconds
        else:
            em.add_component(entity, Owned(
                faction_id=new_owner_id,
                acquired_time=world.game_time.total_seconds,
            ))
        entity.tags.add("owned")
