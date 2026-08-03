"""
Unit tests for adelia.inference.hf_client.HFClient.

All tests mock huggingface_hub.InferenceClient — no real API calls made.
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

# Ensure HF inference is enabled for tests (env must be set BEFORE import)
os.environ["USE_HF_INFERENCE"] = "true"
os.environ["HF_TOKEN"] = "hf_test_fake_token"

from adelia.inference.hf_client import (
    HFClient,
    HFCreditsExhausted,
    HFDisabled,
    HFInferenceError,
    HFTokenForbidden,
)


class _FakeResponse:
    """Minimal response stub for HfHubHTTPError."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.request = MagicMock()


def _make_hf_http_error(status_code: int) -> Exception:
    """Create an HfHubHTTPError-like exception with a .response attribute."""
    from huggingface_hub.utils import HfHubHTTPError

    resp = _FakeResponse(status_code)
    try:
        exc = HfHubHTTPError(f"Mock error {status_code}", response=resp)
    except TypeError:
        exc = HfHubHTTPError(f"Mock error {status_code}")
        exc.response = resp
    return exc


class TestHFClientDisabled(unittest.TestCase):
    """Tests for the USE_HF_INFERENCE kill-switch."""

    @patch.dict(os.environ, {"USE_HF_INFERENCE": "false"}, clear=False)
    def test_embed_raises_hf_disabled(self):
        client = HFClient()
        with self.assertRaises(HFDisabled):
            client.embed(["hello"])

    @patch.dict(os.environ, {"USE_HF_INFERENCE": "false"}, clear=False)
    def test_zero_shot_raises_hf_disabled(self):
        client = HFClient()
        with self.assertRaises(HFDisabled):
            client.zero_shot("text", ["a", "b"])

    @patch.dict(os.environ, {"USE_HF_INFERENCE": "false"}, clear=False)
    def test_generate_image_raises_hf_disabled(self):
        client = HFClient()
        with self.assertRaises(HFDisabled):
            client.generate_image("a cat on the moon")


class TestHFClientEmbed(unittest.TestCase):
    """Tests for HFClient.embed()."""

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_embed_single_text(self, MockClientClass):
        mock_instance = MagicMock()
        # Simulate feature_extraction returning a nested list
        mock_instance.feature_extraction.return_value = [[0.1, 0.2, 0.3]]
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance  # inject mock

        result = client.embed(["hello world"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [0.1, 0.2, 0.3])
        mock_instance.feature_extraction.assert_called_once_with(
            "hello world", model="BAAI/bge-m3"
        )

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_embed_multiple_texts(self, MockClientClass):
        mock_instance = MagicMock()
        mock_instance.feature_extraction.side_effect = [
            [[0.1, 0.2]],
            [[0.3, 0.4]],
        ]
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        result = client.embed(["text one", "text two"])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], [0.1, 0.2])
        self.assertEqual(result[1], [0.3, 0.4])


class TestHFClientZeroShot(unittest.TestCase):
    """Tests for HFClient.zero_shot()."""

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_zero_shot_list_format(self, MockClientClass):
        mock_instance = MagicMock()
        # InferenceClient returns sorted list of {label, score} dicts
        mock_instance.zero_shot_classification.return_value = [
            {"label": "finance", "score": 0.85},
            {"label": "sports", "score": 0.10},
            {"label": "tech", "score": 0.05},
        ]
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        result = client.zero_shot("Bitcoin hits new highs", ["finance", "sports", "tech"])

        self.assertEqual(result["sequence"], "Bitcoin hits new highs")
        self.assertEqual(result["labels"], ["finance", "sports", "tech"])
        self.assertAlmostEqual(result["scores"][0], 0.85)

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_zero_shot_dict_format(self, MockClientClass):
        """Handles older dict-shaped API response gracefully."""
        mock_instance = MagicMock()
        mock_instance.zero_shot_classification.return_value = {
            "sequence": "test",
            "labels": ["a"],
            "scores": [0.99],
        }
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        result = client.zero_shot("test", ["a"])
        self.assertEqual(result["labels"], ["a"])


class TestHFClientGenerateImage(unittest.TestCase):
    """Tests for HFClient.generate_image()."""

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_generate_image_returns_bytes(self, MockClientClass):
        from unittest.mock import PropertyMock

        # Create a mock PIL Image that saves PNG bytes
        mock_image = MagicMock()

        def fake_save(buf, format=None):
            buf.write(b"\x89PNG_FAKE_DATA")

        mock_image.save = fake_save

        mock_instance = MagicMock()
        mock_instance.text_to_image.return_value = mock_image
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        result = client.generate_image("a cat on the moon")

        self.assertIsInstance(result, bytes)
        self.assertTrue(result.startswith(b"\x89PNG"))
        mock_instance.text_to_image.assert_called_once_with(
            "a cat on the moon",
            model="black-forest-labs/FLUX.1-schnell",
            provider="hf-inference",
        )


class TestHFClientErrors(unittest.TestCase):
    """Tests for typed error handling (402, 403)."""

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_402_raises_credits_exhausted(self, MockClientClass):
        mock_instance = MagicMock()
        mock_instance.feature_extraction.side_effect = _make_hf_http_error(402)
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        with self.assertRaises(HFCreditsExhausted):
            client.embed(["test"])

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_403_raises_token_forbidden(self, MockClientClass):
        mock_instance = MagicMock()
        mock_instance.feature_extraction.side_effect = _make_hf_http_error(403)
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        with self.assertRaises(HFTokenForbidden):
            client.embed(["test"])

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_500_retries_then_raises_generic(self, MockClientClass):
        mock_instance = MagicMock()
        # Fail twice (initial + 1 retry) with 500
        mock_instance.feature_extraction.side_effect = [
            _make_hf_http_error(500),
            _make_hf_http_error(500),
        ]
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        with self.assertRaises(HFInferenceError):
            client.embed(["test"])

        # Should have been called twice (initial + 1 retry)
        self.assertEqual(mock_instance.feature_extraction.call_count, 2)

    @patch("adelia.inference.hf_client.InferenceClient")
    def test_retry_succeeds_on_second_attempt(self, MockClientClass):
        mock_instance = MagicMock()
        mock_instance.feature_extraction.side_effect = [
            _make_hf_http_error(500),     # first attempt fails
            [[0.1, 0.2, 0.3]],            # retry succeeds
        ]
        MockClientClass.return_value = mock_instance

        client = HFClient()
        client._client = mock_instance

        result = client.embed(["test"])

        self.assertEqual(result, [[0.1, 0.2, 0.3]])
        self.assertEqual(mock_instance.feature_extraction.call_count, 2)


if __name__ == "__main__":
    unittest.main()
