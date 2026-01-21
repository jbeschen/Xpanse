"""Main rendering logic."""
from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID
import pygame
import math

from ..config import COLORS, SCREEN_WIDTH, SCREEN_HEIGHT
from .camera import Camera
from .panels import (
    InfoPanel, StatusBar, MiniMap, BuildMenuPanel, PlayerHUD,
    ShipPurchasePanel, NotificationPanel, PriceHistoryGraph, UpgradePanel,
    TradeRoutePanel, HelpPanel, ContextPrompt, TradeRouteManagerPanel
)
from ..entities.stations import StationType
from ..entities.ships import ShipType

if TYPE_CHECKING:
    from ..core.world import World
    from ..core.ecs import Entity
    from ..systems.building import BuildingSystem


class Renderer:
    """Main renderer for the game."""

    def __init__(self, screen: pygame.Surface, camera: Camera) -> None:
        self.screen = screen
        self.camera = camera

        # Initialize font
        pygame.font.init()
        self.font = pygame.font.Font(None, 20)
        self.font_large = pygame.font.Font(None, 28)

        # UI panels
        self.info_panel = InfoPanel(
            x=10, y=120, width=250, height=200, title="Info"
        )
        self.status_bar = StatusBar(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.minimap = MiniMap(x=SCREEN_WIDTH - 160, y=10, size=150)
        self.build_menu = BuildMenuPanel(x=SCREEN_WIDTH - 300, y=170)
        self.build_menu.visible = False
        self.player_hud = PlayerHUD(x=10, y=10)
        self.ship_menu = ShipPurchasePanel(x=SCREEN_WIDTH - 300, y=170)
        self.ship_menu.visible = False
        self.notifications = NotificationPanel(x=SCREEN_WIDTH // 2 - 150, y=50)
        self.price_graph = PriceHistoryGraph(x=10, y=SCREEN_HEIGHT - 180)
        self.price_graph.visible = False
        self.upgrade_panel = UpgradePanel(x=SCREEN_WIDTH - 300, y=170)
        self.upgrade_panel.visible = False
        self.trade_route_panel = TradeRoutePanel(x=SCREEN_WIDTH - 340, y=170)
        self.trade_route_panel.visible = False
        self.help_panel = HelpPanel(
            x=SCREEN_WIDTH // 2 - 200, y=SCREEN_HEIGHT // 2 - 240
        )
        self.help_panel.visible = False
        self.context_prompt = ContextPrompt(
            x=SCREEN_WIDTH // 2 - 150, y=80
        )
        self.context_prompt.visible = False
        self.trade_manager = TradeRouteManagerPanel(
            x=SCREEN_WIDTH - 370, y=170
        )
        self.trade_manager.visible = False

        # State
        self.selected_entity: Entity | None = None
        self.show_ui = True
        self.show_orbits = True
        self.show_labels = True
        self.show_trade_routes = True  # Show trade route lines

        # Build mode state
        self.build_mode_active = False
        self.build_menu_visible = False
        self.selected_station_type: StationType | None = None
        self.mouse_world_x = 0.0
        self.mouse_world_y = 0.0

        # Ship purchase state
        self.ship_menu_visible = False

        # Upgrade state
        self.upgrade_menu_visible = False

        # Trade route state
        self.trade_route_visible = False

        # Help state
        self.help_visible = False

        # Waypoint mode state
        self.waypoint_mode = False
        self.waypoint_ship_id: UUID | None = None
        self.waypoint_ship_name: str = ""

        # Trade manager state
        self.trade_manager_visible = False

        # Player faction info
        self.player_faction_id: UUID | None = None
        self.player_faction_color: tuple[int, int, int] = (255, 255, 255)
        self.building_system: "BuildingSystem | None" = None
        self._world: "World | None" = None

    def set_player_faction(self, faction_id: UUID | None, world: "World") -> None:
        """Set the player faction for highlighting."""
        self.player_faction_id = faction_id
        self._world = world

        if faction_id and world:
            from ..entities.factions import Faction
            em = world.entity_manager
            for entity, faction in em.get_all_components(Faction):
                if entity.id == faction_id:
                    self.player_faction_color = faction.color
                    break

    def set_building_system(self, building_system: "BuildingSystem") -> None:
        """Set the building system reference."""
        self.building_system = building_system

    def update_mouse_position(self, world_x: float, world_y: float) -> None:
        """Update the current mouse world position for build preview."""
        self.mouse_world_x = world_x
        self.mouse_world_y = world_y

    def toggle_build_menu(self) -> None:
        """Toggle the build menu visibility."""
        self.build_menu_visible = not self.build_menu_visible
        self.build_menu.visible = self.build_menu_visible

        if not self.build_menu_visible:
            self.cancel_build_mode()

    def select_build_option(self, index: int) -> None:
        """Select a build option from the menu."""
        if not self._world:
            return

        # Update credits in build menu
        self._update_build_menu_credits()

        station_type = self.build_menu.select_option(index)
        if station_type:
            self.selected_station_type = station_type
            self.build_mode_active = True

    def cancel_build_mode(self) -> None:
        """Cancel build mode."""
        self.build_mode_active = False
        self.selected_station_type = None
        self.build_menu.selected_index = -1

    def try_place_station(self, world_x: float, world_y: float, world: "World") -> bool:
        """Try to place a station at the given world coordinates.

        Returns:
            True if station was placed successfully
        """
        if not self.build_mode_active or not self.selected_station_type:
            return False

        if not self.building_system or not self.player_faction_id:
            return False

        # Find nearest celestial body
        parent_body, distance = self.building_system.find_nearest_body(
            (world_x, world_y), world.entity_manager
        )

        # Get resource type if building a mining station
        resource_type = None
        if self.selected_station_type == StationType.MINING_STATION:
            resources = self.building_system.get_body_resources(
                parent_body, world.entity_manager
            )
            if resources:
                resource_type = resources[0][0]  # Use first available resource

        # Request the build
        result = self.building_system.request_build(
            world=world,
            faction_id=self.player_faction_id,
            station_type=self.selected_station_type,
            position=(world_x, world_y),
            parent_body=parent_body,
            resource_type=resource_type,
        )

        if result.success:
            # Successfully built - exit build mode but keep menu open
            self.build_mode_active = False
            self.selected_station_type = None
            self.build_menu.selected_index = -1
            return True

        return False

    def _update_build_menu_credits(self) -> None:
        """Update credits and materials in the build menu."""
        if not self._world or not self.player_faction_id:
            return

        from ..entities.factions import Faction
        from ..entities.stations import Station
        from ..simulation.resources import Inventory

        em = self._world.entity_manager

        # Get player credits
        credits = 0.0
        for entity, faction in em.get_all_components(Faction):
            if entity.id == self.player_faction_id:
                credits = faction.credits
                break

        # Sum up materials across all player-owned stations
        materials: dict = {}
        for entity, station in em.get_all_components(Station):
            if station.owner_faction_id == self.player_faction_id:
                inv = em.get_component(entity, Inventory)
                if inv:
                    for resource, amount in inv.resources.items():
                        materials[resource] = materials.get(resource, 0) + amount

        self.build_menu.update_player_resources(credits, materials)
        self.ship_menu.update_player_resources(credits, materials)
        self.upgrade_panel.update_player_resources(credits, materials)

    def toggle_ship_menu(self) -> None:
        """Toggle the ship purchase menu visibility."""
        if not self._world or not self.player_faction_id:
            return

        # Close build menu if open
        if self.build_menu_visible:
            self.build_menu_visible = False
            self.build_menu.visible = False
            self.cancel_build_mode()

        self.ship_menu_visible = not self.ship_menu_visible
        self.ship_menu.visible = self.ship_menu_visible

        # Update shipyard info if selected entity is a shipyard
        if self.ship_menu_visible and self.selected_entity:
            from ..entities.stations import Station
            em = self._world.entity_manager
            station = em.get_component(self.selected_entity, Station)
            if station and station.station_type == StationType.SHIPYARD:
                if station.owner_faction_id == self.player_faction_id:
                    self.ship_menu.set_shipyard(self.selected_entity.id, self.selected_entity.name)
                else:
                    self.ship_menu.set_shipyard(None, "")
            else:
                self.ship_menu.set_shipyard(None, "")

    def select_ship_option(self, index: int) -> None:
        """Select a ship option from the menu."""
        if not self._world or not self.ship_menu.shipyard_id:
            return

        self._update_build_menu_credits()
        self.ship_menu.select_option(index)

    def purchase_selected_ship(self, world: "World") -> bool:
        """Purchase the selected ship type."""
        if not self.ship_menu_visible:
            return False

        ship_type = self.ship_menu.get_selected_type()
        if not ship_type or not self.ship_menu.shipyard_id:
            return False

        if not self.building_system or not self.player_faction_id:
            return False

        result = self.building_system.purchase_ship(
            world=world,
            faction_id=self.player_faction_id,
            ship_type=ship_type,
            shipyard_id=self.ship_menu.shipyard_id,
        )

        if result.success:
            self.add_notification(result.message, "success")
            self.ship_menu.selected_index = -1
            return True
        else:
            self.add_notification(result.message, "error")
            return False

    def toggle_trade_routes(self) -> None:
        """Toggle trade route display."""
        self.show_trade_routes = not self.show_trade_routes

    def toggle_upgrade_menu(self) -> None:
        """Toggle the station upgrade menu visibility."""
        if not self._world or not self.player_faction_id:
            return

        # Close other menus if open
        if self.build_menu_visible:
            self.build_menu_visible = False
            self.build_menu.visible = False
            self.cancel_build_mode()

        if self.ship_menu_visible:
            self.ship_menu_visible = False
            self.ship_menu.visible = False

        self.upgrade_menu_visible = not self.upgrade_menu_visible
        self.upgrade_panel.visible = self.upgrade_menu_visible

        # Update station info if a player-owned station is selected
        if self.upgrade_menu_visible and self.selected_entity:
            from ..entities.stations import Station
            em = self._world.entity_manager
            station = em.get_component(self.selected_entity, Station)
            if station and station.owner_faction_id == self.player_faction_id:
                self.upgrade_panel.set_station(self.selected_entity.id, station.station_type)
                self._update_build_menu_credits()
            else:
                self.upgrade_panel.set_station(None, None)
        else:
            self.upgrade_panel.set_station(None, None)

    def select_upgrade_option(self, index: int) -> None:
        """Select an upgrade option from the menu."""
        if not self._world:
            return

        self._update_build_menu_credits()
        self.upgrade_panel.select_option(index)

    def perform_upgrade(self, world: "World") -> bool:
        """Perform the selected upgrade."""
        if not self.upgrade_menu_visible:
            return False

        target_type = self.upgrade_panel.get_selected_type()
        if not target_type or not self.upgrade_panel.station_id:
            return False

        if not self.building_system or not self.player_faction_id:
            return False

        result = self.building_system.upgrade_station(
            world=world,
            faction_id=self.player_faction_id,
            station_id=self.upgrade_panel.station_id,
            target_type=target_type,
        )

        if result.success:
            self.add_notification(result.message, "success")
            self.upgrade_panel.selected_index = -1
            # Refresh the upgrade panel with the new station type
            from ..entities.stations import Station
            em = world.entity_manager
            station_entity = em.get_entity(self.upgrade_panel.station_id)
            if station_entity:
                station = em.get_component(station_entity, Station)
                if station:
                    self.upgrade_panel.set_station(station_entity.id, station.station_type)
            return True
        else:
            self.add_notification(result.message, "error")
            return False

    def add_notification(self, message: str, notification_type: str = "info") -> None:
        """Add a notification to display."""
        self.notifications.add_notification(message, notification_type)

    def toggle_trade_route_panel(self) -> None:
        """Toggle the trade route setup panel."""
        if not self._world or not self.player_faction_id:
            return

        # Close other menus
        if self.build_menu_visible:
            self.build_menu_visible = False
            self.build_menu.visible = False
            self.cancel_build_mode()
        if self.ship_menu_visible:
            self.ship_menu_visible = False
            self.ship_menu.visible = False
        if self.upgrade_menu_visible:
            self.upgrade_menu_visible = False
            self.upgrade_panel.visible = False

        self.trade_route_visible = not self.trade_route_visible
        self.trade_route_panel.visible = self.trade_route_visible

        if self.trade_route_visible:
            self._update_trade_route_panel()

    def _update_trade_route_panel(self) -> None:
        """Update the trade route panel with current ship info."""
        if not self._world or not self.selected_entity:
            self.trade_route_panel.set_ship(None)
            return

        from ..entities.ships import Ship
        from ..entities.stations import Station
        from ..simulation.trade import ManualRoute

        em = self._world.entity_manager

        # Check if selected entity is a player-owned ship
        ship = em.get_component(self.selected_entity, Ship)
        if not ship or ship.owner_faction_id != self.player_faction_id:
            self.trade_route_panel.set_ship(None)
            return

        self.trade_route_panel.set_ship(self.selected_entity.id, self.selected_entity.name)

        # Get existing waypoints
        manual_route = em.get_component(self.selected_entity, ManualRoute)
        if manual_route:
            waypoints = [
                {'id': wp.station_id, 'name': wp.station_name}
                for wp in manual_route.waypoints
            ]
            self.trade_route_panel.set_waypoints(waypoints)
        else:
            self.trade_route_panel.set_waypoints([])

        # Get available stations
        stations = []
        for entity, station in em.get_all_components(Station):
            stations.append((entity.id, entity.name))
        self.trade_route_panel.set_available_stations(stations)

    def trade_route_add_waypoint(self) -> None:
        """Add a waypoint to the trade route."""
        if not self._world or not self.trade_route_panel.ship_id:
            return

        station_info = self.trade_route_panel.get_selected_station_to_add()
        if not station_info:
            return

        from ..simulation.trade import ManualRoute

        em = self._world.entity_manager
        ship_entity = em.get_entity(self.trade_route_panel.ship_id)
        if not ship_entity:
            return

        # Get or create ManualRoute component
        manual_route = em.get_component(ship_entity, ManualRoute)
        if not manual_route:
            manual_route = ManualRoute()
            em.add_component(ship_entity, manual_route)

        station_id, station_name = station_info
        manual_route.add_waypoint(station_id, station_name)

        self.trade_route_panel.add_mode = False
        self._update_trade_route_panel()
        self.add_notification(f"Added {station_name} to route", "success")

    def trade_route_delete_waypoint(self) -> None:
        """Delete the selected waypoint."""
        if not self._world or not self.trade_route_panel.ship_id:
            return

        if self.trade_route_panel.selected_index < 0:
            return

        from ..simulation.trade import ManualRoute

        em = self._world.entity_manager
        ship_entity = em.get_entity(self.trade_route_panel.ship_id)
        if not ship_entity:
            return

        manual_route = em.get_component(ship_entity, ManualRoute)
        if manual_route:
            manual_route.remove_waypoint(self.trade_route_panel.selected_index)
            self._update_trade_route_panel()
            self.add_notification("Waypoint removed", "info")

    def trade_route_clear(self) -> None:
        """Clear all waypoints."""
        if not self._world or not self.trade_route_panel.ship_id:
            return

        from ..simulation.trade import ManualRoute

        em = self._world.entity_manager
        ship_entity = em.get_entity(self.trade_route_panel.ship_id)
        if not ship_entity:
            return

        manual_route = em.get_component(ship_entity, ManualRoute)
        if manual_route:
            manual_route.clear()
            self._update_trade_route_panel()
            self.add_notification("Route cleared", "info")

    def toggle_help(self) -> None:
        """Toggle the help panel visibility."""
        self.help_visible = not self.help_visible
        self.help_panel.visible = self.help_visible

        # Close other menus when opening help
        if self.help_visible:
            if self.build_menu_visible:
                self.build_menu_visible = False
                self.build_menu.visible = False
                self.cancel_build_mode()
            if self.ship_menu_visible:
                self.ship_menu_visible = False
                self.ship_menu.visible = False
            if self.upgrade_menu_visible:
                self.upgrade_menu_visible = False
                self.upgrade_panel.visible = False
            if self.trade_route_visible:
                self.trade_route_visible = False
                self.trade_route_panel.visible = False

    def enter_waypoint_mode(self) -> bool:
        """Enter waypoint mode for the selected ship.

        Returns:
            True if waypoint mode was entered, False if no valid ship selected
        """
        if not self._world or not self.selected_entity:
            return False

        from ..entities.ships import Ship

        em = self._world.entity_manager
        ship = em.get_component(self.selected_entity, Ship)

        if not ship or ship.owner_faction_id != self.player_faction_id:
            self.add_notification("Select one of your ships first", "warning")
            return False

        # Close other menus
        self._close_all_menus()

        self.waypoint_mode = True
        self.waypoint_ship_id = self.selected_entity.id
        self.waypoint_ship_name = self.selected_entity.name

        # Set context prompt
        self.context_prompt.set_prompt(
            f"Set destination for: {self.waypoint_ship_name}",
            "Click location or Escape to cancel"
        )
        self.context_prompt.visible = True

        return True

    def cancel_waypoint_mode(self) -> None:
        """Cancel waypoint mode."""
        self.waypoint_mode = False
        self.waypoint_ship_id = None
        self.waypoint_ship_name = ""
        self.context_prompt.visible = False

    def set_waypoint(self, world_x: float, world_y: float) -> bool:
        """Set waypoint for the ship in waypoint mode.

        Returns:
            True if waypoint was set successfully
        """
        if not self.waypoint_mode or not self.waypoint_ship_id or not self._world:
            return False

        from ..solar_system.orbits import NavigationTarget
        from ..entities.ships import Ship

        em = self._world.entity_manager
        ship_entity = em.get_entity(self.waypoint_ship_id)

        if not ship_entity:
            self.cancel_waypoint_mode()
            return False

        # Get ship component for speed/acceleration values
        ship = em.get_component(ship_entity, Ship)
        max_speed = ship.max_speed if ship else 2.5
        acceleration = ship.acceleration if ship else 0.6

        # Get or create NavigationTarget
        nav = em.get_component(ship_entity, NavigationTarget)
        if not nav:
            nav = NavigationTarget(
                max_speed=max_speed,
                acceleration=acceleration,
            )
            em.add_component(ship_entity, nav)

        # Set the target
        nav.target_x = world_x
        nav.target_y = world_y
        nav.max_speed = max_speed
        nav.acceleration = acceleration

        # Try to find what's near the target for notification
        target_name = None
        from ..entities.stations import Station
        from ..solar_system.orbits import Position
        for station_entity, station in em.get_all_components(Station):
            station_pos = em.get_component(station_entity, Position)
            if station_pos:
                dist = ((station_pos.x - world_x)**2 + (station_pos.y - world_y)**2)**0.5
                if dist < 0.1:
                    target_name = station_entity.name
                    break

        if target_name:
            self.add_notification(f"{self.waypoint_ship_name} heading to {target_name}", "success")
        else:
            self.add_notification(f"{self.waypoint_ship_name} heading to ({world_x:.2f}, {world_y:.2f})", "success")

        self.cancel_waypoint_mode()
        return True

    def toggle_trade_manager(self) -> None:
        """Toggle the trade route manager panel."""
        if not self._world or not self.player_faction_id:
            return

        # Close other menus
        self._close_all_menus()

        self.trade_manager_visible = not self.trade_manager_visible
        self.trade_manager.visible = self.trade_manager_visible

        if self.trade_manager_visible:
            self._update_trade_manager()

    def _update_trade_manager(self) -> None:
        """Update the trade manager with current stations and ships."""
        if not self._world:
            return

        from ..entities.stations import Station
        from ..entities.ships import Ship

        em = self._world.entity_manager

        # Get player's stations
        stations = []
        for entity, station in em.get_all_components(Station):
            stations.append((entity.id, entity.name))
        self.trade_manager.set_available_stations(stations)

        # Get player's ships
        ships = []
        for entity, ship in em.get_all_components(Ship):
            if ship.owner_faction_id == self.player_faction_id:
                ships.append((entity.id, entity.name))
        self.trade_manager.set_available_ships(ships)

    def trade_manager_handle_station_click(self, station_id: UUID, station_name: str) -> bool:
        """Handle a station click in trade manager mode.

        Returns:
            True if click was handled
        """
        if not self.trade_manager_visible or not self.trade_manager.creating_route:
            return False

        if self.trade_manager.first_station_id is None:
            # Set first station
            self.trade_manager.set_first_station(station_id, station_name)
            self.add_notification(f"Route start: {station_name}", "info")
            return True
        else:
            # Complete route
            route = self.trade_manager.complete_route(station_id, station_name)
            if route:
                self.add_notification(f"Route created: {route['name']}", "success")
            return True

    def trade_manager_assign_ship_by_index(self, index: int) -> bool:
        """Assign a ship to the route being assigned by index."""
        if not self.trade_manager_visible or not self.trade_manager.assigning_ship:
            return False

        if 0 <= index < len(self.trade_manager.available_ships):
            ship_id, ship_name = self.trade_manager.available_ships[index]
            if self.trade_manager.assign_ship(ship_id, ship_name):
                # Actually assign the route to the ship
                self._apply_trade_route_to_ship(ship_id)
                self.add_notification(f"Assigned {ship_name} to route", "success")
                return True
        return False

    def _apply_trade_route_to_ship(self, ship_id: UUID) -> None:
        """Apply the trade route to a ship."""
        if not self._world:
            return

        from ..simulation.trade import ManualRoute

        # Find the route that was just assigned
        route = None
        for r in self.trade_manager.routes:
            if r.get('ship_id') == ship_id:
                route = r
                break

        if not route:
            return

        em = self._world.entity_manager
        ship_entity = em.get_entity(ship_id)
        if not ship_entity:
            return

        # Get or create ManualRoute
        manual_route = em.get_component(ship_entity, ManualRoute)
        if not manual_route:
            manual_route = ManualRoute()
            em.add_component(ship_entity, manual_route)

        # Clear and set new waypoints
        manual_route.clear()
        manual_route.add_waypoint(route['station1_id'], route['station1_name'])
        manual_route.add_waypoint(route['station2_id'], route['station2_name'])

    def _close_all_menus(self) -> None:
        """Close all open menus."""
        if self.build_menu_visible:
            self.build_menu_visible = False
            self.build_menu.visible = False
            self.cancel_build_mode()
        if self.ship_menu_visible:
            self.ship_menu_visible = False
            self.ship_menu.visible = False
        if self.upgrade_menu_visible:
            self.upgrade_menu_visible = False
            self.upgrade_panel.visible = False
        if self.trade_route_visible:
            self.trade_route_visible = False
            self.trade_route_panel.visible = False
        if self.help_visible:
            self.help_visible = False
            self.help_panel.visible = False
        if self.trade_manager_visible:
            self.trade_manager_visible = False
            self.trade_manager.visible = False
        if self.waypoint_mode:
            self.cancel_waypoint_mode()

    def render(self, world: World, fps: float) -> None:
        """Render the game state."""
        # Clear screen
        self.screen.fill(COLORS['background'])

        # Render world
        self._render_orbits(world)
        self._render_celestial_bodies(world)

        # Render trade routes (behind stations/ships)
        if self.show_trade_routes:
            self._render_trade_routes(world)

        self._render_stations(world)
        self._render_ships(world)

        # Render build preview if in build mode
        if self.build_mode_active:
            self._render_build_preview(world)

        # Render UI
        if self.show_ui:
            self._render_ui(world, fps)

        # Update and render notifications (always visible)
        dt = 1.0 / 60.0  # Approximate frame time
        self.notifications.update(dt)
        self.notifications.draw(self.screen, self.font)

        # Render context prompt (on top of game, below menus)
        if self.context_prompt.visible:
            self.context_prompt.draw(self.screen, self.font)

        # Render trade manager panel
        if self.trade_manager_visible:
            self.trade_manager.draw(self.screen, self.font)

        # Render help panel (on top of everything)
        if self.help_visible:
            self.help_panel.draw(self.screen, self.font)

    def _render_orbits(self, world: World) -> None:
        """Render orbital paths."""
        if not self.show_orbits:
            return

        from ..solar_system.orbits import Orbit, Position

        em = world.entity_manager

        for entity, orbit in em.get_all_components(Orbit):
            # Get parent position
            parent_pos = Position(x=0, y=0)
            for e in em.get_entities_with(Position):
                if e.name == orbit.parent_name:
                    p = em.get_component(e, Position)
                    if p:
                        parent_pos = p
                    break

            # Calculate orbit center on screen
            center_x, center_y = self.camera.world_to_screen(parent_pos.x, parent_pos.y)

            # Calculate orbit radius in pixels
            radius = int(orbit.semi_major_axis * self.camera.zoom * 100)

            # Only draw if orbit is visible
            if radius > 2 and radius < 10000:
                pygame.draw.circle(
                    self.screen, COLORS['orbit'],
                    (center_x, center_y), radius, 1
                )

    def _render_celestial_bodies(self, world: World) -> None:
        """Render planets, moons, etc."""
        from ..solar_system.orbits import Position
        from ..entities.celestial import CelestialBody, get_body_display_radius

        em = world.entity_manager

        for entity, body in em.get_all_components(CelestialBody):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            # Convert to screen coordinates
            screen_x, screen_y = self.camera.world_to_screen(pos.x, pos.y)

            # Skip if off screen
            if not (-100 < screen_x < SCREEN_WIDTH + 100 and -100 < screen_y < SCREEN_HEIGHT + 100):
                continue

            # Get display radius
            radius = int(get_body_display_radius(body, self.camera.zoom))

            # Draw body
            pygame.draw.circle(self.screen, body.color, (screen_x, screen_y), radius)

            # Draw selection highlight
            if self.selected_entity and entity.id == self.selected_entity.id:
                pygame.draw.circle(
                    self.screen, COLORS['ui_highlight'],
                    (screen_x, screen_y), radius + 3, 2
                )

            # Draw label
            if self.show_labels and radius > 3:
                label = self.font.render(entity.name, True, COLORS['ui_text'])
                self.screen.blit(label, (screen_x + radius + 5, screen_y - 8))

    def _render_stations(self, world: World) -> None:
        """Render stations."""
        from ..solar_system.orbits import Position
        from ..entities.stations import Station

        em = world.entity_manager

        for entity, station in em.get_all_components(Station):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            screen_x, screen_y = self.camera.world_to_screen(pos.x, pos.y)

            # Skip if off screen
            if not (-50 < screen_x < SCREEN_WIDTH + 50 and -50 < screen_y < SCREEN_HEIGHT + 50):
                continue

            # Determine station color based on owner
            is_player_owned = (
                self.player_faction_id and
                station.owner_faction_id == self.player_faction_id
            )

            if is_player_owned:
                station_color = self.player_faction_color
            else:
                # Get owner faction color if owned
                station_color = COLORS['station']
                if station.owner_faction_id:
                    from ..entities.factions import Faction
                    for f_entity, faction in em.get_all_components(Faction):
                        if f_entity.id == station.owner_faction_id:
                            station_color = faction.color
                            break

            # Draw station as square
            size = 6
            rect = pygame.Rect(screen_x - size//2, screen_y - size//2, size, size)
            pygame.draw.rect(self.screen, station_color, rect)

            # Draw player ownership indicator (extra border)
            if is_player_owned:
                pygame.draw.rect(
                    self.screen, self.player_faction_color,
                    rect.inflate(4, 4), 1
                )

            # Draw selection highlight
            if self.selected_entity and entity.id == self.selected_entity.id:
                pygame.draw.rect(
                    self.screen, COLORS['ui_highlight'],
                    rect.inflate(8, 8), 2
                )

            # Draw label
            if self.show_labels and self.camera.zoom > 0.5:
                label = self.font.render(entity.name, True, COLORS['ui_text'])
                self.screen.blit(label, (screen_x + size + 3, screen_y - 8))

    def _render_ships(self, world: World) -> None:
        """Render ships."""
        from ..solar_system.orbits import Position, Velocity
        from ..entities.ships import Ship
        from ..entities.factions import Faction

        em = world.entity_manager

        # Build faction color lookup
        faction_colors: dict[UUID, tuple[int, int, int]] = {}
        for faction_entity, faction in em.get_all_components(Faction):
            faction_colors[faction_entity.id] = faction.color

        for entity, ship in em.get_all_components(Ship):
            pos = em.get_component(entity, Position)
            if not pos:
                continue

            screen_x, screen_y = self.camera.world_to_screen(pos.x, pos.y)

            # Skip if off screen
            if not (-50 < screen_x < SCREEN_WIDTH + 50 and -50 < screen_y < SCREEN_HEIGHT + 50):
                continue

            # Draw ship as triangle
            size = 5
            vel = em.get_component(entity, Velocity)

            # Calculate rotation based on velocity
            if vel and (vel.vx != 0 or vel.vy != 0):
                angle = math.atan2(-vel.vy, vel.vx)  # Negative vy due to screen coords
            else:
                angle = 0

            # Triangle points
            points = [
                (screen_x + size * math.cos(angle),
                 screen_y + size * math.sin(angle)),
                (screen_x + size * math.cos(angle + 2.5),
                 screen_y + size * math.sin(angle + 2.5)),
                (screen_x + size * math.cos(angle - 2.5),
                 screen_y + size * math.sin(angle - 2.5)),
            ]

            # Use faction color if available, otherwise default ship color
            ship_color = COLORS['ship']
            if ship.owner_faction_id and ship.owner_faction_id in faction_colors:
                ship_color = faction_colors[ship.owner_faction_id]

            pygame.draw.polygon(self.screen, ship_color, points)

            # Draw selection highlight
            if self.selected_entity and entity.id == self.selected_entity.id:
                pygame.draw.circle(
                    self.screen, COLORS['ui_highlight'],
                    (screen_x, screen_y), size + 4, 2
                )

    def _render_ui(self, world: World, fps: float) -> None:
        """Render UI elements."""
        # Update and draw player HUD
        self.player_hud.update(world, self.player_faction_id)
        self.player_hud.draw(self.screen, self.font)

        # Update and draw info panel
        self.info_panel.update(world, self.selected_entity)
        self.info_panel.draw(self.screen, self.font)

        # Draw status bar
        self.status_bar.draw_status(self.screen, self.font, world, fps)

        # Draw minimap
        camera_bounds = self.camera.get_visible_bounds()
        self.minimap.draw_minimap(self.screen, world, camera_bounds)

        # Update and draw build menu if visible
        if self.build_menu_visible:
            self._update_build_menu_credits()
            self.build_menu.draw(self.screen, self.font)

        # Update and draw ship purchase menu if visible
        if self.ship_menu_visible:
            self._update_build_menu_credits()
            self.ship_menu.draw(self.screen, self.font)

        # Draw price graph if visible
        if self.price_graph.visible:
            self.price_graph.draw(self.screen, self.font)

        # Update and draw upgrade panel if visible
        if self.upgrade_menu_visible:
            self._update_build_menu_credits()
            self.upgrade_panel.draw(self.screen, self.font)

        # Update and draw trade route panel if visible
        if self.trade_route_visible:
            self._update_trade_route_panel()
            self.trade_route_panel.draw(self.screen, self.font)

    def _render_build_preview(self, world: World) -> None:
        """Render the station build preview at mouse position."""
        if not self.selected_station_type:
            return

        # Convert mouse world position to screen
        screen_x, screen_y = self.camera.world_to_screen(
            self.mouse_world_x, self.mouse_world_y
        )

        # Check if position is valid
        is_valid = True
        if self.building_system:
            valid, msg = self.building_system._validate_position(
                (self.mouse_world_x, self.mouse_world_y),
                world.entity_manager
            )
            is_valid = valid

        # Choose preview color based on validity
        if is_valid:
            preview_color = (100, 255, 100, 128)  # Green for valid
            border_color = (0, 255, 0)
        else:
            preview_color = (255, 100, 100, 128)  # Red for invalid
            border_color = (255, 0, 0)

        # Draw station ghost (semi-transparent square)
        size = 10
        preview_surface = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(preview_surface, preview_color, (0, 0, size, size))
        self.screen.blit(
            preview_surface,
            (screen_x - size // 2, screen_y - size // 2)
        )

        # Draw border
        rect = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        pygame.draw.rect(self.screen, border_color, rect, 2)

        # Draw station type label
        type_names = {
            StationType.OUTPOST: "Outpost",
            StationType.MINING_STATION: "Mining",
            StationType.REFINERY: "Refinery",
            StationType.FACTORY: "Factory",
            StationType.COLONY: "Colony",
            StationType.SHIPYARD: "Shipyard",
            StationType.TRADE_HUB: "Trade Hub",
        }
        label_text = type_names.get(self.selected_station_type, "Station")
        label = self.font.render(label_text, True, border_color)
        self.screen.blit(label, (screen_x + size, screen_y - 8))

        # Draw position info
        pos_text = f"({self.mouse_world_x:.2f}, {self.mouse_world_y:.2f}) AU"
        pos_label = self.font.render(pos_text, True, COLORS['ui_text'])
        self.screen.blit(pos_label, (screen_x + size, screen_y + 8))

    def select_at(self, world_x: float, world_y: float, world: World) -> Entity | None:
        """Try to select an entity at world coordinates.

        Args:
            world_x: World X coordinate
            world_y: World Y coordinate
            world: The game world

        Returns:
            Selected entity or None
        """
        from ..solar_system.orbits import Position
        from ..entities.celestial import CelestialBody, get_body_display_radius
        from ..entities.stations import Station
        from ..entities.ships import Ship

        em = world.entity_manager
        best_entity: Entity | None = None
        best_dist = float('inf')

        # Selection radius in AU (adjust based on zoom)
        select_radius = 0.1 / self.camera.zoom

        # Check all positionable entities
        for entity, pos in em.get_all_components(Position):
            dx = pos.x - world_x
            dy = pos.y - world_y
            dist = math.sqrt(dx * dx + dy * dy)

            # Adjust selection radius based on entity type
            entity_radius = select_radius
            body = em.get_component(entity, CelestialBody)
            if body:
                # Larger selection area for celestial bodies
                screen_radius = get_body_display_radius(body, self.camera.zoom)
                entity_radius = max(select_radius, screen_radius / (self.camera.zoom * 100))

            if dist < entity_radius and dist < best_dist:
                best_dist = dist
                best_entity = entity

        self.selected_entity = best_entity
        return best_entity

    def deselect(self) -> None:
        """Clear selection."""
        self.selected_entity = None

    def toggle_ui(self) -> None:
        """Toggle UI visibility."""
        self.show_ui = not self.show_ui

    def toggle_orbits(self) -> None:
        """Toggle orbit display."""
        self.show_orbits = not self.show_orbits

    def toggle_labels(self) -> None:
        """Toggle label display."""
        self.show_labels = not self.show_labels

    def _render_trade_routes(self, world: World) -> None:
        """Render trade route lines from ships to their destinations."""
        from ..solar_system.orbits import Position
        from ..entities.ships import Ship
        from ..ai.ship_ai import ShipAI

        em = world.entity_manager

        for entity, ship in em.get_all_components(Ship):
            # Get ship position
            ship_pos = em.get_component(entity, Position)
            if not ship_pos:
                continue

            # Get ship AI to find destination
            ship_ai = em.get_component(entity, ShipAI)
            if not ship_ai or not ship_ai.target_entity_id:
                continue

            # Find destination entity position
            dest_pos = None
            for dest_entity, pos in em.get_all_components(Position):
                if dest_entity.id == ship_ai.target_entity_id:
                    dest_pos = pos
                    break

            if not dest_pos:
                continue

            # Convert to screen coordinates
            ship_screen = self.camera.world_to_screen(ship_pos.x, ship_pos.y)
            dest_screen = self.camera.world_to_screen(dest_pos.x, dest_pos.y)

            # Skip if both points are off screen
            if not self._line_visible(ship_screen, dest_screen):
                continue

            # Draw route line (dashed effect via drawing multiple segments)
            route_color = (100, 150, 255, 128)  # Light blue
            pygame.draw.line(
                self.screen, route_color,
                ship_screen, dest_screen, 1
            )

    def _line_visible(self, p1: tuple[int, int], p2: tuple[int, int]) -> bool:
        """Check if a line between two screen points would be visible."""
        margin = 50
        # Simple bounding box check
        min_x = min(p1[0], p2[0])
        max_x = max(p1[0], p2[0])
        min_y = min(p1[1], p2[1])
        max_y = max(p1[1], p2[1])

        return (max_x >= -margin and min_x <= SCREEN_WIDTH + margin and
                max_y >= -margin and min_y <= SCREEN_HEIGHT + margin)

    def toggle_price_graph(self) -> None:
        """Toggle price history graph visibility."""
        self.price_graph.visible = not self.price_graph.visible

    def update_price_history(self, world: World) -> None:
        """Update price history data from world."""
        if not self.price_graph.visible:
            return

        from ..entities.stations import Station
        from ..simulation.economy import Market

        em = world.entity_manager

        # Collect current prices from all markets
        for entity, station in em.get_all_components(Station):
            market = em.get_component(entity, Market)
            if market:
                for resource, price in market.prices.items():
                    # Only track selected resource
                    if self.price_graph.resource_type == resource:
                        self.price_graph.add_price(price)
