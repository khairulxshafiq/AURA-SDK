"""
Unit tests for adelia.memory.content_memory.ContentMemory.

All HFClient calls are mocked — no real API traffic. Tests exercise:
  - remember / recall / dedup happy paths
  - dedup tripping on near-identical text
  - dedup passing on unrelated text
  - graceful degradation when USE_HF_INFERENCE is False
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adelia.inference.exceptions import HFDisabled
from adelia.memory.content_memory import ContentMemory
from adelia.memory.vector_store import ContentVectorStore
from adelia.schemas.models import MemoryHit


def _make_memory(tmpdir: str) -> tuple[ContentMemory, MagicMock, ContentVectorStore]:
    """Build a ContentMemory with a mocked HFClient and real vector store."""
    db_path = Path(tmpdir) / "test_memory.db"
    store = ContentVectorStore(db_path=db_path)
    # Force fallback mode (always available)
    if store._vec_enabled:
        store._conn.execute("""
            CREATE TABLE IF NOT EXISTS content_vectors_fallback (
                id        INTEGER PRIMARY KEY,
                embedding BLOB    NOT NULL,
                FOREIGN KEY (id) REFERENCES content_metadata(id)
            )
        """)
        store._conn.commit()
    store._vec_enabled = False

    hf = MagicMock()
    memory = ContentMemory(hf=hf, store=store)
    return memory, hf, store


class TestRemember(unittest.TestCase):
    """Tests for ContentMemory.remember()."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.memory, self.hf, self.store = _make_memory(self._tmpdir)

    def tearDown(self):
        self.store.close()

    def test_remember_stores_embedding(self):
        """remember() embeds the text and persists it in the store."""
        self.hf.embed.return_value = [[1.0, 0.0, 0.0]]

        row_id = self.memory.remember("Bitcoin hits 100k", {"platform": "x"})

        self.assertIsNotNone(row_id)
        self.assertEqual(row_id, 1)
        self.hf.embed.assert_called_once_with(["Bitcoin hits 100k"])

    def test_remember_returns_none_when_disabled(self):
        """remember() returns None gracefully when HF is disabled."""
        self.hf.embed.side_effect = HFDisabled("disabled")

        row_id = self.memory.remember("some text")

        self.assertIsNone(row_id)


class TestRecall(unittest.TestCase):
    """Tests for ContentMemory.recall()."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.memory, self.hf, self.store = _make_memory(self._tmpdir)

    def tearDown(self):
        self.store.close()

    def test_recall_returns_stored_memories(self):
        """recall() embeds the query and returns matching memories."""
        # Store two items with known embeddings
        self.hf.embed.return_value = [[1.0, 0.0]]
        self.memory.remember("first item")

        self.hf.embed.return_value = [[0.0, 1.0]]
        self.memory.remember("second item")

        # Query with embedding close to first item
        self.hf.embed.return_value = [[1.0, 0.0]]
        hits = self.memory.recall("find the first", k=2)

        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].text, "first item")
        self.assertGreater(hits[0].similarity, hits[1].similarity)

    def test_recall_returns_empty_when_disabled(self):
        """recall() returns empty list when HF is disabled."""
        self.hf.embed.side_effect = HFDisabled("disabled")

        hits = self.memory.recall("anything")

        self.assertEqual(hits, [])


class TestDedupCheck(unittest.TestCase):
    """Tests for ContentMemory.dedup_check()."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.memory, self.hf, self.store = _make_memory(self._tmpdir)

    def tearDown(self):
        self.store.close()

    def test_near_identical_trips_dedup(self):
        """A near-identical sentence triggers dedup (similarity >= threshold)."""
        # Store the original
        self.hf.embed.return_value = [[1.0, 0.0, 0.0, 0.0]]
        self.memory.remember("Bitcoin surges past $100,000 milestone")

        # Check a near-identical candidate (same embedding = cosine 1.0)
        self.hf.embed.return_value = [[1.0, 0.0, 0.0, 0.0]]
        is_dup, closest = self.memory.dedup_check(
            "Bitcoin surges past the $100,000 milestone today",
            threshold=0.92,
        )

        self.assertTrue(is_dup)
        self.assertIsNotNone(closest)
        self.assertGreaterEqual(closest.similarity, 0.92)
        self.assertIn("Bitcoin", closest.text)

    def test_unrelated_passes_dedup(self):
        """An unrelated sentence passes dedup (similarity < threshold)."""
        # Store the original
        self.hf.embed.return_value = [[1.0, 0.0, 0.0, 0.0]]
        self.memory.remember("Bitcoin surges past $100,000 milestone")

        # Check a completely unrelated candidate (orthogonal embedding)
        self.hf.embed.return_value = [[0.0, 0.0, 0.0, 1.0]]
        is_dup, closest = self.memory.dedup_check(
            "Malaysian durian season starts in June",
            threshold=0.92,
        )

        self.assertFalse(is_dup)
        self.assertIsNotNone(closest)
        self.assertLess(closest.similarity, 0.92)

    def test_dedup_empty_store(self):
        """dedup_check on empty store returns (False, None)."""
        self.hf.embed.return_value = [[0.5, 0.5]]

        is_dup, closest = self.memory.dedup_check("anything at all")

        self.assertFalse(is_dup)
        self.assertIsNone(closest)

    def test_dedup_greenlights_when_disabled(self):
        """dedup_check returns (False, None) when HF is disabled — never blocks."""
        self.hf.embed.side_effect = HFDisabled("disabled")

        is_dup, closest = self.memory.dedup_check("any text")

        self.assertFalse(is_dup)
        self.assertIsNone(closest)

    def test_dedup_respects_custom_threshold(self):
        """dedup_check uses the provided threshold, not just the default."""
        # Store original
        self.hf.embed.return_value = [[1.0, 0.5, 0.0]]
        self.memory.remember("Original article about tech")

        # Candidate with high but not perfect similarity
        # [1.0, 0.3, 0.0] vs [1.0, 0.5, 0.0] → cosine ≈ 0.975
        self.hf.embed.return_value = [[1.0, 0.3, 0.0]]

        # With a very high threshold (0.99), this should pass
        is_dup_strict, _ = self.memory.dedup_check("Similar tech article", threshold=0.99)
        self.assertFalse(is_dup_strict)

        # With a low threshold (0.5), same similarity should trip
        self.hf.embed.return_value = [[1.0, 0.3, 0.0]]
        is_dup_loose, _ = self.memory.dedup_check("Similar tech article", threshold=0.5)
        self.assertTrue(is_dup_loose)


if __name__ == "__main__":
    unittest.main()
