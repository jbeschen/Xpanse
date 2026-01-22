"""Entry point and game loop."""
from __future__ import annotations
import pygame
import sys

from .config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, COLORS
from .core.world import World
from .core.events import EventBus
from .solar_system.orbits import OrbitalSystem, MovementSystem, NavigationSystem
from .simulation.production import ProductionSystem, ExtractionSystem
from .simulation.economy import EconomySystem, PopulationSystem
from .simulation.trade import TradeSystem
from .simulation.events import EventSystem, DiscoverySystem
from .ai.faction_ai import FactionAI
from .ai.ship_ai import ShipAI
from .ui.camera import Camera
from .ui.renderer import Renderer
from .ui.input import InputHandler, InputAction
from .systems.building import BuildingSystem
from .systems.save_load import save_game, load_game


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
    from .entities.stations import create_earth_market

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

    # Create Freelancers faction - independent traders
    freelancers = create_faction(
        world=world,
        name="Freelancers",
        faction_type=FactionType.INDEPENDENT,
        color=(180, 180, 180),
        credits=500000,
        is_player=False,
    )
    freelancer_id = freelancers.id

    # Create Earth market - the main consumer hub
    # Earth position is approximately (1, 0) AU
    earth_market = create_earth_market(
        world=world,
        position=(1.0, 0.0),
        owner_faction_id=None,  # Earth market is neutral/public
    )

    # Create Freelancer trading ships - they seek profitable trades
    freelancer_positions = [
        (1.05, 0.05),   # Near Earth
        (0.95, -0.05),  # Near Earth
        (1.55, 0.1),    # Near Mars orbit
        (1.45, -0.1),   # Near Mars orbit
        (2.5, 0.05),    # Belt region
        (2.8, -0.05),   # Belt region
    ]

    for i, pos in enumerate(freelancer_positions):
        create_ship(
            world=world,
            name=f"Freelancer {i + 1}",
            ship_type=ShipType.FREIGHTER,
            position=pos,
            owner_faction_id=freelancer_id,
            is_trader=True,
        )

    return {
        "player_faction_id": player_faction_id,
        "corporations": corporations,
        "freelancer_id": freelancer_id,
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
    world.add_system(PopulationSystem(event_bus))
    world.add_system(DiscoverySystem(event_bus))
    world.add_system(ShipAI(event_bus))
    world.add_system(TradeSystem(event_bus))
    world.add_system(EconomySystem(event_bus))
    world.add_system(EventSystem(event_bus))
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
        # If in waypoint mode, set waypoint
        if renderer.waypoint_mode:
            renderer.set_waypoint(world_x, world_y)
        # If in build mode, try to place a station
        elif renderer.build_mode_active:
            renderer.try_place_station(world_x, world_y, world)
        # If trade manager is in route creation mode, try to select station
        elif renderer.trade_manager_visible and renderer.trade_manager.creating_route:
            # Find station at click position
            from src.entities.stations import Station
            from src.solar_system.orbits import Position
            em = world.entity_manager
            for entity, station in em.get_all_components(Station):
                pos = em.get_component(entity, Position)
                if pos:
                    dist = ((pos.x - world_x)**2 + (pos.y - world_y)**2)**0.5
                    if dist < 0.1:
                        renderer.trade_manager_handle_station_click(entity.id, entity.name)
                        return
        else:
            renderer.select_at(world_x, world_y, world)

    def on_deselect() -> None:
        # Cancel various modes
        if renderer.waypoint_mode:
            renderer.cancel_waypoint_mode()
        elif renderer.build_mode_active:
            renderer.cancel_build_mode()
        elif renderer.trade_manager_visible:
            if renderer.trade_manager.creating_route or renderer.trade_manager.assigning_ship:
                renderer.trade_manager.cancel_creation()
            else:
                renderer.trade_manager_visible = False
                renderer.trade_manager.visible = False
        else:
            renderer.deselect()

    def on_pause() -> None:
        world.toggle_pause()

    def on_speed_up() -> None:
        # Speed steps: 1, 2, 5, 10, 20, 50, 100
        speeds = [1, 2, 5, 10, 20, 50, 100]
        current = world.speed
        for s in speeds:
            if s > current:
                world.speed = s
                break

    def on_speed_down() -> None:
        # Speed steps: 1, 2, 5, 10, 20, 50, 100
        speeds = [100, 50, 20, 10, 5, 2, 1]
        current = world.speed
        for s in speeds:
            if s < current:
                world.speed = s
                break

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
        # Or purchase selected ship if ship menu is open
        elif renderer.ship_menu_visible:
            renderer.purchase_selected_ship(world)
        # Or perform upgrade if upgrade menu is open
        elif renderer.upgrade_menu_visible:
            renderer.perform_upgrade(world)

    def on_ship_purchase() -> None:
        renderer.toggle_ship_menu()

    def on_toggle_routes() -> None:
        renderer.toggle_trade_routes()

    def on_upgrade_station() -> None:
        renderer.toggle_upgrade_menu()

    def on_quick_save() -> None:
        success, message = save_game(world, "quicksave")
        if success:
            renderer.add_notification(message, "success")
        else:
            renderer.add_notification(message, "error")

    def on_quick_load() -> None:
        from pathlib import Path
        from .systems.save_load import SAVE_DIR

        quicksave_path = SAVE_DIR / "quicksave.json"
        if quicksave_path.exists():
            success, message = load_game(world, quicksave_path)
            if success:
                renderer.add_notification(message, "success")
                # Find and update player faction
                from .entities.factions import Faction
                for entity, faction in world.entity_manager.get_all_components(Faction):
                    if faction.is_player:
                        nonlocal player_faction_id
                        player_faction_id = entity.id
                        renderer.set_player_faction(player_faction_id, world)
                        break
            else:
                renderer.add_notification(message, "error")
        else:
            renderer.add_notification("No quicksave found (press F5 to save)", "warning")

    input_handler.register_callback(InputAction.SELECT, on_select)
    input_handler.register_callback(InputAction.DESELECT, on_deselect)
    input_handler.register_callback(InputAction.PAUSE, on_pause)
    input_handler.register_callback(InputAction.SPEED_UP, on_speed_up)
    input_handler.register_callback(InputAction.SPEED_DOWN, on_speed_down)
    input_handler.register_callback(InputAction.TOGGLE_UI, on_toggle_ui)
    input_handler.register_callback(InputAction.BUILD_MODE, on_build_mode)
    input_handler.register_callback(InputAction.CONFIRM_BUILD, on_confirm_build)
    input_handler.register_callback(InputAction.SHIP_PURCHASE, on_ship_purchase)
    input_handler.register_callback(InputAction.TOGGLE_ROUTES, on_toggle_routes)
    input_handler.register_callback(InputAction.UPGRADE_STATION, on_upgrade_station)
    input_handler.register_callback(InputAction.QUICK_SAVE, on_quick_save)
    input_handler.register_callback(InputAction.QUICK_LOAD, on_quick_load)

    def on_trade_route() -> None:
        # T key has different behavior depending on state
        if renderer.trade_manager_visible:
            # In trade manager, T starts route creation or advances it
            if renderer.trade_manager.creating_route:
                # Already creating, this shouldn't happen (click to select)
                pass
            else:
                renderer.trade_manager.start_route_creation()
        else:
            # Open trade manager
            renderer.toggle_trade_manager()

    def on_help() -> None:
        renderer.toggle_help()

    def on_waypoint() -> None:
        # W key enters waypoint mode for selected ship
        renderer.enter_waypoint_mode()

    def on_news() -> None:
        renderer.toggle_news_feed()

    input_handler.register_callback(InputAction.TRADE_ROUTE, on_trade_route)
    input_handler.register_callback(InputAction.HELP, on_help)
    input_handler.register_callback(InputAction.WAYPOINT, on_waypoint)
    input_handler.register_callback(InputAction.NEWS, on_news)

    # Main game loop
    running = True
    while running:
        # Handle input
        events = pygame.event.get()
        running = input_handler.process_events(events)

        # Handle quit action and number keys for menus
        # Use menu manager to dispatch input to the active (topmost) menu only
        from src.ui.panels import MenuId

        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    running = False
                    continue

                # Get active menu from manager - only this menu receives input
                active_menu = renderer.menu_manager.active_menu

                # Handle Escape - closes the top menu
                if event.key == pygame.K_ESCAPE and active_menu != MenuId.NONE:
                    renderer.menu_manager.close_top()
                    continue

                # Dispatch input to active menu only
                if active_menu == MenuId.RESOURCE_SELECTION:
                    # Number keys 1-9 for selecting mining resource
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                     pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
                        index = event.key - pygame.K_1
                        renderer.select_mining_resource(index, world)

                elif active_menu == MenuId.BUILD_MENU:
                    # Number keys 1-7 for selecting station type
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                     pygame.K_5, pygame.K_6, pygame.K_7):
                        index = event.key - pygame.K_1
                        renderer.select_build_option(index)

                elif active_menu == MenuId.SHIP_MENU:
                    # Number keys 1-5 for selecting ship type
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                        index = event.key - pygame.K_1
                        renderer.select_ship_option(index)

                elif active_menu == MenuId.UPGRADE_MENU:
                    # Number keys 1-3 for selecting upgrade option
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        index = event.key - pygame.K_1
                        renderer.select_upgrade_option(index)

                elif active_menu == MenuId.TRADE_ROUTE:
                    # Trade route panel controls
                    if renderer.trade_route_panel.add_mode:
                        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                         pygame.K_5, pygame.K_6):
                            index = event.key - pygame.K_1
                            renderer.trade_route_panel.select_waypoint(index)
                        elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                            renderer.trade_route_add_waypoint()
                    else:
                        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                            index = event.key - pygame.K_1
                            renderer.trade_route_panel.select_waypoint(index)
                        elif event.key == pygame.K_a:
                            renderer.trade_route_panel.toggle_add_mode()
                        elif event.key == pygame.K_d:
                            renderer.trade_route_delete_waypoint()
                        elif event.key == pygame.K_c:
                            renderer.trade_route_clear()

                elif active_menu == MenuId.TRADE_MANAGER:
                    # Trade manager controls
                    if renderer.trade_manager.assigning_ship:
                        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                            index = event.key - pygame.K_1
                            renderer.trade_manager_assign_ship_by_index(index)
                    elif not renderer.trade_manager.creating_route:
                        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                         pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8):
                            index = event.key - pygame.K_1
                            renderer.trade_manager.select_route(index)
                            renderer._update_trade_manager()
                        elif event.key == pygame.K_d:
                            renderer.trade_manager.delete_selected_route()

                elif active_menu == MenuId.WAYPOINT_MODE:
                    # Waypoint mode doesn't need number keys, just click handling
                    pass

                elif active_menu == MenuId.HELP:
                    # Help panel doesn't need input, ESC already handled above
                    pass

                elif active_menu == MenuId.NEWS_FEED:
                    # News feed panel keyboard handling
                    action = renderer.news_feed.handle_key(event.key)
                    if action == "close":
                        renderer.menu_manager.close_top()
                    elif action == "accept_contract":
                        # Accept the selected contract
                        from src.simulation.events import EventManager, accept_contract
                        for entity, em in world.entity_manager.get_all_components(EventManager):
                            contracts = [c for c in em.available_contracts if not c.accepted]
                            if contracts and 0 <= renderer.news_feed.selected_contract < len(contracts):
                                contract = contracts[renderer.news_feed.selected_contract]
                                if accept_contract(world.entity_manager, contract.id, player_faction_id):
                                    renderer.notifications.add_notification(
                                        f"Contract accepted: {contract.title}",
                                        duration=3.0
                                    )
                            break

        # Update mouse world position for renderer
        renderer.update_mouse_position(
            input_handler.state.mouse_world_x,
            input_handler.state.mouse_world_y
        )

        # Disable keyboard panning when any menu or mode is active
        input_handler.keyboard_pan_enabled = not renderer.menu_manager.has_open_menu()

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
