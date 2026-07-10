# Trading Modules & Agents Blueprint

Below is the verified code from AURA v5 for stock trading routing, financial indicators, and multi-agent analysis (LangGraph & CrewAI).

## 1. Stock Indicators & Ratios (`stock_tools.py`)
This tool queries Yahoo Finance (`yfinance` package) to get real-time price quotes, fundamental financial ratios, and growth metrics.

```python
import yfinance as yf

def get_stock_quote(symbol: str) -> dict:
    """Get the real-time stock quote and basic info from Yahoo Finance.
    For Bursa Malaysia, append '.KL' (e.g. '1155.KL').
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or "symbol" not in info:
            return {"error": f"No quote data found for {symbol}"}
            
        return {
            "symbol": info.get("symbol", symbol),
            "name": info.get("shortName") or info.get("longName"),
            "price": info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"),
            "dayLow": info.get("dayLow"),
            "dayHigh": info.get("dayHigh"),
            "yearHigh": info.get("fiftyTwoWeekHigh"),
            "yearLow": info.get("fiftyTwoWeekLow"),
            "marketCap": info.get("marketCap"),
            "pe": info.get("trailingPE") or info.get("forwardPE"),
            "eps": info.get("trailingEps") or info.get("forwardEps"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "volume": info.get("volume"),
            "averageVolume": info.get("averageVolume"),
        }
    except Exception as e:
        return {"error": str(e)}

def get_financial_ratios(symbol: str) -> dict:
    """Get fundamental financial ratios from Yahoo Finance.
    Includes growth metrics for swing trading evaluation:
    Revenue Growth, Earnings Growth, ROE, Institutional Ownership, Beta.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or "symbol" not in info:
            return {"error": f"No ratios data found for {symbol}"}
            
        raw_dy = info.get("dividendYield")
        dividend_yield_pct = round(raw_dy * 100, 2) if raw_dy else None

        return {
            "symbol": symbol,
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "returnOnEquityTTM": info.get("returnOnEquity"),
            "peRatioTTM": info.get("trailingPE"),
            "institutionalOwnership": info.get("heldPercentInstitutions"),
            "beta": info.get("beta"),
            "dividendYieldTTM": dividend_yield_pct,
            "payoutRatioTTM": info.get("payoutRatio"),
            "priceToBookRatioTTM": info.get("priceToBook"),
        }
    except Exception as e:
        return {"error": str(e)}
```

---

## 2. Technical Trend Indicators (`technical_tools.py`)
This tool calculates the Relative Strength Index (RSI-14) and 50-day Simple Moving Average (SMA-50) using rolling averages on Yahoo Finance historical pricing.

```python
import yfinance as yf
import pandas as pd

def get_rsi(symbol: str) -> dict:
    """Get the Relative Strength Index (RSI) for a stock symbol using Yahoo Finance.
    Returns the latest RSI value indicating overbought (>70) or oversold (<30) conditions.
    """
    try:
        # Fetch 60 days of data to calculate 14-day RSI
        df = yf.Ticker(symbol).history(period="60d")
        if df.empty:
            return {"error": f"No data found for {symbol}"}
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        rsi_clean = rsi.dropna()
        if rsi_clean.empty:
            return {"error": f"Not enough data to calculate RSI for {symbol}"}
            
        latest_rsi = rsi_clean.iloc[-1]
        latest_date = rsi_clean.index[-1].strftime("%Y-%m-%d")
        
        return {
            "symbol": symbol,
            "date": latest_date,
            "rsi_14_day": float(latest_rsi)
        }
    except Exception as e:
        return {"error": str(e)}

def get_sma(symbol: str) -> dict:
    """Get the Simple Moving Average (SMA) for a stock symbol using Yahoo Finance.
    Useful for identifying the current trend (e.g., above or below 50-day SMA).
    """
    try:
        # Fetch 100 days of data to calculate 50-day SMA
        df = yf.Ticker(symbol).history(period="100d")
        if df.empty:
            return {"error": f"No data found for {symbol}"}
        
        sma = df['Close'].rolling(window=50).mean()
        sma_clean = sma.dropna()
        
        if sma_clean.empty:
            return {"error": f"Not enough data to calculate 50-day SMA for {symbol}"}
            
        latest_sma = sma_clean.iloc[-1]
        latest_date = sma_clean.index[-1].strftime("%Y-%m-%d")
        
        return {
            "symbol": symbol,
            "date": latest_date,
            "sma_50_day": float(latest_sma)
        }
    except Exception as e:
        return {"error": str(e)}
```

---

## 3. Hybrid Intent Router (`trading_router.py`)
Uses a 4-tier filtering logic to parse stock queries from chat, map company names to tickers using `bursa_tickers.json`, and run intent classification.

```python
import re
import json
from typing import Optional

# Bursa Malaysia ticker pattern: 4-digit number optionally followed by .KL
STOCK_TICKER_PATTERN = re.compile(r'\b(\d{4})(\.KL)?\b', re.IGNORECASE)

def extract_ticker(message: str) -> Optional[str]:
    """Scan message for an explicit Bursa ticker (e.g. 1155.KL or 1155)."""
    match = STOCK_TICKER_PATTERN.search(message)
    if match:
        return f"{match.group(1)}.KL"
    return None

def extract_company_name(message: str, ticker_map: dict) -> Optional[str]:
    """Scan message for any company name present in the ticker map."""
    msg_lower = message.lower()
    for name in sorted(ticker_map.keys(), key=len, reverse=True):
        if name in msg_lower:
            return ticker_map[name]
    return None
```

---

## 4. Simple ASB-Style LangGraph Agent (`crews/crew_trading/crew.py`)
Presents a dividend and stability evaluation based on yfinance ratios.

```python
# System prompt criteria:
# 1. Dividend Yield (TTM): 4% - 7% is healthy.
# 2. ROE (Return on Equity): > 15% is good.
# 3. P/E Ratio: Lower is better.
# 4. Payout Ratio: 40% - 70% is healthy.
```

---

## 5. Advanced Multi-Agent Swing Trading Crew (`crews/crew_trading_advanced/crew.py`)
Uses **CrewAI** to launch 3 specialized agents executing sequential tasks to evaluate swing setups and structure an 8-section Telegram report:
1. **Growth Analyst**: Assesses Revenue/Earnings growth, ROE, P/E, and Smart Money interest.
2. **Technical & Momentum Analyst**: Evaluates RSI-14, SMA-50 trend, volume vs avg, and calculates trade setup (Entry, Targets, Stop Loss, R/R).
3. **Portfolio Strategist**: Integrates growth + technical results, structures the decision matrix (/20), assigns portfolio type (Core, Satellite, Casino), and drafts the final Malay report.
