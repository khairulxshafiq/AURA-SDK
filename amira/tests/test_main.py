"""amira/tests/test_main.py

FastAPI integration tests for ``amira.main``.

Uses ``httpx`` + ``fastapi.testclient.TestClient`` for fast, fully in-process
HTTP testing — no real network, no yfinance, no SQLite writes to disk.

All external calls are patched via ``unittest.mock.patch``.
"""

from __future__ import annotations

import json
import tempfile
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from amira.main import app, _ADVISORY_DISCLAIMER
from amira.core.memory import HermesMemoryEngine
from amira.swarm.crew import CrewFinalVerdict, TAResult
from amira.swarm.risk_officer import RiskReport, StopLossDetail, PositionSizeDetail
from amira.swarm.agents import FASentimentReport, HeadlineItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ta(
    symbol: str = "TEST",
    market: str = "MY",
    rsi14: float = 52.0,
    atr14: float = 0.12,
    close: float = 3.85,
) -> TAResult:
    ta = TAResult(
        symbol=symbol, market=market,
        rsi14=rsi14, atr14=atr14,
        ma20=3.80, ma50=3.70, ma200=3.50,
        latest_close=close,
        memory_context="No prior data.",
    )
    return ta


def _make_fa(symbol: str = "TEST", verdict: str = "BUY", score: float = 0.72) -> FASentimentReport:
    return FASentimentReport(
        symbol=symbol, yf_symbol=f"{symbol}.KL",
        name="Test Corp", sector="Technology", market="MY",
        per=12.5, pe_status="normal", eps_ttm=0.55,
        roe_pct=11.0, nta=2.5, dividend_yield_pct=3.2,
        dividend_consistency="consistent", operating_cashflow=1_000_000,
        free_cash_flow="positive", total_debt=500_000,
        debt_to_equity=0.35, interest_cover=4.0,
        health_status="🟢 Budak Healthy",
        health_flags={
            "consistent_net_profit": True, "positive_operating_cashflow": True,
            "pays_dividend": True, "low_gearing": True,
        },
        sentiment_score=0.70, sentiment_label="bullish",
        headlines=[HeadlineItem(title="Up", source="GNews", link="http://x.com", date="2026-07-27")],
        news_source_tier="GNews",
        verdict=verdict,   # type: ignore[arg-type]
        score=score,
        rationale="Test rationale.",
    )


def _make_stop_loss(entry: float = 3.85, atr14: float = 0.12) -> StopLossDetail:
    return StopLossDetail(
        entry=entry, atr14=atr14,
        swing_stop=round(entry - 1.5 * atr14, 3),
        position_stop=round(entry - 2.0 * atr14, 3),
        swing_risk_pct=round(1.5 * atr14 / entry * 100, 2),
        position_risk_pct=round(2.0 * atr14 / entry * 100, 2),
    )


def _make_position_size(capital: float = 3_000.0) -> PositionSizeDetail:
    return PositionSizeDetail(
        capital=capital, risk_amount=60.0, risk_per_unit=0.18,
        max_shares=333, suggested_lots=3,
        capital_deployed=round(300 * 3.85, 2),
        capital_deployed_pct=round(300 * 3.85 / capital * 100, 2),
    )


def _make_risk_report(
    symbol: str = "TEST",
    verdict: str = "BUY",
    veto: bool = False,
) -> RiskReport:
    return RiskReport(
        symbol=symbol, market="MY",
        upstream_verdict=verdict,    # type: ignore[arg-type]
        upstream_score=0.72,
        stop_loss=_make_stop_loss(),
        position_size=_make_position_size(),
        downside_risk_score=0.25,
        downside_risk_label="low",
        veto_applied=veto,
        veto_reason="Veto test." if veto else None,
        veto_triggers=["ATR_ZERO_OR_MISSING"] if veto else [],
        verdict="HOLD" if veto else verdict,  # type: ignore[arg-type]
        rationale="Risk rationale.",
        disclaimer=_ADVISORY_DISCLAIMER,
    )


def _make_crew_verdict(
    symbol: str = "TEST",
    verdict: str = "BUY",
    veto: bool = False,
) -> CrewFinalVerdict:
    ta = _make_ta(symbol=symbol)
    fa = _make_fa(symbol=symbol, verdict=verdict)
    risk = _make_risk_report(symbol=symbol, verdict=verdict, veto=veto)
    return CrewFinalVerdict(
        symbol=symbol, market="MY",
        user_prompt="Test prompt",
        ta=ta, fa_sentiment=fa, risk_report=risk,
    )


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_advisory_mode_true(self, client):
        data = client.get("/health").json()
        assert data["advisory_mode"] is True

    def test_disclaimer_present(self, client):
        data = client.get("/health").json()
        assert "disclaimer" in data
        assert len(data["disclaimer"]) > 10

    def test_version_present(self, client):
        data = client.get("/health").json()
        assert "version" in data
        assert data["version"] != ""


