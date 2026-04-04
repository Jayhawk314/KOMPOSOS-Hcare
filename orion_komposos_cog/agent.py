# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins
#
# This meta-framework is dual-licensed (Apache-2.0 OR KOMPOSOS-IV-Commercial).
# It integrates with Orion Core, which is separately licensed under MIT.
# Orion Core © Borkwork (https://github.com/borkwork/orion-framework)

"""
The Agent class - unified interface for the three-layer architecture.
"""

from __future__ import annotations

import sys
import os
import logging
from typing import Any, Dict, List, Optional, Type

# Add orion-main to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'orion-main', 'src'))

# Import Orion (MIT licensed)
from orion_core import Core, Plugin
from orion_core.protocols import CoreConfig

# Import KOMPOSOS-IV
from core.category import Category

# Import COG
from cog.session import CogSession
from cog.engine import CogEngine
from cog.schema import CogClaim, CheckResult

# Import bridge plugins
from bridges import CogReasoningPlugin, KnowledgeManagerPlugin, SessionManagerPlugin

# Import config
from .config import AgentConfig


logger = logging.getLogger(__name__)


class Agent:
    """
    The complete three-layer AI agent.

    Combines:
    - Orion Core: Plugin framework with hot-loading
    - KOMPOSOS-IV: Categorical knowledge foundation
    - COG: Tiered verification and reasoning

    Example:
        agent = Agent()
        await agent.start()

        # Add capabilities
        await agent.add_plugin(WebSearchPlugin)

        # Use reasoning
        result = await agent.verify_claim(
            source="Python",
            target="ML",
            relation="supports"
        )
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        """Initialize the three-layer agent.

        Args:
            config: Optional agent configuration
        """
        self.config = config or AgentConfig()

        # Setup logging
        logging.basicConfig(level=self.config.log_level)

        # Layer 1: Orion Core (application framework)
        orion_config = CoreConfig(
            tick_rate=self.config.tick_rate,
            hook_precaching=self.config.hook_precaching,
        )
        self.orion = Core(config=orion_config)

        # Layer 2: KOMPOSOS-IV Category (mathematical runtime)
        self.category = Category(db_path=self.config.knowledge_db_path)

        # Layer 3: COG (cognitive co-processor)
        self.cog_session = CogSession(db_path=self.config.cog_db_path)
        self.cog_engine = CogEngine(self.cog_session)

        # Bridge plugins (not yet registered)
        self._cog_plugin: Optional[CogReasoningPlugin] = None
        self._knowledge_plugin: Optional[KnowledgeManagerPlugin] = None
        self._session_plugin: Optional[SessionManagerPlugin] = None

        # Started state
        self._started = False

    async def start(self):
        """Start the agent and register bridge plugins."""
        if self._started:
            logger.warning("Agent already started")
            return

        logger.info("Starting three-layer agent...")

        # Register bridge plugins
        logger.info("Registering COG reasoning plugin...")
        self._cog_plugin = CogReasoningPlugin(
            self.orion,
            cog_session=self.cog_session,
        )
        await self.orion.register_plugin(self._cog_plugin)

        logger.info("Registering knowledge manager plugin...")
        self._knowledge_plugin = KnowledgeManagerPlugin(
            self.orion,
            category=self.category,
        )
        await self.orion.register_plugin(self._knowledge_plugin)

        if self.config.sessions_enabled:
            logger.info("Registering session manager plugin...")
            self._session_plugin = SessionManagerPlugin(
                self.orion,
                sessions_dir=self.config.sessions_dir,
            )
            await self.orion.register_plugin(self._session_plugin)

        # Start Orion core
        await self.orion.start()

        self._started = True
        logger.info("Agent started successfully!")

    async def stop(self):
        """Stop the agent."""
        if not self._started:
            return

        logger.info("Stopping agent...")
        await self.orion.stop()
        self._started = False
        logger.info("Agent stopped")

    # ========================================================================
    # Plugin Management (Orion Layer)
    # ========================================================================

    async def add_plugin(self, plugin: Plugin) -> bool:
        """Add a plugin to the agent.

        Args:
            plugin: Plugin instance

        Returns:
            True if registered successfully
        """
        if not self._started:
            raise RuntimeError("Agent not started. Call await agent.start() first.")

        await self.orion.register_plugin(plugin)
        return True

    async def remove_plugin(self, plugin_id: str) -> bool:
        """Remove a plugin from the agent.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if removed successfully
        """
        await self.orion.unregister_plugin(plugin_id)
        return True

    async def get_capability(self, capability_name: str):
        """Get a capability provider.

        Args:
            capability_name: Capability name

        Returns:
            Capability provider plugin
        """
        plugins = await self.orion.list()
        providers = plugins.capability.provides(capability_name)
        return await providers.first()

    # ========================================================================
    # Knowledge Management (KOMPOSOS-IV Layer)
    # ========================================================================

    async def add_knowledge(
        self,
        source: str,
        target: str,
        relation: str,
        confidence: float = 1.0,
        evidence: str = "",
    ) -> bool:
        """Add knowledge to the graph.

        Args:
            source: Source concept
            target: Target concept
            relation: Relationship type
            confidence: Confidence weight (0-1)
            evidence: Supporting evidence

        Returns:
            True if added successfully
        """
        if self._cog_plugin:
            return await self._cog_plugin.add_knowledge(
                source, target, relation, confidence, evidence
            )
        else:
            # Fallback to direct category access
            return self.category.connect(source, target, relation, confidence=confidence)

    async def query_knowledge(
        self,
        source: str,
        target: Optional[str] = None,
        relation: Optional[str] = None,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """Query the knowledge graph.

        Args:
            source: Source concept
            target: Optional target (finds paths)
            relation: Optional relation filter
            max_results: Maximum results

        Returns:
            Query results
        """
        if self._cog_plugin:
            return await self._cog_plugin.query_knowledge(
                source, target, relation, max_results
            )
        else:
            # Fallback to direct category access
            return self.cog_engine.query(source, target, relation, max_results)

    async def find_paths(
        self, source: str, target: str, max_length: int = 10
    ) -> List[Dict]:
        """Find paths between concepts.

        Args:
            source: Source concept
            target: Target concept
            max_length: Maximum path length

        Returns:
            List of paths
        """
        if self._knowledge_plugin:
            return await self._knowledge_plugin.find_paths(source, target, max_length)
        else:
            # Fallback to direct category access
            paths = self.category.find_paths(source, target, max_length)
            return [
                {
                    "morphisms": p.morphism_ids,
                    "length": p.length,
                    "weight": p.weight,
                }
                for p in paths
            ]

    # ========================================================================
    # Reasoning (COG Layer)
    # ========================================================================

    async def verify_claim(
        self,
        source: str,
        target: str,
        relation: str,
        confidence: float = 0.5,
        max_tier: Optional[int] = None,
    ) -> CheckResult:
        """Verify a claim through tiered reasoning.

        Args:
            source: Source concept
            target: Target concept
            relation: Relationship type
            confidence: Initial confidence
            max_tier: Maximum verification tier (0-4)

        Returns:
            CheckResult with verification status
        """
        max_tier = max_tier or self.config.max_verification_tier

        if self._cog_plugin:
            return await self._cog_plugin.verify_claim(
                source, target, relation, confidence, max_tier
            )
        else:
            # Fallback to direct COG access
            claim = CogClaim(source, target, relation, confidence)
            return self.cog_engine.check_claim(claim, depth=max_tier)

    async def explain_verification(
        self, source: str, target: str, relation: str
    ) -> Dict[str, Any]:
        """Get detailed explanation of verification.

        Args:
            source: Source concept
            target: Target concept
            relation: Relationship type

        Returns:
            Detailed explanation
        """
        if self._cog_plugin:
            return await self._cog_plugin.explain_verification(source, target, relation)
        else:
            claim = CogClaim(source, target, relation)
            return self.cog_engine.explain(claim)

    # ========================================================================
    # Session Management
    # ========================================================================

    async def load_session(self, user_id: str) -> Dict[str, Any]:
        """Load a user session.

        Args:
            user_id: User identifier

        Returns:
            Session data
        """
        if not self._session_plugin:
            raise RuntimeError("Session management not enabled")

        return await self._session_plugin.get_or_create_session(user_id)

    async def save_session(self, user_id: str) -> bool:
        """Save a user session.

        Args:
            user_id: User identifier

        Returns:
            True if saved successfully
        """
        if not self._session_plugin:
            raise RuntimeError("Session management not enabled")

        return await self._session_plugin.save_session(user_id)

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        """Get agent statistics."""
        stats = {
            "orion": {
                "plugins": len(await self.orion.list()),
            },
            "komposos": {
                "objects": len(self.category.objects()),
                "morphisms": len(self.category.morphisms()),
            },
            "cog": self.cog_session.get_summary() if self.cog_session else {},
        }

        if self._session_plugin:
            stats["sessions"] = {
                "active": len(await self._session_plugin.list_active_sessions()),
            }

        return stats
