"""Vector Store for AuraOne backed by sqlite-vec + brute-force fallback."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("aura.core.memory.vectors")


class MemoryHit(BaseModel):
    """Result hit from vector similarity search."""

    text: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


def _serialize_f32(vec: list[float]) -> bytes:
    """Pack float list into float32 buffer."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _deserialize_f32(data: bytes) -> list[float]:
    """Unpack float32 buffer into float list."""
    n = len(data) // 4
    return list(struct.unpack(f"<{n}f", data))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore:
    """Manages semantic vector embeddings with model validation and sqlite-vec support."""

    def __init__(
        self,
        db_path: Path,
        expected_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
        expected_dim: int = 384,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.expected_model = expected_model
        self.expected_dim = expected_dim
        self._conn: sqlite3.Connection | None = None
        self._vec_enabled: bool = False

        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")

        # Create metadata & schema validation table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vector_schema (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Validate stored model & dimension metadata
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM vector_schema WHERE key='model_name'")
        stored_model_row = cur.fetchone()
        cur.execute("SELECT value FROM vector_schema WHERE key='dimension'")
        stored_dim_row = cur.fetchone()

        if stored_model_row and stored_dim_row:
            stored_model = stored_model_row[0]
            stored_dim = int(stored_dim_row[0])
            if stored_model != self.expected_model or stored_dim != self.expected_dim:
                err_msg = (
                    f"CRITICAL VECTOR METADATA MISMATCH! Database '{self.db_path.name}' "
                    f"was initialized with model '{stored_model}' ({stored_dim}-dim), "
                    f"but runtime is configured for '{self.expected_model}' ({self.expected_dim}-dim). "
                    "Re-index vectors or delete vectors.db to resolve."
                )
                logger.error("Vector metadata mismatch", stored_model=stored_model, expected_model=self.expected_model)
                raise ValueError(err_msg)
        else:
            self._conn.execute(
                "INSERT OR REPLACE INTO vector_schema (key, value) VALUES ('model_name', ?)",
                (self.expected_model,),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO vector_schema (key, value) VALUES ('dimension', ?)",
                (str(self.expected_dim),),
            )

        # Metadata table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vector_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Attempt to load sqlite-vec
        try:
            self._conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS content_vectors
                USING vec0(embedding float[{self.expected_dim}])
            """)
            self._vec_enabled = True
            logger.info("sqlite-vec loaded successfully")
        except (AttributeError, OSError, sqlite3.OperationalError, ImportError) as exc:
            logger.warning("sqlite-vec unavailable. Operating in brute-force cosine fallback mode", error=str(exc))
            self._vec_enabled = False
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS content_vectors_fallback (
                    id INTEGER PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    FOREIGN KEY (id) REFERENCES vector_metadata(id)
                )
            """)

        self._conn.commit()

    def add(self, text: str, embedding: list[float], metadata: dict | None = None) -> int:
        """Store text chunk and vector embedding."""
        if len(embedding) != self.expected_dim:
            raise ValueError(f"Vector dimension {len(embedding)} does not match expected {self.expected_dim}")

        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()

        cursor = self._conn.execute(
            "INSERT INTO vector_metadata (text, metadata_json, created_at) VALUES (?, ?, ?)",
            (text, metadata_json, now),
        )
        row_id = cursor.lastrowid
        blob = _serialize_f32(embedding)

        if self._vec_enabled:
            self._conn.execute("INSERT INTO content_vectors (rowid, embedding) VALUES (?, ?)", (row_id, blob))
        else:
            self._conn.execute(
                "INSERT INTO content_vectors_fallback (id, embedding) VALUES (?, ?)", (row_id, blob)
            )

        self._conn.commit()
        return row_id

    def search(self, embedding: list[float], k: int = 5) -> list[MemoryHit]:
        """KNN search returning top k nearest hits."""
        if self._vec_enabled:
            blob = _serialize_f32(embedding)
            rows = self._conn.execute(
                """
                SELECT cv.rowid, cv.distance, vm.text, vm.metadata_json, vm.created_at
                FROM content_vectors cv
                JOIN vector_metadata vm ON vm.id = cv.rowid
                WHERE cv.embedding MATCH ? AND k = ?
                ORDER BY cv.distance
                """,
                (blob, k),
            ).fetchall()

            results = []
            for rowid, distance, text, meta_str, created_at in rows:
                sim = 1.0 / (1.0 + distance)
                results.append(
                    MemoryHit(
                        text=text,
                        similarity=round(sim, 6),
                        metadata=json.loads(meta_str or "{}"),
                        created_at=created_at,
                    )
                )
            return results

        # Brute-force fallback
        rows = self._conn.execute(
            "SELECT cf.id, cf.embedding, vm.text, vm.metadata_json, vm.created_at FROM content_vectors_fallback cf JOIN vector_metadata vm ON vm.id = cf.id"
        ).fetchall()

        scored = []
        for row_id, blob, text, meta_str, created_at in rows:
            stored_vec = _deserialize_f32(blob)
            sim = _cosine_similarity(embedding, stored_vec)
            scored.append((sim, text, meta_str, created_at))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            MemoryHit(
                text=text,
                similarity=round(sim, 6),
                metadata=json.loads(meta_str or "{}"),
                created_at=created_at,
            )
            for sim, text, meta_str, created_at in scored[:k]
        ]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
