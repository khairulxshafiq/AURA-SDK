"""
Unit tests for adelia.core.master_article.generate_master_article.

All LLM calls are mocked — no real API calls made.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from adelia.core.master_article import (
    clean_master_article_text,
    extract_metadata_tags,
    generate_master_article,
)


def _run(coro):
    """Helper to execute coroutines in synchronous tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_SCRAPED_TEXT = (
    "Kementerian Perdagangan Dalam Negeri dan Kos Sara Hidup (KPDN) mengumumkan "
    "pelaksanaan Skim Harga Maksimum Musim Perayaan (SHMMP) sempena Hari Raya 2026. "
    "Menterinya menyatakan bahawa sebanyak 18 jenis barangan kawalan akan dipantau "
    "secara ketat oleh pihak penguat kuasa di seluruh negara bagi mengelakkan kenaikan "
    "harga luar kawalan yang membebankan pengguna."
)

SAMPLE_LLM_RESPONSE = (
    "📌 TAJUK ASAL / FOKUS UTAMA: KPDN Umum Skim Harga Maksimum Hari Raya 2026\n\n"
    "📝 RINGKASAN ISU / RINGKASAN CERITA:\n"
    "KPDN telah menetapkan 18 jenis barangan di bawah Skim Harga Maksimum Musim Perayaan. "
    "Langkah ini diambil bagi memastikan peniaga tidak menaikkan harga sewenang-wenangnya.\n\n"
    "📊 FAKTA & POIN PENTING:\n"
    "• 18 jenis barangan dikawal.\n"
    "• Pemantauan dibuat di seluruh negara.\n\n"
    "💡 SUDUT PANDANG KUNCI: Kawalan harga membantu mengurangkan beban sara hidup awam.\n\n"
    "[DRAFT_TITLE: KPDN Umum Skim Harga Maksimum Hari Raya 2026]\n"
    "[DRAFT_SOURCE_URL: https://example.com/news/123]\n"
    "[DRAFT_IMAGE: https://example.com/img/news.jpg]\n"
    "[DRAFT_HASHTAGS: #Sakluma #KPDN #HargaMaksimum]"
)


class TestExtractMetadataTags(unittest.TestCase):
    """Tests for metadata tag parsing."""

    def test_extract_all_tags(self):
        tags = extract_metadata_tags(SAMPLE_LLM_RESPONSE)
        self.assertEqual(tags.get("title"), "KPDN Umum Skim Harga Maksimum Hari Raya 2026")
        self.assertEqual(tags.get("source_url"), "https://example.com/news/123")
        self.assertEqual(tags.get("image"), "https://example.com/img/news.jpg")
        self.assertEqual(tags.get("hashtags"), "#Sakluma #KPDN #HargaMaksimum")

    def test_clean_master_article_text(self):
        cleaned = clean_master_article_text(SAMPLE_LLM_RESPONSE)
        self.assertNotIn("[DRAFT_", cleaned)
        self.assertIn("📌 TAJUK ASAL", cleaned)
        self.assertIn("💡 SUDUT PANDANG KUNCI", cleaned)


class TestGenerateMasterArticle(unittest.TestCase):
    """Tests for generate_master_article generator."""

    @patch("adelia.core.master_article.call_llm", new_callable=AsyncMock)
    def test_generate_master_article_success(self, mock_call_llm):
        """Happy path: generates clean article and parses metadata tags."""
        mock_call_llm.return_value = SAMPLE_LLM_RESPONSE

        result = _run(
            generate_master_article(
                scraped_text=SAMPLE_SCRAPED_TEXT,
                title="KPDN Harga Maksimum",
                source_url="https://example.com/news/123",
                image_url="https://example.com/img/news.jpg",
            )
        )

        self.assertIn("master_article", result)
        self.assertIn("hashtags", result)
        self.assertEqual(result["title"], "KPDN Umum Skim Harga Maksimum Hari Raya 2026")
        self.assertEqual(result["source_url"], "https://example.com/news/123")
        self.assertEqual(result["image_url"], "https://example.com/img/news.jpg")
        self.assertEqual(result["hashtags"], ["#Sakluma", "#KPDN", "#HargaMaksimum"])
        self.assertNotIn("[DRAFT_", result["master_article"])
        mock_call_llm.assert_called_once()

    @patch("adelia.core.master_article.call_llm", new_callable=AsyncMock)
    def test_generate_master_article_empty_llm_fallback(self, mock_call_llm):
        """Fallback handling when LLM returns empty response."""
        mock_call_llm.return_value = ""

        result = _run(
            generate_master_article(
                scraped_text=SAMPLE_SCRAPED_TEXT,
                title="Test Title",
                source_url="https://example.com/news",
            )
        )

        self.assertIn("Test Title", result["master_article"])
        self.assertEqual(result["hashtags"], ["#Sakluma", "#Berita"])

    def test_generate_master_article_too_short_text(self):
        """Returns raw text directly if scraped text is under 50 chars."""
        short_text = "Terlalu pendek"

        result = _run(
            generate_master_article(
                scraped_text=short_text,
                title="Short Title",
            )
        )

        self.assertEqual(result["master_article"], short_text)
        self.assertEqual(result["title"], "Short Title")


if __name__ == "__main__":
    unittest.main()
