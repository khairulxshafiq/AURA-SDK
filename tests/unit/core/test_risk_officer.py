"""Unit tests for deterministic Risk Officer guard in aura/core/guards/risk_officer.py."""

import pytest
from aura.core.guards.risk_officer import risk_officer


def test_risk_officer_buy_pass():
    report = risk_officer.evaluate(
        symbol="MAYBANK",
        upstream_verdict="BUY",
        current_price=10.0,
        atr14=0.10,
        capital=10000.0,
        risk_pct=0.5,
    )
    assert report.verdict == "BUY"
    assert report.veto_applied is False
    assert report.disclaimer != ""


def test_risk_officer_veto_high_risk_pct():
    # ATR risk = 1.5 * 1.0 = 1.50 -> 15% of entry price (>5% max limit)
    report = risk_officer.evaluate(
        symbol="RISKY",
        upstream_verdict="BUY",
        current_price=10.0,
        atr14=1.00,
        capital=10000.0,
    )
    assert report.verdict == "HOLD"
    assert report.veto_applied is True
    assert len(report.veto_reasons) >= 1
