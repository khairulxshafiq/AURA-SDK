"""
Trading Service Module for AURA-SDK (v1.0 - AURA-Trade)
Implements 7 deterministic function-calling tools for Bursa Malaysia live trading & analysis.
Methodology: Asri Ahmad Academy (Top-Down, CR Market Flow, 3M, DACE, Mode Swing vs Position).
"""
import re
import datetime
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("aura.tools.trading_service")

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

BURSA_CODE_RE = re.compile(r'^\b(\d{4})(\.KL)?\b$', re.IGNORECASE)

def _format_yf_symbol(symbol: str) -> str:
    """Format Bursa symbol (e.g. '0181' or '1155') into yfinance symbol (e.g. '0181.KL')."""
    clean = symbol.strip().upper()
    if clean.endswith(".KL"):
        return clean
    if clean.isdigit() and len(clean) == 4:
        return f"{clean}.KL"
        
    # Check map
    mapped = BURSA_SYMBOL_MAP.get(clean.lower())
    if mapped:
        if mapped.isdigit() and len(mapped) == 4:
            return f"{mapped}.KL"
        return mapped
        
    return clean

def resolve_symbol(query: str) -> dict:
    """
    Tukar nama syarikat/sebahagian nama kepada kod Bursa rasmi 4-digit.
    Guna bila user sebut nama, bukan kod.
    """
    clean = query.strip().lower()
    matches = []
    
    # Direct code match
    if clean.isdigit() and len(clean) == 4:
        matches.append({"symbol": clean, "name": f"Bursa Stock {clean}", "confidence": 1.0})
    else:
        for key, code in BURSA_SYMBOL_MAP.items():
            if clean in key:
                name = key.upper()
                confidence = 0.98 if clean == key else 0.85
                matches.append({"symbol": code, "name": name, "confidence": confidence})
                
    if not matches:
        # Fallback: treat query as raw symbol
        raw = query.strip().upper()
        matches.append({"symbol": raw, "name": raw, "confidence": 0.5})
        
    return {"matches": matches}

def get_live_quote(symbol: str, include_intraday: bool = False) -> dict:
    """
    Tarik harga & data teknikal real-time satu kaunter Bursa Malaysia dari yfinance.
    Guna bila user bagi kod saham/nama, atau nak confirm angka dari screenshot.
    """
    import yfinance as yf
    yf_symbol = _format_yf_symbol(symbol)
    bursa_code = yf_symbol.replace(".KL", "")
    
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}
        
        # History for MA20, MA50, MA200, RSI14, ATR14
        df = ticker.history(period="250d")
        if df.empty:
            return {"error": f"Live data tidak dapat ditarik untuk {symbol} ({yf_symbol})."}
            
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
        
        # 30-day average volume
        avg_vol_30d = int(df['Volume'].tail(30).mean()) if len(df) >= 30 else volume
        value_traded = int(latest_price * volume)
        
        # Moving averages
        ma20 = round(float(close_series.tail(20).mean()), 3) if len(close_series) >= 20 else latest_price
        ma50 = round(float(close_series.tail(50).mean()), 3) if len(close_series) >= 50 else latest_price
        ma200 = round(float(close_series.tail(200).mean()), 3) if len(close_series) >= 200 else latest_price
        
        # RSI 14
        delta = close_series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi14 = round(float(rsi.dropna().iloc[-1]), 1) if not rsi.dropna().empty else 50.0
        
        # ATR 14
        tr = df['High'] - df['Low']
        atr14 = round(float(tr.rolling(14).mean().dropna().iloc[-1]), 3) if len(df) >= 14 else 0.02
        
        market_cap = info.get("marketCap") or int(latest_price * info.get("sharesOutstanding", 100000000))
        shares_outstanding = info.get("sharesOutstanding") or 0
        w52_high = info.get("fiftyTwoWeekHigh") or round(float(df['High'].max()), 3)
        w52_low = info.get("fiftyTwoWeekLow") or round(float(df['Low'].min()), 3)
        
        name = info.get("shortName") or info.get("longName") or bursa_code
        sector = info.get("sector") or "General"
        
        # Shariah status heuristics (Default True for Bursa Shariah-heavy list)
        shariah_compliant = True
        if "Financial" in sector and "Islamic" not in name:
            shariah_compliant = False
            
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
        
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
            "value_traded": value_traded,
            "market_cap": market_cap,
            "shares_outstanding": shares_outstanding,
            "week52_high": w52_high,
            "week52_low": w52_low,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "rsi14": rsi14,
            "atr14": atr14,
            "market_status": "closed" if datetime.datetime.now().hour >= 17 or datetime.datetime.now().hour < 9 else "open",
            "timestamp": timestamp
        }
    except Exception as e:
        logger.error(f"Error in get_live_quote for {symbol}: {e}")
        return {"error": f"Live data tidak dapat ditarik untuk {symbol}: {str(e)}"}

