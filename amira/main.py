"""amira/main.py

AMIRA Trading Engine — FastAPI Application.

Endpoints
---------
GET  /health
    Liveness probe. Returns service name, version, and UTC timestamp.

POST /api/v1/analyze
    Full advisory pipeline:
      1. Validate ``TradeAnalysisRequest`` (Pydantic — extra fields forbidden).
      2. Recall Hermes memory context for the symbol.
      3. Execute ``run_trading_crew`` (TA → FA/Sentiment → Risk Officer).
      4. Map ``CrewFinalVerdict`` → ``TradeAnalysisResponse``.
      5. Validate response with ``TradeAnalysisResponse`` (advisory guardrail).
      6. Persist result to Hermes memory.
      7. Return JSON.

Error handling
--------------
All unhandled exceptions inside the endpoint are caught and returned as
``HTTP 500`` with a typed ``ErrorResponse`` body so callers always receive
structured JSON, never HTML tracebacks.

Advisory guardrail
------------------
The ``TradeAnalysisResponse.verdict`` field is constrained by Pydantic to
``{"BUY", "HOLD", "WATCH"}``.  If the swarm produces an unexpected string
(should never happen given the downstream validators) the ``field_validator``
raises and the endpoint returns HTTP 500 with an ``advisory_violation`` code.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from amira.schemas.models import TradeAnalysisRequest, TradeAnalysisResponse
from amira.swarm.crew import run_trading_crew, CrewFinalVerdict
from amira.core.memory import HermesMemoryEngine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("amira.main")

# ---------------------------------------------------------------------------
# App metadata
# ---------------------------------------------------------------------------
_VERSION = "1.0.0"
_SERVICE = "AMIRA Trading Engine"
_ADVISORY_DISCLAIMER = (
    "⚠️ AMIRA adalah sistem perundingan sahaja. Tiada arahan beli/jual dikeluarkan. "
    "Semua keputusan pelaburan adalah tanggungjawab peribadi pelabur."
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title=_SERVICE,
    version=_VERSION,
    description=(
        "Advisory-only trading analysis swarm. "
        "AMIRA NEVER executes trades or issues buy/sell orders."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Error response schema
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Typed HTTP error body returned on all 4xx / 5xx responses."""

    status: str = "error"
    code: str
    message: str
    symbol: str = ""
    disclaimer: str = _ADVISORY_DISCLAIMER


# ---------------------------------------------------------------------------
# Exception handler — always return JSON, never raw tracebacks
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def _generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s: %s", request.url.path, exc)
    body = ErrorResponse(
        code="internal_error",
        message=f"An unexpected error occurred: {type(exc).__name__}",
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body.model_dump(),
    )


# ---------------------------------------------------------------------------
# Dependency: Hermes memory (singleton per-process; override in tests)
# ---------------------------------------------------------------------------

def _get_hermes() -> HermesMemoryEngine:
    """Return the default Hermes engine. Overridable in tests."""
    return HermesMemoryEngine()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    summary="Liveness probe",
    tags=["infrastructure"],
)
async def health() -> Dict[str, Any]:
    """Return service health status."""
    return {
        "status": "ok",
        "service": _SERVICE,
        "version": _VERSION,
        "timestamp": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "advisory_mode": True,
        "disclaimer": _ADVISORY_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# POST /api/v1/analyze
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/analyze",
    response_model=TradeAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run the full AMIRA advisory pipeline",
    description=(
        "Validates the request, recalls Hermes memory, runs the sequential "
        "TA → FA/Sentiment → Risk Officer crew, and returns a structured "
        "advisory verdict.  NEVER places or suggests executing any order."
    ),
    tags=["trading"],
)
async def analyze(request_body: TradeAnalysisRequest) -> TradeAnalysisResponse:
    """Execute the full AMIRA swarm pipeline for a given symbol."""
    symbol = request_body.symbol.strip().upper()
    market = request_body.market
    user_prompt = request_body.user_prompt

    logger.info("[/analyze] Received request: symbol=%s market=%s", symbol, market)

    # ------------------------------------------------------------------ #
    # 1. Recall Hermes memory context                                      #
    # ------------------------------------------------------------------ #
    try:
        hermes = _get_hermes()
        memory_context = hermes.get_context(symbol)
        logger.info("[/analyze] Hermes context: %r", memory_context[:120])
    except Exception as exc:
        logger.warning("[/analyze] Hermes recall failed (non-fatal): %s", exc)
        memory_context = f"No prior trade analysis available for {symbol}."
        hermes = None  # will skip persistence if Hermes is broken

    # ------------------------------------------------------------------ #
    # 2. Run sequential crew                                               #
    # ------------------------------------------------------------------ #
    try:
        verdict_obj: CrewFinalVerdict = run_trading_crew(
            symbol=symbol,
            user_prompt=user_prompt,
            market=market,
            memory_context=memory_context,
            _hermes=hermes,  # pass same instance so crew doesn't create a second one
        )
    except RuntimeError as exc:
        logger.error("[/analyze] Crew pipeline error for %s: %s", symbol, exc)
        err = ErrorResponse(
            code="pipeline_error",
            message=str(exc),
            symbol=symbol,
        )
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=err.model_dump(),
        )

    # ------------------------------------------------------------------ #
    # 3. Map CrewFinalVerdict → TradeAnalysisResponse                     #
    # (Advisory guardrail: field_validator on verdict fires here)         #
    # ------------------------------------------------------------------ #
    try:
        response = TradeAnalysisResponse(
            status="ok",
            symbol=symbol,
            verdict=verdict_obj.verdict,
            score=round(verdict_obj.score, 4),
            rationale=verdict_obj.rationale,
            risk={
                "swing_stop": verdict_obj.risk_report.stop_loss.swing_stop,
                "position_stop": verdict_obj.risk_report.stop_loss.position_stop,
                "swing_risk_pct": verdict_obj.risk_report.stop_loss.swing_risk_pct,
                "suggested_lots": verdict_obj.risk_report.position_size.suggested_lots,
                "capital_deployed": verdict_obj.risk_report.position_size.capital_deployed,
                "capital_deployed_pct": verdict_obj.risk_report.position_size.capital_deployed_pct,
                "downside_risk_score": verdict_obj.risk_report.downside_risk_score,
                "downside_risk_label": verdict_obj.risk_report.downside_risk_label,
                "veto_applied": verdict_obj.risk_report.veto_applied,
                "veto_triggers": verdict_obj.risk_report.veto_triggers,
                "atr14": verdict_obj.ta.atr14,
                "rsi14": verdict_obj.ta.rsi14,
                "ma20": verdict_obj.ta.ma20,
                "ma50": verdict_obj.ta.ma50,
                "ma200": verdict_obj.ta.ma200,
            },
            disclaimer=verdict_obj.disclaimer,
        )
    except ValidationError as exc:
        # This catches advisory violations (invalid verdict string)
        logger.critical(
            "[/analyze] Advisory guardrail VIOLATED for %s: %s", symbol, exc
        )
        err = ErrorResponse(
            code="advisory_violation",
            message=(
                "The swarm produced a non-advisory verdict. "
                "This is a critical safety violation — request blocked."
            ),
            symbol=symbol,
        )
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=err.model_dump(),
        )

    logger.info(
        "[/analyze] Completed: symbol=%s verdict=%s score=%.4f veto=%s",
        symbol, response.verdict, response.score, verdict_obj.risk_report.veto_applied,
    )
    return response
