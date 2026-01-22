"""Entry point and game loop."""
from __future__ import annotations
import pygame
import sys
import math

from .config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, COLORS, TOOLBAR_HEIGHT
from .core.world import World
from .core.events import EventBus
from .solar_system.orbits import OrbitalSystem, MovementSystem, NavigationSystem
from .simulation.production import ProductionSystem, ExtractionSystem
from .simulation.economy import EconomySystem, PopulationSystem
from .simulation.trade import TradeSystem
from .simulation.events import EventSystem, DiscoverySystem
from .simulation.goals import GoalSystem, EarthShipyardGoal, GoalStatus
from .simulation.freelancer import FreelancerSpawner, FreelancerManager
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
    from .entities.stations import create_earth_market, create_station, create_mining_station, StationType
    from .simulation.resources import ResourceKnowledge, ResourceType
    from .simulation.events import EventManager, STORY_EVENTS

    # Create solar system
    bodies = create_solar_system(world)

    # Create ResourceKnowledge singleton - tracks which bodies have been surveyed
    # Only Moon and Mars have public resource data at start
    knowledge_entity = world.create_entity(name="ResourceKnowledge", tags={"singleton"})
    world.entity_manager.add_component(knowledge_entity, ResourceKnowledge())

    # Create OrbitalSlotManager singleton - manages station orbital positions
    from .entities.station_slots import OrbitalSlotManager
    slot_entity = world.create_entity(name="OrbitalSlotManager", tags={"singleton"})
    world.entity_manager.add_component(slot_entity, OrbitalSlotManager())

    # Create EventManager singleton for events, contracts, discoveries
    event_entity = world.create_entity(name="EventManager", tags={"singleton"})
    event_manager = EventManager()

    # Queue the X-Drive story event - this will pause the game at start
    import copy
    xdrive_event = copy.deepcopy(STORY_EVENTS["xdrive_announcement"])
    event_manager.queue_story_event(xdrive_event)

    world.entity_manager.add_component(event_entity, event_manager)

    # Get Earth's actual position (it has a random starting angle now)
    from .solar_system.orbits import Position, ParentBody
    earth_pos = None
    for entity in world.entity_manager.get_entities_with(Position):
        if entity.name == "Earth":
            earth_pos = world.entity_manager.get_component(entity, Position)
            break

    if not earth_pos:
        # Fallback if Earth not found
        earth_pos = Position(x=1.0, y=0.0)

    # Create corporations with equal resources
    corporations = {}
    player_faction_id = None

    # Starting resources for each corporation
    STARTING_CREDITS = 100000
    STARTING_SHIPS = 1  # Each corp starts with 1 ship

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

        # Create starting ship for this corporation - spread in ring around Earth
        for ship_num in range(STARTING_SHIPS):
            # Spread ships in a ring pattern around Earth for easier clicking
            num_corps = len(COMPETITIVE_CORPORATIONS)
            angle = (i / num_corps) * 2 * math.pi
            offset_x = 0.05 * math.cos(angle)  # 0.05 AU radius circle
            offset_y = 0.05 * math.sin(angle)

            ship = create_ship(
                world=world,
                name=f"{name} Freighter {ship_num + 1}",
                ship_type=ShipType.FREIGHTER,
                position=(earth_pos.x + offset_x, earth_pos.y + offset_y),
                owner_faction_id=faction.id,
                is_trader=True,
            )

            # Lock ship to Earth so it appears in sector view
            world.entity_manager.add_component(ship, ParentBody(
                parent_name="Earth",
                offset_x=offset_x,
                offset_y=offset_y,
            ))

    # Create Freelancers faction - they'll spawn ships on demand when cargo is available
    freelancers = create_faction(
        world=world,
        name="Freelancers",
        faction_type=FactionType.INDEPENDENT,
        color=(180, 180, 180),
        credits=100000,  # Modest starting capital
        is_player=False,
    )
    freelancer_id = freelancers.id

    # Create Earth market - the main consumer hub (at Earth's actual position)
    earth_market = create_earth_market(
        world=world,
        position=(earth_pos.x, earth_pos.y),
        owner_faction_id=None,  # Earth market is neutral/public
    )

    # Create initial NPC stations to kickstart the economy
    # These provide trade opportunities for ships from the start
    from .simulation.resources import ResourceType

    # Luna Mining Outpost - extracts water ice (Moon is ~0.00257 AU from Earth)
    luna_offset_x = 0.003  # Slightly offset from Earth
    luna_offset_y = 0.001
    luna_mining = create_mining_station(
        world=world,
        name="Luna Mining Outpost",
        position=(earth_pos.x + luna_offset_x, earth_pos.y + luna_offset_y),
        parent_body="Moon",
        resource_type=ResourceType.WATER_ICE,
        owner_faction_id=freelancer_id,
    )
    if luna_mining:
        # Add to Earth's sector (Moon is in Earth sector)
        world.entity_manager.add_component(luna_mining, ParentBody(
            parent_name="Moon",
            offset_x=0.001,
            offset_y=0.0,
        ))

    # Earth Orbital Refinery - processes raw materials into refined goods
    refinery_offset_x = -0.04
    refinery_offset_y = 0.02
    earth_refinery = create_station(
        world=world,
        name="Earth Orbital Refinery",
        station_type=StationType.REFINERY,
        position=(earth_pos.x + refinery_offset_x, earth_pos.y + refinery_offset_y),
        parent_body="Earth",
        owner_faction_id=freelancer_id,
    )
    if earth_refinery:
        world.entity_manager.add_component(earth_refinery, ParentBody(
            parent_name="Earth",
            offset_x=refinery_offset_x,
            offset_y=refinery_offset_y,
        ))

    # Create Earth Shipyard Goal - shipyard will be built when resources are collected
    goal_entity = world.create_entity(name="EarthShipyardGoal", tags={"goal", "singleton"})
    world.entity_manager.add_component(goal_entity, EarthShipyardGoal(
        earth_market_id=earth_market.id,
        freelancer_faction_id=freelancer_id,
    ))

    # Create FreelancerManager - handles spawning freelancer ships on demand
    freelancer_mgr_entity = world.create_entity(name="FreelancerManager", tags={"singleton"})
    world.entity_manager.add_component(freelancer_mgr_entity, FreelancerManager(
        freelancer_faction_id=freelancer_id,
        max_freelancers=10,
        spawn_interval=5.0,  # 5 game days between spawns
    ))

    # Spawn initial drones at Earth market for immediate activity
    from .simulation.trade import CargoHold
    for drone_num in range(3):
        drone_angle = (drone_num / 3) * 2 * math.pi + math.pi / 6  # Offset from corp ships
        drone_offset_x = 0.03 * math.cos(drone_angle)
        drone_offset_y = 0.03 * math.sin(drone_angle)

        drone = create_ship(
            world=world,
            name=f"Earth Drone {drone_num + 1}",
            ship_type=ShipType.DRONE,
            position=(earth_pos.x + drone_offset_x, earth_pos.y + drone_offset_y),
            owner_faction_id=freelancer_id,
            is_trader=False,
        )

        # Configure drone for local operations
        from .entities.ships import Ship
        ship_comp = world.entity_manager.get_component(drone, Ship)
        if ship_comp:
            ship_comp.is_drone = True
            ship_comp.home_station_id = earth_market.id
            ship_comp.local_system = "Earth"

        # Add cargo hold for drone hauling
        world.entity_manager.add_component(drone, CargoHold(capacity=20))

        # Lock to Earth with offset
        world.entity_manager.add_component(drone, ParentBody(
            parent_name="Earth",
            offset_x=drone_offset_x,
            offset_y=drone_offset_y,
        ))

    # Spawn initial freelancer ships at Earth for more activity
    for freelancer_num in range(2):
        fl_angle = (freelancer_num / 2) * 2 * math.pi + math.pi / 4
        fl_offset_x = 0.07 * math.cos(fl_angle)
        fl_offset_y = 0.07 * math.sin(fl_angle)

        freelancer_ship = create_ship(
            world=world,
            name=f"Freelancer {freelancer_num + 1}",
            ship_type=ShipType.FREIGHTER,
            position=(earth_pos.x + fl_offset_x, earth_pos.y + fl_offset_y),
            owner_faction_id=freelancer_id,
            is_trader=True,
        )

        # Add cargo hold for trading
        world.entity_manager.add_component(freelancer_ship, CargoHold(capacity=50))

        # Lock to Earth so it appears in sector view
        world.entity_manager.add_component(freelancer_ship, ParentBody(
            parent_name="Earth",
            offset_x=fl_offset_x,
            offset_y=fl_offset_y,
        ))

    return {
        "player_faction_id": player_faction_id,
        "corporations": corporations,
        "freelancer_id": freelancer_id,
        "earth_market_id": earth_market.id,
    }


