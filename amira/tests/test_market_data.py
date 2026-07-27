# amira tools market data tests
"""Unit tests for the market_data.fetch_ohlcv function.
The test uses monkeypatch to replace ``yfinance.Ticker`` with a lightweight stub
that returns a deterministic pandas ``DataFrame``.
"""

import pandas as pd
import datetime as dt
from types import SimpleNamespace

import pytest

from tools.market_data import fetch_ohlcv


class DummyTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period="1mo"):
        # Return a small DataFrame with predictable values
        dates = pd.date_range(end=dt.datetime.utcnow(), periods=3, freq="D")
        data = {
            "Open": [100.0, 101.5, 102.0],
            "High": [105.0, 106.0, 107.5],
            "Low": [99.0, 100.5, 101.0],
            "Close": [104.0, 105.5, 106.0],
            "Volume": [1000, 1500, 1200],
        }
        return pd.DataFrame(data, index=dates)


def test_fetch_ohlcv_success(monkeypatch):
    # Patch yfinance.Ticker to use DummyTicker
    monkeypatch.setattr("yfinance.Ticker", DummyTicker)

    # US market, no suffix needed
    result = fetch_ohlcv("AAPL", "US", period="3d")
    assert isinstance(result, list)
    assert len(result) == 3
    first = result[0]
    # Verify keys exist and types are correct
    assert set(first.keys()) == {"date", "open", "high", "low", "close", "volume"}
    assert isinstance(first["date"], str)
    assert isinstance(first["open"], float)
    assert isinstance(first["volume"], int)


def test_fetch_ohlcv_invalid_symbol(monkeypatch):
    # Patch to raise an exception when history is called
    class BadTicker:
        def __init__(self, symbol):
            pass

        def history(self, period="1mo"):
            raise ValueError("Invalid ticker")

    monkeypatch.setattr("yfinance.Ticker", BadTicker)
    err = fetch_ohlcv("", "US")
    assert isinstance(err, dict)
    assert err["error"] == "Invalid symbol"


def test_fetch_ohlcv_unsupported_market(monkeypatch):
    # Use a valid ticker but unsupported market code
    monkeypatch.setattr("yfinance.Ticker", DummyTicker)
    err = fetch_ohlcv("AAPL", "EU")  # EU not in allowed literals
    assert isinstance(err, dict)
    assert err["error"] == "Invalid market or symbol"

# End of test file
