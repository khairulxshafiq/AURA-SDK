"""Unit tests for aura/core/budget.py."""

import pytest
from aura.config import AuraConfig
from aura.core.budget import BudgetExceededError, BudgetManager


def test_budget_prompt_truncation():
    config = AuraConfig(max_prompt_chars=100)
    mgr = BudgetManager(config=config)
    long_prompt = "A" * 200
    truncated = mgr.check_prompt_length(long_prompt)
    assert len(truncated) < 200
    assert "[...TRUNCATED FOR COST GOVERNANCE]" in truncated


def test_budget_token_tracking_and_limit():
    config = AuraConfig(daily_token_limit=1000)
    mgr = BudgetManager(config=config)
    mgr.track_tokens(500)
    assert mgr.get_status()["daily_tokens_used"] == 500

    with pytest.raises(BudgetExceededError):
        mgr.track_tokens(600)