def main() -> None:
    """Main entry point."""
    # Initialize Pygame
    pygame.init()

    # Get display info for dynamic sizing
    display_info = pygame.display.Info()
    # Use 90% of screen size, but cap at config values
    screen_w = min(int(display_info.current_w * 0.9), SCREEN_WIDTH)
    screen_h = min(int(display_info.current_h * 0.9), SCREEN_HEIGHT)

    # Create resizable window
    screen = pygame.display.set_mode((screen_w, screen_h), pygame.RESIZABLE)
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
    world.add_system(GoalSystem(event_bus))
    world.add_system(building_system)
    world.add_system(faction_ai)

    # Create competitive start (5 corporations racing)
    game_state = create_competitive_start(world)
    player_faction_id = game_state["player_faction_id"]

    # Add FreelancerSpawner system (needs world reference)
    freelancer_spawner = FreelancerSpawner(event_bus, world)
    world.add_system(freelancer_spawner)

    # Connect building system to faction AI
    faction_ai.set_building_system(building_system, world)

    # Set up rendering - start camera locked on Earth
    camera = Camera(screen_width=screen_w, screen_height=screen_h)

    # Find Earth's position and lock camera to it
    from src.solar_system.orbits import Position
    earth_entity = None
    for entity in world.entity_manager.get_entities_with(Position):
        if entity.name == "Earth":
            earth_entity = entity
            earth_pos = world.entity_manager.get_component(entity, Position)
            if earth_pos:
                camera.center_on(earth_pos.x, earth_pos.y)
                camera.lock_to_entity(entity.id, "Earth")
            break

    # Zoom in to show Earth area nicely (about 0.5 AU visible)
    camera.zoom = 8.0

    renderer = Renderer(screen, camera)
    renderer.set_player_faction(player_faction_id, world)
    renderer.set_building_system(building_system)

    # Subscribe to trade events for visual feedback
    from src.core.events import TradeCompleteEvent, ResourceTransferEvent

    def on_trade_complete(event: TradeCompleteEvent) -> None:
        """Show notification when a trade completes."""
        # Get entity names for the notification
        buyer = world.entity_manager.get_entity(event.buyer_id)
        seller = world.entity_manager.get_entity(event.seller_id)
        buyer_name = buyer.name if buyer else "Unknown"
        seller_name = seller.name if seller else "Unknown"
        resource_name = event.resource_type.replace("_", " ").title()

        msg = f"Trade: {event.amount:.0f} {resource_name} sold for {event.total_price:.0f}cr"
        renderer.notifications.add_notification(msg, duration=4.0, color=(100, 200, 100))

    def on_resource_transfer(event: ResourceTransferEvent) -> None:
        """Show notification for resource transfers (buying cargo)."""
        source = world.entity_manager.get_entity(event.source_id)
        target = world.entity_manager.get_entity(event.target_id)
        resource_name = event.resource_type.replace("_", " ").title()

        # Only notify for significant transfers
        if event.amount >= 10:
            source_name = source.name if source else "Unknown"
            target_name = target.name if target else "Unknown"
            msg = f"Cargo: {event.amount:.0f} {resource_name} loaded"
            renderer.notifications.add_notification(msg, duration=3.0, color=(100, 150, 255))

    event_bus.subscribe(TradeCompleteEvent, on_trade_complete)
    event_bus.subscribe(ResourceTransferEvent, on_resource_transfer)

    input_handler = InputHandler(camera)

    # Wire up toolbar speed controls
    from src.ui.toolbar import ToolbarAction
    renderer.toolbar.register_callback(ToolbarAction.PAUSE, lambda: world.toggle_pause())
    renderer.toolbar.register_callback(ToolbarAction.SPEED_UP, lambda: on_speed_up())
    renderer.toolbar.register_callback(ToolbarAction.SPEED_DOWN, lambda: on_speed_down())

    # Register input callbacks
    def on_select(world_x: float, world_y: float) -> None:
        # Check if click is on toolbar first
        if input_handler.state.mouse_y < TOOLBAR_HEIGHT:
            if renderer.handle_toolbar_click(input_handler.state.mouse_x, input_handler.state.mouse_y):
                return

        # Handle sector view selection and building
        if renderer.is_in_sector_view():
            # In sector view with build mode - find nearest body and build there
            if renderer.build_mode_active:
                body_name = renderer.get_body_at_screen_sector(
                    input_handler.state.mouse_x,
                    input_handler.state.mouse_y
                )
                if body_name:
                    renderer.try_place_station_at_body(body_name, world)
                else:
                    renderer.add_notification("Click on a planet or moon to build", "warning")
                return

            # In sector view, use screen coordinates for selection
            # First check for station clicks
            station_id = renderer.get_station_at_screen_sector(
                input_handler.state.mouse_x,
                input_handler.state.mouse_y
            )
            if station_id:
                renderer.sector_view.selected_station_id = station_id
                renderer.sector_view.selected_body = None
                # Also update main renderer selection for info panel
                station_entity = world.entity_manager.get_entity(station_id)
                if station_entity:
                    renderer.selected_entity = station_entity
                    renderer.add_notification(f"Selected {station_entity.name}", "info")
                return

            # Then check for body clicks
            body_name = renderer.get_body_at_screen_sector(
                input_handler.state.mouse_x,
                input_handler.state.mouse_y
            )
            if body_name:
                renderer.sector_view.selected_body = body_name
                renderer.sector_view.selected_station_id = None
                # Find and select the celestial body entity for info panel
                from src.entities.celestial import CelestialBody
                for entity, body in world.entity_manager.get_all_components(CelestialBody):
                    if entity.name == body_name:
                        renderer.selected_entity = entity
                        break
                renderer.add_notification(f"Selected {body_name}", "info")
            else:
                renderer.sector_view.selected_body = None
                renderer.sector_view.selected_station_id = None
                renderer.selected_entity = None
            return

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
        # Cancel various modes in order of priority
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
        elif not renderer.is_in_sector_view():
            # In solar system map - close map and return to sector
            renderer.toggle_solar_system_map()
        else:
            # In sector view - just deselect
            renderer.deselect()
            renderer.sector_view.selected_body = None
            renderer.sector_view.selected_station_id = None
            renderer.sector_view.selected_ship_id = None

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
            if renderer.is_in_sector_view():
                # In sector view - build at hovered body
                body_name = renderer.get_body_at_screen_sector(
                    input_handler.state.mouse_x,
                    input_handler.state.mouse_y
                )
                if body_name:
                    renderer.try_place_station_at_body(body_name, world)
                else:
                    renderer.add_notification("Hover over a body and press Enter to build", "warning")
            else:
                # In solar system view - use world coordinates
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

    def on_double_click(world_x: float, world_y: float) -> None:
        """Handle double-click to enter sector from solar map or lock camera on ship."""
        from src.entities.celestial import CelestialBody
        from src.entities.ships import Ship
        from src.solar_system.orbits import Position
        from src.solar_system.sectors import get_sector_id_for_body

        em = world.entity_manager

        if renderer.is_in_sector_view():
            # In sector view: double-click only locks camera on ships (not bodies)
            ship_id = renderer.get_ship_at_screen_sector(
                input_handler.state.mouse_x,
                input_handler.state.mouse_y
            )
            if ship_id:
                ship_entity = em.get_entity(ship_id)
                if ship_entity:
                    camera.lock_to_entity(ship_id, ship_entity.name)
                    renderer.add_notification(f"Camera locked to {ship_entity.name}", "info")
            else:
                # Double-click on empty space unlocks camera
                if camera.is_locked:
                    camera.unlock()
                    renderer.add_notification("Camera unlocked", "info")
            return

        # In solar system map: double-click enters sector
        # Find closest celestial body to click position
        closest_entity = None
        closest_dist = 0.2  # AU threshold for clicking

        for entity, body in em.get_all_components(CelestialBody):
            pos = em.get_component(entity, Position)
            if pos:
                dist = ((pos.x - world_x)**2 + (pos.y - world_y)**2)**0.5
                if dist < closest_dist:
                    closest_dist = dist
                    closest_entity = entity

        # If clicked on a body with a sector, enter it
        if closest_entity:
            sector_id = get_sector_id_for_body(closest_entity.name)
            if sector_id:
                renderer.enter_sector_by_id(sector_id)
                return

        # Check for ship clicks to follow ships between sectors
        closest_ship = None
        closest_ship_dist = 0.1

        for entity, ship in em.get_all_components(Ship):
            pos = em.get_component(entity, Position)
            if pos:
                dist = ((pos.x - world_x)**2 + (pos.y - world_y)**2)**0.5
                if dist < closest_ship_dist:
                    closest_ship_dist = dist
                    closest_ship = entity

        if closest_ship:
            camera.lock_to_entity(closest_ship.id, closest_ship.name)
            renderer.add_notification(f"Following {closest_ship.name}", "info")
        elif camera.is_locked:
            camera.unlock()
            renderer.add_notification("Camera unlocked", "info")

    input_handler.register_callback(InputAction.SELECT, on_select)
    input_handler.register_callback(InputAction.DOUBLE_CLICK, on_double_click)
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

    def on_fleet() -> None:
        renderer.toggle_ships_list()

    def on_toggle_map() -> None:
        # M key toggles solar system map
        renderer.toggle_solar_system_map()

    input_handler.register_callback(InputAction.TRADE_ROUTE, on_trade_route)
    input_handler.register_callback(InputAction.HELP, on_help)
    input_handler.register_callback(InputAction.WAYPOINT, on_waypoint)
    input_handler.register_callback(InputAction.NEWS, on_news)
    input_handler.register_callback(InputAction.FLEET, on_fleet)
    input_handler.register_callback(InputAction.TOGGLE_MAP, on_toggle_map)

    # Main game loop
    running = True
    while running:
        # Handle input
        events = pygame.event.get()

        # Handle window resize and sector view camera controls
        for event in events:
            if event.type == pygame.VIDEORESIZE:
                screen_w, screen_h = event.w, event.h
                screen = pygame.display.set_mode((screen_w, screen_h), pygame.RESIZABLE)
                renderer.handle_resize(screen_w, screen_h, screen)
                renderer.sector_view.handle_resize(screen_w, screen_h)

            # Sector view camera controls (intercept before main input handler)
            if renderer.is_in_sector_view():
                if event.type == pygame.MOUSEWHEEL:
                    # Zoom sector view
                    mx, my = pygame.mouse.get_pos()
                    if event.y > 0:
                        renderer.sector_view.zoom_in(mx, my)
                    elif event.y < 0:
                        renderer.sector_view.zoom_out(mx, my)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 3:  # Right click - start pan
                        mx, my = pygame.mouse.get_pos()
                        renderer.sector_view.start_pan(mx, my)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 3:  # Right click released - end pan
                        renderer.sector_view.end_pan()

                elif event.type == pygame.MOUSEMOTION:
                    if renderer.sector_view.is_panning:
                        mx, my = pygame.mouse.get_pos()
                        renderer.sector_view.update_pan(mx, my)

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

                # Handle story event first - it blocks all other input
                if active_menu == MenuId.STORY_EVENT:
                    if renderer.handle_story_event_key(event.key):
                        # Story event was acknowledged, check for more
                        from src.simulation.events import EventManager as EM
                        for ent, em in world.entity_manager.get_all_components(EM):
                            em.acknowledge_story_event()
                            break
                    continue

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

                elif active_menu == MenuId.SHIPS_LIST:
                    # Ships list (fleet) panel keyboard handling
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                                     pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
                        index = event.key - pygame.K_1
                        ship_id = renderer.ships_list.select_ship(index)
                        if ship_id:
                            # Select the ship in the game world
                            ship_entity = world.entity_manager.get_entity(ship_id)
                            if ship_entity:
                                renderer.selected_entity = ship_entity
                                renderer.notifications.add_notification(
                                    f"Selected: {ship_entity.name}",
                                    duration=2.0
                                )
                    elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        # Follow selected ship (camera lock)
                        ship_id = renderer.ships_list.get_selected_ship_id()
                        if ship_id:
                            ship_entity = world.entity_manager.get_entity(ship_id)
                            if ship_entity:
                                renderer.selected_entity = ship_entity
                                renderer.camera.lock_to_entity(ship_entity, world.entity_manager)
                                renderer.notifications.add_notification(
                                    f"Following: {ship_entity.name}",
                                    duration=2.0
                                )
                    elif event.key == pygame.K_w:
                        # Set waypoint for selected ship
                        ship_id = renderer.ships_list.get_selected_ship_id()
                        if ship_id:
                            ship_entity = world.entity_manager.get_entity(ship_id)
                            if ship_entity:
                                renderer.selected_entity = ship_entity
                                renderer.enter_waypoint_mode()
                    elif event.key == pygame.K_UP:
                        renderer.ships_list.scroll_up()
                    elif event.key == pygame.K_DOWN:
                        renderer.ships_list.scroll_down()

        # Update mouse world position for renderer
        renderer.update_mouse_position(
            input_handler.state.mouse_world_x,
            input_handler.state.mouse_world_y,
            input_handler.state.mouse_x,
            input_handler.state.mouse_y
        )

        # Update renderer state (hover detection, toolbar)
        dt_render = 1.0 / FPS
        renderer.update(dt_render, world)

        # Disable keyboard panning when any menu or mode is active
        menus_open = renderer.menu_manager.has_open_menu()
        input_handler.keyboard_pan_enabled = not menus_open and not renderer.is_in_sector_view()

        # Handle keyboard panning for sector view separately (arrow keys only)
        if renderer.is_in_sector_view() and not menus_open:
            pan_speed = 10
            dx, dy = 0, 0
            if pygame.K_UP in input_handler.state.keys_pressed:
                dy -= pan_speed
            if pygame.K_DOWN in input_handler.state.keys_pressed:
                dy += pan_speed
            if pygame.K_LEFT in input_handler.state.keys_pressed:
                dx -= pan_speed
            if pygame.K_RIGHT in input_handler.state.keys_pressed:
                dx += pan_speed
            if dx != 0 or dy != 0:
                renderer.sector_view.pan_by_screen(dx, dy)

        # Check for pending story events
        from src.simulation.events import EventManager as EM
        for entity, em in world.entity_manager.get_all_components(EM):
            # Try to show next story event if none is currently displayed
            if not renderer.is_story_event_active():
                next_event = em.show_next_story_event()
                if next_event:
                    renderer.show_story_event(next_event)
            break

        # Update simulation (paused during story events)
        dt = clock.tick(FPS) / 1000.0  # Delta time in seconds
        if not renderer.is_story_event_active():
            world.update(dt)

        # Update camera lock position (even when paused, to follow moving bodies)
        camera.update_lock(world.entity_manager)

        if not renderer.is_story_event_active():
            # Check if Earth shipyard goal is complete - create shipyard
            for entity, goal in world.entity_manager.get_all_components(EarthShipyardGoal):
                if goal.status == GoalStatus.COMPLETED and not hasattr(goal, '_shipyard_created'):
                    goal._shipyard_created = True
                    # Create the shipyard at Earth
                    from src.entities.stations import create_station, StationType
                    from src.solar_system.orbits import Position
                    from src.simulation.resources import ResourceType

                    # Get Earth position
                    earth_pos = None
                    for e in world.entity_manager.get_entities_with(Position):
                        if e.name == "Earth":
                            earth_pos = world.entity_manager.get_component(e, Position)
                            break

                    if earth_pos:
                        create_station(
                            world=world,
                            name="Earth Public Shipyard",
                            station_type=StationType.SHIPYARD,
                            position=(earth_pos.x, earth_pos.y - 0.05),
                            parent_body="Earth",
                            owner_faction_id=goal.freelancer_faction_id,
                            initial_resources={
                                ResourceType.REFINED_METAL: 100,
                                ResourceType.ELECTRONICS: 50,
                                ResourceType.MACHINERY: 25,
                            },
                        )
                        renderer.add_notification("Earth Public Shipyard is now operational!", "success")
                break

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
