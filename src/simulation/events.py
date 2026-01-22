"""Dynamic event system - crises, opportunities, and emergent storytelling."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable
from uuid import UUID
import random
import math

from ..core.ecs import Component, System, EntityManager
from ..core.events import EventBus
from .resources import ResourceType, Inventory

if TYPE_CHECKING:
    pass


class EventSeverity(Enum):
    """How impactful an event is."""
    MINOR = "minor"      # Small price fluctuation
    MODERATE = "moderate"  # Noticeable market impact
    MAJOR = "major"      # Significant disruption
    CRITICAL = "critical"  # Crisis-level event


class EventCategory(Enum):
    """Categories of events."""
    ECONOMIC = "economic"      # Market fluctuations, trade deals
    DISASTER = "disaster"      # Accidents, natural disasters
    POLITICAL = "political"    # Faction relations, policy changes
    DISCOVERY = "discovery"    # New resources, anomalies found
    CRIME = "crime"           # Piracy, smuggling, theft
    TECHNOLOGY = "technology"  # Breakthroughs, failures


@dataclass
class GameEvent:
    """A dynamic event that affects the game world."""
    id: str
    title: str
    description: str
    category: EventCategory
    severity: EventSeverity
    timestamp: float = 0.0  # Game time when event occurred
    duration: float = 0.0   # How long effects last (0 = instant)
    affected_entity_id: UUID | None = None
    affected_resource: ResourceType | None = None
    price_modifier: float = 1.0  # Multiplier on affected resource price
    supply_modifier: float = 1.0  # Multiplier on production/extraction
    expired: bool = False


@dataclass
class Contract:
    """A delivery contract generated from supply/demand."""
    id: str
    title: str
    description: str
    client_station_id: UUID
    client_name: str
    resource: ResourceType
    amount: float
    reward: float
    deadline: float  # Game time deadline
    bonus_reward: float = 0.0  # Extra for early delivery
    penalty: float = 0.0  # Reputation penalty for failure
    accepted: bool = False
    completed: bool = False
    failed: bool = False
    accepted_by: UUID | None = None  # Faction that accepted


@dataclass
class Discovery:
    """Something discovered during travel."""
    id: str
    title: str
    description: str
    discovery_type: str  # "derelict", "anomaly", "deposit", "signal"
    position: tuple[float, float]
    reward_credits: float = 0.0
    reward_resources: dict[ResourceType, float] = field(default_factory=dict)
    discovered_by: UUID | None = None
    claimed: bool = False


@dataclass
class NewsItem:
    """A news item reflecting game state."""
    headline: str
    body: str
    timestamp: float
    category: EventCategory
    importance: int = 1  # 1-5, higher = more important


@dataclass
class StoryEvent:
    """A campaign/story event that pauses the game and requires player acknowledgment.

    Used for major narrative moments, tutorial steps, mission briefings, and rewards.
    These events freeze the game until the player dismisses them.
    """
    id: str
    title: str
    body: str  # Main narrative text
    category: EventCategory
    image_key: str = ""  # Optional image identifier for future use

    # Campaign progression
    chapter: int = 0  # Campaign chapter (0 = prologue)
    sequence: int = 0  # Order within chapter

    # Mission/objective data (optional)
    objectives: list[str] = field(default_factory=list)  # List of objective descriptions
    rewards_credits: float = 0.0
    rewards_resources: dict[ResourceType, float] = field(default_factory=dict)

    # State
    acknowledged: bool = False  # Player has seen and dismissed this
    triggered_at: float = 0.0  # Game time when triggered

    # Trigger conditions (for future events)
    trigger_condition: str = ""  # e.g., "station_built", "credits_reached_100000"
    trigger_value: float = 0.0  # Associated value for condition


# Campaign story events - these are queued and shown in sequence
STORY_EVENTS = {
    "xdrive_announcement": StoryEvent(
        id="xdrive_announcement",
        title="THE X-DRIVE ERA BEGINS",
        body=(
            "BREAKTHROUGH: Stellar Propulsion Labs has unveiled the X-Drive, a revolutionary "
            "propulsion system that will reshape humanity's future.\n\n"
            "For decades, the outer planets remained tantalizingly out of reach - months of "
            "travel through the void made colonization impractical. That changes today.\n\n"
            "With the X-Drive, Jupiter is now just 40 days away. Saturn in 90. The entire "
            "solar system lies open before us.\n\n"
            "Corporations are already mobilizing. The race to claim the riches of the outer "
            "system has begun. Mining rights, trade routes, strategic positions - everything "
            "is up for grabs.\n\n"
            "As the founder of Stellar Dynamics, you have a unique opportunity. Your small "
            "fleet of freighters and modest capital could be the foundation of an interplanetary "
            "empire... or a footnote in someone else's success story.\n\n"
            "The solar system gold rush has begun. Make your mark."
        ),
        category=EventCategory.TECHNOLOGY,
        chapter=0,
        sequence=0,
        objectives=[
            "Explore the solar system with your freighters",
            "Establish your first outpost",
            "Build a profitable trade route",
        ],
    ),
}


# Event templates that can be triggered
EVENT_TEMPLATES = {
    # Economic events
    "trade_boom": {
        "title": "{station} Reports Record Trade Volume",
        "description": "Increased demand at {station} has driven prices up for {resource}.",
        "category": EventCategory.ECONOMIC,
        "severity": EventSeverity.MINOR,
        "price_modifier": 1.3,
        "duration": 300,  # 5 minutes
    },
    "market_crash": {
        "title": "Market Panic at {station}",
        "description": "Oversupply of {resource} has caused prices to plummet at {station}.",
        "category": EventCategory.ECONOMIC,
        "severity": EventSeverity.MODERATE,
        "price_modifier": 0.5,
        "duration": 600,
    },
    "trade_deal": {
        "title": "{faction} Signs Trade Agreement",
        "description": "{faction} has negotiated preferential trade terms, boosting commerce.",
        "category": EventCategory.POLITICAL,
        "severity": EventSeverity.MINOR,
        "price_modifier": 0.9,
        "duration": 900,
    },

    # Disaster events
    "solar_flare": {
        "title": "Solar Storm Disrupts Operations",
        "description": "A solar flare has damaged electronics across the inner system. Production halted at affected stations.",
        "category": EventCategory.DISASTER,
        "severity": EventSeverity.MAJOR,
        "supply_modifier": 0.3,
        "duration": 180,
    },
    "station_accident": {
        "title": "Industrial Accident at {station}",
        "description": "An explosion at {station} has reduced {resource} production capacity.",
        "category": EventCategory.DISASTER,
        "severity": EventSeverity.MODERATE,
        "supply_modifier": 0.5,
        "duration": 450,
    },
    "asteroid_impact": {
        "title": "Asteroid Strike Near {body}",
        "description": "A small asteroid impact has disrupted mining operations near {body}.",
        "category": EventCategory.DISASTER,
        "severity": EventSeverity.MAJOR,
        "supply_modifier": 0.2,
        "duration": 600,
    },

    # Crime events
    "pirate_raid": {
        "title": "Pirates Strike {station}",
        "description": "Pirates have raided supply convoys near {station}. Traders advised to use caution.",
        "category": EventCategory.CRIME,
        "severity": EventSeverity.MODERATE,
        "price_modifier": 1.4,
        "duration": 300,
    },
    "smuggling_ring": {
        "title": "Smuggling Ring Busted at {station}",
        "description": "Authorities have seized contraband at {station}. {resource} supplies affected.",
        "category": EventCategory.CRIME,
        "severity": EventSeverity.MINOR,
        "supply_modifier": 0.8,
        "duration": 240,
    },

    # Discovery events
    "rich_deposit": {
        "title": "Rich {resource} Deposit Found Near {body}",
        "description": "Surveyors report a major {resource} deposit. Mining rights being auctioned.",
        "category": EventCategory.DISCOVERY,
        "severity": EventSeverity.MODERATE,
        "price_modifier": 0.8,  # Anticipation of future supply
        "duration": 1200,
    },
    "derelict_found": {
        "title": "Derelict Vessel Discovered",
        "description": "An abandoned ship has been found drifting near {body}. Salvage rights available.",
        "category": EventCategory.DISCOVERY,
        "severity": EventSeverity.MINOR,
        "duration": 0,
    },

    # Technology events
    "tech_breakthrough": {
        "title": "{faction} Announces Production Breakthrough",
        "description": "New manufacturing techniques at {station} have improved {resource} output.",
        "category": EventCategory.TECHNOLOGY,
        "severity": EventSeverity.MODERATE,
        "supply_modifier": 1.5,
        "duration": 900,
    },
    "equipment_failure": {
        "title": "Equipment Malfunction at {station}",
        "description": "Critical machinery failure has halted {resource} production.",
        "category": EventCategory.TECHNOLOGY,
        "severity": EventSeverity.MODERATE,
        "supply_modifier": 0.1,
        "duration": 360,
    },

    # Political events
    "faction_tension": {
        "title": "Tensions Rise Between {faction} and {faction2}",
        "description": "Trade restrictions imposed. Expect price increases in affected regions.",
        "category": EventCategory.POLITICAL,
        "severity": EventSeverity.MAJOR,
        "price_modifier": 1.5,
        "duration": 1800,
    },
    "colony_growth": {
        "title": "{station} Population Milestone",
        "description": "{station} celebrates population growth. Demand for goods expected to increase.",
        "category": EventCategory.POLITICAL,
        "severity": EventSeverity.MINOR,
        "price_modifier": 1.2,
        "duration": 600,
    },
}


@dataclass
@dataclass
class EventManager(Component):
    """Component that tracks active events, contracts, discoveries, and story events."""
    active_events: list[GameEvent] = field(default_factory=list)
    available_contracts: list[Contract] = field(default_factory=list)
    pending_discoveries: list[Discovery] = field(default_factory=list)
    news_feed: list[NewsItem] = field(default_factory=list)
    event_history: list[GameEvent] = field(default_factory=list)

    # Story/campaign events
    pending_story_events: list[StoryEvent] = field(default_factory=list)
    completed_story_events: list[str] = field(default_factory=list)  # IDs of completed events
    current_story_event: StoryEvent | None = None  # Event currently being displayed

    # Counters for unique IDs
    _event_counter: int = 0
    _contract_counter: int = 0
    _discovery_counter: int = 0

    def queue_story_event(self, event: StoryEvent) -> None:
        """Queue a story event to be shown to the player."""
        if event.id not in self.completed_story_events:
            self.pending_story_events.append(event)
            # Sort by chapter then sequence
            self.pending_story_events.sort(key=lambda e: (e.chapter, e.sequence))

    def show_next_story_event(self) -> StoryEvent | None:
        """Pop the next story event to display. Returns None if none pending."""
        if self.current_story_event is not None:
            return self.current_story_event  # Already showing one

        if self.pending_story_events:
            self.current_story_event = self.pending_story_events.pop(0)
            return self.current_story_event

        return None

    def acknowledge_story_event(self) -> None:
        """Player has acknowledged the current story event."""
        if self.current_story_event:
            self.current_story_event.acknowledged = True
            self.completed_story_events.append(self.current_story_event.id)
            self.current_story_event = None

    def has_pending_story(self) -> bool:
        """Check if there are story events waiting or being shown."""
        return self.current_story_event is not None or len(self.pending_story_events) > 0


class EventSystem(System):
    """System that generates and manages dynamic events."""

    priority = 60  # Run after economy

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._time_since_event_check = 0.0
        self._time_since_contract_check = 0.0
        self._event_check_interval = 30.0  # Check for new events every 30 seconds
        self._contract_check_interval = 45.0  # Generate contracts every 45 seconds
        self._base_event_chance = 0.15  # 15% chance of event per check

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Update events, contracts, and discoveries."""
        # Get or create event manager
        event_manager = self._get_event_manager(entity_manager)
        if not event_manager:
            return

        # Update event timers
        self._time_since_event_check += dt
        self._time_since_contract_check += dt

        # Expire old events
        self._expire_events(event_manager, entity_manager)

        # Check for new random events
        if self._time_since_event_check >= self._event_check_interval:
            self._time_since_event_check = 0.0
            if random.random() < self._base_event_chance:
                self._generate_random_event(event_manager, entity_manager)

        # Generate new contracts based on supply/demand
        if self._time_since_contract_check >= self._contract_check_interval:
            self._time_since_contract_check = 0.0
            self._generate_contracts(event_manager, entity_manager)

        # Clean up old news
        self._clean_news_feed(event_manager)

    def _get_event_manager(self, entity_manager: EntityManager) -> EventManager | None:
        """Get the global event manager, creating if needed."""
        for entity, em in entity_manager.get_all_components(EventManager):
            return em

        # Create new event manager on a system entity
        from ..core.ecs import Entity
        system_entity = entity_manager.create_entity(name="Event System", tags={"system"})
        event_mgr = EventManager()
        entity_manager.add_component(system_entity, event_mgr)
        return event_mgr

    def _expire_events(self, event_manager: EventManager, entity_manager: EntityManager) -> None:
        """Expire events that have run their duration."""
        from ..core.world import World

        current_time = 0.0  # Would get from world.game_time

        for event in event_manager.active_events:
            if event.duration > 0:
                event.duration -= self._event_check_interval
                if event.duration <= 0:
                    event.expired = True
                    event_manager.event_history.append(event)

        # Remove expired events
        event_manager.active_events = [e for e in event_manager.active_events if not e.expired]

    def _generate_random_event(self, event_manager: EventManager, entity_manager: EntityManager) -> None:
        """Generate a random event based on game state."""
        from ..entities.stations import Station
        from ..entities.factions import Faction
        from ..solar_system.orbits import Position

        # Get lists of stations and factions for event generation
        stations = list(entity_manager.get_all_components(Station))
        factions = list(entity_manager.get_all_components(Faction))

        if not stations:
            return

        # Pick a random event template
        template_key = random.choice(list(EVENT_TEMPLATES.keys()))
        template = EVENT_TEMPLATES[template_key]

        # Pick affected entities
        station_entity, station = random.choice(stations)
        resource = random.choice(list(ResourceType))

        faction_entity = None
        faction_name = "Unknown"
        if factions:
            faction_entity, faction = random.choice(factions)
            faction_name = faction_entity.name

        # Get body name from station
        body_name = station.parent_body or "Unknown"

        # Format event text
        title = template["title"].format(
            station=station_entity.name,
            resource=resource.value.replace("_", " ").title(),
            body=body_name,
            faction=faction_name,
            faction2=factions[1][0].name if len(factions) > 1 else "Unknown",
        )
        description = template["description"].format(
            station=station_entity.name,
            resource=resource.value.replace("_", " ").title(),
            body=body_name,
            faction=faction_name,
        )

        # Create event
        event_manager._event_counter += 1
        event = GameEvent(
            id=f"event_{event_manager._event_counter}",
            title=title,
            description=description,
            category=template["category"],
            severity=template["severity"],
            duration=template.get("duration", 0),
            affected_entity_id=station_entity.id,
            affected_resource=resource,
            price_modifier=template.get("price_modifier", 1.0),
            supply_modifier=template.get("supply_modifier", 1.0),
        )

        event_manager.active_events.append(event)

        # Generate news item
        importance = {
            EventSeverity.MINOR: 1,
            EventSeverity.MODERATE: 2,
            EventSeverity.MAJOR: 3,
            EventSeverity.CRITICAL: 5,
        }.get(event.severity, 1)

        news = NewsItem(
            headline=title,
            body=description,
            timestamp=0.0,  # Would use game time
            category=event.category,
            importance=importance,
        )
        event_manager.news_feed.insert(0, news)

        # Apply event effects to market
        self._apply_event_effects(event, entity_manager)

    def _apply_event_effects(self, event: GameEvent, entity_manager: EntityManager) -> None:
        """Apply event effects to affected entities."""
        from .economy import Market

        if not event.affected_entity_id:
            return

        entity = entity_manager.get_entity(event.affected_entity_id)
        if not entity:
            return

        market = entity_manager.get_component(entity, Market)
        if market and event.affected_resource:
            # Modify prices temporarily
            base_price = market.prices.get(event.affected_resource, 100.0)
            market.prices[event.affected_resource] = base_price * event.price_modifier

    def _generate_contracts(self, event_manager: EventManager, entity_manager: EntityManager) -> None:
        """Generate delivery contracts based on supply/demand."""
        from ..entities.stations import Station
        from .economy import Market, Population

        # Find stations with high demand (low stock relative to target)
        for entity, station in entity_manager.get_all_components(Station):
            market = entity_manager.get_component(entity, Market)
            inventory = entity_manager.get_component(entity, Inventory)
            population = entity_manager.get_component(entity, Population)

            if not market or not inventory:
                continue

            # Check each resource this station buys
            for resource, buys in market.buys.items():
                if not buys:
                    continue

                current = inventory.get(resource)
                target = market.target_stock.get(resource, 100)

                # Generate contract if stock is below 30% of target
                if current < target * 0.3 and random.random() < 0.3:
                    # Already have a contract for this?
                    existing = [c for c in event_manager.available_contracts
                               if c.client_station_id == entity.id
                               and c.resource == resource
                               and not c.completed and not c.failed]
                    if existing:
                        continue

                    # Calculate contract details
                    amount = min((target - current) * 0.5, 100)  # Request half the deficit
                    if amount < 10:
                        continue

                    # Price is premium over market rate
                    base_price = market.get_buy_price(resource) or 100
                    reward = amount * base_price * 1.3  # 30% premium
                    bonus = reward * 0.2  # 20% bonus for early delivery

                    # Urgency affects deadline
                    urgency = 1.0 - (current / target) if target > 0 else 1.0
                    deadline_seconds = 600 - (urgency * 300)  # 5-10 minutes

                    event_manager._contract_counter += 1
                    contract = Contract(
                        id=f"contract_{event_manager._contract_counter}",
                        title=f"Urgent: {resource.value.replace('_', ' ').title()} Needed",
                        description=f"{entity.name} urgently requires {amount:.0f} units of {resource.value.replace('_', ' ')}.",
                        client_station_id=entity.id,
                        client_name=entity.name,
                        resource=resource,
                        amount=amount,
                        reward=reward,
                        deadline=deadline_seconds,
                        bonus_reward=bonus,
                        penalty=0.1,  # Reputation penalty
                    )

                    event_manager.available_contracts.append(contract)

                    # Add news about contract
                    if urgency > 0.7:
                        news = NewsItem(
                            headline=f"{entity.name} Issues Emergency Supply Request",
                            body=f"Critical shortage of {resource.value.replace('_', ' ')} reported. Premium rates offered.",
                            timestamp=0.0,
                            category=EventCategory.ECONOMIC,
                            importance=3,
                        )
                        event_manager.news_feed.insert(0, news)

        # Clean up old/completed contracts
        event_manager.available_contracts = [
            c for c in event_manager.available_contracts
            if not c.completed and not c.failed and c.deadline > 0
        ]

        # Update contract deadlines
        for contract in event_manager.available_contracts:
            contract.deadline -= self._contract_check_interval
            if contract.deadline <= 0 and contract.accepted and not contract.completed:
                contract.failed = True

    def _clean_news_feed(self, event_manager: EventManager) -> None:
        """Keep news feed at reasonable size."""
        max_news = 20
        if len(event_manager.news_feed) > max_news:
            event_manager.news_feed = event_manager.news_feed[:max_news]


