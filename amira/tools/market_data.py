# amira tools market data
"""Utility for fetching OHLCV market data via yfinance.
The function maps market codes to Yahoo Finance ticker suffixes, adds a simple
in‑memory cache to avoid hitting the rate limits, and returns a typed error
structure instead of raising exceptions.
"""

from __future__ import annotations

import datetime as _dt
import threading
from typing import List, Dict, Any, TypedDict, Literal, Union
import yfinance as yf

# ---------------------------------------------------------------------------
# Simple thread‑safe cache
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 60  # keep results for 1 minute
_CACHE: Dict[str, tuple[_dt.datetime, Any]] = {}


class OHLCVRecord(TypedDict):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class FetchError(TypedDict):
    error: str
    details: str


def _cache_key(symbol: str, market: str, period: str) -> str:
    return f"{symbol}|{market}|{period}"


def _map_symbol(symbol: str, market: str) -> str:
    """Map a plain ticker symbol to the Yahoo Finance format based on market.

    - ``MY``   → ``{symbol}.KL``
    - ``US``   → ``{symbol}`` (no suffix)
    - ``HK``   → ``{symbol}.HK``
    - ``INDEX``→ keep as‑is (used for indices like ``^GSPC``)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")

    market = market.upper()
    if market == "MY":
        return f"{symbol}.KL"
    if market == "US":
        return symbol
    if market == "HK":
        return f"{symbol}.HK"
    if market == "INDEX":
        return symbol  # caller should provide the correct index symbol (e.g. ^GSPC)
    raise ValueError(f"Unsupported market code: {market}")


def fetch_ohlcv(
    symbol: str,
    market: Literal["MY", "US", "HK", "INDEX"],
    period: str = "1mo",
) -> Union[List[OHLCVRecord], FetchError]:
    """Fetch OHLCV data for *symbol* on *market*.

    Parameters
    ----------
    symbol: str
        Base ticker symbol without any market suffix.
    market: Literal["MY", "US", "HK", "INDEX"]
        Market identifier used to map the ticker.
    period: str, optional
        yfinance period string (e.g. ``"1d"``, ``"5d"``, ``"1mo"``). Defaults to ``"1mo"``.

    Returns
    -------
    List[OHLCVRecord]
        List of OHLCV dictionaries ordered by date (oldest → newest).
    FetchError
        ``{"error": "...", "details": "..."}`` when the request cannot be
        satisfied (invalid symbol, network issue, etc.).
    """
    # Validate input early to avoid unnecessary work
    if not symbol:
        return {"error": "Invalid symbol", "details": "Symbol is empty"}

    try:
        yf_symbol = _map_symbol(symbol, market)
    except ValueError as exc:
        return {"error": "Invalid market or symbol", "details": str(exc)}

    cache_key = _cache_key(yf_symbol, market, period)
    now = _dt.datetime.utcnow()

    # -----------------------------------------------------------------------
    # Cache lookup
    # -----------------------------------------------------------------------
    with _CACHE_LOCK:
        entry = _CACHE.get(cache_key)
        if entry:
            ts, data = entry
            if (now - ts).total_seconds() < _CACHE_TTL_SECONDS:
                return data  # cached hit
            else:
                # stale entry – drop it
                del _CACHE[cache_key]

    # -----------------------------------------------------------------------
    # Fetch from yfinance – any exception is captured and turned into a FetchError
    # -----------------------------------------------------------------------
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period)
        if df.empty:
            raise ValueError("No data returned for the given symbol/period")
    except Exception as exc:
        return {"error": "Data fetch failed", "details": str(exc)}

    # Transform into list of TypedDicts
    records: List[OHLCVRecord] = []
    for idx, row in df.iterrows():
        # yfinance may return Timestamp objects; convert to ISO date string
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        records.append(
            OHLCVRecord(
                date=date_str,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
            )
        )

    # Store in cache for next calls
    with _CACHE_LOCK:
        _CACHE[cache_key] = (now, records)

    return records

# End of file
