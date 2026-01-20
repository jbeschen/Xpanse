# Xpanse - Solar System Economic Simulation

## Project Overview
A single-player space economic simulation inspired by X4: Foundations. Players guide humanity's expansion from Earth across the solar system through outposts, colonies, resource extraction, manufacturing, and trade.

## Architecture
- **Pattern**: Entity-Component-System (ECS)
- **Graphics**: Pygame 2.x
- **Data**: JSON for configuration, SQLite for saves (future)

## Key Concepts

### Resource Tiers
- Tier 0 (Raw): Water Ice, Iron Ore, Silicates, Rare Earths, Helium-3
- Tier 1 (Basic): Refined Metal, Silicon, Water, Fuel
- Tier 2 (Advanced): Electronics, Machinery, Life Support Units
- Tier 3 (Complex): Habitat Modules, Ship Components, Advanced Tech

### Economic Model
- Each station has local supply/demand
- Prices fluctuate based on inventory
- Trade ships seek profitable routes
- Emergent economy from independent actors

## Running the Game
```bash
python -m src.main
```

## Running Tests
```bash
pytest tests/
```

## Code Organization
- `src/core/` - ECS framework, world state, events
- `src/simulation/` - Economy, production, resources, trade
- `src/entities/` - Celestial bodies, stations, ships, factions
- `src/solar_system/` - Orbital mechanics, solar system data
- `src/ai/` - Faction and ship AI
- `src/ui/` - Pygame rendering and input
- `src/data/` - JSON game data files
