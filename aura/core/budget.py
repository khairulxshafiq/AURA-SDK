"""Cost governance and token budget enforcement for AuraOne."""

from __future__ import annotations

import time
from typing import Any
import structlog
from aura.config import AuraConfig

logger = structlog.get_logger("aura.core.budget")


class BudgetExceededError(Exception):
    """Raised when daily budget or token limits are exceeded."""

    pass


class BudgetManager:
    """Manages daily token limits, cost caps, and prompt character truncation."""

    def __init__(self, config: AuraConfig | None = None) -> None:
        self.config = config or AuraConfig()
        self._daily_tokens: int = 0
        self._last_reset_day: int = time.localtime().tm_mday

    def _check_day_reset(self) -> None:
        current_day = time.localtime().tm_mday
        if current_day != self._last_reset_day:
            logger.info("Resetting daily token budget counter", previous=self._daily_tokens)
            self._daily_tokens = 0
            self._last_reset_day = current_day

    def check_prompt_length(self, prompt: str) -> str:
        """Truncate prompt if it exceeds max_prompt_chars to protect token limit."""
        if len(prompt) > self.config.max_prompt_chars:
            logger.warning(
                "Truncating oversized prompt",
                original_len=len(prompt),
                max_len=self.config.max_prompt_chars,
            )
            return prompt[: self.config.max_prompt_chars] + "\n[...TRUNCATED FOR COST GOVERNANCE]"
        return prompt

    def track_tokens(self, estimated_tokens: int) -> None:
        """Track consumed tokens and enforce daily cap limit."""
        self._check_day_reset()
        if self._daily_tokens + estimated_tokens > self.config.daily_token_limit:
            err_msg = (
                f"Daily token budget limit reached ({self._daily_tokens}/{self.config.daily_token_limit}). "
                f"Request of ~{estimated_tokens} tokens blocked by Cost Governance Guard."
            )
            logger.error("Budget cap exceeded", current_tokens=self._daily_tokens, limit=self.config.daily_token_limit)
            raise BudgetExceededError(err_msg)

        self._daily_tokens += estimated_tokens
        logger.debug("Tokens tracked", added=estimated_tokens, total_daily=self._daily_tokens)

    def get_status(self) -> dict[str, Any]:
        """Return budget consumption status."""
        self._check_day_reset()
        return {
            "daily_tokens_used": self._daily_tokens,
            "daily_token_limit": self.config.daily_token_limit,
            "usage_pct": round((self._daily_tokens / self.config.daily_token_limit) * 100, 2),
        }


# Global singleton instance
budget = BudgetManager()
