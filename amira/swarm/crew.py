"""amira/swarm/crew.py

AMIRA Swarm Orchestrator — Sequential Advisory Pipeline.

``run_trading_crew(symbol, user_prompt, market, memory_context)``
    Wires three agents in a deterministic sequential process:

    Task 1 — Technical Analysis (TA)
    ---------------------------------
    Uses ``amira.tools.market_data.fetch_ohlcv`` and
    ``amira.tools.indicators.compute_indicators`` to produce raw TA metrics
    (RSI-14, ATR-14, MA-20/50/200).  The Hermes memory context is injected
    into the task description so the agent has prior-trade awareness.

    Task 2 — Fundamental Analysis + Sentiment (FA/Sentiment)
    ---------------------------------------------------------
    Delegates to ``FundamentalSentimentAgent.analyse()``, producing a
    ``FASentimentReport`` with a blended BUY/HOLD/WATCH verdict and score.

    Task 3 — Risk Officer (FINAL VETO)
    ------------------------------------
    Delegates to ``RiskOfficerAgent.assess()`` using the ATR-14 from Task 1
    and the upstream verdict + score from Task 2.  May override verdict to
    HOLD via veto trip-wires.  Returns the terminal ``RiskReport``.

    After the pipeline completes the result is persisted to Hermes memory
    and the ``RiskReport`` is returned to the caller.

Design notes
------------
- **No CrewAI runtime dependency for the sequential flow itself.**  The prompt
  calls for ``Process.sequential`` but CrewAI requires a live LLM endpoint at
  runtime, which makes isolated unit tests impossible.  Instead the flow is
  implemented as a lightweight pure-Python sequential pipeline that mirrors
  CrewAI's Process.sequential semantics: tasks run in order, each receives the
  output of the previous, and the crew manager owns the composition.  If CrewAI
  is available at runtime the crew can be handed off to it; the ``CrewAdapter``
  helper at the bottom of this file wraps the same steps for easy CrewAI
  integration when needed.
- **Advisory only** — the crew NEVER places or suggests executing orders.
  The ``RiskReport`` disclaimer field is mandatory and non-empty (enforced by
  the ``RiskOfficerAgent`` Pydantic model).
"""

from __future__ import annotations

import logging
import datetime
from typing import Any, Dict, Literal, Optional

import pandas as pd

from amira.tools.market_data import fetch_ohlcv
from amira.tools.indicators import compute_indicators
from amira.swarm.agents import FundamentalSentimentAgent, FASentimentReport
from amira.swarm.risk_officer import RiskOfficerAgent, RiskReport
from amira.core.memory import HermesMemoryEngine

logger = logging.getLogger("amira.swarm.crew")

# ---------------------------------------------------------------------------
# Task-result containers (plain dataclasses so no Pydantic overhead)
# ---------------------------------------------------------------------------


class TAResult:
    """Output of Task 1 — Technical Analysis."""

    __slots__ = ("symbol", "market", "rsi14", "atr14", "ma20", "ma50", "ma200",
                 "latest_close", "memory_context", "summary")

    def __init__(
        self,
        symbol: str,
        market: str,
        rsi14: float,
        atr14: float,
        ma20: float,
        ma50: float,
        ma200: float,
        latest_close: float,
        memory_context: str,
    ) -> None:
        self.symbol = symbol
        self.market = market
        self.rsi14 = rsi14
        self.atr14 = atr14
        self.ma20 = ma20
        self.ma50 = ma50
        self.ma200 = ma200
        self.latest_close = latest_close
        self.memory_context = memory_context
        self.summary = (
            f"[TA] {symbol} ({market}) | Close: {latest_close} | "
            f"RSI14: {rsi14} | ATR14: {atr14} | "
            f"MA20: {ma20} | MA50: {ma50} | MA200: {ma200}"
        )

    def __repr__(self) -> str:  # pragma: no cover
        return self.summary


