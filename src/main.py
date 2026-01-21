"""Entry point and game loop."""
from __future__ import annotations
import pygame
import sys

from .config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, COLORS
from .core.world import World
from .core.events import EventBus
from .solar_system.orbits import OrbitalSystem, MovementSystem, NavigationSystem
from .simulation.production import ProductionSystem, ExtractionSystem
from .simulation.economy import EconomySystem
from .simulation.trade import TradeSystem
from .ai.faction_ai import FactionAI
from .ai.ship_ai import ShipAI
from .ui.camera import Camera
from .ui.renderer import Renderer
from .ui.input import InputHandler, InputAction
from .systems.building import BuildingSystem


def create_initial_world(world: World) -> None:
    """Set up the initial game world with celestial bodies, stations, and ships."""
    from .entities.celestial import create_solar_system
    from .entities.factions import create_predefined_factions, Faction
    from .entities.stations import create_station, create_mining_station, StationType
    from .entities.ships import create_ship, ShipType
    from .simulation.resources import ResourceType

    # Create solar system
    bodies = create_solar_system(world)

    # Create factions
    factions = create_predefined_factions(world)

    # Get faction IDs
    earth_coalition = factions.get("Earth Coalition")
    mars_republic = factions.get("Mars Republic")
    belt_alliance = factions.get("Belt Alliance")
    opc = factions.get("Outer Planets Consortium")

    ec_id = earth_coalition.id if earth_coalition else None
    mr_id = mars_republic.id if mars_republic else None
    ba_id = belt_alliance.id if belt_alliance else None
    opc_id = opc.id if opc else None

    # Create stations

    # Earth area
    create_station(
        world, "Earth Orbital Hub", StationType.TRADE_HUB,
        position=(1.0, 0.05), parent_body="Earth", owner_faction_id=ec_id,
        initial_resources={
            ResourceType.WATER: 500,
            ResourceType.FUEL: 300,
            ResourceType.ELECTRONICS: 100,
        }
    )

    create_station(
        world, "Luna Mining Complex", StationType.MINING_STATION,
        position=(1.0, 0.02), parent_body="Moon", owner_faction_id=ec_id,
    )

    # Mars area
    create_station(
        world, "Mars Colony Prime", StationType.COLONY,
        position=(1.52, 0.05), parent_body="Mars", owner_faction_id=mr_id,
        initial_resources={
            ResourceType.WATER: 200,
            ResourceType.LIFE_SUPPORT: 50,
        }
    )

    create_station(
        world, "Olympus Refinery", StationType.REFINERY,
        position=(1.55, -0.02), parent_body="Mars", owner_faction_id=mr_id,
        initial_resources={
            ResourceType.IRON_ORE: 500,
            ResourceType.WATER_ICE: 300,
        }
    )

    # Asteroid Belt
    create_mining_station(
        world, "Ceres Mining Outpost", position=(2.77, 0.1),
        parent_body="Ceres", resource_type=ResourceType.IRON_ORE,
        owner_faction_id=ba_id,
    )

    create_station(
        world, "Vesta Industrial", StationType.FACTORY,
        position=(2.36, -0.1), parent_body="Vesta", owner_faction_id=ba_id,
        initial_resources={
            ResourceType.REFINED_METAL: 200,
            ResourceType.SILICON: 100,
        }
    )

    # Outer System
    create_station(
        world, "Europa Research Station", StationType.OUTPOST,
        position=(5.2, 0.1), parent_body="Europa", owner_faction_id=opc_id,
        initial_resources={
            ResourceType.WATER_ICE: 1000,
        }
    )

    create_station(
        world, "Titan Fuel Depot", StationType.REFINERY,
        position=(9.5, 0.2), parent_body="Titan", owner_faction_id=opc_id,
        initial_resources={
            ResourceType.HELIUM3: 500,
            ResourceType.WATER_ICE: 300,
        }
    )

    # Create some trading ships
    create_ship(
        world, "Trader One", ShipType.FREIGHTER,
        position=(1.0, 0.1), owner_faction_id=ec_id,
    )

    create_ship(
        world, "Mars Express", ShipType.FREIGHTER,
        position=(1.52, 0.0), owner_faction_id=mr_id,
    )

    create_ship(
        world, "Belt Runner", ShipType.BULK_HAULER,
        position=(2.5, 0.0), owner_faction_id=ba_id,
    )

    create_ship(
        world, "Ice Hauler", ShipType.TANKER,
        position=(5.2, 0.15), owner_faction_id=opc_id,
    )


# Competitive corporation definitions
COMPETITIVE_CORPORATIONS = {
    "Stellar Dynamics": {
        "color": (100, 180, 255),  # Light blue
        "is_player": True,
    },
    "Nova Industries": {
        "color": (255, 100, 100),  # Red
        "is_player": False,
    },
    "Frontier Mining Corp": {
        "color": (100, 255, 100),  # Green
        "is_player": False,
    },
    "Orbital Logistics": {
        "color": (255, 200, 50),  # Gold
        "is_player": False,
    },
    "Deep Space Ventures": {
        "color": (200, 100, 255),  # Purple
        "is_player": False,
    },
}


