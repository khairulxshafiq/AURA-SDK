"""
Trading Service Module for AURA-SDK
Fetch real-time stock quotes, fundamental ratios, and technical indicators via yfinance.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger("aura.tools.trading_service")

# Common Bursa Malaysia & International stock name mappings
TICKER_MAP = {
    "maybank": "1155.KL",
    "malayan banking": "1155.KL",
    "tenaga": "5347.KL",
    "tenaga nasional": "5347.KL",
    "tnb": "5347.KL",
    "public bank": "1295.KL",
    "pbbank": "1295.KL",
    "cimb": "1023.KL",
    "cimb group": "1023.KL",
    "ihh": "5225.KL",
    "ihh healthcare": "5225.KL",
    "celcomdigi": "6947.KL",
    "digi": "6947.KL",
    "topglov": "7113.KL",
    "top glove": "7113.KL",
    "gamuda": "5398.KL",
    "simedarby": "4197.KL",
    "sime darby": "4197.KL",
    "apple": "AAPL",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "microsoft": "MSFT",
    "google": "GOOGL",
}

# Regex for explicit Bursa 4-digit ticker (e.g. 1155 or 1155.KL)
BURSA_NUMERIC_PATTERN = re.compile(r'^\b(\d{4})(\.KL)?\b$', re.IGNORECASE)

def resolve_stock_ticker(query: str) -> str:
    """
    Resolve a search query or company name into a standard stock ticker.
    Appends '.KL' for Bursa Malaysia 4-digit codes if omitted.
    """
    clean = query.strip()
    
    # Check exact match in ticker map
    q_lower = clean.lower()
    if q_lower in TICKER_MAP:
        return TICKER_MAP[q_lower]
        
    # Check if query is 4 digits (e.g. 1155)
    match = BURSA_NUMERIC_PATTERN.match(clean)
    if match:
        return f"{match.group(1)}.KL"
        
    # Return upper-case ticker (e.g. AAPL, 1155.KL)
    return clean.upper()

def get_stock_quote(symbol: str) -> dict:
    """
    Get real-time stock quote and market summary from Yahoo Finance.
    For Bursa Malaysia stocks, symbol must end with '.KL' (e.g. '1155.KL').
    """
    import yfinance as yf
    resolved = resolve_stock_ticker(symbol)
    try:
        ticker = yf.Ticker(resolved)
        info = ticker.info
        if not info or ("symbol" not in info and "shortName" not in info):
            return {"error": f"No quote data found for symbol '{symbol}' ({resolved})"}
            
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        return {
            "symbol": info.get("symbol", resolved),
            "name": info.get("shortName") or info.get("longName") or resolved,
            "price": price,
            "currency": info.get("currency", "MYR" if resolved.endswith(".KL") else "USD"),
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
        logger.error(f"Error fetching stock quote for {resolved}: {e}")
        return {"error": f"Gagal mengambil petikan harga bagi {resolved}: {str(e)}"}

def get_financial_ratios(symbol: str) -> dict:
    """
    Get fundamental financial ratios from Yahoo Finance.
    Evaluates revenue growth, earnings growth, ROE, P/E ratio, dividend yield, and institutional ownership.
    """
    import yfinance as yf
    resolved = resolve_stock_ticker(symbol)
    try:
        ticker = yf.Ticker(resolved)
        info = ticker.info
        if not info or ("symbol" not in info and "shortName" not in info):
            return {"error": f"No ratios data found for symbol '{symbol}' ({resolved})"}
            
        raw_dy = info.get("dividendYield")
        if raw_dy is not None:
            dividend_yield_pct = round(raw_dy, 2) if raw_dy > 1.0 else round(raw_dy * 100, 2)
        else:
            dividend_yield_pct = None
        
        roe = info.get("returnOnEquity")
        roe_pct = round(roe * 100, 2) if roe else None

        rev_growth = info.get("revenueGrowth")
        rev_growth_pct = round(rev_growth * 100, 2) if rev_growth else None

        earn_growth = info.get("earningsGrowth")
        earn_growth_pct = round(earn_growth * 100, 2) if earn_growth else None

        payout = info.get("payoutRatio")
        payout_pct = round(payout * 100, 2) if payout else None

        return {
            "symbol": resolved,
            "name": info.get("shortName") or info.get("longName"),
            "revenueGrowthPct": rev_growth_pct,
            "earningsGrowthPct": earn_growth_pct,
            "returnOnEquityPct": roe_pct,
            "peRatioTTM": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "institutionalOwnershipPct": round(info.get("heldPercentInstitutions", 0) * 100, 2) if info.get("heldPercentInstitutions") else None,
            "beta": info.get("beta"),
            "dividendYieldPct": dividend_yield_pct,
            "payoutRatioPct": payout_pct,
            "priceToBookTTM": info.get("priceToBook"),
        }
    except Exception as e:
        logger.error(f"Error fetching ratios for {resolved}: {e}")
        return {"error": f"Gagal mengambil nisbah kewangan bagi {resolved}: {str(e)}"}

def get_rsi(symbol: str) -> dict:
    """
    Get 14-day Relative Strength Index (RSI-14) using historical price data.
    Indicates Overbought (>70), Oversold (<30), or Neutral conditions.
    """
    import yfinance as yf
    resolved = resolve_stock_ticker(symbol)
    try:
        df = yf.Ticker(resolved).history(period="60d")
        if df.empty:
            return {"error": f"No price history data found for {resolved}"}
            
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        rsi_clean = rsi.dropna()
        if rsi_clean.empty:
            return {"error": f"Not enough historical data to calculate RSI-14 for {resolved}"}
            
        latest_rsi = round(float(rsi_clean.iloc[-1]), 2)
        latest_date = rsi_clean.index[-1].strftime("%Y-%m-%d")
        
        status = "NEUTRAL"
        if latest_rsi >= 70:
            status = "OVERBOUGHT (Terlebih Beli)"
        elif latest_rsi <= 30:
            status = "OVERSOLD (Terlebih Jual)"

        return {
            "symbol": resolved,
            "date": latest_date,
            "rsi_14": latest_rsi,
            "condition": status
        }
    except Exception as e:
        logger.error(f"Error calculating RSI for {resolved}: {e}")
        return {"error": f"Gagal mengira RSI bagi {resolved}: {str(e)}"}

def get_sma(symbol: str) -> dict:
    """
    Get 50-day Simple Moving Average (SMA-50) using historical price data.
    Helps identify short/medium-term trend direction relative to current price.
    """
    import yfinance as yf
    resolved = resolve_stock_ticker(symbol)
    try:
        df = yf.Ticker(resolved).history(period="100d")
        if df.empty:
            return {"error": f"No price history data found for {resolved}"}
            
        sma = df['Close'].rolling(window=50).mean()
        sma_clean = sma.dropna()
        
        if sma_clean.empty:
            return {"error": f"Not enough historical data to calculate 50-day SMA for {resolved}"}
            
        latest_sma = round(float(sma_clean.iloc[-1]), 2)
        latest_price = round(float(df['Close'].iloc[-1]), 2)
        latest_date = sma_clean.index[-1].strftime("%Y-%m-%d")
        
        trend = "BULLISH (Harga atas SMA-50)" if latest_price >= latest_sma else "BEARISH (Harga bawah SMA-50)"

        return {
            "symbol": resolved,
            "date": latest_date,
            "current_price": latest_price,
            "sma_50": latest_sma,
            "trend": trend
        }
    except Exception as e:
        logger.error(f"Error calculating SMA for {resolved}: {e}")
        return {"error": f"Gagal mengira SMA bagi {resolved}: {str(e)}"}

__all__ = [
    "resolve_stock_ticker",
    "get_stock_quote",
    "get_financial_ratios",
    "get_rsi",
    "get_sma",
]
