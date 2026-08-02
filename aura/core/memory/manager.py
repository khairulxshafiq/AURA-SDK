"""Unified MemoryManager providing a single serialized write path for all stores."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import structlog

from aura.config import AuraConfig
from aura.core.memory.embeddings import embeddings_engine
from aura.core.memory.store import MemoryStores
from aura.core.memory.vectors import MemoryHit, VectorStore

logger = structlog.get_logger("aura.core.memory.manager")


class MemoryManager:
    """Unified single-writer MemoryManager over SQLite KV and Vector stores."""

    def __init__(self, config: AuraConfig | None = None) -> None:
        self.config = config or AuraConfig()
        self.data_dir = self.config.app_data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.stores = MemoryStores(self.data_dir)
        self.vector_store = VectorStore(self.data_dir / "vectors.db")
        self._write_lock = asyncio.Lock()

    # ── Idempotency Check ──────────────────────────────────────────────
    async def is_update_processed(self, update_id: int) -> bool:
        """Check if Telegram update_id has already been processed."""
        with self.stores.activity.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM processed_updates WHERE update_id = ?", (update_id,))
            return cur.fetchone() is not None

    async def mark_update_processed(self, update_id: int) -> None:
        """Mark Telegram update_id as processed to enforce idempotency."""
        async with self._write_lock:
            now = datetime.now(timezone.utc).isoformat()
            with self.stores.activity.get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO processed_updates (update_id, processed_at) VALUES (?, ?)",
                    (update_id, now),
                )
                conn.commit()

    # ── Vector Embeddings & Deduplication ──────────────────────────────
    async def remember(self, text: str, metadata: dict | None = None) -> int:
        """Embed text using local CPU model and store vector + metadata."""
        async with self._write_lock:
            embedding = embeddings_engine.embed_text(text)
            row_id = self.vector_store.add(text=text, embedding=embedding, metadata=metadata)
            logger.info("Stored vector memory", row_id=row_id, text_len=len(text))
            return row_id

    async def recall(self, query_text: str, k: int = 5) -> list[MemoryHit]:
        """Perform semantic search against vector store."""
        query_embedding = embeddings_engine.embed_text(query_text)
        hits = self.vector_store.search(query_embedding, k=k)
        logger.debug("Recalled vector memory", query=query_text, count=len(hits))
        return hits

    async def dedup_check(self, text: str, threshold: float = 0.85) -> tuple[bool, MemoryHit | None]:
        """Check if similar content already exists above similarity threshold."""
        hits = await self.recall(text, k=1)
        if hits and hits[0].similarity >= threshold:
            return True, hits[0]
        return False, hits[0] if hits else None

    def close(self) -> None:
        """Close vector store connection."""
        self.vector_store.close()


# Global singleton instance
memory = MemoryManager()
