"""
AMIRA Trading Engine — Decoupled Trading Microservice Core
Methodology: Asri Ahmad Academy (Top-Down, CR Market Flow, 3M, DACE, Mode Swing vs Position).
Guardrail: Advisory Only — No Auto Buy/Sell/Execution.
"""
import re
import datetime
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("amira.trading_engine")

# Symbol resolution mapping for common Bursa Malaysia stocks & tickers
BURSA_SYMBOL_MAP: Dict[str, str] = {
    "aemulus": "0181",
    "maybank": "1155",
    "malayan banking": "1155",
    "tenaga": "5347",
    "tenaga nasional": "5347",
    "tnb": "5347",
    "public bank": "1295",
    "pbbank": "1295",
    "cimb": "1023",
    "cimb group": "1023",
    "ihh": "5225",
    "ihh healthcare": "5225",
    "celcomdigi": "6947",
    "digi": "6947",
    "topglov": "7113",
    "top glove": "7113",
    "gamuda": "5398",
    "simedarby": "4197",
    "sime darby": "4197",
    "ytl": "4677",
    "ytl corp": "4677",
    "ytlpow": "6742",
    "ytl power": "6742",
    "myeg": "0138",
    "inari": "0166",
    "frontken": "0128",
    "pentamaster": "7160",
    "penta": "7160",
    "genetec": "0104",
    "greatech": "0082",
    "dayang": "5141",
    "wasco": "5142",
    "hibiscus": "5199",
    "dialog": "7277",
    "apple": "AAPL",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "microsoft": "MSFT",
    "google": "GOOGL",
}

DISCLAIMER_TEXT = "⚠️ Disclaimer: Ini analisis pendidikan (DYOR). AMIRA BUKAN advisor automatik buy/sell & tidak execute trade."

def _format_yf_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    if clean.endswith(".KL"):
        return clean
    if clean.isdigit() and len(clean) == 4:
        return f"{clean}.KL"
    mapped = BURSA_SYMBOL_MAP.get(clean.lower())
    if mapped:
        if mapped.isdigit() and len(mapped) == 4:
            return f"{mapped}.KL"
        return mapped
    return clean

def resolve_symbol(query: str) -> dict:
    clean = query.strip().lower()
    matches = []
    if clean.isdigit() and len(clean) == 4:
        matches.append({"symbol": clean, "name": f"Bursa Stock {clean}", "confidence": 1.0})
    else:
        for key, code in BURSA_SYMBOL_MAP.items():
            if clean in key:
                name = key.upper()
                confidence = 0.98 if clean == key else 0.85
                matches.append({"symbol": code, "name": name, "confidence": confidence})
    if not matches:
        raw = query.strip().upper()
        matches.append({"symbol": raw, "name": raw, "confidence": 0.5})
    return {"matches": matches, "disclaimer": DISCLAIMER_TEXT}

def get_live_quote(symbol: str) -> dict:
    import yfinance as yf
    yf_symbol = _format_yf_symbol(symbol)
    bursa_code = yf_symbol.replace(".KL", "")
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}
        df = ticker.history(period="250d")
        if df.empty:
            return {"error": f"Live data tidak dapat ditarik untuk {symbol} ({yf_symbol}).", "disclaimer": DISCLAIMER_TEXT}
            
        close_series = df['Close']
        latest_price = round(float(close_series.iloc[-1]), 3)
        prev_close = round(float(close_series.iloc[-2]), 3) if len(close_series) > 1 else latest_price
        change = round(latest_price - prev_close, 3)
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
        
        latest_row = df.iloc[-1]
        day_high = round(float(latest_row['High']), 3)
        day_low = round(float(latest_row['Low']), 3)
        open_price = round(float(latest_row['Open']), 3)
        volume = int(latest_row['Volume'])
        avg_vol_30d = int(df['Volume'].tail(30).mean()) if len(df) >= 30 else volume
        
        ma20 = round(float(close_series.tail(20).mean()), 3) if len(close_series) >= 20 else latest_price
        ma50 = round(float(close_series.tail(50).mean()), 3) if len(close_series) >= 50 else latest_price
        ma200 = round(float(close_series.tail(200).mean()), 3) if len(close_series) >= 200 else latest_price
        
        delta = close_series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi14 = round(float(rsi.dropna().iloc[-1]), 1) if not rsi.dropna().empty else 50.0
        
        tr = df['High'] - df['Low']
        atr14 = round(float(tr.rolling(14).mean().dropna().iloc[-1]), 3) if len(df) >= 14 else 0.02
        
        name = info.get("shortName") or info.get("longName") or bursa_code
        sector = info.get("sector") or "General"
        shariah_compliant = not ("Financial" in sector and "Islamic" not in name)
        
        return {
            "symbol": bursa_code,
            "yf_symbol": yf_symbol,
            "name": name,
            "sector": sector,
            "shariah_compliant": shariah_compliant,
            "price": latest_price,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "open": open_price,
            "volume": volume,
            "avg_volume_30d": avg_vol_30d,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "rsi14": rsi14,
            "atr14": atr14,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "disclaimer": DISCLAIMER_TEXT
        }
    except Exception as e:
        logger.error(f"Error in get_live_quote: {e}")
        return {"error": f"Live data tidak dapat ditarik untuk {symbol}: {str(e)}", "disclaimer": DISCLAIMER_TEXT}