# ---------------------------------------------------------------------------
# POST /api/v1/analyze — happy path
# ---------------------------------------------------------------------------

class TestAnalyzeHappyPath:
    _PAYLOAD = {"symbol": "1155", "user_prompt": "Bagaimana prospek Maybank?", "market": "MY"}

    def _patched_crew(self, verdict: str = "BUY") -> MagicMock:
        mock = MagicMock(return_value=_make_crew_verdict(symbol="1155", verdict=verdict))
        return mock

    def test_returns_200(self, client):
        with patch("amira.main.run_trading_crew", self._patched_crew()), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            r = client.post("/api/v1/analyze", json=self._PAYLOAD)
        assert r.status_code == 200

    def test_response_status_ok(self, client):
        with patch("amira.main.run_trading_crew", self._patched_crew()), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            data = client.post("/api/v1/analyze", json=self._PAYLOAD).json()
        assert data["status"] == "ok"

    def test_response_has_verdict(self, client):
        with patch("amira.main.run_trading_crew", self._patched_crew("WATCH")), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            data = client.post("/api/v1/analyze", json=self._PAYLOAD).json()
        assert data["verdict"] in {"BUY", "HOLD", "WATCH"}

    def test_response_has_disclaimer(self, client):
        with patch("amira.main.run_trading_crew", self._patched_crew()), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            data = client.post("/api/v1/analyze", json=self._PAYLOAD).json()
        assert len(data["disclaimer"]) > 10

    def test_response_has_risk_block(self, client):
        with patch("amira.main.run_trading_crew", self._patched_crew()), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            data = client.post("/api/v1/analyze", json=self._PAYLOAD).json()
        risk = data["risk"]
        for key in ("swing_stop", "position_stop", "atr14", "rsi14", "veto_applied"):
            assert key in risk, f"Missing risk key: {key}"

    def test_symbol_uppercased(self, client):
        payload = {"symbol": "aapl", "user_prompt": "test", "market": "US"}
        with patch("amira.main.run_trading_crew", self._patched_crew()), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            data = client.post("/api/v1/analyze", json=payload).json()
        assert data["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# POST /api/v1/analyze — validation errors
# ---------------------------------------------------------------------------

class TestAnalyzeValidation:
    def test_missing_symbol_returns_422(self, client):
        r = client.post("/api/v1/analyze", json={"user_prompt": "?", "market": "MY"})
        assert r.status_code == 422

    def test_invalid_market_returns_422(self, client):
        r = client.post("/api/v1/analyze",
                        json={"symbol": "X", "user_prompt": "?", "market": "INVALID"})
        assert r.status_code == 422

    def test_extra_field_returns_422(self, client):
        r = client.post("/api/v1/analyze",
                        json={"symbol": "X", "user_prompt": "?", "market": "MY", "hack": True})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/analyze — pipeline error handling
# ---------------------------------------------------------------------------

class TestAnalyzePipelineErrors:
    _PAYLOAD = {"symbol": "ERR", "user_prompt": "test", "market": "MY"}

    def test_runtime_error_returns_500(self, client):
        with patch("amira.main.run_trading_crew",
                   side_effect=RuntimeError("yfinance failure")), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            r = client.post("/api/v1/analyze", json=self._PAYLOAD)
        assert r.status_code == 500

    def test_pipeline_error_body_is_typed(self, client):
        with patch("amira.main.run_trading_crew",
                   side_effect=RuntimeError("timeout")), \
             patch("amira.main._get_hermes", return_value=HermesMemoryEngine(db_path=tempfile.mktemp(suffix=".db"))):
            data = client.post("/api/v1/analyze", json=self._PAYLOAD).json()
        assert data["status"] == "error"
        assert "code" in data
        assert "disclaimer" in data

    def test_hermes_failure_non_fatal(self, client):
        """If Hermes recall crashes, the crew should still run."""
        broken_hermes = MagicMock()
        broken_hermes.get_context.side_effect = RuntimeError("DB locked")
        broken_hermes.save_trade_log.side_effect = RuntimeError("DB locked")
        with patch("amira.main.run_trading_crew",
                   return_value=_make_crew_verdict("1155", "HOLD")), \
             patch("amira.main._get_hermes", return_value=broken_hermes):
            r = client.post("/api/v1/analyze",
                            json={"symbol": "1155", "user_prompt": "?", "market": "MY"})
        assert r.status_code == 200