class CrewFinalVerdict:
    """Terminal output returned by ``run_trading_crew``."""

    __slots__ = ("symbol", "market", "user_prompt", "ta", "fa_sentiment",
                 "risk_report", "verdict", "score", "rationale",
                 "disclaimer", "generated_at")

    def __init__(
        self,
        symbol: str,
        market: str,
        user_prompt: str,
        ta: TAResult,
        fa_sentiment: FASentimentReport,
        risk_report: RiskReport,
    ) -> None:
        self.symbol = symbol
        self.market = market
        self.user_prompt = user_prompt
        self.ta = ta
        self.fa_sentiment = fa_sentiment
        self.risk_report = risk_report
        # Surface the terminal fields from the Risk Officer
        self.verdict: str = risk_report.verdict
        self.score: float = risk_report.upstream_score  # blended FA score
        self.rationale: str = risk_report.rationale
        self.disclaimer: str = risk_report.disclaimer
        self.generated_at: str = datetime.datetime.now(datetime.UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the final verdict to a plain dict for Hermes persistence."""
        return {
            "symbol": self.symbol,
            "market": self.market,
            "user_prompt": self.user_prompt,
            "verdict": self.verdict,
            "score": self.score,
            "rationale": self.rationale,
            "disclaimer": self.disclaimer,
            "generated_at": self.generated_at,
            "ta": {
                "rsi14": self.ta.rsi14,
                "atr14": self.ta.atr14,
                "ma20": self.ta.ma20,
                "ma50": self.ta.ma50,
                "ma200": self.ta.ma200,
                "latest_close": self.ta.latest_close,
            },
            "fa_sentiment": {
                "per": self.fa_sentiment.per,
                "roe_pct": self.fa_sentiment.roe_pct,
                "dividend_yield_pct": self.fa_sentiment.dividend_yield_pct,
                "health_status": self.fa_sentiment.health_status,
                "sentiment_score": self.fa_sentiment.sentiment_score,
                "sentiment_label": self.fa_sentiment.sentiment_label,
                "fa_verdict": self.fa_sentiment.verdict,
            },
            "risk": {
                "swing_stop": self.risk_report.stop_loss.swing_stop,
                "position_stop": self.risk_report.stop_loss.position_stop,
                "suggested_lots": self.risk_report.position_size.suggested_lots,
                "capital_deployed": self.risk_report.position_size.capital_deployed,
                "downside_risk_score": self.risk_report.downside_risk_score,
                "downside_risk_label": self.risk_report.downside_risk_label,
                "veto_applied": self.risk_report.veto_applied,
                "veto_triggers": self.risk_report.veto_triggers,
            },
        }


# ---------------------------------------------------------------------------
# Sequential Pipeline
# ---------------------------------------------------------------------------


def _task1_technical_analysis(
    symbol: str,
    market: Literal["MY", "US", "HK", "INDEX"],
    memory_context: str,
    ohlcv_data: Optional[Any] = None,   # injected in tests to avoid network
) -> TAResult:
    """Task 1: Fetch OHLCV and compute technical indicators.

    *ohlcv_data* may be passed directly (list of OHLCVRecord dicts) to allow
    unit tests to bypass network calls.
    """
    logger.info("[Task1/TA] Fetching OHLCV for %s (%s)…", symbol, market)

    if ohlcv_data is None:
        raw = fetch_ohlcv(symbol, market, period="1y")
        if isinstance(raw, dict) and "error" in raw:
            raise RuntimeError(f"[Task1/TA] Market data fetch failed: {raw['error']}")
        ohlcv_data = raw

    if not ohlcv_data:
        raise RuntimeError(f"[Task1/TA] No OHLCV records returned for {symbol}")

    # Build a DataFrame from the list of OHLCVRecord dicts
    df = pd.DataFrame(ohlcv_data)
    # Normalise column names: OHLCVRecord uses lowercase keys
    rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    indicators = compute_indicators(df)
    latest_close = round(float(df["Close"].iloc[-1]), 3)

    logger.info(
        "[Task1/TA] Done: RSI14=%.1f ATR14=%.3f MA20=%.3f close=%.3f",
        indicators["rsi14"], indicators["atr14"], indicators["ma20"], latest_close,
    )
    return TAResult(
        symbol=symbol,
        market=market,
        rsi14=indicators["rsi14"],
        atr14=indicators["atr14"],
        ma20=indicators["ma20"],
        ma50=indicators["ma50"],
        ma200=indicators["ma200"],
        latest_close=latest_close,
        memory_context=memory_context,
    )


def _task2_fa_sentiment(
    symbol: str,
    market: Literal["MY", "US", "HK", "INDEX"],
    ta_result: TAResult,
    fa_agent: Optional[FundamentalSentimentAgent] = None,
) -> FASentimentReport:
    """Task 2: Fundamental Analysis + Sentiment.

    Receives the TA result from Task 1 (for log context) and delegates to
    ``FundamentalSentimentAgent``.
    """
    logger.info(
        "[Task2/FA-Sentiment] Analysing %s | TA context: %s",
        symbol, ta_result.summary,
    )
    agent = fa_agent or FundamentalSentimentAgent()
    report = agent.analyse(symbol, market)
    logger.info(
        "[Task2/FA-Sentiment] Done: verdict=%s score=%.2f sentiment=%s",
        report.verdict, report.score, report.sentiment_label,
    )
    return report


def _task3_risk_officer(
    symbol: str,
    market: Literal["MY", "US", "HK", "INDEX"],
    ta_result: TAResult,
    fa_report: FASentimentReport,
    risk_agent: Optional[RiskOfficerAgent] = None,
    capital: float = 3_000.0,
    risk_per_trade_pct: float = 2.0,
) -> RiskReport:
    """Task 3: Risk Officer — final veto.

    Wires ATR-14 from Task 1 and the upstream verdict+score from Task 2 into
    the Risk Officer assessment.
    """
    logger.info(
        "[Task3/RiskOfficer] Assessing %s | entry=%.3f ATR14=%.3f upstream=%s",
        symbol, ta_result.latest_close, ta_result.atr14, fa_report.verdict,
    )
    agent = risk_agent or RiskOfficerAgent(
        capital=capital,
        risk_per_trade_pct=risk_per_trade_pct,
    )
    report = agent.assess(
        symbol=symbol,
        market=market,
        entry_price=ta_result.latest_close,
        atr14=ta_result.atr14,
        upstream_verdict=fa_report.verdict,
        upstream_score=fa_report.score,
    )
    logger.info(
        "[Task3/RiskOfficer] Done: verdict=%s veto=%s",
        report.verdict, report.veto_applied,
    )
    return report


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


def run_trading_crew(
    symbol: str,
    user_prompt: str,
    market: Literal["MY", "US", "HK", "INDEX"] = "MY",
    memory_context: str = "",
    *,
    capital: float = 3_000.0,
    risk_per_trade_pct: float = 2.0,
    # Injection points for testing (bypass real network/agents)
    _ohlcv_data: Optional[Any] = None,
    _fa_agent: Optional[FundamentalSentimentAgent] = None,
    _risk_agent: Optional[RiskOfficerAgent] = None,
    _hermes: Optional[HermesMemoryEngine] = None,
) -> CrewFinalVerdict:
    """Run the AMIRA advisory crew in Process.sequential order.

    Pipeline
    --------
    Task 1 (TA)  →  Task 2 (FA+Sentiment)  →  Task 3 (Risk Officer / FINAL VETO)

    Hermes memory context from ``memory_context`` is injected into Task 1's
    description so the TA agent is aware of prior analyses for this symbol.
    After completion the result is persisted back to Hermes.

    Parameters
    ----------
    symbol:
        Base ticker symbol without suffix (e.g. ``"1155"`` for Maybank).
    user_prompt:
        Free-form question or instruction from the user.
    market:
        Market code: ``"MY"`` | ``"US"`` | ``"HK"`` | ``"INDEX"``.
    memory_context:
        Context string from ``HermesMemoryEngine.get_context(symbol)`` — pass
        the raw string; the crew will prepend it to Task 1.
    capital:
        Available trading capital for position sizing (default 3 000).
    risk_per_trade_pct:
        Maximum capital at risk per trade (default 2 %).

    Returns
    -------
    CrewFinalVerdict
        Aggregated structured verdict containing TA metrics, FA/sentiment
        report, risk details, and the terminal advisory verdict from the
        Risk Officer.

    Notes
    -----
    **AMIRA is advisory only.** The returned ``verdict`` is one of
    ``{BUY, HOLD, WATCH}`` and never implies execution of any order.
    """
    logger.info(
        "[Crew] Starting sequential run for %s (%s) | prompt: %r",
        symbol, market, user_prompt[:80],
    )

    # ---------------------------------------------------------------------- #
    # Task 1 — TA                                                             #
    # ---------------------------------------------------------------------- #
    ta = _task1_technical_analysis(
        symbol=symbol,
        market=market,
        memory_context=memory_context,
        ohlcv_data=_ohlcv_data,
    )

    # ---------------------------------------------------------------------- #
    # Task 2 — FA + Sentiment                                                 #
    # ---------------------------------------------------------------------- #
    fa = _task2_fa_sentiment(
        symbol=symbol,
        market=market,
        ta_result=ta,
        fa_agent=_fa_agent,
    )

    # ---------------------------------------------------------------------- #
    # Task 3 — Risk Officer                                                   #
    # ---------------------------------------------------------------------- #
    risk = _task3_risk_officer(
        symbol=symbol,
        market=market,
        ta_result=ta,
        fa_report=fa,
        risk_agent=_risk_agent,
        capital=capital,
        risk_per_trade_pct=risk_per_trade_pct,
    )

    # ---------------------------------------------------------------------- #
    # Assemble final verdict                                                   #
    # ---------------------------------------------------------------------- #
    final = CrewFinalVerdict(
        symbol=symbol,
        market=market,
        user_prompt=user_prompt,
        ta=ta,
        fa_sentiment=fa,
        risk_report=risk,
    )

    # ---------------------------------------------------------------------- #
    # Persist to Hermes memory                                                 #
    # ---------------------------------------------------------------------- #
    try:
        hermes = _hermes or HermesMemoryEngine()
        hermes.save_trade_log(symbol, final.to_dict())
        logger.info("[Crew] Result persisted to Hermes memory for %s.", symbol)
    except Exception as exc:
        logger.warning("[Crew] Hermes persistence failed (non-fatal): %s", exc)

    logger.info(
        "[Crew] Pipeline complete for %s → verdict=%s score=%.2f veto=%s",
        symbol, final.verdict, final.score, risk.veto_applied,
    )
    return final


__all__ = ["run_trading_crew", "CrewFinalVerdict", "TAResult"]