def create_competitive_start(world: World) -> dict:
    """Set up competitive corporation race with equal starting resources.

    Returns:
        Dictionary with 'player_faction_id' and 'corporations' info
    """
    from .entities.celestial import create_solar_system
    from .entities.factions import create_faction, FactionType
    from .entities.ships import create_ship, ShipType

    # Create solar system
    bodies = create_solar_system(world)

    # Create corporations with equal resources
    corporations = {}
    player_faction_id = None

    # Starting resources for each corporation
    STARTING_CREDITS = 100000
    STARTING_SHIPS = 2

    # Ship starting positions - spread around Earth's orbit (1 AU)
    # Each corp gets a slightly different starting angle
    import math
    num_corps = len(COMPETITIVE_CORPORATIONS)

    for i, (name, config) in enumerate(COMPETITIVE_CORPORATIONS.items()):
        # Create faction
        faction = create_faction(
            world=world,
            name=name,
            faction_type=FactionType.PLAYER if config["is_player"] else FactionType.CORPORATION,
            color=config["color"],
            credits=STARTING_CREDITS,
            is_player=config["is_player"],
        )

        corporations[name] = {
            "entity": faction,
            "id": faction.id,
            "color": config["color"],
            "is_player": config["is_player"],
        }

        if config["is_player"]:
            player_faction_id = faction.id

        # Calculate starting position - spread around Earth orbit
        angle = (2 * math.pi * i) / num_corps
        base_x = 1.0 + 0.1 * math.cos(angle)
        base_y = 0.1 * math.sin(angle)

        # Create starting ships for this corporation
        for ship_num in range(STARTING_SHIPS):
            offset = 0.02 * ship_num
            ship_position = (base_x + offset, base_y + offset)

            create_ship(
                world=world,
                name=f"{name} Freighter {ship_num + 1}",
                ship_type=ShipType.FREIGHTER,
                position=ship_position,
                owner_faction_id=faction.id,
                is_trader=True,
            )

    return {
        "player_faction_id": player_faction_id,
        "corporations": corporations,
    }


def main() -> None:
    """Main entry point."""
    # Initialize Pygame
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    # Create game world
    world = World()
    event_bus = world.event_bus

    # Create systems
    building_system = BuildingSystem(event_bus)
    faction_ai = FactionAI(event_bus)

    # Add systems (order matters - priority determines update order)
    world.add_system(OrbitalSystem())
    world.add_system(NavigationSystem())
    world.add_system(MovementSystem())
    world.add_system(ExtractionSystem(event_bus))
    world.add_system(ProductionSystem(event_bus))
    world.add_system(ShipAI(event_bus))
    world.add_system(TradeSystem(event_bus))
    world.add_system(EconomySystem(event_bus))
    world.add_system(building_system)
    world.add_system(faction_ai)

    # Create competitive start (5 corporations racing)
    game_state = create_competitive_start(world)
    player_faction_id = game_state["player_faction_id"]

    # Connect building system to faction AI
    faction_ai.set_building_system(building_system, world)

    # Set up rendering
    camera = Camera()
    camera.fit_bounds(-2, -2, 2, 2)  # Start zoomed to show inner solar system

    renderer = Renderer(screen, camera)
    renderer.set_player_faction(player_faction_id, world)
    renderer.set_building_system(building_system)

    input_handler = InputHandler(camera)

    # Register input callbacks
    def on_select(world_x: float, world_y: float) -> None:
        # If in build mode, try to place a station
        if renderer.build_mode_active:
            renderer.try_place_station(world_x, world_y, world)
        else:
            renderer.select_at(world_x, world_y, world)

    def on_deselect() -> None:
        if renderer.build_mode_active:
            renderer.cancel_build_mode()
        else:
            renderer.deselect()

    def on_pause() -> None:
        world.toggle_pause()

    def on_speed_up() -> None:
        world.speed = min(10.0, world.speed * 2)

    def on_speed_down() -> None:
        world.speed = max(0.1, world.speed / 2)

    def on_toggle_ui() -> None:
        renderer.toggle_ui()

    def on_build_mode() -> None:
        renderer.toggle_build_menu()

    def on_confirm_build() -> None:
        # Place station at current mouse position in build mode
        if renderer.build_mode_active:
            wx, wy = camera.screen_to_world(
                input_handler.state.mouse_x,
                input_handler.state.mouse_y
            )
            renderer.try_place_station(wx, wy, world)

    input_handler.register_callback(InputAction.SELECT, on_select)
    input_handler.register_callback(InputAction.DESELECT, on_deselect)
    input_handler.register_callback(InputAction.PAUSE, on_pause)
    input_handler.register_callback(InputAction.SPEED_UP, on_speed_up)
    input_handler.register_callback(InputAction.SPEED_DOWN, on_speed_down)
    input_handler.register_callback(InputAction.TOGGLE_UI, on_toggle_ui)
    input_handler.register_callback(InputAction.BUILD_MODE, on_build_mode)
    input_handler.register_callback(InputAction.CONFIRM_BUILD, on_confirm_build)

    # Main game loop
    running = True
    while running:
        # Handle input
        events = pygame.event.get()
        running = input_handler.process_events(events)

        # Handle quit action and number keys for build menu
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    running = False
                # Number keys 1-7 for selecting station type in build menu
                elif renderer.build_menu_visible:
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                     pygame.K_5, pygame.K_6, pygame.K_7):
                        index = event.key - pygame.K_1
                        renderer.select_build_option(index)

        # Update mouse world position for renderer
        renderer.update_mouse_position(
            input_handler.state.mouse_world_x,
            input_handler.state.mouse_world_y
        )

        # Update simulation
        dt = clock.tick(FPS) / 1000.0  # Delta time in seconds
        world.update(dt)

        # Render
        fps = clock.get_fps()
        renderer.render(world, fps)

        # Flip display
        pygame.display.flip()

    # Cleanup
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