def get_fundamentals(symbol: str) -> dict:
    import yfinance as yf
    yf_symbol = _format_yf_symbol(symbol)
    bursa_code = yf_symbol.replace(".KL", "")
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}
        per = float(info.get("trailingPE") or info.get("forwardPE") or 0.0)
        eps_ttm = float(info.get("trailingEps") or 0.0)
        roe = float(info.get("returnOnEquity") or 0.0)
        roe_pct = round(roe * 100, 2) if abs(roe) < 5.0 else round(roe, 2)
        nta = float(info.get("bookValue") or 0.0)
        raw_dy = float(info.get("dividendYield") or 0.0)
        dividend_yield_pct = round(raw_dy if raw_dy > 1.0 else raw_dy * 100, 2)
        
        is_healthy = roe_pct > 8.0 and per > 0
        health_status = "🟢 Budak Healthy" if is_healthy else "🟡 Turnaround / Speculative"
        
        return {
            "symbol": bursa_code,
            "name": info.get("shortName") or bursa_code,
            "per": round(per, 2),
            "eps_ttm": round(eps_ttm, 3),
            "roe_pct": roe_pct,
            "nta": round(nta, 3),
            "dividend_yield_pct": dividend_yield_pct,
            "health_status": health_status,
            "disclaimer": DISCLAIMER_TEXT
        }
    except Exception as e:
        return {"error": f"Fundamental fetch error: {str(e)}", "disclaimer": DISCLAIMER_TEXT}

def analyze_counter(symbol: str, mode: str = "swing") -> dict:
    quote = get_live_quote(symbol)
    if "error" in quote:
        return quote
    fundamentals = get_fundamentals(symbol)
    
    price = quote["price"]
    rsi = quote["rsi14"]
    ma20 = quote["ma20"]
    ma50 = quote["ma50"]
    
    mode_clean = mode.lower().strip()
    if mode_clean == "swing":
        tp1 = round(price * 1.08, 3)
        tp2 = round(price * 1.15, 3)
        cut_loss = round(price * 0.95, 3)
        risk = round(price - cut_loss, 3)
        reward = round(tp1 - price, 3)
        rrr = round(reward / risk, 2) if risk > 0 else 0.0
        
        verdict = f"Kaunter {quote['name']} berada dalam keadaan trend {'UPTREND' if price >= ma20 else 'CONSOLIDATION'}. RRR minima 1:{rrr}."
        
        return {
            "symbol": quote["symbol"],
            "name": quote["name"],
            "sector": quote["sector"],
            "mode": "swing",
            "price": price,
            "rsi14": rsi,
            "ma20": ma20,
            "ma50": ma50,
            "trade_plan": {
                "entry": price,
                "tp1": tp1,
                "tp2": tp2,
                "cut_loss": cut_loss,
                "risk_pct": -5.0,
                "reward_pct": 8.0,
                "rrr": f"1:{rrr}",
                "holding_period": "1-4 minggu"
            },
            "verdict": verdict,
            "disclaimer": DISCLAIMER_TEXT
        }
    else: # position
        is_healthy = fundamentals.get("health_status", "").startswith("🟢")
        verdict = f"Kaunter {quote['name']} {'SESUAI' if is_healthy else 'TIDAK SESUAI'} untuk akumulasi long-term/DCA. Health: {fundamentals.get('health_status')}."
        return {
            "symbol": quote["symbol"],
            "name": quote["name"],
            "sector": quote["sector"],
            "mode": "position",
            "price": price,
            "fundamentals": fundamentals,
            "dca_suitability": "Sesuai" if is_healthy else "Kurang Sesuai",
            "verdict": verdict,
            "disclaimer": DISCLAIMER_TEXT
        }

def screen_stocks(mode: str = "swing", shariah_only: bool = False, limit: int = 8) -> dict:
    mode_clean = mode.lower().strip()
    results = []
    if mode_clean == "swing":
        candidates = [
            ("0181", "AEMULUS", "Technology", 0.385, 2.1, 4, "Volum lonjak 2.1x, breakout consolidation"),
            ("6742", "YTLPOW", "Utilities", 4.85, 1.8, 4, "Permintaan tenaga data center"),
            ("0166", "INARI", "Technology", 3.20, 1.6, 3, "Catalyst semikonduktor"),
            ("5141", "DAYANG", "Energy", 2.45, 1.9, 4, "Sektor rotation oil & gas"),
            ("5398", "GAMUDA", "Construction", 7.50, 1.5, 4, "Anugerah projek infrastruktur baharu"),
        ]
    else:
        candidates = [
            ("1155", "MAYBANK", "Financials", 10.78, 1.0, 5, "Budak healthy, dividen 6.1%, ROE 11.3%"),
            ("5347", "TENAGA", "Utilities", 14.20, 1.2, 5, "Budak healthy, monopoli transmisi tenaga"),
            ("4197", "SIMEDARBY", "Industrial", 2.65, 1.1, 4, "Kewangan kukuh, hasil dividen menarik"),
            ("5225", "IHH", "Healthcare", 6.30, 1.0, 4, "Megatrend pasaran kesihatan"),
        ]
    for sym, name, sec, price, vol_x, score, reason in candidates[:limit]:
        results.append({
            "symbol": sym,
            "name": name,
            "sector": sec,
            "price": price,
            "volume_x_avg": vol_x,
            "score": score,
            "reason": reason
        })
    return {
        "mode": mode_clean,
        "shariah_only": shariah_only,
        "results": results,
        "disclaimer": DISCLAIMER_TEXT
    }
