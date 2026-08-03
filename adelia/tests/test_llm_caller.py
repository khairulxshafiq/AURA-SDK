"""
Unit tests for adelia.llm.llm_caller.

All Gemini and OpenRouter calls are mocked — no real API traffic.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from adelia.llm.llm_caller import (
    _current_key_idx,
    call_llm,
    clear_cooldowns,
    is_key_on_cooldown,
    set_key_cooldown,
)


def _run(coro):
    """Helper to run async coroutines in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestCooldownTracker(unittest.TestCase):
    """Tests for the in-memory cooldown tracker."""

    def setUp(self):
        clear_cooldowns()

    def test_key_not_on_cooldown_by_default(self):
        self.assertFalse(is_key_on_cooldown("some_key"))

    def test_set_and_check_cooldown(self):
        set_key_cooldown("key_a", duration=60)
        self.assertTrue(is_key_on_cooldown("key_a"))

    def test_expired_cooldown(self):
        set_key_cooldown("key_b", duration=-1)  # already expired
        self.assertFalse(is_key_on_cooldown("key_b"))

    def test_clear_cooldowns(self):
        set_key_cooldown("key_c", duration=60)
        clear_cooldowns()
        self.assertFalse(is_key_on_cooldown("key_c"))


class TestCallLlmGemini(unittest.TestCase):
    """Tests for the Gemini primary path."""

    def setUp(self):
        clear_cooldowns()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test_key_1"}, clear=False)
    @patch("adelia.llm.llm_caller._sync_gemini_call")
    def test_gemini_success(self, mock_gemini):
        """Gemini returns text on the first key attempt."""
        mock_gemini.return_value = "Generated content from Gemini"

        result = _run(call_llm("Write a summary"))

        self.assertEqual(result, "Generated content from Gemini")
        mock_gemini.assert_called_once_with("test_key_1", "Write a summary")

    @patch.dict(os.environ, {"GEMINI_API_KEY": "key_a", "GEMINI_API_KEY_1": "key_b"}, clear=False)
    @patch("adelia.llm.llm_caller._sync_gemini_call")
    def test_key_rotation_on_failure(self, mock_gemini):
        """First key fails, second key succeeds → rotation works."""
        mock_gemini.side_effect = [
            Exception("429 rate limit"),     # key_a fails
            "Success from key_b",            # key_b succeeds
        ]

        result = _run(call_llm("prompt text"))

        self.assertEqual(result, "Success from key_b")
        self.assertEqual(mock_gemini.call_count, 2)

    @patch.dict(os.environ, {"GEMINI_API_KEY": "key_a"}, clear=False)
    @patch("adelia.llm.llm_caller._sync_gemini_call")
    def test_cooldown_on_429(self, mock_gemini):
        """A 429 error places the key on cooldown."""
        mock_gemini.side_effect = Exception("429 quota exceeded")

        _run(call_llm("prompt"))

        self.assertTrue(is_key_on_cooldown("key_a"))

    @patch.dict(os.environ, {"GEMINI_API_KEY": "key_a"}, clear=False)
    @patch("adelia.llm.llm_caller._sync_gemini_call")
    def test_skips_cooled_down_key(self, mock_gemini):
        """A key already on cooldown is skipped."""
        set_key_cooldown("key_a", duration=60)
        mock_gemini.return_value = "should not be called"

        result = _run(call_llm("prompt"))

        # Only key is on cooldown, falls through to OpenRouter (which is not set)
        mock_gemini.assert_not_called()
        self.assertEqual(result, "")


class TestCallLlmOpenRouter(unittest.TestCase):
    """Tests for the OpenRouter fallback path."""

    def setUp(self):
        clear_cooldowns()

    @patch.dict(os.environ, {
        "GEMINI_API_KEY": "key_a",
        "OPENROUTER_API_KEY": "or_test_key",
        "OPENROUTER_FALLBACK_MODEL": "google/gemini-2.5-flash",
    }, clear=False)
    @patch("adelia.llm.llm_caller._sync_gemini_call")
    @patch("httpx.AsyncClient.post")
    def test_openrouter_fallback_on_gemini_failure(self, mock_post, mock_gemini):
        """Falls back to OpenRouter when all Gemini keys fail."""
        mock_gemini.side_effect = Exception("All keys dead")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter response"}}]
        }
        mock_post.return_value = mock_response

        result = _run(call_llm("prompt text"))

        self.assertEqual(result, "OpenRouter response")

    @patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENROUTER_API_KEY": ""}, clear=False)
    @patch("adelia.llm.llm_caller._sync_gemini_call")
    def test_returns_empty_when_no_keys_or_fallback(self, mock_gemini):
        """Returns empty string when no Gemini keys AND no OpenRouter key."""
        result = _run(call_llm("prompt"))
        self.assertEqual(result, "")

    @patch.dict(os.environ, {
        "GEMINI_API_KEY": "",
        "OPENROUTER_API_KEY": "or_key",
    }, clear=False)
    @patch("httpx.AsyncClient.post")
    def test_openrouter_direct_when_no_gemini_keys(self, mock_post):
        """Goes straight to OpenRouter when no Gemini keys are set."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Direct OR response"}}]
        }
        mock_post.return_value = mock_response

        result = _run(call_llm("prompt"))

        self.assertEqual(result, "Direct OR response")

    @patch.dict(os.environ, {
        "GEMINI_API_KEY": "key_a",
        "OPENROUTER_API_KEY": "or_key",
    }, clear=False)
    @patch("adelia.llm.llm_caller._sync_gemini_call")
    @patch("httpx.AsyncClient.post")
    def test_custom_openrouter_messages(self, mock_post, mock_gemini):
        """Custom openrouter_messages are forwarded to the fallback."""
        mock_gemini.side_effect = Exception("fail")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Custom msg response"}}]
        }
        mock_post.return_value = mock_response

        custom_msgs = [
            {"role": "system", "content": "You are ADELIA."},
            {"role": "user", "content": "Hello"},
        ]
        result = _run(call_llm("Hello", openrouter_messages=custom_msgs))

        self.assertEqual(result, "Custom msg response")
        # Verify custom messages were sent in the payload
        call_kwargs = mock_post.call_args
        sent_payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertEqual(sent_payload["messages"], custom_msgs)


if __name__ == "__main__":
    unittest.main()
