"""
Unit tests for adelia.memory.vector_store.ContentVectorStore.

Tests run against BOTH the brute-force fallback path (always available)
and the sqlite-vec vec0 code path (mocked at the connection level so it
runs on every system, including macOS framework Python without
enable_load_extension support).
"""

from __future__ import annotations

import math
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adelia.memory.vector_store import (
    ContentVectorStore,
    _cosine_similarity,
    _deserialize_f32,
    _serialize_f32,
)
from adelia.schemas.models import MemoryHit


class TestSerialisation(unittest.TestCase):
    """Round-trip tests for float32 packing."""

    def test_round_trip(self):
        original = [0.1, 0.2, 0.3, -0.5, 1.0]
        blob = _serialize_f32(original)
        restored = _deserialize_f32(blob)
        for a, b in zip(original, restored):
            self.assertAlmostEqual(a, b, places=5)

    def test_empty_vector(self):
        blob = _serialize_f32([])
        self.assertEqual(_deserialize_f32(blob), [])


class TestCosineSimilarity(unittest.TestCase):
    """Tests for the pure-Python cosine similarity helper."""

    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        self.assertAlmostEqual(_cosine_similarity(v, v), 1.0, places=6)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(_cosine_similarity(a, b), 0.0, places=6)

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        self.assertAlmostEqual(_cosine_similarity(a, b), 0.0, places=6)


class TestContentVectorStoreFallback(unittest.TestCase):
    """Tests against the brute-force cosine fallback (always works)."""

    def setUp(self):
        """Create a temp DB with sqlite-vec forcibly disabled."""
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test_memory.db"

        # Build store, then force fallback mode
        self.store = ContentVectorStore(db_path=self._db_path)
        self._force_fallback()

    def _force_fallback(self):
        """Switch to fallback mode regardless of sqlite-vec availability."""
        if self.store._vec_enabled:
            # vec0 was loaded — recreate the fallback table so tests work
            self.store._conn.execute("""
                CREATE TABLE IF NOT EXISTS content_vectors_fallback (
                    id        INTEGER PRIMARY KEY,
                    embedding BLOB    NOT NULL,
                    FOREIGN KEY (id) REFERENCES content_metadata(id)
                )
            """)
            self.store._conn.commit()
        self.store._vec_enabled = False

    def tearDown(self):
        self.store.close()
        if self._db_path.exists():
            self._db_path.unlink()

    def test_add_and_retrieve(self):
        """Insert one vector and verify it comes back as the nearest hit."""
        vec = [1.0] * 4
        row_id = self.store.add(
            text="hello world",
            embedding=vec,
            metadata={"source_url": "https://example.com", "platform": "facebook"},
        )
        self.assertEqual(row_id, 1)

        hits = self.store.search(vec, k=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].text, "hello world")
        self.assertEqual(hits[0].source_url, "https://example.com")
        self.assertAlmostEqual(hits[0].similarity, 1.0, places=4)

    def test_nearest_neighbour_ordering(self):
        """Insert 3 vectors and verify search returns them in correct order.

        Vectors:
            v_close   = [1, 1, 0, 0]  — most similar to query [1, 1, 0, 0]
            v_medium  = [1, 0, 1, 0]  — moderately similar
            v_far     = [0, 0, 1, 1]  — least similar (orthogonal-ish)
        """
        query = [1.0, 1.0, 0.0, 0.0]

        v_close = [1.0, 1.0, 0.0, 0.0]    # cosine = 1.0
        v_medium = [1.0, 0.0, 1.0, 0.0]   # cosine = 0.5
        v_far = [0.0, 0.0, 1.0, 1.0]      # cosine = 0.0

        self.store.add("close text", v_close, {"platform": "x"})
        self.store.add("medium text", v_medium, {"platform": "fb"})
        self.store.add("far text", v_far, {"platform": "ig"})

        hits = self.store.search(query, k=3)

        self.assertEqual(len(hits), 3)

        # Verify ordering: close > medium > far
        self.assertEqual(hits[0].text, "close text")
        self.assertEqual(hits[1].text, "medium text")
        self.assertEqual(hits[2].text, "far text")

        # Verify similarity scores
        self.assertAlmostEqual(hits[0].similarity, 1.0, places=4)
        self.assertAlmostEqual(hits[1].similarity, 0.5, places=4)
        self.assertAlmostEqual(hits[2].similarity, 0.0, places=4)

    def test_k_limits_results(self):
        """Requesting k=1 returns only the single best match."""
        self.store.add("a", [1.0, 0.0], {})
        self.store.add("b", [0.0, 1.0], {})

        hits = self.store.search([1.0, 0.0], k=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].text, "a")

    def test_empty_store_returns_empty(self):
        """Searching an empty store returns no hits."""
        hits = self.store.search([1.0, 0.0], k=5)
        self.assertEqual(hits, [])

    def test_returns_memory_hit_type(self):
        """All results are proper MemoryHit instances."""
        self.store.add("test", [1.0], {})
        hits = self.store.search([1.0], k=1)
        self.assertIsInstance(hits[0], MemoryHit)

    def test_context_manager(self):
        """Store works as a context manager."""
        db_path = Path(self._tmpdir) / "ctx_test.db"
        with ContentVectorStore(db_path=db_path) as store:
            store._vec_enabled = False
            store._conn.execute("""
                CREATE TABLE IF NOT EXISTS content_vectors_fallback (
                    id        INTEGER PRIMARY KEY,
                    embedding BLOB    NOT NULL
                )
            """)
            store.add("ctx", [0.5, 0.5], {})
        # After exit, connection should be closed
        self.assertIsNone(store._conn)


