# amira core memory tests
"""Unit tests for HermesMemoryEngine.
Uses a temporary in‑memory SQLite database by passing a custom path.
"""

import os
import tempfile
import json

from core.memory import HermesMemoryEngine


def test_save_and_recall():
    # Create a temporary directory for isolation
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "hermes_memory.db")
        engine = HermesMemoryEngine(db_path=db_path)

        # Sample result payload
        result = {
            "status": "ok",
            "symbol": "AAPL",
            "verdict": "BUY",
            "score": 0.87,
            "rationale": "Strong momentum with positive earnings",
            "risk": {"volatility": 0.12},
            "disclaimer": "Advisory only",
        }

        # Save and then recall
        engine.save_trade_log("AAPL", result)
        logs = engine.recall_past_trades("AAPL")
        assert len(logs) == 1
        assert logs[0]["result"] == result

        # Context generation should include verdict and rationale
        ctx = engine.get_context("AAPL")
        assert "BUY" in ctx and "Strong momentum" in ctx

        # Clean up
        engine.clear_all()
        assert engine.recall_past_trades("AAPL") == []
