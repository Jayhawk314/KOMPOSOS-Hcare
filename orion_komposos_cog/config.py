# SPDX-License-Identifier: Apache-2.0 OR LicenseRef-KOMPOSOS-IV-Commercial
# Copyright (c) 2024-2026 James Ray Hawkins

"""Agent configuration."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    """Configuration for the three-layer agent."""

    # Orion configuration
    tick_rate: int = 60
    hook_precaching: str = "on_core_start"

    # KOMPOSOS-IV configuration
    knowledge_db_path: str = "knowledge.db"

    # COG configuration
    cog_db_path: str = ":memory:"
    max_verification_tier: int = 4

    # Session management
    sessions_enabled: bool = True
    sessions_dir: str = "sessions"

    # Logging
    log_level: str = "INFO"
