"""
ContentVectorStore — Semantic memory layer for ADELIA (sqlite-vec + fallback).

Storage lives at adelia/data/adelia_memory.db (NEVER AURA's aura_memory.db).

Primary path: sqlite-vec ``vec0`` virtual table for fast KNN search.
Fallback path: if the Python/SQLite build cannot load extensions, stores
embeddings as binary blobs in a regular table and performs brute-force
cosine similarity in pure Python (no numpy required). A warning is logged
once when the fallback activates.

bge-m3 produces 1024-dimensional float32 vectors.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path

from adelia.schemas.models import MemoryHit

logger = logging.getLogger(__name__)

# bge-m3 embedding dimensionality
_EMBED_DIM = 1024


# ── Helpers ────────────────────────────────────────────────────────────


def _serialize_f32(vec: list[float]) -> bytes:
    """Pack a float list into a little-endian float32 buffer for sqlite-vec."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _deserialize_f32(data: bytes) -> list[float]:
    """Unpack a little-endian float32 buffer back into a float list."""
    n = len(data) // 4
    return list(struct.unpack(f"<{n}f", data))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity (no numpy). Returns 0.0–1.0."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Vector Store ───────────────────────────────────────────────────────


class ContentVectorStore:
    """Semantic content memory backed by SQLite + sqlite-vec.

    Args:
        db_path: Path to the SQLite database file. Defaults to
                 ``adelia/data/adelia_memory.db``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent / "data" / "adelia_memory.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn: sqlite3.Connection | None = None
        self._vec_enabled: bool = False

        self._init_db()

    # ── Initialisation ─────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Open the database and attempt to load sqlite-vec."""
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")

        # Always create the metadata table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS content_metadata (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT    NOT NULL,
                source_url TEXT,
                platform   TEXT,
                created_at TEXT    NOT NULL
            )
        """)

        # Attempt to load sqlite-vec for native vector search
        try:
            self._conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)

            # Create vec0 virtual table (rowid maps to content_metadata.id)
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS content_vectors
                USING vec0(embedding float[{_EMBED_DIM}])
            """)
            self._vec_enabled = True
            logger.info("sqlite-vec loaded — native KNN search enabled.")

        except (AttributeError, OSError, sqlite3.OperationalError) as exc:
            # Fallback: store embeddings as blobs in a regular table
            logger.warning(
                "sqlite-vec unavailable (%s). Falling back to brute-force "
                "cosine search. Performance will degrade with large datasets.",
                exc,
            )
            self._vec_enabled = False
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS content_vectors_fallback (
                    id        INTEGER PRIMARY KEY,
                    embedding BLOB    NOT NULL,
                    FOREIGN KEY (id) REFERENCES content_metadata(id)
                )
            """)

        self._conn.commit()

    # ── Public API ─────────────────────────────────────────────────────

    def add(
        self,
        text: str,
        embedding: list[float],
        metadata: dict | None = None,
    ) -> int:
        """Store a text chunk and its embedding.

        Args:
            text: The original text content.
            embedding: Float vector (len = 1024 for bge-m3).
            metadata: Optional dict with keys ``source_url``, ``platform``.

        Returns:
            The row ID of the inserted record.
        """
        metadata = metadata or {}
        now = datetime.now(timezone.utc).isoformat()

        cursor = self._conn.execute(
            """
            INSERT INTO content_metadata (text, source_url, platform, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                text,
                metadata.get("source_url"),
                metadata.get("platform"),
                now,
            ),
        )
        row_id = cursor.lastrowid

        blob = _serialize_f32(embedding)

        if self._vec_enabled:
            self._conn.execute(
                "INSERT INTO content_vectors (rowid, embedding) VALUES (?, ?)",
                (row_id, blob),
            )
        else:
            self._conn.execute(
                "INSERT INTO content_vectors_fallback (id, embedding) VALUES (?, ?)",
                (row_id, blob),
            )

        self._conn.commit()
        return row_id

    def search(self, embedding: list[float], k: int = 5) -> list[MemoryHit]:
        """Find the k nearest neighbours to the given embedding.

        Args:
            embedding: Query vector (same dimensionality as stored vectors).
            k: Number of results to return.

        Returns:
            List of MemoryHit ordered by similarity (descending).
        """
        if self._vec_enabled:
            return self._search_vec0(embedding, k)
        return self._search_brute_force(embedding, k)

    # ── Native sqlite-vec search ───────────────────────────────────────

    def _search_vec0(self, embedding: list[float], k: int) -> list[MemoryHit]:
        """KNN search via the vec0 virtual table."""
        blob = _serialize_f32(embedding)

        rows = self._conn.execute(
            """
            SELECT
                cv.rowid,
                cv.distance,
                cm.text,
                cm.source_url,
                cm.created_at
            FROM content_vectors cv
            JOIN content_metadata cm ON cm.id = cv.rowid
            WHERE cv.embedding MATCH ?
                AND k = ?
            ORDER BY cv.distance
            """,
            (blob, k),
        ).fetchall()

        results: list[MemoryHit] = []
        for row in rows:
            _rowid, distance, text, source_url, created_at = row
            # vec0 returns L2 distance — convert to a 0–1 similarity score.
            # similarity = 1 / (1 + distance)  gives a monotonically
            # decreasing function that maps [0, ∞) → (0, 1].
            similarity = 1.0 / (1.0 + distance)
            results.append(
                MemoryHit(
                    text=text,
                    similarity=round(similarity, 6),
                    source_url=source_url,
                    created_at=created_at,
                )
            )
        return results

    # ── Brute-force fallback ───────────────────────────────────────────

    def _search_brute_force(self, embedding: list[float], k: int) -> list[MemoryHit]:
        """Pure-Python cosine similarity scan (no numpy)."""
        rows = self._conn.execute(
            """
            SELECT
                cf.id,
                cf.embedding,
                cm.text,
                cm.source_url,
                cm.created_at
            FROM content_vectors_fallback cf
            JOIN content_metadata cm ON cm.id = cf.id
            """
        ).fetchall()

        scored: list[tuple[float, str, str | None, str]] = []
        for _row_id, blob, text, source_url, created_at in rows:
            stored_vec = _deserialize_f32(blob)
            sim = _cosine_similarity(embedding, stored_vec)
            scored.append((sim, text, source_url, created_at))

        # Sort by similarity descending, take top-k
        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            MemoryHit(
                text=text,
                similarity=round(sim, 6),
                source_url=source_url,
                created_at=created_at,
            )
            for sim, text, source_url, created_at in scored[:k]
        ]

    # ── Lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def vec_enabled(self) -> bool:
        """Whether native sqlite-vec is active (vs brute-force fallback)."""
        return self._vec_enabled
