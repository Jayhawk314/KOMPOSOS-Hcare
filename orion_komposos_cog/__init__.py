# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins
#
# This meta-framework is dual-licensed (Apache-2.0 OR KOMPOSOS-IV-Commercial).
# It integrates with Orion Core, which is separately licensed under MIT.
# Orion Core © Borkwork (https://github.com/borkwork/orion-framework)

"""
Orion-KOMPOSOS-COG Meta-Framework

The complete three-layer architecture for production AI agents:
- Layer 1: Orion (extensibility & hot-loading)
- Layer 2: KOMPOSOS-IV (mathematical foundation)
- Layer 3: COG (intelligent reasoning)

Usage:
    from orion_komposos_cog import Agent

    agent = Agent()
    await agent.start()

    # Add tools as Orion plugins
    await agent.add_plugin(WebSearchPlugin)

    # Use COG reasoning
    result = await agent.verify_claim(
        source="Python",
        target="ML",
        relation="supports"
    )
"""

__version__ = "0.1.0"

from .agent import Agent
from .config import AgentConfig

__all__ = [
    "Agent",
    "AgentConfig",
]
