"""Event bus for decoupled communication between systems."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any
from uuid import UUID


@dataclass
class Event:
    """Base class for all events."""
    pass


@dataclass
class EntityCreatedEvent(Event):
    """Fired when an entity is created."""
    entity_id: UUID
    entity_name: str


@dataclass
class EntityDestroyedEvent(Event):
    """Fired when an entity is destroyed."""
    entity_id: UUID


@dataclass
class ResourceTransferEvent(Event):
    """Fired when resources are transferred between entities."""
    source_id: UUID | None
    target_id: UUID
    resource_type: str
    amount: float


@dataclass
class ProductionCompleteEvent(Event):
    """Fired when a production cycle completes."""
    entity_id: UUID
    recipe_id: str
    outputs: dict[str, float]


@dataclass
class TradeCompleteEvent(Event):
    """Fired when a trade is completed."""
    buyer_id: UUID
    seller_id: UUID
    resource_type: str
    amount: float
    total_price: float


@dataclass
class PriceChangeEvent(Event):
    """Fired when market prices change significantly."""
    station_id: UUID
    resource_type: str
    old_price: float
    new_price: float


@dataclass
class ShipArrivedEvent(Event):
    """Fired when a ship arrives at a destination."""
    ship_id: UUID
    destination_id: UUID


@dataclass
class FactionEvent(Event):
    """Base class for faction-related events."""
    faction_id: UUID


@dataclass
class StationBuiltEvent(Event):
    """Fired when a station is constructed."""
    station_id: UUID
    faction_id: UUID
    station_type: str  # StationType.value
    position: tuple[float, float]
    cost: float


@dataclass
class ShipPurchasedEvent(Event):
    """Fired when a ship is purchased."""
    ship_id: UUID
    faction_id: UUID
    ship_type: str  # ShipType.value
    shipyard_id: UUID
    cost: float


@dataclass
class NotificationEvent(Event):
    """Fired for UI notifications."""
    message: str
    notification_type: str = "info"  # info, success, warning, error
    duration: float = 5.0  # How long to display (seconds)


@dataclass
class DividendEvent(Event):
    """Fired when a station pays dividends to its owner faction."""
    station_id: UUID
    faction_id: UUID
    amount: float
    station_name: str = ""


EventHandler = Callable[[Event], None]


class EventBus:
    """Central event bus for publishing and subscribing to events."""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = {}
        self._queued_events: list[Event] = []
        self._processing: bool = False

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.

        If called during event processing, the event is queued.
        """
        if self._processing:
            self._queued_events.append(event)
            return

        self._dispatch(event)

    def _dispatch(self, event: Event) -> None:
        """Dispatch an event to handlers."""
        event_type = type(event)

        # Check for exact type match
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                handler(event)

        # Check for base class matches
        for registered_type, handlers in self._handlers.items():
            if registered_type != event_type and isinstance(event, registered_type):
                for handler in handlers:
                    handler(event)

    def process_queue(self) -> None:
        """Process all queued events."""
        self._processing = True

        while self._queued_events:
            # Process current queue, new events go to a fresh queue
            current_queue = self._queued_events
            self._queued_events = []

            for event in current_queue:
                self._dispatch(event)

        self._processing = False

    def clear(self) -> None:
        """Clear all handlers and queued events."""
        self._handlers.clear()
        self._queued_events.clear()