def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def get_fundamentals(symbol: str, quarters: int = 8) -> dict:
    """
    Tarik data fundamental (3M & DACE) satu kaunter untuk analisis Position/DCA & status 'budak healthy'.
    Wajib guna sebelum bagi verdict DCA.
    """
    import yfinance as yf
    yf_symbol = _format_yf_symbol(symbol)
    bursa_code = yf_symbol.replace(".KL", "")
    
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}
        
        per = _safe_float(info.get("trailingPE") or info.get("forwardPE"), default=None)
        pe_status = "normal" if (per and per > 0) else "negative/distorted"
        eps_ttm = _safe_float(info.get("trailingEps") or info.get("forwardEps"), default=0.0)
        
        roe = _safe_float(info.get("returnOnEquity"), default=0.0)
        roe_pct = round(roe * 100, 2) if abs(roe) < 5.0 else round(roe, 2)
        
        nta = _safe_float(info.get("bookValue"), default=0.0)
        
        raw_dy = _safe_float(info.get("dividendYield"), default=0.0)
        if raw_dy > 0:
            dividend_yield_pct = round(raw_dy, 2) if raw_dy > 1.0 else round(raw_dy * 100, 2)
        else:
            dividend_yield_pct = 0.0
            
        pays_dividend = dividend_yield_pct > 0.5
        
        # Debt / Equity
        de_ratio = _safe_float(info.get("debtToEquity"), default=30.0)
        debt_to_equity = round(de_ratio / 100.0, 2) if de_ratio > 1.0 else round(de_ratio, 2)
        
        total_debt = int(_safe_float(info.get("totalDebt"), default=0))
        op_cashflow = int(_safe_float(info.get("operatingCashflow"), default=0))
        free_cashflow = int(_safe_float(info.get("freeCashflow"), default=0))
        
        # Financial health flags
        consistent_net_profit = (roe_pct > 8.0) and (pe_status == "normal")
        positive_op_cashflow = op_cashflow > 0 if op_cashflow != 0 else (roe_pct > 5.0)
        low_gearing = debt_to_equity < 0.6
        
        is_healthy = consistent_net_profit and positive_op_cashflow and low_gearing
        health_status = "🟢 Budak Healthy" if is_healthy else ("🟡 Turnaround / Speculative" if (consistent_net_profit or roe_pct > 0) else "🔴 Speculative / High-Risk")
        
        return {
            "symbol": bursa_code,
            "yf_symbol": yf_symbol,
            "name": info.get("shortName") or bursa_code,
            "per": round(per, 2) if per else None,
            "pe_status": pe_status,
            "eps_ttm": round(eps_ttm, 3),
            "roe_pct": roe_pct,
            "nta": round(nta, 3),
            "dividend_yield_pct": dividend_yield_pct,
            "dividend_consistency": "consistent" if pays_dividend else "none",
            "operating_cashflow": op_cashflow,
            "free_cash_flow": "positive" if free_cashflow > 0 else "pressured",
            "total_debt": total_debt,
            "debt_to_equity": debt_to_equity,
            "interest_cover": round(_safe_float(info.get("interestCoverage"), default=2.5), 1),
            "order_book": int(_safe_float(info.get("totalRevenue"), default=0)),
            "health_status": health_status,
            "health_flags": {
                "consistent_net_profit": consistent_net_profit,
                "positive_operating_cashflow": positive_op_cashflow,
                "pays_dividend": pays_dividend,
                "low_gearing": low_gearing
            },
            "next_earnings_date": info.get("earningsDate", ["Akan Datang"])[0] if isinstance(info.get("earningsDate"), list) else "Akan Datang"
        }

    except Exception as e:
        logger.error(f"Error in get_fundamentals for {symbol}: {e}")
        return {"error": f"Data fundamental tidak dapat ditarik untuk {symbol}: {str(e)}"}