class DiscoverySystem(System):
    """System that generates discoveries for traveling ships and surveys new bodies."""

    priority = 38  # Run before ship AI

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._discovery_chance = 0.002  # 0.2% chance per update while traveling

    def update(self, dt: float, entity_manager: EntityManager) -> None:
        """Check for discoveries by traveling ships and survey bodies."""
        from ..entities.ships import Ship
        from ..entities.celestial import CelestialBody
        from ..solar_system.orbits import NavigationTarget, Position, Velocity, ParentBody
        from .resources import ResourceKnowledge, ResourceDeposit

        event_manager = None
        for entity, em in entity_manager.get_all_components(EventManager):
            event_manager = em
            break

        if not event_manager:
            return

        # Get resource knowledge singleton
        knowledge = None
        for entity, k in entity_manager.get_all_components(ResourceKnowledge):
            knowledge = k
            break

        # Check each ship for body surveys (ships that just arrived)
        if knowledge:
            for entity, ship in entity_manager.get_all_components(Ship):
                parent_body = entity_manager.get_component(entity, ParentBody)

                # Ship is docked/orbiting a body - check if we can survey it
                if parent_body:
                    body_name = parent_body.parent_name
                    if knowledge.survey(body_name):
                        # Newly surveyed! Generate news
                        self._generate_survey_news(
                            body_name, ship, event_manager, entity_manager
                        )

        # Check each ship that's traveling for random discoveries
        for entity, ship in entity_manager.get_all_components(Ship):
            nav = entity_manager.get_component(entity, NavigationTarget)
            vel = entity_manager.get_component(entity, Velocity)
            pos = entity_manager.get_component(entity, Position)

            # Only ships actively traveling can make discoveries
            if not nav or not vel or not pos:
                continue

            if vel.speed < 0.01:  # Must be moving (reduced for slower X-Drive speeds)
                continue

            # Random discovery check
            if random.random() < self._discovery_chance:
                self._generate_discovery(entity, ship, pos, event_manager, entity_manager)

    def _generate_survey_news(
        self,
        body_name: str,
        ship,
        event_manager: EventManager,
        entity_manager: EntityManager
    ) -> None:
        """Generate news for a newly surveyed body."""
        from ..entities.celestial import CelestialBody
        from ..solar_system.bodies import SOLAR_SYSTEM_DATA
        from .resources import ResourceDeposit

        # Get body data for resource info
        body_data = SOLAR_SYSTEM_DATA.get(body_name)
        if not body_data:
            return

        # Build resource description
        resource_desc = "No significant deposits found."
        if body_data.resources:
            resources_str = ", ".join(
                f"{r.value.replace('_', ' ').title()} (richness: {rich:.1f})"
                for r, rich in body_data.resources
            )
            resource_desc = f"Resources detected: {resources_str}"

        news = NewsItem(
            headline=f"Survey Complete: {body_name} Resources Catalogued",
            body=(
                f"A ship has completed the first detailed survey of {body_name}. "
                f"{resource_desc} "
                f"This data is now available to all corporations for mining and development planning."
            ),
            timestamp=0.0,  # Will be set by current game time
            category=EventCategory.DISCOVERY,
            importance=3,
        )
        event_manager.news_feed.insert(0, news)

    def _generate_discovery(
        self,
        ship_entity,
        ship,
        pos,
        event_manager: EventManager,
        entity_manager: EntityManager
    ) -> None:
        """Generate a discovery near the ship."""
        discovery_types = [
            ("derelict", "Derelict Vessel", "An abandoned ship drifting in space. Salvage potential.", 0.4),
            ("anomaly", "Sensor Anomaly", "Unusual readings detected. Worth investigating.", 0.2),
            ("debris", "Debris Field", "Scattered cargo containers. Some may contain valuables.", 0.3),
            ("signal", "Distress Signal", "A faint emergency beacon. Someone may need help.", 0.1),
        ]

        # Pick type based on weights
        roll = random.random()
        cumulative = 0
        discovery_type = discovery_types[0]
        for dt in discovery_types:
            cumulative += dt[3]
            if roll < cumulative:
                discovery_type = dt
                break

        # Generate rewards
        reward_credits = random.randint(500, 5000)
        reward_resources = {}

        if discovery_type[0] == "derelict":
            reward_credits = random.randint(2000, 10000)
            # Random salvage
            possible_resources = [
                ResourceType.REFINED_METAL,
                ResourceType.ELECTRONICS,
                ResourceType.MACHINERY,
                ResourceType.FUEL,
            ]
            for _ in range(random.randint(1, 3)):
                res = random.choice(possible_resources)
                reward_resources[res] = random.randint(10, 50)

        elif discovery_type[0] == "debris":
            reward_credits = random.randint(500, 2000)
            # Random cargo
            possible_resources = list(ResourceType)
            res = random.choice(possible_resources)
            reward_resources[res] = random.randint(5, 30)

        elif discovery_type[0] == "signal":
            # Rescue mission - reputation reward (represented as credits for now)
            reward_credits = random.randint(1000, 3000)

        # Create discovery near ship position
        offset_x = random.uniform(-0.05, 0.05)
        offset_y = random.uniform(-0.05, 0.05)
        discovery_pos = (pos.x + offset_x, pos.y + offset_y)

        event_manager._discovery_counter += 1
        discovery = Discovery(
            id=f"discovery_{event_manager._discovery_counter}",
            title=discovery_type[1],
            description=discovery_type[2],
            discovery_type=discovery_type[0],
            position=discovery_pos,
            reward_credits=reward_credits,
            reward_resources=reward_resources,
            discovered_by=ship.owner_faction_id,
        )

        event_manager.pending_discoveries.append(discovery)

        # Generate news
        news = NewsItem(
            headline=f"{discovery_type[1]} Detected",
            body=f"Ship {ship_entity.name} reports: {discovery_type[2]}",
            timestamp=0.0,
            category=EventCategory.DISCOVERY,
            importance=2,
        )
        event_manager.news_feed.insert(0, news)


