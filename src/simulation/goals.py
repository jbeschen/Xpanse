"""Goal-based progression system for campaign objectives."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from ..core.ecs import Component, System, EntityManager
from ..core.events import EventBus
from .resources import ResourceType, Inventory
from .events import EventManager, NewsItem, EventCategory, StoryEvent

if TYPE_CHECKING:
    pass


class GoalStatus(Enum):
    """Status of a goal."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class EarthShipyardGoal(Component):
    """Goal to build the public shipyard at Earth.

    Earth needs to collect raw materials from space before the shipyard can be built.
    This is the first major objective of the game.
    """
    status: GoalStatus = GoalStatus.PENDING

    # Resource requirements to build the shipyard
    required_iron_ore: float = 500.0
    required_silicates: float = 300.0
    required_rare_earths: float = 100.0

    # Current collected amounts (tracked at Earth market)
    collected_iron_ore: float = 0.0
    collected_silicates: float = 0.0
    collected_rare_earths: float = 0.0

    # Reference to Earth market entity
    earth_market_id: UUID | None = None

    # Freelancer faction (will own the shipyard)
    freelancer_faction_id: UUID | None = None

    def get_progress(self) -> float:
        """Get overall completion progress (0.0 to 1.0)."""
        iron_progress = min(1.0, self.collected_iron_ore / self.required_iron_ore)
        silicates_progress = min(1.0, self.collected_silicates / self.required_silicates)
        rare_earths_progress = min(1.0, self.collected_rare_earths / self.required_rare_earths)
        return (iron_progress + silicates_progress + rare_earths_progress) / 3.0

    def is_complete(self) -> bool:
        """Check if all resources have been collected."""
        return (
            self.collected_iron_ore >= self.required_iron_ore and
            self.collected_silicates >= self.required_silicates and
            self.collected_rare_earths >= self.required_rare_earths
        )


class GoalSystem(System):
    """System that tracks and updates game goals."""

    priority = 70  # Run after events

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._check_interval = 5.0  # Check every 5 game days
        self._time_since_check = 0.0

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update goal progress."""
        self._time_since_check += dt

        if self._time_since_check < self._check_interval:
            return

        self._time_since_check = 0.0

        # Update Earth shipyard goal
        for entity, goal in entity_manager.get_all_components(EarthShipyardGoal):
            if goal.status == GoalStatus.COMPLETED:
                continue

            self._update_earth_shipyard_goal(goal, entity_manager)

    def _update_earth_shipyard_goal(
        self,
        goal: EarthShipyardGoal,
        entity_manager: EntityManager
    ) -> None:
        """Update Earth shipyard goal progress."""
        if not goal.earth_market_id:
            return

        # Get Earth market inventory
        earth_market = entity_manager.get_entity(goal.earth_market_id)
        if not earth_market:
            return

        inventory = entity_manager.get_component(earth_market, Inventory)
        if not inventory:
            return

        # Check current resources at Earth market
        goal.collected_iron_ore = inventory.get(ResourceType.IRON_ORE)
        goal.collected_silicates = inventory.get(ResourceType.SILICATES)
        goal.collected_rare_earths = inventory.get(ResourceType.RARE_EARTHS)

        # Update status
        if goal.status == GoalStatus.PENDING:
            # Start tracking when any resources arrive
            if goal.get_progress() > 0:
                goal.status = GoalStatus.IN_PROGRESS
                self._announce_goal_started(entity_manager)

        # Check for completion
        if goal.is_complete() and goal.status != GoalStatus.COMPLETED:
            self._complete_earth_shipyard_goal(goal, entity_manager)

    def _announce_goal_started(self, entity_manager: EntityManager) -> None:
        """Announce that the shipyard goal has started."""
        # Get event manager
        for entity, em in entity_manager.get_all_components(EventManager):
            news = NewsItem(
                headline="Earth Begins Shipyard Construction Project",
                body=(
                    "Earth's governing council has announced a major infrastructure project: "
                    "the construction of a public orbital shipyard. The facility will require "
                    "significant quantities of raw materials from space - Iron Ore, Silicates, "
                    "and Rare Earths. Corporations are encouraged to contribute materials to "
                    "the effort. Upon completion, the shipyard will be available to all factions."
                ),
                timestamp=0.0,
                category=EventCategory.ECONOMIC,
                importance=4,
            )
            em.news_feed.insert(0, news)
            break

    def _complete_earth_shipyard_goal(
        self,
        goal: EarthShipyardGoal,
        entity_manager: EntityManager
    ) -> None:
        """Complete the Earth shipyard goal - build the shipyard."""
        from ..entities.stations import create_station, StationType
        from ..solar_system.orbits import Position

        goal.status = GoalStatus.COMPLETED

        # Get Earth market position to build shipyard nearby
        earth_market = entity_manager.get_entity(goal.earth_market_id)
        if not earth_market:
            return

        earth_pos = entity_manager.get_component(earth_market, Position)
        if not earth_pos:
            return

        # Consume the resources from Earth market
        inventory = entity_manager.get_component(earth_market, Inventory)
        if inventory:
            inventory.remove(ResourceType.IRON_ORE, goal.required_iron_ore)
            inventory.remove(ResourceType.SILICATES, goal.required_silicates)
            inventory.remove(ResourceType.RARE_EARTHS, goal.required_rare_earths)

        # Create the shipyard
        # We need access to World to create entities - this is a workaround
        # The shipyard will be created by the main game loop checking goal status

        # Queue a story event announcing completion
        for entity, em in entity_manager.get_all_components(EventManager):
            story_event = StoryEvent(
                id="shipyard_complete",
                title="EARTH PUBLIC SHIPYARD OPERATIONAL",
                body=(
                    "After weeks of construction, Earth's first public orbital shipyard is now "
                    "operational. The facility, built from materials gathered across the solar "
                    "system, represents humanity's growing industrial capacity in space.\n\n"
                    "The shipyard is managed by the Freelancers Guild, an independent consortium "
                    "of traders and mechanics. All corporations may purchase vessels here.\n\n"
                    "With ship construction capability now available, the race to expand across "
                    "the solar system accelerates. More ships mean more trade routes, more "
                    "stations, and more opportunities.\n\n"
                    "The Freelancers Guild has also begun hiring independent traders to haul "
                    "cargo between stations. These freelance haulers will help balance supply "
                    "and demand across the growing colonial network."
                ),
                category=EventCategory.TECHNOLOGY,
                chapter=0,
                sequence=1,
                objectives=[
                    "Purchase additional ships at the shipyard",
                    "Establish mining operations in the asteroid belt",
                    "Build a refinery to process raw materials",
                ],
            )
            em.queue_story_event(story_event)

            # Also add news
            news = NewsItem(
                headline="Earth Public Shipyard Now Operational!",
                body=(
                    "The orbital shipyard construction is complete! Ships are now available "
                    "for purchase by all corporations. The Freelancers Guild will manage "
                    "the facility and provide independent trading services."
                ),
                timestamp=0.0,
                category=EventCategory.TECHNOLOGY,
                importance=5,
            )
            em.news_feed.insert(0, news)
            break
