"""Interface-Agnostic Intent Pre-Filter Router for AuraOne (<80 lines)."""

from __future__ import annotations

import re
from enum import Enum
import structlog

logger = structlog.get_logger("aura.core.router")


class Intent(str, Enum):
    COMMAND = "COMMAND"
    URL_SCRAPE = "URL_SCRAPE"
    TICKER_ANALYSIS = "TICKER_ANALYSIS"
    CONVERSATIONAL = "CONVERSATIONAL"


_TICKER_REGEX = re.compile(r"^(?:[A-Z0-9]{2,10}|[0-9]{4}\.[A-Z]{2})$")
_URL_REGEX = re.compile(r"^https?://[^\s]+$")


class IntentRouter:
    """Zero-cost, deterministic pre-filter router."""

    def classify(self, text: str) -> Intent:
        """Classify input text into Intent enum without calling LLM."""
        raw = text.strip()
        if not raw:
            return Intent.CONVERSATIONAL

        # 1. Command Check
        if raw.startswith("/"):
            logger.debug("Routed to COMMAND", text=raw)
            return Intent.COMMAND

        # 2. URL Check
        if _URL_REGEX.match(raw):
            logger.debug("Routed to URL_SCRAPE", url=raw)
            return Intent.URL_SCRAPE

        # 3. Ticker Check (e.g. MAYBANK, 1155.KL, AAPL, TSLA)
        if _TICKER_REGEX.match(raw.upper()):
            logger.debug("Routed to TICKER_ANALYSIS", ticker=raw)
            return Intent.TICKER_ANALYSIS

        # 4. Default Conversational (requires Agent processing)
        logger.debug("Routed to CONVERSATIONAL", text=raw[:30])
        return Intent.CONVERSATIONAL


router = IntentRouter()
