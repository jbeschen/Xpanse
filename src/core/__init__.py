"""Core simulation engine."""
from .ecs import Entity, Component, System, EntityManager
from .world import World
from .events import EventBus, Event
from .system_priority import SystemPriority
from .registries import ResourceRegistry, RecipeRegistry, get_resource_registry, get_recipe_registry
from .transactions import TransactionService, Transaction, TransactionType, get_transaction_service

__all__ = [
    'Entity', 'Component', 'System', 'EntityManager',
    'World', 'EventBus', 'Event',
    'SystemPriority',
    'ResourceRegistry', 'RecipeRegistry', 'get_resource_registry', 'get_recipe_registry',
    'TransactionService', 'Transaction', 'TransactionType', 'get_transaction_service',
]
