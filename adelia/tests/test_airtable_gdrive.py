"""
Unit tests for adelia.publishers.airtable_gdrive.

All HTTP calls (httpx) and HFClient calls are mocked — zero network traffic.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock huggingface_hub if missing in local environment
try:
    import huggingface_hub
    from huggingface_hub.utils import HfHubHTTPError
except ImportError:
    mock_hub = MagicMock()
    class _MockHfHubHTTPError(Exception):
        pass
    mock_hub.utils.HfHubHTTPError = _MockHfHubHTTPError
    sys.modules["huggingface_hub"] = mock_hub
    sys.modules["huggingface_hub.utils"] = mock_hub.utils

from adelia.publishers.airtable_gdrive import (
    ensure_image_url,
    save_draft_to_airtable,
    save_thread_posts_to_airtable,
    upload_article_dump_to_drive,
    upload_file_to_drive,
)


class TestAirtableSaveDraft(unittest.TestCase):
    """Tests for save_draft_to_airtable with mock httpx calls."""

    @patch.dict(
        os.environ,
        {
            "AIRTABLE_API_KEY": "pat_test_key",
            "AIRTABLE_BASE_ID": "app_test_base",
            "AIRTABLE_TABLE_NAME": "Content Station",
        },
        clear=False,
    )
    @patch("httpx.Client.post")
    def test_save_draft_success(self, mock_post):
        """Happy path: post draft to Airtable and receive record_id."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "rec12345ABC"}
        mock_post.return_value = mock_resp

        res = save_draft_to_airtable(
            title="Malaysia Digital Economy",
            caption="Peruntukan khas RM100j untuk usahawan.",
            platform="facebook",
            image_url="https://example.com/image.jpg",
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["record_id"], "rec12345ABC")

        # Verify typecast=True was passed in payload
        call_kwargs = mock_post.call_args[1]
        self.assertTrue(call_kwargs["json"]["typecast"])
        self.assertEqual(call_kwargs["json"]["fields"]["Title"], "Malaysia Digital Economy")
        self.assertEqual(call_kwargs["json"]["fields"]["Platform"], ["Facebook"])

    @patch.dict(
        os.environ,
        {
            "AIRTABLE_API_KEY": "pat_test_key",
            "AIRTABLE_BASE_ID": "app_test_base",
        },
        clear=False,
    )
    @patch("httpx.Client.post")
    def test_self_healing_422_retry(self, mock_post):
        """Self-healing 422 retry: removes UNKNOWN_FIELD_NAME on 422 and retries."""
        mock_resp_422 = MagicMock()
        mock_resp_422.status_code = 422
        mock_resp_422.text = "UNKNOWN_FIELD_NAME: Field 'Original Price' does not exist"

        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"id": "rec422Fixed"}

        mock_post.side_effect = [mock_resp_422, mock_resp_200]

        res = save_draft_to_airtable(
            title="Test Post",
            caption="Test caption",
            original_price="RM99",
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["record_id"], "rec422Fixed")
        self.assertEqual(mock_post.call_count, 2)


