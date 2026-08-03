"""Deterministic Risk Officer Guard for AuraOne.

The Risk Officer is the final gatekeeper in AuraOne trading advisory pipelines.
It applies deterministic risk calculations and hard veto rules (pure Python, zero LLM).
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import structlog

logger = structlog.get_logger("aura.core.guards.risk_officer")

_DISCLAIMER = (
    "⚠️ PERINGATAN WAJIB — Risk Officer AURA: Laporan ini adalah NASIHAT PERUNDINGAN SAHAJA. "
    "Tiada sebarang arahan beli/jual dikeluarkan. AURA tidak melaksanakan transaksi. "
    "Semua keputusan pelaburan adalah tanggungjawab peribadi pelabur."
)

_ATR_MULTIPLIER_SWING: float = 1.5
_ATR_MULTIPLIER_POSITION: float = 2.0
_DEFAULT_CAPITAL: float = 3_000.0
_DEFAULT_RISK_PCT: float = 2.0
_MAX_RISK_PCT_OF_ENTRY: float = 5.0
_MAX_CAPITAL_DEPLOY_PCT: float = 50.0


class PositionSizeDetail(BaseModel):
    capital: float = Field(description="Total available trading capital.")
    risk_amount: float = Field(description="Maximum monetary risk per trade.")
    risk_per_unit: float = Field(description="Loss per share if stop-loss is hit.")
    max_shares: int = Field(description="Maximum shares before exceeding risk budget.")
    suggested_lots: int = Field(description="Suggested round lots (1 lot = 100 shares).")
    capital_deployed: float = Field(description="Capital committed to suggested_lots.")
    capital_deployed_pct: float = Field(description="Percentage of capital deployed.")

    model_config = ConfigDict(extra="forbid")


class StopLossDetail(BaseModel):
    entry: float = Field(description="Entry price used for calculation.")
    atr14: float = Field(description="ATR-14 value used.")
    swing_stop: float = Field(description="Stop-loss for swing traders.")
    position_stop: float = Field(description="Stop-loss for position traders.")
    swing_risk_pct: float = Field(description="Risk as % of entry for swing stop.")
    position_risk_pct: float = Field(description="Risk as % of entry for position stop.")

    model_config = ConfigDict(extra="forbid")


class RiskReport(BaseModel):
    symbol: str = Field(..., description="Ticker symbol.")
    verdict: Literal["BUY", "HOLD", "WATCH"] = Field(..., description="Terminal advisory verdict.")
    veto_applied: bool = Field(default=False, description="True if Risk Officer overrode upstream verdict.")
    veto_reasons: List[str] = Field(default_factory=list, description="List of trip-wires that fired.")
    downside_risk_score: float = Field(..., ge=0.0, le=1.0, description="Normalised downside risk (0=low, 1=high).")
    stop_loss: StopLossDetail
    position_size: PositionSizeDetail
    disclaimer: str = Field(default=_DISCLAIMER, description="Mandatory non-execution disclaimer.")
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    model_config = ConfigDict(extra="forbid")

    @field_validator("verdict", mode="before")
    @classmethod
    def _validate_verdict_str(cls, val: object) -> str:
        if not isinstance(val, str):
            raise ValueError("verdict must be a string")
        clean = val.strip().upper()
        if clean not in {"BUY", "HOLD", "WATCH"}:
            raise ValueError(f"Verdict '{clean}' is forbidden. Must be one of BUY, HOLD, WATCH.")
        return clean

    @model_validator(mode="after")
    def _verify_disclaimer(self) -> RiskReport:
        if not self.disclaimer or not self.disclaimer.strip():
            raise ValueError("disclaimer must not be empty")
        return self


class RiskOfficer:
    """Pure deterministic Risk Officer gatekeeper."""

    def evaluate(
        self,
        symbol: str,
        upstream_verdict: str,
        current_price: float,
        atr14: float,
        capital: float = _DEFAULT_CAPITAL,
        risk_pct: float = _DEFAULT_RISK_PCT,
    ) -> RiskReport:
        veto_reasons = []
        veto_applied = False

        if current_price <= 0:
            raise ValueError("current_price must be positive")

        if atr14 <= 0:
            veto_reasons.append("ATR-14 is missing or zero.")
            veto_applied = True
            atr14 = current_price * 0.02  # fallback 2% assumption

        swing_stop = round(max(0.0, current_price - (_ATR_MULTIPLIER_SWING * atr14)), 4)
        position_stop = round(max(0.0, current_price - (_ATR_MULTIPLIER_POSITION * atr14)), 4)

        swing_risk_pct = round(((current_price - swing_stop) / current_price) * 100.0, 2)
        position_risk_pct = round(((current_price - position_stop) / current_price) * 100.0, 2)

        stop_detail = StopLossDetail(
            entry=current_price,
            atr14=atr14,
            swing_stop=swing_stop,
            position_stop=position_stop,
            swing_risk_pct=swing_risk_pct,
            position_risk_pct=position_risk_pct,
        )

        risk_amount = round(capital * (risk_pct / 100.0), 2)
        risk_per_unit = round(current_price - swing_stop, 4)

        if risk_per_unit <= 0:
            max_shares = 0
            suggested_lots = 0
            capital_deployed = 0.0
            capital_deployed_pct = 0.0
        else:
            max_shares = int(risk_amount // risk_per_unit)
            suggested_lots = max_shares // 100
            capital_deployed = round(suggested_lots * 100 * current_price, 2)
            capital_deployed_pct = round((capital_deployed / capital) * 100.0, 2)

        pos_detail = PositionSizeDetail(
            capital=capital,
            risk_amount=risk_amount,
            risk_per_unit=risk_per_unit,
            max_shares=max_shares,
            suggested_lots=suggested_lots,
            capital_deployed=capital_deployed,
            capital_deployed_pct=capital_deployed_pct,
        )

        # Trip-wire checks
        if swing_risk_pct > _MAX_RISK_PCT_OF_ENTRY:
            veto_reasons.append(f"Swing risk ({swing_risk_pct}%) > max allowed ({_MAX_RISK_PCT_OF_ENTRY}%).")
            veto_applied = True

        if capital_deployed_pct > _MAX_CAPITAL_DEPLOY_PCT:
            veto_reasons.append(f"Capital deploy ({capital_deployed_pct}%) > max allowed ({_MAX_CAPITAL_DEPLOY_PCT}%).")
            veto_applied = True

        final_verdict = "HOLD" if veto_applied else upstream_verdict.strip().upper()
        if final_verdict not in {"BUY", "HOLD", "WATCH"}:
            final_verdict = "HOLD"

        downside_score = round(min(1.0, (swing_risk_pct / 10.0) + (capital_deployed_pct / 100.0) * 0.5), 2)

        return RiskReport(
            symbol=symbol.upper(),
            verdict=final_verdict,
            veto_applied=veto_applied,
            veto_reasons=veto_reasons,
            downside_risk_score=downside_score,
            stop_loss=stop_detail,
            position_size=pos_detail,
            disclaimer=_DISCLAIMER,
        )


risk_officer = RiskOfficer()
