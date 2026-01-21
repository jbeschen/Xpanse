"""Save and load game state."""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from ..core.world import World

# Default save directory
SAVE_DIR = Path.home() / ".xpanse" / "saves"


def ensure_save_dir() -> Path:
    """Ensure save directory exists."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    return SAVE_DIR


def get_save_files() -> list[Path]:
    """Get list of available save files."""
    ensure_save_dir()
    return sorted(SAVE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def save_game(world: "World", save_name: str = "") -> tuple[bool, str]:
    """Save the current game state to a file.

    Args:
        world: The game world to save
        save_name: Optional name for the save file

    Returns:
        (success, message) tuple
    """
    try:
        ensure_save_dir()

        # Generate save name if not provided
        if not save_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_name = f"save_{timestamp}"

        # Add .json extension if not present
        if not save_name.endswith(".json"):
            save_name += ".json"

        save_path = SAVE_DIR / save_name

        # Serialize world state
        save_data = serialize_world(world)

        # Write to file
        with open(save_path, "w") as f:
            json.dump(save_data, f, indent=2)

        return True, f"Game saved to {save_name}"

    except Exception as e:
        return False, f"Failed to save: {str(e)}"


def load_game(world: "World", save_path: Path | str) -> tuple[bool, str]:
    """Load a game state from a file.

    Args:
        world: The world to load into
        save_path: Path to the save file

    Returns:
        (success, message) tuple
    """
    try:
        save_path = Path(save_path)
        if not save_path.exists():
            return False, f"Save file not found: {save_path}"

        # Read save file
        with open(save_path, "r") as f:
            save_data = json.load(f)

        # Deserialize into world
        deserialize_world(world, save_data)

        return True, f"Game loaded from {save_path.name}"

    except Exception as e:
        return False, f"Failed to load: {str(e)}"


def serialize_world(world: "World") -> dict[str, Any]:
    """Serialize world state to a dictionary."""
    from ..entities.celestial import CelestialBody
    from ..entities.stations import Station
    from ..entities.ships import Ship
    from ..entities.factions import Faction
    from ..solar_system.orbits import Position, Velocity, Orbit
    from ..simulation.resources import Inventory
    from ..simulation.economy import Market
    from ..simulation.production import Producer, Extractor, ResourceDeposit
    from ..ai.ship_ai import ShipAI

    em = world.entity_manager

    data = {
        "version": 1,
        "timestamp": datetime.now().isoformat(),
        "game_time": {
            "total_days": world.game_time.total_days,
            "day": world.game_time.day,
            "year": world.game_time.year,
        },
        "paused": world.paused,
        "speed": world.speed,
        "entities": [],
    }

    # Serialize each entity
    for entity in em._entities.values():
        entity_data = {
            "id": str(entity.id),
            "name": entity.name,
            "tags": list(entity.tags),
            "components": {},
        }

        # Serialize components - need to gather components for this entity
        components = {}
        for comp_type in em._entity_components.get(entity.id, set()):
            if comp_type in em._components and entity.id in em._components[comp_type]:
                components[comp_type] = em._components[comp_type][entity.id]

        for comp_type, comp in components.items():
            comp_name = comp_type.__name__

            if comp_name == "Position":
                entity_data["components"]["Position"] = {
                    "x": comp.x,
                    "y": comp.y,
                }

            elif comp_name == "Velocity":
                entity_data["components"]["Velocity"] = {
                    "vx": comp.vx,
                    "vy": comp.vy,
                }

            elif comp_name == "Orbit":
                entity_data["components"]["Orbit"] = {
                    "semi_major_axis": comp.semi_major_axis,
                    "eccentricity": comp.eccentricity,
                    "period": comp.period,
                    "angle": comp.angle,
                    "parent_name": comp.parent_name,
                }

            elif comp_name == "CelestialBody":
                entity_data["components"]["CelestialBody"] = {
                    "body_type": comp.body_type.value,
                    "mass": comp.mass,
                    "radius": comp.radius,
                    "color": list(comp.color),
                }

            elif comp_name == "Station":
                entity_data["components"]["Station"] = {
                    "station_type": comp.station_type.value,
                    "owner_faction_id": str(comp.owner_faction_id) if comp.owner_faction_id else None,
                    "population": comp.population,
                    "production_multiplier": comp.production_multiplier,
                    "storage_capacity": comp.storage_capacity,
                    "parent_body": comp.parent_body,
                }

            elif comp_name == "Ship":
                entity_data["components"]["Ship"] = {
                    "ship_type": comp.ship_type.value,
                    "owner_faction_id": str(comp.owner_faction_id) if comp.owner_faction_id else None,
                    "speed": comp.speed,
                    "cargo_capacity": comp.cargo_capacity,
                    "fuel": comp.fuel,
                    "fuel_capacity": comp.fuel_capacity,
                    "crew": comp.crew,
                    "max_crew": comp.max_crew,
                }

            elif comp_name == "Faction":
                entity_data["components"]["Faction"] = {
                    "faction_type": comp.faction_type.value,
                    "credits": comp.credits,
                    "color": list(comp.color),
                    "is_player": comp.is_player,
                }

            elif comp_name == "Inventory":
                entity_data["components"]["Inventory"] = {
                    "resources": {r.value: a for r, a in comp.resources.items()},
                    "capacity": comp.capacity,
                }

            elif comp_name == "Market":
                entity_data["components"]["Market"] = {
                    "prices": {r.value: p for r, p in comp.prices.items()},
                    "demand": {r.value: d for r, d in comp.demand.items()},
                    "supply": {r.value: s for r, s in comp.supply.items()},
                    "credits": comp.credits,
                }

            elif comp_name == "Producer":
                entity_data["components"]["Producer"] = {
                    "available_recipes": list(comp.available_recipes),
                    "active_recipe": comp.active_recipe,
                    "progress": comp.progress,
                    "is_active": comp.is_active,
                }

            elif comp_name == "Extractor":
                entity_data["components"]["Extractor"] = {
                    "resource_type": comp.resource_type.value if comp.resource_type else None,
                    "extraction_rate": comp.extraction_rate,
                    "is_active": comp.is_active,
                }

            elif comp_name == "ResourceDeposit":
                entity_data["components"]["ResourceDeposit"] = {
                    "resource_type": comp.resource_type.value,
                    "amount": comp.amount,
                    "max_amount": comp.max_amount,
                    "richness": comp.richness,
                    "extraction_difficulty": comp.extraction_difficulty,
                }

            elif comp_name == "ShipAI":
                entity_data["components"]["ShipAI"] = {
                    "state": comp.state.value,
                    "target_entity_id": str(comp.target_entity_id) if comp.target_entity_id else None,
                    "target_position": list(comp.target_position) if comp.target_position else None,
                    "cargo_resource": comp.cargo_resource.value if comp.cargo_resource else None,
                    "is_trader": comp.is_trader,
                    "idle_time": comp.idle_time,
                }

        data["entities"].append(entity_data)

    return data


def deserialize_world(world: "World", data: dict[str, Any]) -> None:
    """Deserialize world state from a dictionary."""
    from ..entities.celestial import CelestialBody, BodyType
    from ..entities.stations import Station, StationType
    from ..entities.ships import Ship, ShipType
    from ..entities.factions import Faction, FactionType
    from ..solar_system.orbits import Position, Velocity, Orbit
    from ..simulation.resources import Inventory, ResourceType
    from ..simulation.economy import Market
    from ..simulation.production import Producer, Extractor, ResourceDeposit
    from ..ai.ship_ai import ShipAI, ShipState

    em = world.entity_manager

    # Clear existing entities
    em.clear()

    # Restore game time
    gt = data.get("game_time", {})
    world.game_time.total_days = gt.get("total_days", 0)
    world.game_time.day = gt.get("day", 1)
    world.game_time.year = gt.get("year", 2150)

    world.paused = data.get("paused", False)
    world.speed = data.get("speed", 1.0)

    # Create entities
    for entity_data in data.get("entities", []):
        entity_id = UUID(entity_data["id"])
        entity = em.create_entity(
            name=entity_data.get("name", ""),
            entity_id=entity_id
        )

        # Restore tags
        for tag in entity_data.get("tags", []):
            entity.add_tag(tag)

        # Restore components
        components = entity_data.get("components", {})

        if "Position" in components:
            c = components["Position"]
            em.add_component(entity, Position(x=c["x"], y=c["y"]))

        if "Velocity" in components:
            c = components["Velocity"]
            em.add_component(entity, Velocity(vx=c["vx"], vy=c["vy"]))

        if "Orbit" in components:
            c = components["Orbit"]
            em.add_component(entity, Orbit(
                semi_major_axis=c["semi_major_axis"],
                eccentricity=c["eccentricity"],
                period=c["period"],
                angle=c["angle"],
                parent_name=c["parent_name"],
            ))

        if "CelestialBody" in components:
            c = components["CelestialBody"]
            em.add_component(entity, CelestialBody(
                body_type=BodyType(c["body_type"]),
                mass=c["mass"],
                radius=c["radius"],
                color=tuple(c["color"]),
            ))

        if "Station" in components:
            c = components["Station"]
            em.add_component(entity, Station(
                station_type=StationType(c["station_type"]),
                owner_faction_id=UUID(c["owner_faction_id"]) if c["owner_faction_id"] else None,
                population=c["population"],
                production_multiplier=c["production_multiplier"],
                storage_capacity=c["storage_capacity"],
                parent_body=c.get("parent_body", ""),
            ))

        if "Ship" in components:
            c = components["Ship"]
            em.add_component(entity, Ship(
                ship_type=ShipType(c["ship_type"]),
                owner_faction_id=UUID(c["owner_faction_id"]) if c["owner_faction_id"] else None,
                speed=c["speed"],
                cargo_capacity=c["cargo_capacity"],
                fuel=c["fuel"],
                fuel_capacity=c["fuel_capacity"],
                crew=c["crew"],
                max_crew=c["max_crew"],
            ))

        if "Faction" in components:
            c = components["Faction"]
            em.add_component(entity, Faction(
                faction_type=FactionType(c["faction_type"]),
                credits=c["credits"],
                color=tuple(c["color"]),
                is_player=c.get("is_player", False),
            ))

        if "Inventory" in components:
            c = components["Inventory"]
            inv = Inventory(capacity=c["capacity"])
            for res_name, amount in c.get("resources", {}).items():
                inv.resources[ResourceType(res_name)] = amount
            em.add_component(entity, inv)

        if "Market" in components:
            c = components["Market"]
            market = Market(credits=c["credits"])
            for res_name, price in c.get("prices", {}).items():
                market.prices[ResourceType(res_name)] = price
            for res_name, demand in c.get("demand", {}).items():
                market.demand[ResourceType(res_name)] = demand
            for res_name, supply in c.get("supply", {}).items():
                market.supply[ResourceType(res_name)] = supply
            em.add_component(entity, market)

        if "Producer" in components:
            c = components["Producer"]
            em.add_component(entity, Producer(
                available_recipes=set(c["available_recipes"]),
                active_recipe=c["active_recipe"],
                progress=c["progress"],
                is_active=c["is_active"],
            ))

        if "Extractor" in components:
            c = components["Extractor"]
            em.add_component(entity, Extractor(
                resource_type=ResourceType(c["resource_type"]) if c["resource_type"] else None,
                extraction_rate=c["extraction_rate"],
                is_active=c["is_active"],
            ))

        if "ResourceDeposit" in components:
            c = components["ResourceDeposit"]
            em.add_component(entity, ResourceDeposit(
                resource_type=ResourceType(c["resource_type"]),
                amount=c["amount"],
                max_amount=c["max_amount"],
                richness=c["richness"],
                extraction_difficulty=c["extraction_difficulty"],
            ))

        if "ShipAI" in components:
            c = components["ShipAI"]
            ship_ai = ShipAI.__new__(ShipAI)
            ship_ai.state = ShipState(c["state"])
            ship_ai.target_entity_id = UUID(c["target_entity_id"]) if c["target_entity_id"] else None
            ship_ai.target_position = tuple(c["target_position"]) if c["target_position"] else None
            ship_ai.cargo_resource = ResourceType(c["cargo_resource"]) if c["cargo_resource"] else None
            ship_ai.is_trader = c["is_trader"]
            ship_ai.idle_time = c["idle_time"]
            em.add_component(entity, ship_ai)
