"""Declarative Safety Policy Matrix for AuraOne (Deny-by-default)."""

from __future__ import annotations

from typing import Any, Callable
import structlog
from google.antigravity.hooks import policy

logger = structlog.get_logger("aura.core.runtime.policies")


def build_aura_policies(ask_user_handler: Callable | None = None) -> list[Any]:
    """Build the official deny-by-default policy matrix for AuraOne.

    Rules:
    - DENY: run_command (shell execution hard blocked).
    - ASK_USER: airtable_create_record, upload_gdrive (requires approval).
    - ALLOW: read-only tools, technical analysis math, in-process memory.
    """
    policies = [
        # Hard deny on shell command execution
        policy.deny("run_command", name="deny_shell_execution"),
        # Ask user for external state mutations
        policy.ask_user("airtable_create_record", handler=ask_user_handler, name="confirm_airtable_write"),
        policy.ask_user("upload_gdrive", handler=ask_user_handler, name="confirm_gdrive_write"),
        # Allow safe read-only & local execution tools
        policy.allow("view_file"),
        policy.allow("fetch_ohlcv"),
        policy.allow("compute_indicators"),
        policy.allow("fetch_fundamentals"),
        policy.allow("run_trading_analysis"),
        policy.allow("scrape_url"),
        policy.allow("search_gnews"),
        policy.allow("remember"),
        policy.allow("recall"),
    ]
    return policies
