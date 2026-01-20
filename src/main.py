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

    # Add systems (order matters - priority determines update order)
    world.add_system(OrbitalSystem())
    world.add_system(NavigationSystem())
    world.add_system(MovementSystem())
    world.add_system(ExtractionSystem(event_bus))
    world.add_system(ProductionSystem(event_bus))
    world.add_system(ShipAI(event_bus))
    world.add_system(TradeSystem(event_bus))
    world.add_system(EconomySystem(event_bus))
    world.add_system(FactionAI(event_bus))

    # Create initial world state
    create_initial_world(world)

    # Set up rendering
    camera = Camera()
    camera.fit_bounds(-2, -2, 2, 2)  # Start zoomed to show inner solar system

    renderer = Renderer(screen, camera)
    input_handler = InputHandler(camera)

    # Register input callbacks
    def on_select(world_x: float, world_y: float) -> None:
        renderer.select_at(world_x, world_y, world)

    def on_deselect() -> None:
        renderer.deselect()

    def on_pause() -> None:
        world.toggle_pause()

    def on_speed_up() -> None:
        world.speed = min(10.0, world.speed * 2)

    def on_speed_down() -> None:
        world.speed = max(0.1, world.speed / 2)

    def on_toggle_ui() -> None:
        renderer.toggle_ui()

    input_handler.register_callback(InputAction.SELECT, on_select)
    input_handler.register_callback(InputAction.DESELECT, on_deselect)
    input_handler.register_callback(InputAction.PAUSE, on_pause)
    input_handler.register_callback(InputAction.SPEED_UP, on_speed_up)
    input_handler.register_callback(InputAction.SPEED_DOWN, on_speed_down)
    input_handler.register_callback(InputAction.TOGGLE_UI, on_toggle_ui)

    # Main game loop
    running = True
    while running:
        # Handle input
        events = pygame.event.get()
        running = input_handler.process_events(events)

        # Handle quit action
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                running = False

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
