# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins

"""
Production AI Agent Example

Demonstrates the complete three-layer architecture:
- Orion: Plugin-based tools
- KOMPOSOS-IV: Categorical knowledge
- COG: Tiered verification

This example shows:
1. Creating an agent
2. Adding custom plugins
3. Learning facts
4. Verifying claims
5. Session management
"""

import asyncio
import sys
import os

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'orion-main', 'src'))

from orion_core import Plugin
from orion_core.plugin import on

from orion_komposos_cog import Agent, AgentConfig
from cog.schema import VerificationStatus, CogRelation, RelationType


# ============================================================================
# Custom Plugin: Mock Web Search
# ============================================================================

class WebSearchPlugin(Plugin):
    """Simple web search plugin for demonstration."""

    def __init__(self, core):
        super().__init__(
            core,
            name="web_search",
            version="1.0.0",
            provides={"web_search"},
            events_published={"search.result"},
        )

    async def search(self, query: str):
        """Mock web search."""
        # In production, this would call a real search API
        results = {
            "python machine learning": [
                {"title": "Python has extensive ML libraries", "confidence": 0.95},
                {"title": "TensorFlow and PyTorch use Python", "confidence": 0.9},
            ],
            "python typing": [
                {"title": "Python 3.5+ has typing module", "confidence": 0.9},
                {"title": "Type hints improve code safety", "confidence": 0.85},
            ],
        }

        result = results.get(query.lower(), [])

        await self.emit("search.result", {"query": query, "results": result})
        return result

    @on("query.search")
    async def on_search(self, event):
        """Handle search events."""
        return await self.search(event.data["query"])


# ============================================================================
# Example Usage
# ============================================================================

