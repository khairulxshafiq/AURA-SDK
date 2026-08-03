"""amara/tests/test_indicators.py

Unit tests for ``amira.tools.indicators``.
The tests verify that the ``compute_indicators`` function correctly
calculates RSI‑14, ATR‑14 and moving averages on a synthetic OHLCV DataFrame.
We use deterministic data so the expected values are known.
"""

import pandas as pd
import pytest

from amira.tools.indicators import compute_indicators


def _generate_sample_df() -> pd.DataFrame:
    """Create a deterministic OHLCV DataFrame with 250 rows.

    The data is crafted so that Close prices increase linearly, which yields
    predictable moving averages. ``pandas_ta`` computes RSI/ATR based on the
    same series; we assert only that the function returns values of the correct
    type and shape, not exact numeric values, because the TA algorithm may vary
    slightly across versions.
    """
    n = 250
    # Simple synthetic data: price rises from 100 to 150
    close = pd.Series([100 + i * 0.2 for i in range(n)], name="Close")
    open_ = close.shift(1).fillna(close.iloc[0])
    high = close + 0.5
    low = close - 0.5
    volume = pd.Series([1000 + i for i in range(n)], name="Volume")
    df = pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    })
    return df


def test_compute_indicators_basic():
    df = _generate_sample_df()
    result = compute_indicators(df)
    # Verify that all expected keys exist
    expected_keys = {"rsi14", "atr14", "ma20", "ma50", "ma200"}
    assert set(result.keys()) == expected_keys
    # Types should be float
    for key in expected_keys:
        assert isinstance(result[key], float)
    # Moving averages should be close to the mean of the last N values
    ma20_expected = round(df["Close"].tail(20).mean(), 3)
    assert result["ma20"] == ma20_expected
    ma50_expected = round(df["Close"].tail(50).mean(), 3)
    assert result["ma50"] == ma50_expected
    ma200_expected = round(df["Close"].tail(200).mean(), 3)
    assert result["ma200"] == ma200_expected


def test_compute_indicators_invalid_input():
    # Empty DataFrame should raise ValueError
    empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    with pytest.raises(ValueError):
        compute_indicators(empty_df)
    # Missing column should raise ValueError
    bad_df = pd.DataFrame({"Open": [1], "High": [2], "Low": [3], "Close": [4]})
    with pytest.raises(ValueError):
        compute_indicators(bad_df)