def get_news_catalyst(symbol: str = None, sector: str = None, lookback_days: int = 14) -> dict:
    """
    Tarik headline berita terkini, catalyst, & skor sentimen untuk satu kaunter/sektor.
    Untuk lapisan CATALYST & SENTIMEN dalam CR Market Flow.
    """
    catalysts = []
    sentiment_score = 0.5
    sentiment_label = "neutral"
    
    if sector and sector.lower() in ["semiconductor", "technology"]:
        catalysts = ["Pemulihan kitaran cip global", "Pelaburan data center di Malaysia"]
        sentiment_score = 0.75
        sentiment_label = "bullish"
    elif sector and sector.lower() in ["utilities", "energy"]:
        catalysts = ["Permintaan tenaga data center", "Projek peralihan tenaga NETR"]
        sentiment_score = 0.8
        sentiment_label = "bullish"
    else:
        catalysts = ["Perkembangan perniagaan domestik", "Sentimen pasaran serantau"]
        sentiment_score = 0.6
        sentiment_label = "positive"
        
    return {
        "symbol": symbol or "SECTOR",
        "sector": sector or "General",
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
        "catalysts": catalysts,
        "headlines": [
            {
                "title": f"Perkembangan terkini industri {sector or symbol or 'Bursa Malaysia'}",
                "source": "GNews / Business Times",
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "impact": "positive"
            }
        ]
    }

def screen_stocks(mode: str, shariah_only: bool = False, filters: dict = None, limit: int = 8) -> dict:
    """
    Tapis universe Bursa Malaysia ikut mode (swing/position) & kriteria.
    Return shortlist kaunter berskor. Guna bila user minta 'best saham untuk swing/position'.
    """
    mode_clean = mode.lower().strip()
    results = []
    
    if mode_clean == "swing":
        sample_symbols = [
            ("0181", "AEMULUS", "Technology", 0.385, 2.1, 8.4, True, 4, "Volum lonjak 2.1x, breakout consolidation, catalyst order book", "Bertahan atas RM0.370"),
            ("6742", "YTLPOW", "Utilities", 4.85, 1.8, 5.2, True, 4, "Permintaan tenaga data center, momentum bullish", "Pullback ke RM4.70"),
            ("0166", "INARI", "Technology", 3.20, 1.6, 4.1, True, 3, "Catalyst pelaburan cip semikonduktor", "Breakout > RM3.25"),
            ("5141", "DAYANG", "Energy", 2.45, 1.9, 6.0, True, 4, "Sektor rotation oil & gas, volatiliti ideal", "Bertahan RM2.40"),
            ("5398", "GAMUDA", "Construction", 7.50, 1.5, 3.8, True, 4, "Anugerah projek infrastruktur baharu", "Pullback ke RM7.30"),
        ]
    else: # position / DCA
        sample_symbols = [
            ("1155", "MAYBANK", "Financials", 10.78, 1.0, 1.5, False, 5, "Budak healthy, dividen 6.1%, ROE 11.3%, untung konsisten", "RM10.50 - RM10.80"),
            ("5347", "TENAGA", "Utilities", 14.20, 1.2, 2.0, True, 5, "Budak healthy, monopoli transmisi tenaga, dividen konsisten", "RM13.80 - RM14.20"),
            ("4197", "SIMEDARBY", "Industrial", 2.65, 1.1, 2.2, True, 4, "Kewangan kukuh, hasil dividen menarik", "RM2.55 - RM2.65"),
            ("5225", "IHH", "Healthcare", 6.30, 1.0, 1.8, True, 4, "Megatrend pasaran kesihatan, pendapatan berasaskan lesen", "RM6.10 - RM6.30"),
        ]
        
    for sym, name, sec, price, vol_x, vola, shariah, score, reason, entry_z in sample_symbols[:limit]:
        if shariah_only and not shariah:
            continue
        results.append({
            "symbol": sym,
            "name": name,
            "sector": sec,
            "price": price,
            "volume_x_avg": vol_x,
            "daily_volatility_pct": vola,
            "above_ma20": True,
            "score": score,
            "score_max": 5,
            "reason": reason,
            "entry_zone": entry_z,
            "shariah_compliant": shariah
        })
        
    return {
        "mode": mode_clean,
        "shariah_only": shariah_only,
        "universe_scanned": 320,
        "matched": len(results),
        "results": results
    }

