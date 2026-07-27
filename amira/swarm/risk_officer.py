"""amira/swarm/risk_officer.py

Risk Officer Agent — AMIRA Advisory Swarm.

Role
----
The ``RiskOfficerAgent`` is the **final gatekeeper** in the AMIRA swarm.
It receives a raw upstream verdict (BUY / HOLD / WATCH) together with price
and volatility data and applies deterministic risk rules before issuing the
swarm's terminal advisory output.

Responsibilities
----------------
1. **ATR-based Stop-Loss**: Computes a stop-loss price at
   ``entry - (atr_multiplier × ATR-14)``.  Default multiplier: **1.5×**
   (tight intraday swing).  A 2.0× multiplier is also surfaced for position
   traders.
2. **Position Sizing**: Given ``capital`` and ``risk_per_trade_pct``
   (default 2 %), calculates the maximum share-lot size whose monetary risk
   does not exceed the per-trade risk budget.  Output mirrors the conventions
   of ``AuraOne/tools/trading_service.compute_trade_plan``.
3. **Downside Risk Score**: A normalised (0–1) measure of how much capital is
   at risk relative to the trade size.  Higher = more dangerous.
4. **Final Veto**: The agent may override the upstream verdict to ``"HOLD"``
   when any hard trip-wire fires:
   - Risk-per-unit > 5 % of entry price.
   - Position size would deploy > 50 % of capital in a single trade.
   - ATR is zero or missing (data quality guard).
5. **Mandatory Disclaimer**: Every ``RiskReport`` carries a disclaimer field
   that is immutable and non-empty.

Hard Guardrail (backstory / goal)
----------------------------------
The Risk Officer NEVER places, suggests placing, or implies execution of any
order.  Its output is PURELY ADVISORY.  The ``verdict`` field is constrained
by Pydantic to ``{"BUY", "HOLD", "WATCH"}``.  Any attempt to emit an
execution-type string raises a ``ValueError`` at model instantiation time.
"""

from __future__ import annotations

import datetime
import logging
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger("amira.swarm.risk_officer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DISCLAIMER = (
    "⚠️ PERINGATAN WAJIB — Risk Officer AMIRA: Laporan ini adalah NASIHAT PERUNDINGAN SAHAJA. "
    "Tiada sebarang arahan beli/jual dikeluarkan. AMIRA tidak melaksanakan transaksi. "
    "Semua keputusan pelaburan adalah tanggungjawab peribadi pelabur."
)

_ATR_MULTIPLIER_SWING: float = 1.5   # swing/intraday stop
_ATR_MULTIPLIER_POSITION: float = 2.0  # position/DCA stop

_DEFAULT_CAPITAL: float = 3_000.0
_DEFAULT_RISK_PCT: float = 2.0          # 2 % of capital per trade

# Veto trip-wires
_MAX_RISK_PCT_OF_ENTRY: float = 5.0     # cut-loss > 5 % of entry → HOLD
_MAX_CAPITAL_DEPLOY_PCT: float = 50.0   # single trade > 50 % of capital → HOLD

# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class PositionSizeDetail(BaseModel):
    """Breakdown of the recommended position size."""

    capital: float = Field(description="Total available trading capital (MYR/USD).")
    risk_amount: float = Field(description="Maximum monetary risk per trade.")
    risk_per_unit: float = Field(description="Loss per share if stop-loss is hit.")
    max_shares: int = Field(description="Maximum shares before exceeding risk budget.")
    suggested_lots: int = Field(description="Suggested round lots (1 lot = 100 shares).")
    capital_deployed: float = Field(description="Capital committed to suggested_lots.")
    capital_deployed_pct: float = Field(description="Percentage of capital deployed.")

    model_config = ConfigDict(extra="forbid")


class StopLossDetail(BaseModel):
    """ATR-derived stop-loss levels."""

    entry: float = Field(description="Entry price used for calculation.")
    atr14: float = Field(description="ATR-14 value used.")
    swing_stop: float = Field(description="Stop-loss for swing traders (1.5 × ATR below entry).")
    position_stop: float = Field(description="Stop-loss for position traders (2.0 × ATR below entry).")
    swing_risk_pct: float = Field(description="Risk as % of entry for swing stop.")
    position_risk_pct: float = Field(description="Risk as % of entry for position stop.")

    model_config = ConfigDict(extra="forbid")


