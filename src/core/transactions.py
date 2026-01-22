"""Centralized transaction service for all credit and resource transfers.

Provides a single point for all economic transactions with full audit trail.
Benefits:
- Single place for all money movement
- Full ledger for debugging and analytics
- Events for UI notifications
- Easy to add transaction fees, taxes later
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Iterator
from uuid import UUID, uuid4

from .events import EventBus, Event

if TYPE_CHECKING:
    from .ecs import EntityManager


class TransactionType(Enum):
    """Types of economic transactions."""
    CREDIT_TRANSFER = "credit_transfer"
    RESOURCE_TRANSFER = "resource_transfer"
    TRADE = "trade"
    PRODUCTION_COST = "production_cost"
    MAINTENANCE = "maintenance"
    TAX = "tax"
    REWARD = "reward"
    REFUND = "refund"


@dataclass
class Transaction:
    """Record of a single transaction."""
    id: UUID
    timestamp: float  # Game time in days
    transaction_type: TransactionType
    from_entity_id: UUID | None
    to_entity_id: UUID | None
    credits: float = 0.0
    resource_id: str | None = None
    resource_qty: float = 0.0
    reason: str = ""
    success: bool = True
    error_message: str = ""

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()


@dataclass
class TransactionCompleteEvent(Event):
    """Event fired when a transaction completes."""
    transaction_id: UUID = field(default_factory=uuid4)
    transaction_type: str = ""
    from_entity_id: UUID | None = None
    to_entity_id: UUID | None = None
    credits: float = 0.0
    resource_id: str | None = None
    resource_qty: float = 0.0
    success: bool = True


class TransactionService:
    """Centralized service for all economic transactions.

    Manages credit and resource transfers with full audit trail.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._ledger: list[Transaction] = []
        self._max_ledger_size = 10000  # Keep last N transactions
        self._game_time: float = 0.0  # Updated by systems

    def set_game_time(self, game_time_days: float) -> None:
        """Update current game time for transaction timestamps."""
        self._game_time = game_time_days

    def transfer_credits(
        self,
        entity_manager: EntityManager,
        from_entity_id: UUID | None,
        to_entity_id: UUID | None,
        amount: float,
        reason: str = "",
        transaction_type: TransactionType = TransactionType.CREDIT_TRANSFER
    ) -> Transaction:
        """Transfer credits between entities.

        Args:
            entity_manager: Entity manager for component access
            from_entity_id: Source entity (None for system-generated credits)
            to_entity_id: Destination entity (None for system sink)
            amount: Amount of credits to transfer
            reason: Human-readable reason for the transfer
            transaction_type: Type of transaction for categorization

        Returns:
            Transaction record (check .success for result)
        """
        from ..simulation.economy import Market

        transaction = Transaction(
            id=uuid4(),
            timestamp=self._game_time,
            transaction_type=transaction_type,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            credits=amount,
            reason=reason,
        )

        # Validate amount
        if amount < 0:
            transaction.success = False
            transaction.error_message = "Cannot transfer negative credits"
            self._record_transaction(transaction)
            return transaction

        # Get source market (if exists)
        from_market = None
        if from_entity_id:
            from_entity = entity_manager.get_entity(from_entity_id)
            if from_entity:
                from_market = entity_manager.get_component(from_entity, Market)

        # Get destination market (if exists)
        to_market = None
        if to_entity_id:
            to_entity = entity_manager.get_entity(to_entity_id)
            if to_entity:
                to_market = entity_manager.get_component(to_entity, Market)

        # Check if source has sufficient credits
        if from_market and from_market.credits < amount:
            transaction.success = False
            transaction.error_message = f"Insufficient credits: have {from_market.credits}, need {amount}"
            self._record_transaction(transaction)
            return transaction

        # Execute transfer
        if from_market:
            from_market.credits -= amount
        if to_market:
            to_market.credits += amount

        transaction.success = True
        self._record_transaction(transaction)

        # Fire event
        self.event_bus.publish(TransactionCompleteEvent(
            transaction_id=transaction.id,
            transaction_type=transaction_type.value,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            credits=amount,
            success=True,
        ))

        return transaction

    def transfer_resources(
        self,
        entity_manager: EntityManager,
        from_entity_id: UUID | None,
        to_entity_id: UUID | None,
        resource_id: str,
        quantity: float,
        reason: str = ""
    ) -> Transaction:
        """Transfer resources between entities.

        Args:
            entity_manager: Entity manager for component access
            from_entity_id: Source entity (None for system-generated resources)
            to_entity_id: Destination entity (None for system sink)
            resource_id: Resource type ID (string key)
            quantity: Amount to transfer
            reason: Human-readable reason for the transfer

        Returns:
            Transaction record (check .success for result)
        """
        from ..simulation.resources import Inventory, ResourceType

        transaction = Transaction(
            id=uuid4(),
            timestamp=self._game_time,
            transaction_type=TransactionType.RESOURCE_TRANSFER,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            resource_id=resource_id,
            resource_qty=quantity,
            reason=reason,
        )

        # Validate
        if quantity < 0:
            transaction.success = False
            transaction.error_message = "Cannot transfer negative quantity"
            self._record_transaction(transaction)
            return transaction

        # Convert resource_id to ResourceType
        try:
            resource_type = ResourceType(resource_id)
        except ValueError:
            transaction.success = False
            transaction.error_message = f"Unknown resource type: {resource_id}"
            self._record_transaction(transaction)
            return transaction

        # Get source inventory
        from_inv = None
        if from_entity_id:
            from_entity = entity_manager.get_entity(from_entity_id)
            if from_entity:
                from_inv = entity_manager.get_component(from_entity, Inventory)

        # Get destination inventory
        to_inv = None
        if to_entity_id:
            to_entity = entity_manager.get_entity(to_entity_id)
            if to_entity:
                to_inv = entity_manager.get_component(to_entity, Inventory)

        # Check source has resources
        if from_inv and from_inv.get(resource_type) < quantity:
            transaction.success = False
            transaction.error_message = f"Insufficient resources: have {from_inv.get(resource_type)}, need {quantity}"
            self._record_transaction(transaction)
            return transaction

        # Check destination has space
        if to_inv and to_inv.free_space < quantity:
            # Transfer what we can
            quantity = to_inv.free_space
            transaction.resource_qty = quantity

        if quantity <= 0:
            transaction.success = False
            transaction.error_message = "No space in destination"
            self._record_transaction(transaction)
            return transaction

        # Execute transfer
        actual_removed = 0.0
        if from_inv:
            actual_removed = from_inv.remove(resource_type, quantity)
        else:
            actual_removed = quantity

        actual_added = 0.0
        if to_inv:
            actual_added = to_inv.add(resource_type, actual_removed)
        else:
            actual_added = actual_removed

        transaction.resource_qty = actual_added
        transaction.success = True
        self._record_transaction(transaction)

        # Fire event
        self.event_bus.publish(TransactionCompleteEvent(
            transaction_id=transaction.id,
            transaction_type=TransactionType.RESOURCE_TRANSFER.value,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            resource_id=resource_id,
            resource_qty=actual_added,
            success=True,
        ))

        return transaction

    def execute_trade(
        self,
        entity_manager: EntityManager,
        buyer_id: UUID,
        seller_id: UUID,
        resource_id: str,
        quantity: float,
        price_per_unit: float,
        reason: str = ""
    ) -> Transaction:
        """Execute a complete trade transaction (credits + resources).

        Args:
            entity_manager: Entity manager for component access
            buyer_id: Entity buying the resource (receives goods, pays credits)
            seller_id: Entity selling the resource (provides goods, receives credits)
            resource_id: Resource type being traded
            quantity: Amount to trade
            price_per_unit: Price per unit of resource
            reason: Human-readable reason for the trade

        Returns:
            Transaction record (check .success for result)
        """
        from ..simulation.resources import Inventory, ResourceType
        from ..simulation.economy import Market

        total_price = quantity * price_per_unit

        transaction = Transaction(
            id=uuid4(),
            timestamp=self._game_time,
            transaction_type=TransactionType.TRADE,
            from_entity_id=seller_id,
            to_entity_id=buyer_id,
            credits=total_price,
            resource_id=resource_id,
            resource_qty=quantity,
            reason=reason,
        )

        # Get components
        buyer_entity = entity_manager.get_entity(buyer_id)
        seller_entity = entity_manager.get_entity(seller_id)

        if not buyer_entity or not seller_entity:
            transaction.success = False
            transaction.error_message = "Invalid buyer or seller entity"
            self._record_transaction(transaction)
            return transaction

        buyer_market = entity_manager.get_component(buyer_entity, Market)
        seller_inv = entity_manager.get_component(seller_entity, Inventory)

        # Convert resource_id to ResourceType
        try:
            resource_type = ResourceType(resource_id)
        except ValueError:
            transaction.success = False
            transaction.error_message = f"Unknown resource type: {resource_id}"
            self._record_transaction(transaction)
            return transaction

        # Validate buyer has credits
        if buyer_market and buyer_market.credits < total_price:
            transaction.success = False
            transaction.error_message = f"Buyer has insufficient credits: {buyer_market.credits} < {total_price}"
            self._record_transaction(transaction)
            return transaction

        # Validate seller has resources
        if seller_inv and seller_inv.get(resource_type) < quantity:
            transaction.success = False
            transaction.error_message = f"Seller has insufficient resources"
            self._record_transaction(transaction)
            return transaction

        # Execute the trade atomically
        # Transfer credits: buyer -> seller
        credit_tx = self.transfer_credits(
            entity_manager,
            buyer_id,
            seller_id,
            total_price,
            f"Trade: {quantity} {resource_id}",
            TransactionType.TRADE
        )

        if not credit_tx.success:
            transaction.success = False
            transaction.error_message = f"Credit transfer failed: {credit_tx.error_message}"
            self._record_transaction(transaction)
            return transaction

        # Transfer resources: seller -> buyer
        resource_tx = self.transfer_resources(
            entity_manager,
            seller_id,
            buyer_id,
            resource_id,
            quantity,
            f"Trade: sold to {buyer_id}"
        )

        if not resource_tx.success:
            # Rollback credits
            self.transfer_credits(
                entity_manager,
                seller_id,
                buyer_id,
                total_price,
                "Trade rollback",
                TransactionType.REFUND
            )
            transaction.success = False
            transaction.error_message = f"Resource transfer failed: {resource_tx.error_message}"
            self._record_transaction(transaction)
            return transaction

        transaction.success = True
        transaction.resource_qty = resource_tx.resource_qty
        self._record_transaction(transaction)

        return transaction

    def _record_transaction(self, transaction: Transaction) -> None:
        """Add transaction to ledger, trimming if needed."""
        self._ledger.append(transaction)

        # Trim old transactions
        if len(self._ledger) > self._max_ledger_size:
            self._ledger = self._ledger[-self._max_ledger_size:]

    def get_ledger(
        self,
        entity_id: UUID | None = None,
        after: float | None = None,
        transaction_type: TransactionType | None = None,
        limit: int = 100
    ) -> list[Transaction]:
        """Query the transaction ledger.

        Args:
            entity_id: Filter by entity involvement (as sender or receiver)
            after: Only return transactions after this game time
            transaction_type: Filter by transaction type
            limit: Maximum number of transactions to return

        Returns:
            List of matching transactions, newest first
        """
        results = []

        for tx in reversed(self._ledger):
            # Apply filters
            if entity_id and tx.from_entity_id != entity_id and tx.to_entity_id != entity_id:
                continue
            if after and tx.timestamp <= after:
                continue
            if transaction_type and tx.transaction_type != transaction_type:
                continue

            results.append(tx)
            if len(results) >= limit:
                break

        return results

    def get_balance_changes(
        self,
        entity_id: UUID,
        after: float | None = None
    ) -> tuple[float, float]:
        """Calculate net credit and resource changes for an entity.

        Args:
            entity_id: Entity to calculate for
            after: Only include transactions after this game time

        Returns:
            Tuple of (credits_delta, resources_traded_count)
        """
        credits_delta = 0.0
        resources_traded = 0.0

        for tx in self._ledger:
            if after and tx.timestamp <= after:
                continue
            if not tx.success:
                continue

            if tx.to_entity_id == entity_id:
                credits_delta += tx.credits
            if tx.from_entity_id == entity_id:
                credits_delta -= tx.credits

            if tx.resource_qty > 0:
                if tx.to_entity_id == entity_id or tx.from_entity_id == entity_id:
                    resources_traded += tx.resource_qty

        return credits_delta, resources_traded

    def clear_ledger(self) -> None:
        """Clear all transactions (for testing)."""
        self._ledger.clear()


# Singleton instance
_transaction_service: TransactionService | None = None


def get_transaction_service(event_bus: EventBus | None = None) -> TransactionService:
    """Get or create the singleton TransactionService instance."""
    global _transaction_service
    if _transaction_service is None:
        if event_bus is None:
            raise ValueError("EventBus required for initial TransactionService creation")
        _transaction_service = TransactionService(event_bus)
    return _transaction_service


def reset_transaction_service() -> None:
    """Reset the singleton (for testing)."""
    global _transaction_service
    _transaction_service = None
