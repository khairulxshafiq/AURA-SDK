"""Lifecycle Hooks for AuraOne agent runtime."""

from __future__ import annotations

from typing import Any
import structlog
from google.antigravity import types
from google.antigravity.hooks import hooks

from aura.core.budget import budget

logger = structlog.get_logger("aura.core.runtime.hooks")


@hooks.on_session_start
async def on_session_start() -> None:
    """Log session initialization."""
    logger.info("AuraOne Agent Session started")


@hooks.on_session_end
async def on_session_end() -> None:
    """Log session shutdown."""
    logger.info("AuraOne Agent Session ended")


@hooks.pre_turn
async def pre_turn_guard(data: str) -> types.HookResult:
    """Intercept inbound turn: inspect prompt, check budget, truncate if oversized."""
    logger.info("Pre-turn hook triggered", prompt_length=len(data))

    # Cost Governance Check
    sanitized_prompt = budget.check_prompt_length(data)
    estimated_tokens = len(sanitized_prompt) // 4
    budget.track_tokens(estimated_tokens)

    return types.HookResult(allow=True)


@hooks.pre_tool_call_decide
async def pre_tool_call_guard(data: types.ToolCall) -> types.HookResult:
    """Audit tool execution before proceeding."""
    logger.info("Pre-tool call audit", tool_name=data.name)
    return types.HookResult(allow=True)


@hooks.on_tool_error
async def on_tool_error_handler(data: Exception) -> Any:
    """Log tool errors without crashing agent loop."""
    logger.error("Tool execution failed", error=str(data))
    return None
