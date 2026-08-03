"""
Integration unit tests for adelia.main (FastAPI endpoints).

Uses FastAPI TestClient with mocked background services — zero network calls.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock huggingface_hub if missing in local environment
try:
    import huggingface_hub
except ImportError:
    mock_hub = MagicMock()
    class _MockHfHubHTTPError(Exception):
        pass
    mock_hub.utils.HfHubHTTPError = _MockHfHubHTTPError
    sys.modules["huggingface_hub"] = mock_hub
    sys.modules["huggingface_hub.utils"] = mock_hub.utils

try:
    from fastapi.testclient import TestClient
except ImportError:
    import asyncio

    class _TestResponse:
        def __init__(self, status_code: int, data: Any):
            self.status_code = status_code
            self._data = data

        def json(self):
            if isinstance(self._data, list):
                return [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in self._data
                ]
            if hasattr(self._data, "model_dump"):
                return self._data.model_dump()
            return self._data

    class TestClient:
        def __init__(self, app):
            self.app = app

        def _run_async(self, coro):
            return asyncio.get_event_loop().run_until_complete(coro)

        def get(self, path: str):
            handler = self.app.routes.get(("GET", path))
            if not handler:
                return _TestResponse(404, {"detail": "Not found"})
            try:
                res = self._run_async(handler())
                return _TestResponse(200, res)
            except Exception as err:
                status_code = getattr(err, "status_code", 500)
                detail = getattr(err, "detail", str(err))
                return _TestResponse(status_code, {"detail": detail})

        def post(self, path: str, json: dict = None):
            handler = self.app.routes.get(("POST", path))
            if not handler:
                return _TestResponse(404, {"detail": "Not found"})

            import inspect
            from adelia import main as main_mod

            sig = inspect.signature(handler)
            param = list(sig.parameters.values())[0]
            annotation = param.annotation

            if isinstance(annotation, str):
                model_cls = getattr(main_mod, annotation)
            else:
                model_cls = annotation

            req_obj = model_cls(**(json or {}))
            try:
                res = self._run_async(handler(req_obj))
                return _TestResponse(200, res)
            except Exception as err:
                status_code = getattr(err, "status_code", 500)
                detail = getattr(err, "detail", str(err))
                return _TestResponse(status_code, {"detail": detail})

from adelia.main import app, state
from adelia.schemas.models import ContentResponse, MemoryHit, PlatformDraft


class TestFastApiApp(unittest.TestCase):
    """Test suite for ADELIA FastAPI routes."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Initialise services on state for tests
        from adelia.inference.hf_client import HFClient
        from adelia.memory.content_memory import ContentMemory
        from adelia.memory.vector_store import ContentVectorStore
        from adelia.personas.persona_router import PersonaRouter

        state.hf_client = HFClient()
        state.vector_store = ContentVectorStore()
        state.memory = ContentMemory(hf=state.hf_client, store=state.vector_store)
        state.persona_router = PersonaRouter(hf_client=state.hf_client)

    @classmethod
    def tearDownClass(cls):
        if hasattr(state, "vector_store") and state.vector_store:
            state.vector_store.close()

    def test_health_endpoint(self):
        """GET /health returns health report."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "ADELIA Content Engine")

    @patch("adelia.main.generate_master_article", new_callable=AsyncMock)
    def test_generate_master_endpoint(self, mock_gen_master):
        """POST /api/v1/generate-master returns master article payload."""
        mock_gen_master.return_value = {
            "master_article": "Clean master article text.",
            "title": "News Title",
            "source_url": "https://example.com/news",
            "image_url": "",
            "hashtags": ["#Sakluma"],
            "raw_generated": "raw response",
        }

        payload = {
            "scraped_text": "Scraped body content for testing master article generation.",
            "title": "News Title",
            "source_url": "https://example.com/news",
        }
        resp = self.client.post("/api/v1/generate-master", json=payload)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "News Title")
        self.assertEqual(data["master_article"], "Clean master article text.")

    @patch("adelia.main.generate_platform_drafts", new_callable=AsyncMock)
    def test_generate_content_endpoint(self, mock_gen_drafts):
        """POST /api/v1/generate-content returns ContentResponse."""
        mock_gen_drafts.return_value = ContentResponse(
            status="ok",
            drafts=[
                PlatformDraft(
                    platform="facebook",
                    caption="FB Caption content",
                    suggested_persona="viral_santai",
                )
            ],
            warnings=[],
        )

        payload = {
            "master_article": "Master article text content for social engine.",
            "platforms": ["facebook"],
            "fb_style": "viral_santai",
        }
        resp = self.client.post("/api/v1/generate-content", json=payload)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["drafts"]), 1)
        self.assertEqual(data["drafts"][0]["platform"], "facebook")

    @patch("adelia.main.save_draft_to_airtable")
    def test_publish_endpoint(self, mock_save_airtable):
        """POST /api/v1/publish returns PublishResponse."""
        mock_save_airtable.return_value = {"status": "success", "record_id": "recPub999"}

        payload = {
            "draft": {
                "platform": "facebook",
                "caption": "Approved Facebook caption for publishing.",
            },
            "content_type": "Post",
            "extra_fields": {"title": "Test Title", "brand": "Sakluma"},
        }
        resp = self.client.post("/api/v1/publish", json=payload)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "published")
        self.assertEqual(data["record_id"], "recPub999")

    def test_recall_endpoint(self):
        """POST /api/v1/recall returns MemoryHit list."""
        mock_hit = MemoryHit(
            text="Past memory content",
            similarity=0.91,
            source_url="https://example.com",
            created_at="2026-07-30T12:00:00Z",
        )
        state.memory = MagicMock()
        state.memory.recall.return_value = [mock_hit]

        payload = {"query_text": "digital economy", "k": 3}
        resp = self.client.post("/api/v1/recall", json=payload)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["text"], "Past memory content")
        self.assertEqual(data[0]["similarity"], 0.91)

    @patch("adelia.main.generate_master_article", new_callable=AsyncMock)
    def test_endpoint_error_handling(self, mock_gen_master):
        """Endpoint exceptions return 500 status code."""
        mock_gen_master.side_effect = Exception("Database connection failed")

        payload = {"scraped_text": "Test content for failure test."}
        resp = self.client.post("/api/v1/generate-master", json=payload)

        self.assertEqual(resp.status_code, 500)
        self.assertIn("Master article generation failed", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