async def main():
    """Main example demonstrating all three layers."""

    print("=" * 70)
    print("Three-Layer AI Agent Example")
    print("=" * 70)
    print()

    # ========================================================================
    # Step 1: Create and start agent
    # ========================================================================

    print("Step 1: Creating agent...")
    config = AgentConfig(
        knowledge_db_path="example_knowledge.db",
        sessions_enabled=True,
        log_level="INFO",
    )
    agent = Agent(config)

    print("Starting agent...")
    await agent.start()
    print("✓ Agent started!\n")

    # ========================================================================
    # Step 2: Add custom plugin (Orion layer)
    # ========================================================================

    print("Step 2: Adding web search plugin (Orion layer)...")
    search_plugin = WebSearchPlugin(agent.orion)
    await agent.add_plugin(search_plugin)
    print("✓ Plugin added!\n")

    # ========================================================================
    # Step 3: Use plugin to gather facts
    # ========================================================================

    print("Step 3: Using web search to gather facts...")
    search_results = await search_plugin.search("python machine learning")
    print(f"Found {len(search_results)} results:")
    for r in search_results:
        print(f"  - {r['title']} (confidence: {r['confidence']})")
    print()

    # ========================================================================
    # Step 4: Store facts in knowledge graph (KOMPOSOS-IV layer)
    # ========================================================================

    print("Step 4: Storing facts in categorical knowledge graph...")

    # Learn from search results
    await agent.add_knowledge(
        source="Python",
        target="ML_libraries",
        relation="has",
        confidence=0.95,
        evidence="Python has extensive ML libraries"
    )

    await agent.add_knowledge(
        source="ML_libraries",
        target="TensorFlow",
        relation="includes",
        confidence=0.9,
        evidence="TensorFlow is a Python ML library"
    )

    await agent.add_knowledge(
        source="ML_libraries",
        target="PyTorch",
        relation="includes",
        confidence=0.9,
        evidence="PyTorch is a Python ML library"
    )

    await agent.add_knowledge(
        source="Python",
        target="typing",
        relation="supports",
        confidence=0.9,
        evidence="Python 3.5+ has typing module"
    )

    print("✓ Facts stored in knowledge graph!\n")

    # ========================================================================
    # Step 5: Query knowledge graph
    # ========================================================================

    print("Step 5: Querying knowledge graph...")

    # Find paths
    paths = await agent.find_paths("Python", "TensorFlow")
    print(f"Found {len(paths)} path(s) from Python to TensorFlow:")
    for i, path in enumerate(paths, 1):
        print(f"  Path {i}: length={path['length']}, weight={path['weight']:.3f}")
        print(f"    {' → '.join(path['morphisms'])}")
    print()

    # Get neighbors
    result = await agent.query_knowledge("Python")
    print(f"Python neighbors: {len(result['outgoing'])} outgoing")
    for neighbor in result['outgoing']:
        print(f"  → {neighbor['target']} ({neighbor['relation']})")
    print()

    # ========================================================================
    # Step 6: Verify claims (COG layer)
    # ========================================================================

    print("Step 6: Verifying claims with tiered reasoning (COG layer)...")

    # Claim 1: Direct edge (Tier 0)
    print("\nClaim 1: 'Python has ML_libraries'")
    result = await agent.verify_claim(
        source="Python",
        target="ML_libraries",
        relation="has"
    )
    print(f"  Status: {result.status.value}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Tier reached: {result.tier_reached}")
    print(f"  Explanation: {result.explanation}")

    # Claim 2: Compositional path (Tier 1)
    print("\nClaim 2: 'Python includes TensorFlow' (compositional)")
    result = await agent.verify_claim(
        source="Python",
        target="TensorFlow",
        relation="includes"
    )
    print(f"  Status: {result.status.value}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Tier reached: {result.tier_reached}")
    print(f"  Explanation: {result.explanation}")
    if result.supporting_paths:
        print(f"  Proof path: {result.supporting_paths[0]}")

    # Claim 3: Unknown (will fail)
    print("\nClaim 3: 'Python supports Rust' (unknown)")
    result = await agent.verify_claim(
        source="Python",
        target="Rust",
        relation="supports"
    )
    print(f"  Status: {result.status.value}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Tier reached: {result.tier_reached}")
    print(f"  Explanation: {result.explanation}")
    print()

    # ========================================================================
    # Step 7: Session management
    # ========================================================================

    print("Step 7: Session management (per-user memory)...")

    # Load user session
    user_session = await agent.load_session("alice")
    print("✓ Loaded session for user 'alice'")

    # User-specific knowledge
    user_cog = user_session["cog_engine"]
    user_cog.session.add_relation(
        CogRelation(
            source="Alice",
            target="Python",
            relation_type=RelationType.PART_OF,
            confidence=1.0,
        )
    )
    print("✓ Added user-specific knowledge")

    # Save session
    await agent.save_session("alice")
    print("✓ Session saved\n")

    # ========================================================================
    # Step 8: Statistics
    # ========================================================================

    print("Step 8: Agent statistics...")
    stats = await agent.get_statistics()

    print(f"\nOrion (Application Layer):")
    print(f"  Plugins: {stats['orion']['plugins']}")

    print(f"\nKOMPOSOS-IV (Mathematical Layer):")
    print(f"  Objects: {stats['komposos']['objects']}")
    print(f"  Morphisms: {stats['komposos']['morphisms']}")

    print(f"\nCOG (Reasoning Layer):")
    print(f"  Concepts added: {stats['cog']['activity']['concepts_added']}")
    print(f"  Relations added: {stats['cog']['activity']['relations_added']}")
    print(f"  Checks performed: {stats['cog']['activity']['checks_performed']}")

    if 'sessions' in stats:
        print(f"\nSessions:")
        print(f"  Active: {stats['sessions']['active']}")

    print()

    # ========================================================================
    # Cleanup
    # ========================================================================

    print("Stopping agent...")
    await agent.stop()
    print("✓ Agent stopped cleanly!\n")

    print("=" * 70)
    print("Example complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
