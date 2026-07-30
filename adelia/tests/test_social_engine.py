"""
Unit tests for adelia.core.social_engine.generate_platform_drafts.

All LLM, HF, and memory calls are mocked — no real network/API traffic.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from adelia.core.social_engine import (
    clean_draft_text,
    generate_platform_drafts,
    parse_thread_posts,
)
from adelia.inference.exceptions import HFDisabled
from adelia.memory.content_memory import ContentMemory
from adelia.memory.vector_store import ContentVectorStore
from adelia.personas.persona_router import PersonaRouter, PersonaSuggestion
from adelia.schemas.models import ContentRequest, ContentResponse, MemoryHit, PlatformDraft


def _run(coro):
    """Helper to run coroutines in synchronous unit tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_ARTICLE = (
    "Kuala Lumpur: Kerajaan mengumumkan peruntukan baharu untuk pembangunan "
    "ekonomi digital negara. Menteri memaklumkan insentif ini menyasarkan "
    "usahawan muda dan syarikat tempatan."
)


class TestCleanDraftText(unittest.TestCase):
    """Tests for text cleaning and post-processing."""

    def test_strips_visual_notes(self):
        raw = "Kapsyen utama.\n\n[Gambar: Foto menteri di pentas utama]\n(Visual: Infografik)"
        cleaned = clean_draft_text(raw)
        self.assertNotIn("Gambar", cleaned)
        self.assertNotIn("Visual", cleaned)
        self.assertIn("Kapsyen utama", cleaned)

    def test_strips_hashtags_when_disabled(self):
        raw = "Kapsyen berita menarik. #Sakluma #Trending #IsuSemasa"
        cleaned = clean_draft_text(raw, hashtags_on=False)
        self.assertNotIn("#Sakluma", cleaned)
        self.assertNotIn("#Trending", cleaned)
        self.assertIn("Kapsyen berita menarik", cleaned)

    def test_parse_thread_posts(self):
        raw = "Bebanang 1: Hook tajam.\n---\nBebanang 2: Point 1.\n---\nBebanang 3: Penutup."
        posts = parse_thread_posts(raw)
        self.assertEqual(len(posts), 3)
        self.assertIn("Hook tajam", posts[0])
        self.assertIn("Point 1", posts[1])
        self.assertIn("Penutup", posts[2])


class TestGeneratePlatformDrafts(unittest.TestCase):
    """Tests for generate_platform_drafts core workflow."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test_engine_store.db"
        self.store = ContentVectorStore(db_path=self._db_path)
        self.store._vec_enabled = False

        self.mock_hf = MagicMock()
        self.memory = ContentMemory(hf=self.mock_hf, store=self.store)

    def tearDown(self):
        self.store.close()
        if self._db_path.exists():
            self._db_path.unlink()

    @patch("adelia.core.social_engine.call_llm", new_callable=AsyncMock)
    def test_happy_path_fb_and_threads(self, mock_call_llm):
        """Happy path: generates FB(viral_santai) + Threads(5) drafts."""
        mock_call_llm.side_effect = [
            "FB Caption viral santai! #Sakluma #Viral",  # FB response
            "Thread 1: Hook\n---\nThread 2: Point 1\n---\nThread 3: Point 2\n---\nThread 4: Point 3\n---\nThread 5: Outro",  # Threads response
        ]
        self.mock_hf.embed.return_value = [[0.1, 0.2, 0.3]]  # for dedup & remember

        req = ContentRequest(
            master_article=SAMPLE_ARTICLE,
            platforms=["facebook", "threads"],
            fb_style="viral_santai",
            thread_length=5,
            image_url="https://cdn.example.com/img.jpg",
        )

        res = _run(generate_platform_drafts(req, memory=self.memory))

        self.assertEqual(res.status, "ok")
        self.assertEqual(len(res.drafts), 2)

        fb_draft = next(d for d in res.drafts if d.platform == "facebook")
        self.assertEqual(fb_draft.image_url, "https://cdn.example.com/img.jpg")
        self.assertIn("FB Caption viral santai", fb_draft.caption)

        threads_draft = next(d for d in res.drafts if d.platform == "threads")
        self.assertIsNotNone(threads_draft.thread_posts)
        self.assertEqual(len(threads_draft.thread_posts), 5)
        self.assertEqual(threads_draft.thread_posts[0], "Hook")

    @patch("adelia.core.social_engine.call_llm", new_callable=AsyncMock)
    def test_dedup_warning_path(self, mock_call_llm):
        """Dedup warning path: flags warning when generated draft matches existing memory."""
        mock_call_llm.return_value = "Content about digital economy"

        # Pre-seed memory with identical embedding to simulate duplicate content
        self.mock_hf.embed.return_value = [[1.0, 0.0, 0.0]]
        self.memory.remember("Content about digital economy")

        # Query embedding is identical (similarity = 1.0 >= 0.85)
        self.mock_hf.embed.return_value = [[1.0, 0.0, 0.0]]

        req = ContentRequest(
            master_article=SAMPLE_ARTICLE,
            platforms=["facebook"],
            fb_style="berita",
        )

        res = _run(generate_platform_drafts(req, memory=self.memory))

        self.assertEqual(len(res.drafts), 1)
        self.assertGreater(len(res.warnings), 0)
        self.assertIn("Duplicate content detected", res.warnings[0])
        self.assertEqual(res.drafts[0].dedup_score, 1.0)

    @patch("adelia.core.social_engine.call_llm", new_callable=AsyncMock)
    def test_auto_persona_path(self, mock_call_llm):
        """Auto persona path: zero-shot router sets suggested_persona."""
        mock_call_llm.return_value = "Inspirational story caption"

        mock_router = MagicMock(spec=PersonaRouter)
        mock_router.suggest_fb_persona.return_value = PersonaSuggestion(
            persona="kisah_inspirasi", confidence=0.88
        )
        self.mock_hf.embed.return_value = [[0.1, 0.1]]

        req = ContentRequest(
            master_article=SAMPLE_ARTICLE,
            platforms=["facebook"],
            auto_persona=True,
            fb_style=None,  # let auto_persona decide
        )

        res = _run(generate_platform_drafts(req, memory=self.memory, router=mock_router))

        self.assertEqual(res.status, "ok")
        self.assertEqual(len(res.drafts), 1)
        draft = res.drafts[0]
        self.assertEqual(draft.suggested_persona, "kisah_inspirasi")
        mock_router.suggest_fb_persona.assert_called_once_with(SAMPLE_ARTICLE)


if __name__ == "__main__":
    unittest.main()
