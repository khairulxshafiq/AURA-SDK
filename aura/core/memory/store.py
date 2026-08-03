"""5-Tier Isolated SQLite Database Store for AuraOne."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import structlog

logger = structlog.get_logger("aura.core.memory.store")


class SqliteStore:
    """Manages connection, WAL mode, pragmas, and schema migrations for a target SQLite DB."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            conn.commit()


class MemoryStores:
    """Container holding connections to the 5 isolated SQLite databases."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.conversations = SqliteStore(self.data_dir / "conversations.db")
        self.memories = SqliteStore(self.data_dir / "memories.db")
        self.knowledge = SqliteStore(self.data_dir / "knowledge.db")
        self.activity = SqliteStore(self.data_dir / "activity.db")

        self._ensure_schemas()

    def _ensure_schemas(self) -> None:
        # Conversations schema
        with self.conversations.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    state_json TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.commit()

        # Memories schema (User facts & preferences)
        with self.memories.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    fact_category TEXT NOT NULL,
                    fact_value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (user_id, key)
                )
            """)
            conn.commit()

        # Knowledge schema (RAG Chunks)
        with self.knowledge.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT,
                    title TEXT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

        # Activity schema (Idempotency & Audit logs)
        with self.activity.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_updates (
                    update_id INTEGER PRIMARY KEY,
                    processed_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()