def get_active_events(entity_manager: EntityManager) -> list[GameEvent]:
    """Get all active events."""
    for entity, em in entity_manager.get_all_components(EventManager):
        return em.active_events
    return []


def get_available_contracts(entity_manager: EntityManager) -> list[Contract]:
    """Get all available contracts."""
    for entity, em in entity_manager.get_all_components(EventManager):
        return [c for c in em.available_contracts if not c.accepted]
    return []


def get_news_feed(entity_manager: EntityManager, limit: int = 10) -> list[NewsItem]:
    """Get recent news items."""
    for entity, em in entity_manager.get_all_components(EventManager):
        return em.news_feed[:limit]
    return []


def accept_contract(entity_manager: EntityManager, contract_id: str, faction_id: UUID) -> bool:
    """Accept a contract for a faction."""
    for entity, em in entity_manager.get_all_components(EventManager):
        for contract in em.available_contracts:
            if contract.id == contract_id and not contract.accepted:
                contract.accepted = True
                contract.accepted_by = faction_id
                return True
    return False


def claim_discovery(entity_manager: EntityManager, discovery_id: str, faction_id: UUID) -> Discovery | None:
    """Claim a discovery and get rewards."""
    for entity, em in entity_manager.get_all_components(EventManager):
        for i, discovery in enumerate(em.pending_discoveries):
            if discovery.id == discovery_id and not discovery.claimed:
                discovery.claimed = True
                em.pending_discoveries.pop(i)
                return discovery
    return None
