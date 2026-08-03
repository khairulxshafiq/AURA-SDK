"""
Unit tests for AuraOne.tools.adelia_client.

All httpx calls are mocked — no real HTTP network traffic.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.adelia_client import (
    AdeliaConnectionError,
    AdeliaResponseError,
    generate_content,
    generate_master,
    publish,
    recall,
)


def _run(coro):
    """Helper to run coroutines in synchronous tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestAdeliaClient(unittest.TestCase):
    """Test suite for adelia_client functions."""

    @patch("httpx.AsyncClient.post")
    def test_generate_master_success(self, mock_post):
        """Happy path: generate_master returns dict response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "master_article": "Clean article",
            "title": "Title",
            "source_url": "https://example.com",
            "hashtags": ["#Sakluma"],
        }
        mock_post.return_value = mock_resp

        res = _run(generate_master(scraped_text="Scraped content", title="Title"))
        self.assertEqual(res["master_article"], "Clean article")

    @patch("httpx.AsyncClient.post")
    def test_generate_content_success(self, mock_post):
        """Happy path: generate_content passes resolved image_url and returns ContentResponse dict."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "ok",
            "drafts": [{"platform": "facebook", "caption": "FB Caption"}],
            "warnings": [],
        }
        mock_post.return_value = mock_resp

        res = _run(
            generate_content(
                master_article="Master text",
                platforms=["facebook"],
                fb_style="viral_santai",
                image_url="https://api.telegram.org/file/botTOKEN/file.jpg",
            )
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["drafts"][0]["platform"], "facebook")

    @patch("httpx.AsyncClient.post")
    def test_publish_success(self, mock_post):
        """Happy path: publish posts draft to ADELIA and returns record ID."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "published", "record_id": "recClient123"}
        mock_post.return_value = mock_resp

        draft_payload = {"platform": "facebook", "caption": "Caption"}
        res = _run(publish(draft=draft_payload, content_type="Post"))

        self.assertEqual(res["status"], "published")
        self.assertEqual(res["record_id"], "recClient123")

    @patch("httpx.AsyncClient.post")
    def test_recall_success(self, mock_post):
        """Happy path: recall searches memory and returns hits."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"text": "Memory text", "similarity": 0.88}]
        mock_post.return_value = mock_resp

        hits = _run(recall("digital economy", k=3))

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["similarity"], 0.88)

    @patch("httpx.AsyncClient.post")
    def test_response_error_on_non_200(self, mock_post):
        """Raises AdeliaResponseError when service returns non-200 HTTP status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        with self.assertRaises(AdeliaResponseError):
            _run(generate_master("Text"))

    @patch("httpx.AsyncClient.post")
    def test_connection_error_on_timeout(self, mock_post):
        """Raises AdeliaConnectionError when request fails or times out."""
        import httpx

        mock_post.side_effect = httpx.RequestError("Connection refused")

        with self.assertRaises(AdeliaConnectionError):
            _run(recall("Query"))


if __name__ == "__main__":
    unittest.main()
