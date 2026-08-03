# amira schemas models
"""Pydantic models defining the request/response contracts for the AMIRA trading analysis service.
The hard guardrail ensures that the `verdict` field is advisory only (BUY, HOLD, WATCH).
"""

from typing import Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class TradeAnalysisRequest(BaseModel):
    """Input payload for a trade analysis request.

    Attributes
    ----------
    symbol: str
        Ticker symbol to analyze.
    user_prompt: str
        Free‑form prompt from the user providing context or questions.
    market: Literal["MY", "US", "HK", "INDEX"]
        Market region identifier.
    """

    symbol: str
    user_prompt: str
    market: Literal["MY", "US", "HK", "INDEX"]

    model_config = ConfigDict(extra="forbid")


class TradeAnalysisResponse(BaseModel):
    """Output payload containing the analysis result.

    Attributes
    ----------
    status: str
        e.g. "ok" or error code.
    symbol: str
        The ticker that was analyzed.
    verdict: Literal["BUY", "HOLD", "WATCH"]
        Advisory recommendation – never an execution order.
    score: float
        Confidence score (0‑1).
    rationale: str
        Human‑readable explanation of the recommendation.
    risk: Dict[str, Any]
        Structured risk metrics (e.g., volatility, exposure).
    disclaimer: str
        Legal disclaimer reminding the user this is advisory only.
    """

    status: str
    symbol: str
    verdict: Literal["BUY", "HOLD", "WATCH"]
    score: float
    rationale: str
    risk: Dict[str, Any]
    disclaimer: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("verdict")
    def enforce_advisory(cls, v: str) -> str:
        """Ensure the verdict is one of the allowed advisory values.
        This prevents accidental inclusion of execution‑type commands.
        """
        allowed = {"BUY", "HOLD", "WATCH"}
        if v not in allowed:
            raise ValueError(
                f"Verdict '{v}' is not an advisory value. Allowed: {sorted(allowed)}"
            )
        return v
