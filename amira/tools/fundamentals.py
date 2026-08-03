"""amira/tools/fundamentals.py

Standalone tool for fetching fundamental financial metrics via yfinance.
Mirrors the conventions in ``AuraOne/tools/trading_service.get_fundamentals``
so downstream consumers receive identical key names and value semantics,
but the implementation is completely isolated from the AuraOne package.

Main function
-------------
``fetch_fundamentals(symbol, market)``
    Returns a typed dict with keys:
    - ``symbol``         – cleaned symbol string
    - ``yf_symbol``      – yahoo-finance ticker string used for the request
    - ``name``           – company short name
    - ``per``            – trailing P/E (None if unavailable)
    - ``pe_status``      – "normal" | "negative/distorted"
    - ``eps_ttm``        – EPS trailing twelve months
    - ``roe_pct``        – Return on Equity as a percentage
    - ``nta``            – Net Tangible Asset / Book Value per share
    - ``dividend_yield_pct`` – dividend yield as a percentage (0.0 if none)
    - ``dividend_consistency`` – "consistent" | "none"
    - ``operating_cashflow``   – operating cash flow int
    - ``free_cash_flow``       – "positive" | "pressured"
    - ``total_debt``           – total debt int
    - ``debt_to_equity``       – D/E ratio float
    - ``interest_cover``       – interest coverage ratio float
    - ``health_status``        – emoji + human label (e.g. "🟢 Budak Healthy")
    - ``health_flags``         – dict of individual health boolean checks
    - ``error``                – only present on failure; other keys absent
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional, Union

import yfinance as yf

from amira.tools.market_data import _map_symbol  # reuse ticker mapping

logger = logging.getLogger("amira.tools.fundamentals")


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely coerce *val* to float; return *default* on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


FundamentalsResult = Dict[str, Any]


def fetch_fundamentals(
    symbol: str,
    market: Literal["MY", "US", "HK", "INDEX"] = "MY",
) -> FundamentalsResult:
    """Fetch fundamental metrics for *symbol* on *market*.

    Parameters
    ----------
    symbol:
        Base ticker symbol without suffix (e.g. ``"1155"`` for Maybank on MY).
    market:
        Market code – used to build the Yahoo Finance ticker suffix.

    Returns
    -------
    FundamentalsResult
        Dictionary of fundamental metrics.  On failure the dict contains an
        ``"error"`` key and no other financial keys.
    """
    if not symbol:
        return {"error": "Symbol cannot be empty"}

    try:
        yf_symbol = _map_symbol(symbol, market)
    except ValueError as exc:
        return {"error": str(exc)}

    clean_symbol = yf_symbol.replace(".KL", "").replace(".HK", "")

    try:
        ticker = yf.Ticker(yf_symbol)
        info: Dict[str, Any] = ticker.info or {}
    except Exception as exc:
        logger.error("yfinance fetch failed for %s: %s", yf_symbol, exc)
        return {"error": f"Failed to fetch data for {yf_symbol}: {exc}"}

    # ------------------------------------------------------------------
    # P/E ratio
    # ------------------------------------------------------------------
    per_raw = info.get("trailingPE") or info.get("forwardPE")
    per: Optional[float] = _safe_float(per_raw, default=None) if per_raw is not None else None
    pe_status = "normal" if (per is not None and per > 0) else "negative/distorted"
    eps_ttm = round(_safe_float(info.get("trailingEps") or info.get("forwardEps")), 3)

    # ------------------------------------------------------------------
    # ROE
    # ------------------------------------------------------------------
    roe = _safe_float(info.get("returnOnEquity"))
    # yfinance returns ROE as a decimal (0.12 = 12 %); normalise the same way
    # trading_service does: if abs value < 5 assume it's a decimal fraction.
    roe_pct = round(roe * 100, 2) if abs(roe) < 5.0 else round(roe, 2)

    # ------------------------------------------------------------------
    # Book value / NTA
    # ------------------------------------------------------------------
    nta = round(_safe_float(info.get("bookValue")), 3)

    # ------------------------------------------------------------------
    # Dividend yield
    # ------------------------------------------------------------------
    raw_dy = _safe_float(info.get("dividendYield"))
    if raw_dy > 0:
        dividend_yield_pct = round(raw_dy, 2) if raw_dy > 1.0 else round(raw_dy * 100, 2)
    else:
        dividend_yield_pct = 0.0
    pays_dividend = dividend_yield_pct > 0.5

    # ------------------------------------------------------------------
    # Debt / gearing
    # ------------------------------------------------------------------
    de_ratio = _safe_float(info.get("debtToEquity"), default=30.0)
    debt_to_equity = round(de_ratio / 100.0, 2) if de_ratio > 1.0 else round(de_ratio, 2)
    total_debt = int(_safe_float(info.get("totalDebt")))
    op_cashflow = int(_safe_float(info.get("operatingCashflow")))
    free_cashflow = int(_safe_float(info.get("freeCashflow")))
    interest_cover = round(_safe_float(info.get("interestCoverage"), default=2.5), 1)

    # ------------------------------------------------------------------
    # Health flags  (mirrors trading_service.get_fundamentals logic)
    # ------------------------------------------------------------------
    consistent_net_profit = (roe_pct > 8.0) and (pe_status == "normal")
    positive_op_cashflow = op_cashflow > 0 if op_cashflow != 0 else (roe_pct > 5.0)
    low_gearing = debt_to_equity < 0.6

    is_healthy = consistent_net_profit and positive_op_cashflow and low_gearing
    if is_healthy:
        health_status = "🟢 Budak Healthy"
    elif consistent_net_profit or roe_pct > 0:
        health_status = "🟡 Turnaround / Speculative"
    else:
        health_status = "🔴 Speculative / High-Risk"

    return {
        "symbol": clean_symbol,
        "yf_symbol": yf_symbol,
        "name": info.get("shortName") or info.get("longName") or clean_symbol,
        "sector": info.get("sector") or "General",
        "per": round(per, 2) if per is not None else None,
        "pe_status": pe_status,
        "eps_ttm": eps_ttm,
        "roe_pct": roe_pct,
        "nta": nta,
        "dividend_yield_pct": dividend_yield_pct,
        "dividend_consistency": "consistent" if pays_dividend else "none",
        "operating_cashflow": op_cashflow,
        "free_cash_flow": "positive" if free_cashflow > 0 else "pressured",
        "total_debt": total_debt,
        "debt_to_equity": debt_to_equity,
        "interest_cover": interest_cover,
        "health_status": health_status,
        "health_flags": {
            "consistent_net_profit": consistent_net_profit,
            "positive_operating_cashflow": positive_op_cashflow,
            "pays_dividend": pays_dividend,
            "low_gearing": low_gearing,
        },
    }


__all__ = ["fetch_fundamentals"]