class _ConnectionProxy:
    """Thin proxy around sqlite3.Connection that intercepts execute() calls.

    sqlite3.Connection.execute is read-only in CPython 3.13+, so we cannot
    monkey-patch it. This proxy delegates everything to the real connection
    but lets tests inject custom behaviour for specific SQL patterns.
    """

    def __init__(self, real_conn: sqlite3.Connection):
        self._real = real_conn
        self._execute_hook = None  # callable(sql, params) -> cursor | None
        self._captured_sqls: list[str] = []
        self._suppress_commit = False

    def execute(self, sql, params=None):
        self._captured_sqls.append(sql.strip())
        if self._execute_hook is not None:
            result = self._execute_hook(sql, params)
            if result is not None:
                return result
        if params is not None:
            return self._real.execute(sql, params)
        return self._real.execute(sql)

    def commit(self):
        if not self._suppress_commit:
            self._real.commit()

    def __getattr__(self, name):
        return getattr(self._real, name)


class TestContentVectorStoreVec0(unittest.TestCase):
    """Tests for the vec0 (sqlite-vec) code path.

    Uses a ConnectionProxy to intercept SQL so that ``_search_vec0`` is
    fully exercised even on systems where ``enable_load_extension`` is
    unavailable (e.g. macOS framework Python).
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test_vec0.db"
        self.store = ContentVectorStore(db_path=self._db_path)
        # Force vec0 mode regardless of actual extension availability
        self.store._vec_enabled = True
        # Wrap the real connection in our interceptor
        self._proxy = _ConnectionProxy(self.store._conn)
        self.store._conn = self._proxy

    def tearDown(self):
        # Restore real connection for clean close
        self.store._conn = self._proxy._real
        self.store.close()
        if self._db_path.exists():
            self._db_path.unlink()

    def test_vec0_nearest_neighbour_ordering(self):
        """Exercise _search_vec0 with mocked SQL results.

        Simulates 3 stored vectors at varying L2 distances and verifies
        the method converts distances to descending similarity scores
        and returns correctly ordered MemoryHit objects.
        """
        # Pre-populate metadata rows so the JOIN has real data
        self._proxy._real.execute(
            "INSERT INTO content_metadata (id, text, source_url, platform, created_at) "
            "VALUES (1, 'close', 'https://a.com', 'x', '2026-01-01T00:00:00+00:00')"
        )
        self._proxy._real.execute(
            "INSERT INTO content_metadata (id, text, source_url, platform, created_at) "
            "VALUES (2, 'medium', 'https://b.com', 'fb', '2026-01-02T00:00:00+00:00')"
        )
        self._proxy._real.execute(
            "INSERT INTO content_metadata (id, text, source_url, platform, created_at) "
            "VALUES (3, 'far', 'https://c.com', 'ig', '2026-01-03T00:00:00+00:00')"
        )
        self._proxy._real.commit()

        # Mock the vec0 KNN query to return L2-distance-sorted rows
        mock_vec0_rows = [
            (1, 0.0,   "close",  "https://a.com", "2026-01-01T00:00:00+00:00"),
            (2, 1.414, "medium", "https://b.com", "2026-01-02T00:00:00+00:00"),
            (3, 2.0,   "far",    "https://c.com", "2026-01-03T00:00:00+00:00"),
        ]

        def hook(sql, params):
            if "content_vectors" in sql and "MATCH" in sql:
                mock_cursor = MagicMock()
                mock_cursor.fetchall.return_value = mock_vec0_rows
                return mock_cursor
            return None  # fall through to real execute

        self._proxy._execute_hook = hook

        query = [1.0, 1.0, 0.0, 0.0]
        hits = self.store.search(query, k=3)

        # Verify 3 results returned
        self.assertEqual(len(hits), 3)

        # Verify ordering: close > medium > far
        self.assertEqual(hits[0].text, "close")
        self.assertEqual(hits[1].text, "medium")
        self.assertEqual(hits[2].text, "far")

        # Verify similarity scores (1 / (1 + distance))
        self.assertAlmostEqual(hits[0].similarity, 1.0, places=4)          # 1/(1+0)
        self.assertAlmostEqual(hits[1].similarity, 1.0 / 2.414, places=3)  # 1/(1+1.414)
        self.assertAlmostEqual(hits[2].similarity, 1.0 / 3.0, places=4)    # 1/(1+2)

        # Verify descending similarity
        self.assertGreater(hits[0].similarity, hits[1].similarity)
        self.assertGreater(hits[1].similarity, hits[2].similarity)

    def test_vec0_add_routes_to_vec_table(self):
        """Verify that add() routes inserts to the vec0 table when enabled."""
        def hook(sql, params):
            if "content_vectors" in sql and "INSERT" in sql:
                # Swallow the vec0 INSERT (table may not exist)
                mock_cursor = MagicMock()
                mock_cursor.lastrowid = 1
                return mock_cursor
            return None

        self._proxy._execute_hook = hook
        self._proxy._suppress_commit = True

        self.store.add("test text", [0.1, 0.2], {"source_url": "https://x.com"})

        # Find the vec0 INSERT among captured SQL
        vec_inserts = [
            s for s in self._proxy._captured_sqls
            if "content_vectors" in s and "INSERT" in s
        ]
        self.assertEqual(len(vec_inserts), 1)
        self.assertIn("content_vectors", vec_inserts[0])
        self.assertNotIn("fallback", vec_inserts[0])

    def test_vec0_empty_result(self):
        """_search_vec0 returns empty list when no rows match."""
        def hook(sql, params):
            if "content_vectors" in sql and "MATCH" in sql:
                mock_cursor = MagicMock()
                mock_cursor.fetchall.return_value = []
                return mock_cursor
            return None

        self._proxy._execute_hook = hook

        hits = self.store.search([1.0, 0.0], k=5)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
