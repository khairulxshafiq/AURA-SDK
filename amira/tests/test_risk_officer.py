"""amira/tests/test_risk_officer.py

Unit tests for ``amira.swarm.risk_officer``.

All tests are fully deterministic and offline — no yfinance or HTTP calls.
We test:
- Pure calculation helpers (_compute_stop_loss, _compute_position_size,
  _compute_downside_risk, _evaluate_veto)
- RiskOfficerAgent.assess() happy path (no veto)
- All three veto trip-wires individually
- Advisory guardrail: verdict must be BUY / HOLD / WATCH
- Mandatory disclaimer: non-empty
- Model serialisability (model_dump round-trip)
- Constructor guards (bad capital / risk_pct)
"""

from __future__ import annotations

import pytest

from amira.swarm.risk_officer import (
    RiskOfficerAgent,
    RiskReport,
    _compute_downside_risk,
    _compute_position_size,
    _compute_stop_loss,
    _evaluate_veto,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ENTRY = 3.85
ATR14 = 0.12
CAPITAL = 5_000.0
RISK_PCT = 2.0


def _agent(capital: float = CAPITAL, risk_pct: float = RISK_PCT) -> RiskOfficerAgent:
    return RiskOfficerAgent(capital=capital, risk_per_trade_pct=risk_pct)


# ---------------------------------------------------------------------------
# _compute_stop_loss
# ---------------------------------------------------------------------------

class TestComputeStopLoss:
    def test_swing_stop_below_entry(self):
        sl = _compute_stop_loss(ENTRY, ATR14)
        assert sl.swing_stop < ENTRY

    def test_position_stop_below_swing_stop(self):
        sl = _compute_stop_loss(ENTRY, ATR14)
        assert sl.position_stop < sl.swing_stop

    def test_swing_stop_formula(self):
        sl = _compute_stop_loss(10.0, 0.5)
        # 1.5 × 0.5 = 0.75 → 10.0 - 0.75 = 9.25
        assert sl.swing_stop == pytest.approx(9.25, rel=1e-3)
        assert sl.position_stop == pytest.approx(9.0, rel=1e-3)

    def test_atr_zero_floor(self):
        sl = _compute_stop_loss(5.0, 0.0)
        assert sl.swing_stop == pytest.approx(5.0)
        assert sl.position_stop == pytest.approx(5.0)

    def test_risk_pct_values(self):
        sl = _compute_stop_loss(10.0, 1.0)
        assert sl.swing_risk_pct == pytest.approx(15.0, rel=1e-2)
        assert sl.position_risk_pct == pytest.approx(20.0, rel=1e-2)


# ---------------------------------------------------------------------------
# _compute_position_size
# ---------------------------------------------------------------------------

class TestComputePositionSize:
    def test_basic_shape(self):
        sl = _compute_stop_loss(ENTRY, ATR14)
        ps = _compute_position_size(ENTRY, sl.swing_stop, CAPITAL, RISK_PCT)
        assert ps.capital == CAPITAL
        assert ps.risk_amount == pytest.approx(100.0)   # 2 % of 5000
        assert ps.suggested_lots >= 0
        assert ps.capital_deployed >= 0

    def test_capital_deployed_pct_within_bounds(self):
        sl = _compute_stop_loss(ENTRY, ATR14)
        ps = _compute_position_size(ENTRY, sl.swing_stop, CAPITAL, RISK_PCT)
        assert 0.0 <= ps.capital_deployed_pct <= 100.0

    def test_zero_lots_when_entry_equals_stop(self):
        # Entry == stop → risk_per_unit forced to 0.0001 (floor) → large max_shares
        # Capital deployed should still be finite and ≥ 0
        ps = _compute_position_size(5.0, 5.0, CAPITAL, RISK_PCT)
        assert ps.capital_deployed >= 0


# ---------------------------------------------------------------------------
# _compute_downside_risk
# ---------------------------------------------------------------------------

class TestComputeDownsideRisk:
    def test_score_in_range(self):
        score, label = _compute_downside_risk(ENTRY, ATR14, 20.0)
        assert 0.0 <= score <= 1.0
        assert label in {"low", "moderate", "high", "extreme"}

    def test_high_atr_increases_risk(self):
        score_low, _ = _compute_downside_risk(10.0, 0.05, 10.0)
        score_high, _ = _compute_downside_risk(10.0, 2.0, 10.0)
        assert score_high > score_low

    def test_extreme_when_both_components_maxed(self):
        # ATR = entry (100 % of price) and 90 % capital deployed
        score, label = _compute_downside_risk(1.0, 1.0, 90.0)
        assert label in {"high", "extreme"}


# ---------------------------------------------------------------------------
# _evaluate_veto
# ---------------------------------------------------------------------------

class TestEvaluateVeto:
    def test_no_veto_normal_trade(self):
        fired, reason, triggers = _evaluate_veto(
            entry=3.85, swing_risk_pct=4.0, capital_deployed_pct=30.0,
            atr14=0.12, upstream_verdict="BUY"
        )
        assert not fired
        assert reason is None
        assert triggers == []

    def test_veto_on_zero_atr(self):
        fired, reason, triggers = _evaluate_veto(
            entry=3.85, swing_risk_pct=0.0, capital_deployed_pct=20.0,
            atr14=0.0, upstream_verdict="BUY"
        )
        assert fired
        assert "ATR_ZERO_OR_MISSING" in triggers

    def test_veto_on_excessive_swing_risk(self):
        fired, reason, triggers = _evaluate_veto(
            entry=3.85, swing_risk_pct=6.5, capital_deployed_pct=20.0,
            atr14=0.25, upstream_verdict="BUY"
        )
        assert fired
        assert any("SWING_RISK_PCT" in t for t in triggers)

    def test_veto_on_capital_concentration(self):
        fired, reason, triggers = _evaluate_veto(
            entry=3.85, swing_risk_pct=2.0, capital_deployed_pct=75.0,
            atr14=0.12, upstream_verdict="BUY"
        )
        assert fired
        assert any("CAPITAL_DEPLOY" in t for t in triggers)


# ---------------------------------------------------------------------------
# RiskOfficerAgent.assess() — happy path (no veto)
# ---------------------------------------------------------------------------

class TestRiskOfficerAgentHappyPath:
    def test_returns_risk_report(self):
        agent = _agent()
        report = agent.assess("0181", "MY", ENTRY, ATR14, "BUY", 0.72)
        assert isinstance(report, RiskReport)

    def test_verdict_preserved_when_no_veto(self):
        agent = _agent()
        report = agent.assess("0181", "MY", ENTRY, ATR14, "BUY", 0.72)
        assert not report.veto_applied
        assert report.verdict == "BUY"

    def test_watch_verdict_preserved(self):
        agent = _agent()
        report = agent.assess("0181", "MY", ENTRY, ATR14, "WATCH", 0.50)
        assert report.verdict == "WATCH"

    def test_hold_verdict_preserved(self):
        agent = _agent()
        report = agent.assess("0181", "MY", ENTRY, ATR14, "HOLD", 0.30)
        assert report.verdict == "HOLD"

    def test_disclaimer_non_empty(self):
        agent = _agent()
        report = agent.assess("0181", "MY", ENTRY, ATR14, "BUY", 0.72)
        assert len(report.disclaimer) > 20

    def test_rationale_contains_symbol(self):
        agent = _agent()
        report = agent.assess("NVDA", "US", 120.0, 3.5, "BUY", 0.80)
        assert "NVDA" in report.rationale

    def test_model_serialisable(self):
        agent = _agent()
        report = agent.assess("0181", "MY", ENTRY, ATR14, "BUY", 0.72)
        data = report.model_dump()
        assert "stop_loss" in data
        assert "position_size" in data
        assert "verdict" in data
        assert data["disclaimer"] != ""


# ---------------------------------------------------------------------------
# Veto behaviour in full assess() flow
# ---------------------------------------------------------------------------

class TestRiskOfficerAgentVeto:
    def test_veto_overrides_buy_to_hold(self):
        agent = _agent()
        # ATR = 0 → triggers ATR_ZERO_OR_MISSING veto
        report = agent.assess("XXXX", "MY", 5.0, 0.0, "BUY", 0.70)
        assert report.veto_applied
        assert report.verdict == "HOLD"
        assert "ATR_ZERO_OR_MISSING" in report.veto_triggers

    def test_veto_reason_present_when_fired(self):
        agent = _agent()
        report = agent.assess("XXXX", "MY", 5.0, 0.0, "BUY", 0.70)
        assert report.veto_reason is not None
        assert len(report.veto_reason) > 0

    def test_veto_triggers_listed(self):
        agent = _agent()
        report = agent.assess("XXXX", "MY", 5.0, 0.0, "BUY", 0.70)
        assert isinstance(report.veto_triggers, list)
        assert len(report.veto_triggers) > 0


# ---------------------------------------------------------------------------
# Advisory guardrail — Pydantic model constraints
# ---------------------------------------------------------------------------

class TestAdvisoryGuardrail:
    def test_invalid_verdict_raises(self):
        """SELL / EXECUTE / ORDER must raise ValueError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RiskReport(
                symbol="X", market="MY", upstream_verdict="SELL",  # <-- forbidden
                upstream_score=0.5,
                stop_loss=_compute_stop_loss(1.0, 0.05),
                position_size=_compute_position_size(1.0, 0.925, 1000.0, 2.0),
                downside_risk_score=0.3, downside_risk_label="low",
                veto_applied=False, veto_reason=None, veto_triggers=[],
                verdict="HOLD", rationale="test", disclaimer="test disclaimer",
            )

    def test_empty_disclaimer_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RiskReport(
                symbol="X", market="MY", upstream_verdict="BUY",
                upstream_score=0.5,
                stop_loss=_compute_stop_loss(1.0, 0.05),
                position_size=_compute_position_size(1.0, 0.925, 1000.0, 2.0),
                downside_risk_score=0.3, downside_risk_label="low",
                veto_applied=False, veto_reason=None, veto_triggers=[],
                verdict="BUY", rationale="test", disclaimer="",   # <-- empty
            )


# ---------------------------------------------------------------------------
# Constructor guards
# ---------------------------------------------------------------------------

class TestConstructorGuards:
    def test_negative_capital_raises(self):
        with pytest.raises(ValueError, match="capital must be positive"):
            RiskOfficerAgent(capital=-100.0)

    def test_zero_capital_raises(self):
        with pytest.raises(ValueError, match="capital must be positive"):
            RiskOfficerAgent(capital=0.0)

    def test_excessive_risk_pct_raises(self):
        with pytest.raises(ValueError, match="risk_per_trade_pct"):
            RiskOfficerAgent(risk_per_trade_pct=15.0)

    def test_negative_entry_raises(self):
        agent = _agent()
        with pytest.raises(ValueError, match="entry_price"):
            agent.assess("X", "MY", -1.0, 0.1, "BUY", 0.5)
