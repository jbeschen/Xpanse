"""System execution priority definitions.

Defines the order in which systems update during the game loop.
Lower numbers execute first.
"""
from enum import IntEnum


class SystemPriority(IntEnum):
    """Priority levels for system execution order.

    Systems are sorted by priority and executed in ascending order.
    Use these constants when defining System.priority to ensure
    consistent execution order across the codebase.
    """
    # Input and physics (first)
    INPUT = 0
    PHYSICS = 5
    ORBITAL = 8

    # Movement and navigation
    NAVIGATION = 10
    MOVEMENT = 12

    # Resource extraction and production
    EXTRACTION = 15
    PRODUCTION = 20

    # AI decision making
    AI_FACTION = 25
    AI_SHIP = 30
    AI_SHIP_BEHAVIOR = 32

    # Trade execution
    TRADE = 40

    # Population and economy
    POPULATION = 45
    ECONOMY = 50

    # Transaction processing
    TRANSACTIONS = 55

    # Events and goals
    DISCOVERY = 58
    EVENTS = 60
    GOALS = 65

    # Building and construction
    BUILDING = 70

    # Spawning
    SPAWNING = 75

    # Late update (cleanup, etc.)
    LATE_UPDATE = 90

    # Rendering (last)
    RENDER = 100


# Convenience mapping from system name to priority
SYSTEM_PRIORITIES = {
    "OrbitalSystem": SystemPriority.ORBITAL,
    "NavigationSystem": SystemPriority.NAVIGATION,
    "MovementSystem": SystemPriority.MOVEMENT,
    "ExtractionSystem": SystemPriority.EXTRACTION,
    "ProductionSystem": SystemPriority.PRODUCTION,
    "FactionAI": SystemPriority.AI_FACTION,
    "ShipAI": SystemPriority.AI_SHIP,
    "ShipAISystemV2": SystemPriority.AI_SHIP_BEHAVIOR,
    "TradeSystem": SystemPriority.TRADE,
    "PopulationSystem": SystemPriority.POPULATION,
    "EconomySystem": SystemPriority.ECONOMY,
    "DiscoverySystem": SystemPriority.DISCOVERY,
    "EventSystem": SystemPriority.EVENTS,
    "GoalSystem": SystemPriority.GOALS,
    "BuildingSystem": SystemPriority.BUILDING,
    "FreelancerSpawner": SystemPriority.SPAWNING,
}
