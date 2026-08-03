# amira core memory engine
"""HermesMemoryEngine provides a lightweight, isolated SQLite store for AMIRA trade
logs and context generation. It mirrors the Repository Pattern used in AURA's
`AuraOne/storage` modules but keeps its data completely separate in
`./data/hermes_memory.db`.
"""

import os
import json
import sqlite3
import datetime
from typing import List, Dict, Any


class HermesMemoryEngine:
    """Simple SQLite‑backed memory store for AMIRA trade analysis.

    The database lives at ``./data/hermes_memory.db`` relative to the project root
    (i.e. ``amira/data/hermes_memory.db``). It contains a single table
    ``trade_logs`` with the columns:

    - ``id``            INTEGER PRIMARY KEY AUTOINCREMENT
    - ``symbol``        TEXT – ticker symbol
    - ``result_json``   TEXT – JSON serialized analysis result
    - ``created_at``    TIMESTAMP – insertion time
    """

    def __init__(self, db_path: str | None = None) -> None:
        # Resolve default path inside the ``amira/data`` folder
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
            os.makedirs(base_dir, exist_ok=True)
            db_path = os.path.join(base_dir, "hermes_memory.db")
        self.db_path = db_path
        self._ensure_schema()

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20.0, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def save_trade_log(self, symbol: str, result: Dict[str, Any]) -> None:
        """Persist a single analysis result for *symbol*.

        ``result`` is JSON‑serialisable (e.g. the ``TradeAnalysisResponse`` model as a
        dict). The method does not return anything; failures raise ``sqlite3``
        exceptions which bubble up for the caller to handle.
        """
        payload = json.dumps(result, ensure_ascii=False)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trade_logs (symbol, result_json) VALUES (?, ?)",
            (symbol, payload),
        )
        conn.commit()
        conn.close()

    def recall_past_trades(self, symbol: str) -> List[Dict[str, Any]]:
        """Return a list of all stored analysis results for *symbol* ordered by
        newest first.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT result_json, created_at FROM trade_logs WHERE symbol = ? ORDER BY created_at DESC",
            (symbol,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"result": json.loads(row["result_json"]), "created_at": row["created_at"]}
            for row in rows
        ]

    def get_context(self, symbol: str) -> str:
        """Generate a short textual context block for *symbol*.

        The context concatenates the most recent verdict and a short rationale.
        If no logs exist, a placeholder message is returned.
        """
        logs = self.recall_past_trades(symbol)
        if not logs:
            return f"No prior trade analysis available for {symbol}."
        latest = logs[0]["result"]
        verdict = latest.get("verdict", "UNKNOWN")
        rationale = latest.get("rationale", "")
        return f"Latest AMIRA advisory for {symbol}: {verdict}. Reason: {rationale}"

    # Optional convenience method used by tests
    def clear_all(self) -> None:
        """Delete every record – useful for test teardown.
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM trade_logs")
        conn.commit()
        conn.close()

# End of file
