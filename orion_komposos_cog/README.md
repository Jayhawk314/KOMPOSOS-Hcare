# Orion-KOMPOSOS-COG Meta-Framework

The complete three-layer architecture for production AI agents.

## Overview

This meta-framework combines:
- **Orion Core** (MIT, by Borkwork): Plugin framework with hot-loading
- **KOMPOSOS-IV** (Apache-2.0/Commercial): Categorical knowledge foundation
- **COG** (Apache-2.0/Commercial): Tiered verification and reasoning

## Quick Start

```python
from orion_komposos_cog import Agent, AgentConfig

# Create agent
agent = Agent()
await agent.start()

# Add knowledge
await agent.add_knowledge(
    source="Python",
    target="ML",
    relation="supports",
    confidence=0.9
)

# Verify claim
result = await agent.verify_claim(
    source="Python",
    target="ML",
    relation="supports"
)

print(f"Verified: {result.status}")  # AGREE
print(f"Tier: {result.tier_reached}")  # 0 (direct lookup)
```

## Architecture

```
┌─────────────────────────────────────┐
│  Agent (Unified API)                │
└─────────────────────────────────────┘
         ↓         ↓         ↓
┌────────┴───┬────┴────┬────┴─────┐
│  Orion     │KOMPOSOS │   COG    │
│  Plugins   │Category │ Tiers    │
│ (tools)    │ (math)  │(reasoning│
└────────────┴─────────┴──────────┘
```

## Features

### Layer 1: Orion (Extensibility)
- Hot-loadable plugins
- Event-driven communication
- Capability-based dependencies

### Layer 2: KOMPOSOS-IV (Foundation)
- Categorical knowledge graph
- Automatic persistence (SQLite)
- Compositional inference

### Layer 3: COG (Intelligence)
- Tiered verification (0-4)
- Energy-based routing
- Formal proofs when needed

## API

### Agent Creation

```python
config = AgentConfig(
    knowledge_db_path="knowledge.db",
    sessions_enabled=True,
    max_verification_tier=4
)
agent = Agent(config)
await agent.start()
```

### Plugin Management

```python
# Add plugin
await agent.add_plugin(WebSearchPlugin(agent.orion))

# Get capability
search = await agent.get_capability("web_search")
results = await search.search("query")
```

### Knowledge Management

```python
# Add facts
await agent.add_knowledge(
    source="A",
    target="B",
    relation="relates",
    confidence=0.9
)

# Query
result = await agent.query_knowledge("A", "B")

# Find paths
paths = await agent.find_paths("A", "B")
```

### Reasoning

```python
# Verify claim
result = await agent.verify_claim(
    source="A",
    target="B",
    relation="relates"
)

# Get explanation
explanation = await agent.explain_verification("A", "B", "relates")
```

### Session Management

```python
# Load user session
session = await agent.load_session("user_123")

# Save session
await agent.save_session("user_123")
```

## Configuration

```python
@dataclass
class AgentConfig:
    # Orion
    tick_rate: int = 60
    hook_precaching: str = "on_core_start"

    # KOMPOSOS-IV
    knowledge_db_path: str = "knowledge.db"

    # COG
    cog_db_path: str = ":memory:"
    max_verification_tier: int = 4

    # Sessions
    sessions_enabled: bool = True
    sessions_dir: str = "sessions"

    # Logging
    log_level: str = "INFO"
```

## Examples

See `examples/production_agent.py` for a complete working example.

## License

This meta-framework is dual-licensed:
- Apache License 2.0, OR
- KOMPOSOS-IV Commercial License

It integrates with Orion Core (MIT licensed by Borkwork).

## Attribution

- **Orion Core**: © Borkwork (MIT) - https://github.com/borkwork/orion-framework
- **KOMPOSOS-IV**: © 2024-2026 James Ray Hawkins
- **Meta-Framework**: © 2024-2026 James Ray Hawkins