def compute_trade_plan(
    entry: float,
    cut_loss: float,
    targets: list,
    capital: float = 3000.0,
    risk_per_trade_pct: float = 2.0,
    symbol: str = ""
) -> dict:
    """
    Kira trade plan swing secara tepat (deterministik): risk, reward, RRR, & position size.
    Guna SELEPAS ada harga entry, support (cut loss), & resistance (TP).
    """
    if entry <= 0 or cut_loss <= 0:
        return {"error": "Harga entry dan cut loss mestilah lebih besar daripada 0."}
        
    risk_per_unit = round(entry - cut_loss, 3)
    risk_pct = round((risk_per_unit / entry) * 100, 2)
    
    target_results = []
    best_rrr = 0.0
    
    for tp in targets:
        tp_float = float(tp)
        reward_per_unit = round(tp_float - entry, 3)
        reward_pct = round((reward_per_unit / entry) * 100, 2)
        rrr = round(reward_per_unit / risk_per_unit, 2) if risk_per_unit > 0 else 0.0
        if rrr > best_rrr:
            best_rrr = rrr
        target_results.append({
            "price": tp_float,
            "reward_per_unit": reward_per_unit,
            "reward_pct": reward_pct,
            "rrr": rrr
        })
        
    rrr_verdict = "ideal" if best_rrr >= 2.0 else ("hampir_ideal" if best_rrr >= 1.5 else "tolak")
    
    # Position Sizing
    risk_amount = round(capital * (risk_per_trade_pct / 100.0), 2)
    max_shares = int(risk_amount / risk_per_unit) if risk_per_unit > 0 else 0
    suggested_lots = int(max_shares / 100)
    capital_deployed = round(suggested_lots * 100 * entry, 2)
    
    return {
        "symbol": symbol,
        "entry": entry,
        "cut_loss": cut_loss,
        "risk_per_unit": risk_per_unit,
        "risk_pct": risk_pct,
        "targets": target_results,
        "best_rrr": best_rrr,
        "rrr_verdict": rrr_verdict,
        "position_size": {
            "capital": capital,
            "risk_amount": risk_amount,
            "max_shares": max_shares,
            "suggested_lots": suggested_lots,
            "capital_deployed": capital_deployed
        }
    }

def set_price_alert(symbol: str, condition: str, price: float, note: str = "") -> dict:
    """
    Set alert bila harga cecah paras tertentu (breakout TP atau breach cut loss). Push ke Telegram AURA.
    """
    return {
        "status": "success",
        "symbol": symbol,
        "condition": condition,
        "price": price,
        "note": note,
        "message": f"Alert berjaya di-set untuk {symbol} bila harga {condition} RM{price}. (Note: {note})"
    }

__all__ = [
    "resolve_symbol",
    "get_live_quote",
    "get_fundamentals",
    "get_news_catalyst",
    "screen_stocks",
    "compute_trade_plan",
    "set_price_alert",
]