class RiskReport(BaseModel):
    """Terminal output from the Risk Officer Agent.

    Hard Guardrail: ``verdict`` MUST be one of ``{BUY, HOLD, WATCH}``.
    The ``disclaimer`` field is mandatory and non-empty.
    Execution language (SELL, SHORT, EXECUTE, ORDER …) is forbidden.
    """

    # Identification
    symbol: str
    market: Literal["MY", "US", "HK", "INDEX"]
    generated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    # Input from upstream agent
    upstream_verdict: Literal["BUY", "HOLD", "WATCH"]
    upstream_score: float = Field(ge=0.0, le=1.0)

    # Risk calculations
    stop_loss: StopLossDetail
    position_size: PositionSizeDetail

    # Downside risk score (0 = low risk, 1 = extreme risk)
    downside_risk_score: float = Field(ge=0.0, le=1.0)
    downside_risk_label: str   # "low" | "moderate" | "high" | "extreme"

    # Veto flags
    veto_applied: bool
    veto_reason: Optional[str]   # human-readable explanation when veto fires
    veto_triggers: List[str]     # list of trip-wire names that fired

    # Terminal advisory verdict (may differ from upstream_verdict if vetoed)
    verdict: Literal["BUY", "HOLD", "WATCH"]
    rationale: str
    disclaimer: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("verdict", "upstream_verdict")
    @classmethod
    def _enforce_advisory(cls, v: str) -> str:
        allowed = {"BUY", "HOLD", "WATCH"}
        forbidden = {"SELL", "SHORT", "EXECUTE", "ORDER", "BUY_NOW", "SELL_NOW"}
        if v.upper() in forbidden or v not in allowed:
            raise ValueError(
                f"Verdict '{v}' contains execution language. "
                f"AMIRA is advisory only. Allowed: {sorted(allowed)}"
            )
        return v

    @model_validator(mode="after")
    def _disclaimer_non_empty(self) -> "RiskReport":
        if not self.disclaimer or not self.disclaimer.strip():
            raise ValueError("disclaimer must be non-empty — this is a mandatory guardrail field.")
        return self


# ---------------------------------------------------------------------------
# Pure calculation helpers (no I/O, easily testable)
# ---------------------------------------------------------------------------


def _compute_stop_loss(entry: float, atr14: float) -> StopLossDetail:
    swing_stop = round(entry - _ATR_MULTIPLIER_SWING * atr14, 3)
    position_stop = round(entry - _ATR_MULTIPLIER_POSITION * atr14, 3)
    swing_risk_pct = round((_ATR_MULTIPLIER_SWING * atr14 / entry) * 100, 2) if entry else 0.0
    position_risk_pct = round((_ATR_MULTIPLIER_POSITION * atr14 / entry) * 100, 2) if entry else 0.0
    return StopLossDetail(
        entry=entry,
        atr14=atr14,
        swing_stop=max(swing_stop, 0.0),   # floor at 0
        position_stop=max(position_stop, 0.0),
        swing_risk_pct=swing_risk_pct,
        position_risk_pct=position_risk_pct,
    )


def _compute_position_size(
    entry: float,
    stop_loss_price: float,
    capital: float,
    risk_per_trade_pct: float,
) -> PositionSizeDetail:
    risk_per_unit = round(max(entry - stop_loss_price, 0.0001), 4)
    risk_amount = round(capital * (risk_per_trade_pct / 100.0), 2)
    max_shares = int(risk_amount / risk_per_unit) if risk_per_unit > 0 else 0
    suggested_lots = max(int(max_shares / 100), 0)
    capital_deployed = round(suggested_lots * 100 * entry, 2)
    capital_deployed_pct = round((capital_deployed / capital) * 100, 2) if capital else 0.0
    return PositionSizeDetail(
        capital=capital,
        risk_amount=risk_amount,
        risk_per_unit=risk_per_unit,
        max_shares=max_shares,
        suggested_lots=suggested_lots,
        capital_deployed=capital_deployed,
        capital_deployed_pct=capital_deployed_pct,
    )


