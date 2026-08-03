"""amira/swarm/agents.py

AMIRA Swarm Agents.

This module defines the first agent in the AMIRA advisory swarm:

``FundamentalSentimentAgent``
    Analyses a single ticker by combining:
    - **Fundamental Analysis (FA)**: P/E, ROE, dividend yield, debt metrics via
      ``amira.tools.fundamentals.fetch_fundamentals``.
    - **Sentiment**: Live news headlines + DuckDuckGo web search via the same
      3-tier cascade already proven in ``AuraOne/tools/search_engine.py``
      (GNews RSS → Internet Search → RSS Feeds).

    The agent returns a structured ``FASentimentReport`` Pydantic model that
    the downstream swarm orchestrator can aggregate with TA and other signals.

Hard guardrails
---------------
- **AMIRA is advisory only.**  The agent NEVER issues buy/sell execution orders.
- The ``verdict`` field is constrained to ``"BUY" | "HOLD" | "WATCH"`` and is
  always accompanied by a disclaimer.
- The ``score`` is a normalised float (0‑1) used as a *confidence indicator*,
  not a trade signal.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from amira.tools.fundamentals import fetch_fundamentals

# ---------------------------------------------------------------------------
# Re-use AURA's live news / search logic without copying code.
# The import is resolved lazily inside _load_search_engine() so that:
#  (a) tests can mock _get_sentiment without needing AuraOne on sys.path, and
#  (b) production code still resolves correctly when PYTHONPATH is set.
# ---------------------------------------------------------------------------
import sys
import os


def _load_search_engine():
    """Lazily import AuraOne search_engine, trying multiple path strategies."""
    try:
        import search_engine as _se  # noqa: PLC0415
        return _se
    except ModuleNotFoundError:
        pass
    # Fallback: explicit AuraOne path relative to this file
    aura_one_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "AuraOne")
    )
    if aura_one_path not in sys.path:
        sys.path.insert(0, aura_one_path)
    import search_engine as _se  # noqa: PLC0415
    return _se

logger = logging.getLogger("amira.swarm.agents")

# ---------------------------------------------------------------------------
# Report model
# ---------------------------------------------------------------------------

class HeadlineItem(BaseModel):
    """A single news headline contributing to sentiment."""

    title: str
    source: str
    link: str
    date: str
    snippet: str = ""

    model_config = ConfigDict(extra="ignore")


class FASentimentReport(BaseModel):
    """Structured output produced by FundamentalSentimentAgent.

    Advisory guardrail: the ``verdict`` is constrained to BUY/HOLD/WATCH.
    No execution order is ever emitted.
    """

    # Metadata
    symbol: str
    yf_symbol: str
    name: str
    sector: str
    market: Literal["MY", "US", "HK", "INDEX"]
    generated_at: str = Field(default_factory=lambda: datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))

    # Fundamental block
    per: Optional[float]
    pe_status: str
    eps_ttm: float
    roe_pct: float
    nta: float
    dividend_yield_pct: float
    dividend_consistency: str
    operating_cashflow: int
    free_cash_flow: str
    total_debt: int
    debt_to_equity: float
    interest_cover: float
    health_status: str
    health_flags: Dict[str, bool]

    # Sentiment block
    sentiment_score: float = Field(ge=0.0, le=1.0, description="0=bearish, 0.5=neutral, 1=bullish")
    sentiment_label: str
    headlines: List[HeadlineItem]
    news_source_tier: str

    # Advisory verdict
    verdict: Literal["BUY", "HOLD", "WATCH"]
    score: float = Field(ge=0.0, le=1.0, description="Overall advisory confidence 0‑1")
    rationale: str
    disclaimer: str = (
        "⚠️ AMIRA adalah sistem perundingan sahaja. Keputusan ini BUKAN nasihat kewangan rasmi "
        "dan TIDAK melaksanakan sebarang transaksi. Sila buat keputusan pelaburan anda sendiri."
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("verdict")
    @classmethod
    def enforce_advisory(cls, v: str) -> str:
        allowed = {"BUY", "HOLD", "WATCH"}
        if v not in allowed:
            raise ValueError(f"Verdict '{v}' is not advisory-safe. Allowed: {sorted(allowed)}")
        return v


# ---------------------------------------------------------------------------
# Sentiment helpers
# ---------------------------------------------------------------------------

_BULLISH_WORDS = {"naik", "kukuh", "rekod", "pelaburan", "pertumbuhan", "lonjak",
                  "rally", "bull", "surge", "growth", "record", "up", "positive",
                  "melebihi", "meningkat", "untung", "profit", "laba"}
_BEARISH_WORDS = {"jatuh", "turun", "rugi", "susut", "bear", "drop", "fall",
                  "decline", "loss", "debt", "bankrupt", "saham jatuh", "kerugian",
                  "downgrade", "default", "sekatan", "sanction"}


def _score_sentiment(headlines: List[Dict[str, Any]]) -> tuple[float, str]:
    """Heuristic sentiment scorer over headline texts.

    Returns (score 0‑1, label).
    """
    if not headlines:
        return 0.5, "neutral"

    bull_hits = 0
    bear_hits = 0
    for h in headlines:
        text = (h.get("title", "") + " " + h.get("desc", "")).lower()
        for w in _BULLISH_WORDS:
            if w in text:
                bull_hits += 1
                break
        for w in _BEARISH_WORDS:
            if w in text:
                bear_hits += 1
                break

    total = bull_hits + bear_hits
    if total == 0:
        return 0.5, "neutral"

    score = bull_hits / total
    if score >= 0.65:
        label = "bullish"
    elif score <= 0.35:
        label = "bearish"
    else:
        label = "neutral"
    return round(score, 2), label


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FundamentalSentimentAgent:
    """AMIRA advisory agent: Fundamental Analysis + Sentiment.

    This agent is stateless — each call to ``analyse`` is independent and
    suitable for concurrent use inside a CrewAI task.

    Parameters
    ----------
    news_max_items:
        Maximum number of headlines to fetch for sentiment analysis.
    """

    def __init__(self, news_max_items: int = 6) -> None:
        self._news_max_items = news_max_items

    # ------------------------------------------------------------------
    # Private tools
    # ------------------------------------------------------------------

    def _get_fundamentals(self, symbol: str, market: str) -> Dict[str, Any]:
        """Thin wrapper so tests can mock just this method."""
        return fetch_fundamentals(symbol, market)

    def _get_sentiment(self, symbol: str, company_name: str) -> tuple[float, str, List[Dict], str]:
        """Fetch headlines via AURA's 3-tier cascade and score sentiment.

        Returns (score, label, raw_articles, source_tier).
        """
        se = _load_search_engine()
        query = f"{company_name} {symbol} stock saham"
        articles, tier = se.fetch_live_news_with_fallback(query, max_items=self._news_max_items)
        score, label = _score_sentiment(articles)
        return score, label, articles, tier

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(
        self,
        symbol: str,
        market: Literal["MY", "US", "HK", "INDEX"] = "MY",
    ) -> FASentimentReport:
        """Run the FA + Sentiment analysis for *symbol* on *market*.

        Parameters
        ----------
        symbol:
            Base ticker symbol without suffix.
        market:
            Market code.

        Returns
        -------
        FASentimentReport
            Structured advisory report.

        Raises
        ------
        RuntimeError
            If the fundamentals fetch fails with an error (network, bad symbol, etc.).
        """
        logger.info("[FASentimentAgent] Analysing %s (%s)", symbol, market)

        # ------------------------------------------------------------------ #
        # Step 1: Fundamentals                                                 #
        # ------------------------------------------------------------------ #
        fa = self._get_fundamentals(symbol, market)
        if "error" in fa:
            raise RuntimeError(f"Fundamentals fetch failed: {fa['error']}")

        # ------------------------------------------------------------------ #
        # Step 2: Sentiment                                                    #
        # ------------------------------------------------------------------ #
        sentiment_score, sentiment_label, raw_articles, news_tier = self._get_sentiment(
            symbol, fa.get("name", symbol)
        )

        headlines = [
            HeadlineItem(
                title=a.get("title", ""),
                source=a.get("source", ""),
                link=a.get("link", ""),
                date=a.get("date", ""),
                snippet=a.get("desc", ""),
            )
            for a in raw_articles
        ]

        # ------------------------------------------------------------------ #
        # Step 3: Combine → advisory verdict                                   #
        # ------------------------------------------------------------------ #
        health_flags = fa.get("health_flags", {})
        healthy_count = sum(1 for v in health_flags.values() if v)

        # FA score (0–1): proportion of health checks that pass
        fa_score = round(healthy_count / max(len(health_flags), 1), 2)

        # Blended score: 60 % FA + 40 % sentiment
        blended = round(0.6 * fa_score + 0.4 * sentiment_score, 2)

        if blended >= 0.65:
            verdict: Literal["BUY", "HOLD", "WATCH"] = "BUY"
        elif blended >= 0.45:
            verdict = "WATCH"
        else:
            verdict = "HOLD"

        roe = fa.get("roe_pct", 0.0)
        dy = fa.get("dividend_yield_pct", 0.0)
        per = fa.get("per")
        rationale = (
            f"{fa.get('name', symbol)} ({fa.get('yf_symbol', symbol)}) — "
            f"ROE {roe:.1f}%, DY {dy:.1f}%, P/E {'N/A' if per is None else f'{per:.1f}x'}. "
            f"Kesihatan kewangan: {fa.get('health_status', '—')}. "
            f"Sentimen berita: {sentiment_label} (skor {sentiment_score}). "
            f"Skor keseluruhan: {blended}/1.0 → verdict advisory: {verdict}."
        )

        return FASentimentReport(
            # metadata
            symbol=fa["symbol"],
            yf_symbol=fa["yf_symbol"],
            name=fa["name"],
            sector=fa.get("sector", "General"),
            market=market,
            # fundamentals
            per=fa.get("per"),
            pe_status=fa.get("pe_status", ""),
            eps_ttm=fa.get("eps_ttm", 0.0),
            roe_pct=roe,
            nta=fa.get("nta", 0.0),
            dividend_yield_pct=dy,
            dividend_consistency=fa.get("dividend_consistency", "none"),
            operating_cashflow=fa.get("operating_cashflow", 0),
            free_cash_flow=fa.get("free_cash_flow", "pressured"),
            total_debt=fa.get("total_debt", 0),
            debt_to_equity=fa.get("debt_to_equity", 0.0),
            interest_cover=fa.get("interest_cover", 0.0),
            health_status=fa.get("health_status", ""),
            health_flags=health_flags,
            # sentiment
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            headlines=headlines,
            news_source_tier=news_tier,
            # verdict
            verdict=verdict,
            score=blended,
            rationale=rationale,
        )


__all__ = ["FundamentalSentimentAgent", "FASentimentReport", "HeadlineItem"]
