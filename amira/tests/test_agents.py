"""amira/tests/test_agents.py

Unit tests for ``amira.swarm.agents.FundamentalSentimentAgent``.

All external I/O (yfinance, HTTP news fetches) is mocked so the suite runs
fully offline and deterministically.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from amira.swarm.agents import (
    FASentimentReport,
    FundamentalSentimentAgent,
    _score_sentiment,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

FAKE_FA: dict = {
    "symbol": "1155",
    "yf_symbol": "1155.KL",
    "name": "MAYBANK",
    "sector": "Financials",
    "per": 12.5,
    "pe_status": "normal",
    "eps_ttm": 0.85,
    "roe_pct": 11.3,
    "nta": 5.2,
    "dividend_yield_pct": 6.1,
    "dividend_consistency": "consistent",
    "operating_cashflow": 5_000_000,
    "free_cash_flow": "positive",
    "total_debt": 200_000_000,
    "debt_to_equity": 0.45,
    "interest_cover": 4.5,
    "health_status": "🟢 Budak Healthy",
    "health_flags": {
        "consistent_net_profit": True,
        "positive_operating_cashflow": True,
        "pays_dividend": True,
        "low_gearing": True,
    },
}

FAKE_ARTICLES = [
    {"title": "Maybank rekod untung tertinggi", "source": "GNews", "link": "http://example.com/1",
     "date": "2026-07-27", "desc": "Pertumbuhan kukuh 12% YoY."},
    {"title": "BSKL naik pagi ini", "source": "GNews", "link": "http://example.com/2",
     "date": "2026-07-27", "desc": "Saham bank melonjak."},
]


def _make_agent() -> FundamentalSentimentAgent:
    return FundamentalSentimentAgent(news_max_items=3)


# ---------------------------------------------------------------------------
# Sentiment scorer unit tests (pure, no mocks needed)
# ---------------------------------------------------------------------------

def test_score_sentiment_empty():
    score, label = _score_sentiment([])
    assert score == 0.5
    assert label == "neutral"


def test_score_sentiment_bullish():
    arts = [
        {"title": "Saham rekod", "desc": "pertumbuhan kuat"},
        {"title": "Profit naik", "desc": "untung meningkat"},
    ]
    score, label = _score_sentiment(arts)
    assert score > 0.5
    assert label == "bullish"


def test_score_sentiment_bearish():
    arts = [
        {"title": "Saham jatuh teruk", "desc": "kerugian besar"},
        {"title": "Debt meningkat", "desc": "rugi operasi"},
    ]
    score, label = _score_sentiment(arts)
    assert score <= 0.5


# ---------------------------------------------------------------------------
# FundamentalSentimentAgent integration tests (mocked I/O)
# ---------------------------------------------------------------------------

class TestFundamentalSentimentAgent:

    def test_analyse_returns_report(self):
        agent = _make_agent()
        agent._get_fundamentals = MagicMock(return_value=FAKE_FA)
        agent._get_sentiment = MagicMock(return_value=(0.75, "bullish", FAKE_ARTICLES, "GNews"))

        report = agent.analyse("1155", market="MY")

        assert isinstance(report, FASentimentReport)
        assert report.symbol == "1155"
        assert report.verdict in {"BUY", "HOLD", "WATCH"}
        assert 0.0 <= report.score <= 1.0
        assert report.disclaimer != ""
        assert len(report.headlines) == len(FAKE_ARTICLES)

    def test_analyse_verdict_advisory_only(self):
        """Verdict must never be an execution command."""
        agent = _make_agent()
        agent._get_fundamentals = MagicMock(return_value=FAKE_FA)
        agent._get_sentiment = MagicMock(return_value=(0.9, "bullish", FAKE_ARTICLES, "GNews"))

        report = agent.analyse("1155", market="MY")
        assert report.verdict in {"BUY", "HOLD", "WATCH"}

    def test_analyse_raises_on_fa_error(self):
        agent = _make_agent()
        agent._get_fundamentals = MagicMock(return_value={"error": "Symbol not found"})

        with pytest.raises(RuntimeError, match="Fundamentals fetch failed"):
            agent.analyse("INVALID", market="MY")

    def test_blended_score_hold_when_low(self):
        """Weak FA + bearish sentiment → HOLD."""
        poor_fa = {**FAKE_FA,
                   "health_flags": {k: False for k in FAKE_FA["health_flags"]},
                   "health_status": "🔴 Speculative / High-Risk"}
        agent = _make_agent()
        agent._get_fundamentals = MagicMock(return_value=poor_fa)
        agent._get_sentiment = MagicMock(return_value=(0.1, "bearish", [], "None"))

        report = agent.analyse("XXXX", market="MY")
        assert report.verdict == "HOLD"
        assert report.score < 0.45

    def test_report_model_serializable(self):
        """FASentimentReport must serialise to a plain dict without raising."""
        agent = _make_agent()
        agent._get_fundamentals = MagicMock(return_value=FAKE_FA)
        agent._get_sentiment = MagicMock(return_value=(0.6, "neutral", FAKE_ARTICLES, "GNews"))

        report = agent.analyse("1155", market="MY")
        data = report.model_dump()
        assert "verdict" in data
        assert "disclaimer" in data
        assert "headlines" in data
        assert isinstance(data["headlines"], list)