class TestAirtableThreadPosts(unittest.TestCase):
    """Tests for save_thread_posts_to_airtable."""

    @patch.dict(
        os.environ,
        {
            "AIRTABLE_API_KEY": "pat_test_key",
            "AIRTABLE_BASE_ID": "app_test_base",
        },
        clear=False,
    )
    @patch("httpx.Client.post")
    def test_save_thread_posts_success(self, mock_post):
        """Saves individual thread posts linked to parent record."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"records": [{"id": "recT1"}, {"id": "recT2"}]}
        mock_post.return_value = mock_resp

        posts = ["Post 1: Hook", "Post 2: Main point"]
        res = save_thread_posts_to_airtable("recParent123", posts, platform="x")

        self.assertEqual(res["status"], "success")
        call_kwargs = mock_post.call_args[1]
        records = call_kwargs["json"]["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["fields"]["Content Station"], ["recParent123"])
        self.assertEqual(records[0]["fields"]["Platform"], "X")


class TestGoogleDriveUpload(unittest.TestCase):
    """Tests for upload_file_to_drive and upload_article_dump_to_drive."""

    @patch("adelia.publishers.airtable_gdrive._get_gdrive_access_token")
    @patch("httpx.Client.post")
    def test_upload_file_to_drive_success(self, mock_post, mock_token):
        """Uploads file bytes to Google Drive and sets reader permissions."""
        mock_token.return_value = "ya29.test_token"

        mock_upload_resp = MagicMock()
        mock_upload_resp.status_code = 200
        mock_upload_resp.json.return_value = {"id": "fileDrive999", "name": "web-1.txt"}

        mock_perm_resp = MagicMock()
        mock_perm_resp.status_code = 200

        mock_post.side_effect = [mock_upload_resp, mock_perm_resp]

        res = upload_file_to_drive(b"Sample article content", "web-1.txt", mime_type="text/plain")

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["file_id"], "fileDrive999")
        self.assertIn("fileDrive999", res["link"])

    @patch("adelia.publishers.airtable_gdrive.upload_file_to_drive")
    def test_upload_article_dump_to_drive(self, mock_upload):
        """Formulates article dump text file and calls upload_file_to_drive."""
        mock_upload.return_value = {"status": "success", "file_id": "dumpFile123"}

        res = upload_article_dump_to_drive(
            title="Article Title",
            master_article="Master content snippet",
            hashtags="#Sakluma",
            source_url="https://example.com",
            response_text="[DRAFT_FB: FB draft content]",
            counter=42,
        )

        self.assertEqual(res["status"], "success")
        mock_upload.assert_called_once()
        uploaded_bytes, filename = mock_upload.call_args[0][0], mock_upload.call_args[0][1]
        self.assertEqual(filename, "web-42.txt")
        self.assertIn(b"Master content snippet", uploaded_bytes)


class TestImageFallbackHook(unittest.TestCase):
    """Tests for FLUX image fallback hook when image_url is missing."""

    @patch.dict(os.environ, {"USE_HF_INFERENCE": "true"}, clear=False)
    @patch("adelia.publishers.airtable_gdrive.upload_file_to_drive")
    def test_ensure_image_url_generates_flux_image_when_missing(self, mock_upload):
        """Generates synthetic FLUX image when image_url is empty."""
        mock_upload.return_value = {
            "status": "success",
            "link": "https://docs.google.com/uc?export=download&id=fluxImg123",
        }
        mock_hf = MagicMock()
        mock_hf.generate_image.return_value = b"\x89PNG_FAKE_FLUX_BYTES"

        url = ensure_image_url(
            image_url="",
            prompt="Digital economy in Malaysia",
            hf_client=mock_hf,
            counter=5,
        )

        self.assertEqual(url, "https://docs.google.com/uc?export=download&id=fluxImg123")
        mock_hf.generate_image.assert_called_once_with("Digital economy in Malaysia")
        mock_upload.assert_called_once()

    @patch.dict(os.environ, {"USE_HF_INFERENCE": "false"}, clear=False)
    def test_ensure_image_url_skips_when_hf_disabled(self):
        """Skips FLUX image generation when USE_HF_INFERENCE is false."""
        mock_hf = MagicMock()
        url = ensure_image_url(image_url="", prompt="Prompt", hf_client=mock_hf)

        self.assertEqual(url, "")
        mock_hf.generate_image.assert_not_called()

    def test_ensure_image_url_returns_existing_url(self):
        """Returns existing valid image_url without calling HF generator."""
        mock_hf = MagicMock()
        existing_url = "https://example.com/existing.jpg"

        url = ensure_image_url(image_url=existing_url, prompt="Prompt", hf_client=mock_hf)

        self.assertEqual(url, existing_url)
        mock_hf.generate_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
