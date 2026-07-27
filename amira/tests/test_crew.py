"""amira/tests/test_crew.py

Unit tests for ``amira.swarm.crew.run_trading_crew``.

All external I/O is injected or mocked:
- OHLCV data → synthetic DataFrame via ``_ohlcv_data`` injection param
- FA+Sentiment agent → ``_fa_agent`` with mocked ``analyse()``
- Risk Officer agent → ``_risk_agent`` with a real agent (no network)
- Hermes memory → in-memory SQLite via ``_hermes`` injection (tmp path)

Nothing hits yfinance, HTTP, or the filesystem outside of a tempfile.
"""

from __future__ import annotations

import os
import tempfile
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from amira.core.memory import HermesMemoryEngine
from amira.swarm.agents import FASentimentReport, HeadlineItem
from amira.swarm.crew import CrewFinalVerdict, run_trading_crew
from amira.swarm.risk_officer import RiskOfficerAgent

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(rows: int = 60, base_price: float = 3.85) -> List[dict]:
    """Return a list of synthetic OHLCVRecord dicts."""
    records = []
    for i in range(rows):
        p = base_price + i * 0.005
        records.append(
            {"date": f"2026-01-{(i % 28) + 1:02d}",
             "open": round(p - 0.01, 3),
             "high": round(p + 0.02, 3),
             "low":  round(p - 0.02, 3),
             "close": round(p, 3),
             "volume": 100_000 + i * 1_000}
        )
    return records


def _make_fa_report(
    symbol: str = "TEST",
    verdict: str = "BUY",
    score: float = 0.72,
) -> FASentimentReport:
    """Build a minimal FASentimentReport for injection."""
    return FASentimentReport(
        symbol=symbol,
        yf_symbol=f"{symbol}.KL",
        name="Test Corp",
        sector="Technology",
        market="MY",
        per=12.5,
        pe_status="normal",
        eps_ttm=0.55,
        roe_pct=11.0,
        nta=2.5,
        dividend_yield_pct=3.2,
        dividend_consistency="consistent",
        operating_cashflow=1_000_000,
        free_cash_flow="positive",
        total_debt=500_000,
        debt_to_equity=0.35,
        interest_cover=4.0,
        health_status="🟢 Budak Healthy",
        health_flags={
            "consistent_net_profit": True,
            "positive_operating_cashflow": True,
            "pays_dividend": True,
            "low_gearing": True,
        },
        sentiment_score=0.7,
        sentiment_label="bullish",
        headlines=[
            HeadlineItem(title="Test stock rises", source="GNews",
                         link="http://example.com", date="2026-07-27")
        ],
        news_source_tier="GNews",
        verdict=verdict,  # type: ignore[arg-type]
        score=score,
        rationale="Synthetic rationale for test.",
    )


def _make_fa_agent(
    symbol: str = "TEST",
    verdict: str = "BUY",
    score: float = 0.72,
) -> MagicMock:
    """Return a mock FundamentalSentimentAgent."""
    agent = MagicMock()
    agent.analyse.return_value = _make_fa_report(symbol, verdict, score)
    return agent


def _make_hermes() -> HermesMemoryEngine:
    """Return a Hermes instance backed by a temp file."""
    tmp = tempfile.mktemp(suffix=".db")
    return HermesMemoryEngine(db_path=tmp)


def _make_risk_agent(capital: float = 3_000.0) -> RiskOfficerAgent:
    return RiskOfficerAgent(capital=capital, risk_per_trade_pct=2.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunTradingCrewHappyPath:

    def test_returns_crew_final_verdict(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="Apa prospek TEST?",
            market="MY",
            memory_context="No prior data.",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert isinstance(result, CrewFinalVerdict)

    def test_verdict_is_advisory(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="Analisis",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(verdict="BUY"),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert result.verdict in {"BUY", "HOLD", "WATCH"}

    def test_score_in_range(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert 0.0 <= result.score <= 1.0

    def test_disclaimer_non_empty(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert len(result.disclaimer) > 20

    def test_ta_result_attached(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(rows=60, base_price=3.85),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert result.ta.rsi14 >= 0.0
        assert result.ta.atr14 >= 0.0
        assert result.ta.latest_close > 0.0

    def test_fa_sentiment_attached(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert result.fa_sentiment.symbol == "TEST"
        assert result.fa_sentiment.sentiment_label == "bullish"

    def test_risk_report_attached(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert hasattr(result.risk_report, "stop_loss")
        assert hasattr(result.risk_report, "position_size")
        assert result.risk_report.disclaimer != ""


class TestRunTradingCrewMemory:

    def test_result_persisted_to_hermes(self):
        hermes = _make_hermes()
        run_trading_crew(
            symbol="MEM",
            user_prompt="Test memory",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(symbol="MEM"),
            _risk_agent=_make_risk_agent(),
            _hermes=hermes,
        )
        logs = hermes.recall_past_trades("MEM")
        assert len(logs) == 1
        assert logs[0]["result"]["symbol"] == "MEM"

    def test_memory_context_in_ta_result(self):
        ctx = "Latest AMIRA advisory for MEM: HOLD. Prior high volatility."
        result = run_trading_crew(
            symbol="MEM",
            user_prompt="",
            market="MY",
            memory_context=ctx,
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(symbol="MEM"),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        assert result.ta.memory_context == ctx

    def test_hermes_failure_is_non_fatal(self):
        """If Hermes raises, the crew should still return the verdict."""
        bad_hermes = MagicMock()
        bad_hermes.save_trade_log.side_effect = RuntimeError("DB locked")
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=bad_hermes,
        )
        assert result.verdict in {"BUY", "HOLD", "WATCH"}  # still returned OK


class TestRunTradingCrewVeto:

    def test_veto_via_zero_atr(self):
        """A flat-price OHLCV (ATR≈0) should trigger Risk Officer veto."""
        # All rows with same high/low → ATR ≈ 0
        flat = [
            {"date": f"2026-01-{(i % 28) + 1:02d}",
             "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1000}
            for i in range(30)
        ]
        result = run_trading_crew(
            symbol="FLAT",
            user_prompt="flat market",
            market="MY",
            memory_context="",
            _ohlcv_data=flat,
            _fa_agent=_make_fa_agent(symbol="FLAT", verdict="BUY"),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        # ATR=0 triggers veto → verdict must be HOLD
        assert result.verdict == "HOLD"
        assert result.risk_report.veto_applied


class TestToDict:

    def test_to_dict_contains_all_sections(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="serialize me",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        d = result.to_dict()
        for key in ("symbol", "market", "verdict", "score", "rationale",
                    "disclaimer", "ta", "fa_sentiment", "risk"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_ta_section(self):
        result = run_trading_crew(
            symbol="TEST",
            user_prompt="",
            market="MY",
            memory_context="",
            _ohlcv_data=_make_ohlcv(),
            _fa_agent=_make_fa_agent(),
            _risk_agent=_make_risk_agent(),
            _hermes=_make_hermes(),
        )
        ta_dict = result.to_dict()["ta"]
        for key in ("rsi14", "atr14", "ma20", "ma50", "ma200", "latest_close"):
            assert key in ta_dict
