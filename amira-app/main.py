"""
AMIRA Trading Microservice API (FastAPI)
Exposes endpoints for Bursa Malaysia quote parsing, technical/fundamental analysis, and screening.
Hard Guardrail: Advisory Only — No Auto Buy/Sell/Execution.
"""
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, List
import trading_engine

app = FastAPI(
    title="AMIRA Trading Microservice",
    description="Bursa Malaysia Advisory Trading Co-Pilot (Asri Ahmad Academy Framework)",
    version="1.0.0"
)

class QuoteRequest(BaseModel):
    symbol: str

class AnalyzeRequest(BaseModel):
    symbol: str
    mode: Optional[str] = "swing"

class ScreenerRequest(BaseModel):
    mode: Optional[str] = "swing"
    shariah_only: Optional[bool] = False
    limit: Optional[int] = 8

class TradePlanRequest(BaseModel):
    symbol: str
    entry: float
    cut_loss: float
    targets: List[float]
    capital: Optional[float] = 3000.0

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "amira-app",
        "version": "1.0.0",
        "advisory_only": True
    }

@app.post("/api/v1/trading/resolve")
def resolve_symbol(req: QuoteRequest):
    return trading_engine.resolve_symbol(req.symbol)

@app.post("/api/v1/trading/quote")
def get_quote(req: QuoteRequest):
    res = trading_engine.get_live_quote(req.symbol)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.post("/api/v1/trading/fundamentals")
def get_fundamentals(req: QuoteRequest):
    res = trading_engine.get_fundamentals(req.symbol)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.post("/api/v1/trading/analyze")
def analyze_counter(req: AnalyzeRequest):
    res = trading_engine.analyze_counter(req.symbol, mode=req.mode or "swing")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.post("/api/v1/trading/screener")
def screen_stocks(req: ScreenerRequest):
    return trading_engine.screen_stocks(
        mode=req.mode or "swing",
        shariah_only=req.shariah_only or False,
        limit=req.limit or 8
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
