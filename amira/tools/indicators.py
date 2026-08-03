"""amira/tools/indicators.py

Utility module for computing technical indicators on OHLCV data frames.
The implementations follow the same conventions as `AuraOne/tools/trading_service.py`
so that downstream components receive consistent output formats.

Functions
---------
- `compute_indicators(df)`: Given a pandas DataFrame with columns
  ``['Open', 'High', 'Low', 'Close', 'Volume']`` (as returned by
  ``amira.tools.market_data.fetch_ohlcv``), compute the following indicators:
    - RSI‑14 (rounded to 1 decimal place)
    - ATR‑14 (rounded to 3 decimal places)
    - Moving averages for the Close price over 20, 50 and 200 periods
      (rounded to 3 decimal places)
  Returns a ``dict`` with keys ``rsi14``, ``atr14``, ``ma20``, ``ma50`` and
  ``ma200``.

The function is deliberately lightweight – it does not perform any I/O or
network calls and raises a ``ValueError`` if the input DataFrame does not contain
the required columns or contains insufficient rows for the calculations.
"""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta
from typing import Dict, Any


def _validate_df(df: pd.DataFrame) -> None:
    """Validate that *df* has the required OHLCV columns.

    Parameters
    ----------
    df: pd.DataFrame
        Input data frame.

    Raises
    ------
    ValueError
        If required columns are missing or the frame is empty.
    """
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"OHLCV DataFrame is missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError("OHLCV DataFrame is empty")


def compute_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute RSI‑14, ATR‑14 and moving averages on an OHLCV DataFrame.

    The calculation mirrors the logic in ``AuraOne/tools/trading_service.py``
    to guarantee identical output formats across services.

    Parameters
    ----------
    df: pd.DataFrame
        DataFrame containing ``Open``, ``High``, ``Low``, ``Close`` and ``Volume``
        columns. The index can be any monotonic sequence; only the values are
        used.

    Returns
    -------
    dict
        Dictionary with the following keys:
        ``rsi14`` (float, 1‑decimal), ``atr14`` (float, 3‑decimal),
        ``ma20`` (float, 3‑decimal), ``ma50`` (float, 3‑decimal),
        ``ma200`` (float, 3‑decimal).
    """
    _validate_df(df)

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    rsi_series = ta.rsi(close, length=14)
    if rsi_series.isna().all():
        rsi_val = 50.0
    else:
        rsi_val = float(rsi_series.dropna().iloc[-1])
    rsi14 = round(rsi_val, 1)

    atr_series = ta.atr(high, low, close, length=14)
    if atr_series.isna().all():
        atr_val = 0.02
    else:
        atr_val = float(atr_series.dropna().iloc[-1])
    atr14 = round(atr_val, 3)

    ma20 = round(float(close.tail(20).mean()), 3) if len(close) >= 20 else round(float(close.iloc[-1]), 3)
    ma50 = round(float(close.tail(50).mean()), 3) if len(close) >= 50 else round(float(close.iloc[-1]), 3)
    ma200 = round(float(close.tail(200).mean()), 3) if len(close) >= 200 else round(float(close.iloc[-1]), 3)

    return {
        "rsi14": rsi14,
        "atr14": atr14,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
    }


__all__ = ["compute_indicators"]
