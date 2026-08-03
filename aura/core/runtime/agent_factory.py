"""Agent Factory — The ONLY module that configures Antigravity Agent runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import structlog
from google.antigravity import Agent, LocalAgentConfig, types

from aura.config import AuraConfig
from aura.core.runtime.hooks import (
    on_session_end,
    on_session_start,
    pre_tool_call_guard,
    pre_turn_guard,
)
from aura.core.runtime.policies import build_aura_policies

logger = structlog.get_logger("aura.core.runtime.agent_factory")


class AgentFactory:
    """Builds and configures Antigravity Agent instances with AuraOne policies."""

    def __init__(self, config: AuraConfig | None = None) -> None:
        self.config = config or AuraConfig()

    def build_agent_config(
        self,
        tools: list[Callable] | None = None,
        skills_paths: list[str] | None = None,
        ask_user_handler: Callable | None = None,
        system_instructions: str = "You are AuraOne, a helpful personal AI operating system.",
    ) -> LocalAgentConfig:
        """Construct typed LocalAgentConfig for Agent creation."""
        keys = self.config.get_gemini_keys()
        primary_key = keys[0] if keys else None

        policies = build_aura_policies(ask_user_handler=ask_user_handler)
        skills_paths = skills_paths or []

        # Include default skills directory if present
        default_skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        if default_skills_dir.exists() and str(default_skills_dir) not in skills_paths:
            skills_paths.append(str(default_skills_dir))

        agent_config = LocalAgentConfig(
            api_key=primary_key,
            model=self.config.gemini_model,
            app_data_dir=str(self.config.app_data_dir),
            system_instructions=system_instructions,
            tools=tools or [],
            skills_paths=skills_paths,
            policies=policies,
            hooks=[
                on_session_start,
                on_session_end,
                pre_turn_guard,
                pre_tool_call_guard,
            ],
            capabilities=types.CapabilitiesConfig(enable_subagents=True),
        )
        logger.info(
            "Built LocalAgentConfig",
            model=self.config.gemini_model,
            tools_count=len(tools or []),
            skills_count=len(skills_paths),
        )
        return agent_config

    def create_agent(
        self,
        tools: list[Callable] | None = None,
        skills_paths: list[str] | None = None,
        ask_user_handler: Callable | None = None,
    ) -> Agent:
        """Instantiate Agent context with configured LocalAgentConfig."""
        config = self.build_agent_config(
            tools=tools, skills_paths=skills_paths, ask_user_handler=ask_user_handler
        )
        return Agent(config=config)


# Global singleton instance
agent_factory = AgentFactory()