def _compute_downside_risk(
    entry: float,
    atr14: float,
    capital_deployed_pct: float,
) -> tuple[float, str]:
    """Return (normalised_score 0‑1, label)."""
    # Components: atr as % of entry + capital concentration
    atr_pct = (atr14 / entry * 100) if entry else 0.0
    # Normalise atr_pct: treat 10 % as fully dangerous
    atr_component = min(atr_pct / 10.0, 1.0)
    # Normalise capital deployed: treat 80 % as fully dangerous
    deploy_component = min(capital_deployed_pct / 80.0, 1.0)
    score = round(0.6 * atr_component + 0.4 * deploy_component, 2)
    if score < 0.25:
        label = "low"
    elif score < 0.50:
        label = "moderate"
    elif score < 0.75:
        label = "high"
    else:
        label = "extreme"
    return score, label


def _evaluate_veto(
    entry: float,
    swing_risk_pct: float,
    capital_deployed_pct: float,
    atr14: float,
    upstream_verdict: str,
) -> tuple[bool, Optional[str], List[str]]:
    """Evaluate veto trip-wires.

    Returns (veto_fired, human_reason_or_None, list_of_trigger_names).
    """
    triggers: List[str] = []

    if atr14 <= 0:
        triggers.append("ATR_ZERO_OR_MISSING")
    if swing_risk_pct > _MAX_RISK_PCT_OF_ENTRY:
        triggers.append(f"SWING_RISK_PCT_EXCEEDS_{_MAX_RISK_PCT_OF_ENTRY}PCT")
    if capital_deployed_pct > _MAX_CAPITAL_DEPLOY_PCT:
        triggers.append(f"CAPITAL_DEPLOY_EXCEEDS_{_MAX_CAPITAL_DEPLOY_PCT}PCT")

    fired = len(triggers) > 0
    reason: Optional[str] = None
    if fired:
        parts = []
        if "ATR_ZERO_OR_MISSING" in triggers:
            parts.append("ATR=0 (data quality issue — cannot compute stop-loss)")
        if any("SWING_RISK_PCT" in t for t in triggers):
            parts.append(
                f"swing stop-loss implies >{_MAX_RISK_PCT_OF_ENTRY}% loss per share "
                f"(actual: {swing_risk_pct:.2f}%)"
            )
        if any("CAPITAL_DEPLOY" in t for t in triggers):
            parts.append(
                f"position would deploy >{_MAX_CAPITAL_DEPLOY_PCT}% of capital "
                f"(actual: {capital_deployed_pct:.2f}%)"
            )
        reason = "Veto applied — " + "; ".join(parts) + ". Verdict overridden to HOLD."

    return fired, reason, triggers


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class RiskOfficerAgent:
    """AMIRA Risk Officer — final veto authority in the advisory swarm.

    Backstory / Goal
    ----------------
    You are the Risk Officer of AMIRA, a strictly advisory AI system.
    Your role is to protect the user from outsized losses by computing
    ATR-based stop-losses, position sizes, and downside risk scores.
    You have FINAL VETO power over the swarm's upstream verdict.

    HARD RULE: You NEVER place, suggest placing, or imply execution of any
    order.  You are ADVISORY ONLY.  The word "execute", "order", "sell now",
    or any broker-execution verb is FORBIDDEN in your outputs.

    Parameters
    ----------
    capital:
        Available trading capital in the user's base currency.
    risk_per_trade_pct:
        Maximum percentage of capital risked on a single trade (default 2 %).
    """

    BACKSTORY = (
        "Saya adalah Risk Officer AMIRA — penjaga akhir dalam swarm penasihat ini. "
        "Tugas saya: mengira stop-loss berasaskan ATR, saiz posisi selamat, dan skor risiko negatif. "
        "Saya mempunyai VETO MUKTAMAD ke atas verdict hulu. "
        "PERATURAN KERAS: Saya TIDAK PERNAH mengeluarkan arahan atau cadangan untuk melaksanakan "
        "transaksi beli/jual. Semua output adalah NASIHAT PERUNDINGAN SAHAJA."
    )

    def __init__(
        self,
        capital: float = _DEFAULT_CAPITAL,
        risk_per_trade_pct: float = _DEFAULT_RISK_PCT,
    ) -> None:
        if capital <= 0:
            raise ValueError("capital must be positive")
        if not (0 < risk_per_trade_pct <= 10):
            raise ValueError("risk_per_trade_pct must be between 0 and 10")
        self._capital = capital
        self._risk_pct = risk_per_trade_pct

    def assess(
        self,
        symbol: str,
        market: Literal["MY", "US", "HK", "INDEX"],
        entry_price: float,
        atr14: float,
        upstream_verdict: Literal["BUY", "HOLD", "WATCH"],
        upstream_score: float,
    ) -> RiskReport:
        """Run the Risk Officer assessment.

        Parameters
        ----------
        symbol:
            Base ticker symbol (no suffix).
        market:
            Market code.
        entry_price:
            Latest close price used as the hypothetical entry.
        atr14:
            ATR-14 value from ``amira.tools.indicators.compute_indicators``.
        upstream_verdict:
            Verdict produced by the upstream FA+Sentiment agent.
        upstream_score:
            Blended confidence score from the upstream agent (0–1).

        Returns
        -------
        RiskReport
            Terminal advisory report.  May differ from ``upstream_verdict``
            if a veto trip-wire fires.
        """
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price}")
        if upstream_score < 0 or upstream_score > 1:
            raise ValueError("upstream_score must be in [0, 1]")

        logger.info(
            "[RiskOfficer] Assessing %s | entry=%.3f | ATR14=%.3f | upstream=%s (%.2f)",
            symbol, entry_price, atr14, upstream_verdict, upstream_score,
        )

        # ------------------------------------------------------------------ #
        # Step 1 — ATR-based stop-loss levels                                  #
        # ------------------------------------------------------------------ #
        stop = _compute_stop_loss(entry_price, atr14)

        # ------------------------------------------------------------------ #
        # Step 2 — Position sizing (using swing stop as primary)               #
        # ------------------------------------------------------------------ #
        pos = _compute_position_size(
            entry=entry_price,
            stop_loss_price=stop.swing_stop,
            capital=self._capital,
            risk_per_trade_pct=self._risk_pct,
        )

        # ------------------------------------------------------------------ #
        # Step 3 — Downside risk score                                         #
        # ------------------------------------------------------------------ #
        risk_score, risk_label = _compute_downside_risk(
            entry=entry_price,
            atr14=atr14,
            capital_deployed_pct=pos.capital_deployed_pct,
        )

        # ------------------------------------------------------------------ #
        # Step 4 — Veto evaluation                                             #
        # ------------------------------------------------------------------ #
        veto_fired, veto_reason, veto_triggers = _evaluate_veto(
            entry=entry_price,
            swing_risk_pct=stop.swing_risk_pct,
            capital_deployed_pct=pos.capital_deployed_pct,
            atr14=atr14,
            upstream_verdict=upstream_verdict,
        )

        final_verdict: Literal["BUY", "HOLD", "WATCH"] = "HOLD" if veto_fired else upstream_verdict

        # ------------------------------------------------------------------ #
        # Step 5 — Rationale                                                   #
        # ------------------------------------------------------------------ #
        rationale_parts = [
            f"{symbol} ({market}) | Entry: {entry_price} | ATR-14: {atr14}",
            f"Swing stop: {stop.swing_stop} ({stop.swing_risk_pct}% below entry) | "
            f"Position stop: {stop.position_stop} ({stop.position_risk_pct}% below entry)",
            f"Cadangan posisi: {pos.suggested_lots} lot(s) ({pos.max_shares} unit) | "
            f"Modal digunakan: {pos.capital_deployed} ({pos.capital_deployed_pct}% daripada {self._capital})",
            f"Skor risiko negatif: {risk_score}/1.0 → {risk_label}",
            f"Verdict hulu: {upstream_verdict} (skor {upstream_score:.2f}) → "
            f"Verdict Risk Officer: {final_verdict}",
        ]
        if veto_fired:
            rationale_parts.append(f"🛑 {veto_reason}")

        rationale = "\n".join(rationale_parts)

        return RiskReport(
            symbol=symbol,
            market=market,
            upstream_verdict=upstream_verdict,
            upstream_score=upstream_score,
            stop_loss=stop,
            position_size=pos,
            downside_risk_score=risk_score,
            downside_risk_label=risk_label,
            veto_applied=veto_fired,
            veto_reason=veto_reason,
            veto_triggers=veto_triggers,
            verdict=final_verdict,
            rationale=rationale,
            disclaimer=_DISCLAIMER,
        )


__all__ = [
    "RiskOfficerAgent",
    "RiskReport",
    "StopLossDetail",
    "PositionSizeDetail",
    # helpers exposed for unit tests
    "_compute_stop_loss",
    "_compute_position_size",
    "_compute_downside_risk",
    "_evaluate_veto",
]
