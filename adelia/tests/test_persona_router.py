"""
Unit tests for adelia.personas.persona_router.suggest_fb_persona.

All HFClient calls are mocked — no real API traffic.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from adelia.inference.exceptions import HFDisabled
from adelia.personas.persona_router import (
    FB_PERSONA_LABELS,
    PersonaSuggestion,
    suggest_fb_persona,
)


class TestSuggestFbPersona(unittest.TestCase):
    """Tests for the zero-shot persona router."""

    def test_returns_top_label_and_confidence(self):
        """Router returns the highest-scoring persona from zero_shot."""
        hf = MagicMock()
        hf.zero_shot.return_value = {
            "sequence": "Harga minyak naik mendadak hari ini",
            "labels": ["berita", "pemerhati", "kedai_kopi", "viral_santai",
                       "makcik_bawang", "kisah_inspirasi", "borak_kawan"],
            "scores": [0.72, 0.12, 0.06, 0.04, 0.03, 0.02, 0.01],
        }

        result = suggest_fb_persona("Harga minyak naik mendadak hari ini", hf)

        self.assertIsInstance(result, PersonaSuggestion)
        self.assertEqual(result.persona, "berita")
        self.assertAlmostEqual(result.confidence, 0.72, places=2)

    def test_passes_default_labels(self):
        """Router passes the full FB_PERSONA_LABELS to zero_shot."""
        hf = MagicMock()
        hf.zero_shot.return_value = {
            "sequence": "text",
            "labels": FB_PERSONA_LABELS,
            "scores": [0.3, 0.2, 0.15, 0.12, 0.1, 0.08, 0.05],
        }

        suggest_fb_persona("any text", hf)

        _, call_kwargs = hf.zero_shot.call_args
        # zero_shot is called as hf.zero_shot(text, labels)
        call_args = hf.zero_shot.call_args[0]
        self.assertEqual(call_args[1], FB_PERSONA_LABELS)

    def test_accepts_custom_labels(self):
        """Router accepts an overridden label set."""
        hf = MagicMock()
        custom_labels = ["style_a", "style_b"]
        hf.zero_shot.return_value = {
            "sequence": "text",
            "labels": custom_labels,
            "scores": [0.8, 0.2],
        }

        result = suggest_fb_persona("text", hf, labels=custom_labels)

        self.assertEqual(result.persona, "style_a")
        call_args = hf.zero_shot.call_args[0]
        self.assertEqual(call_args[1], custom_labels)

    def test_returns_none_when_hf_disabled(self):
        """Router returns None (no blocking) when HF inference is off."""
        hf = MagicMock()
        hf.zero_shot.side_effect = HFDisabled("disabled")

        result = suggest_fb_persona("any article text", hf)

        self.assertIsNone(result)

    def test_inspirational_article_suggests_kisah_inspirasi(self):
        """An inspirational article should route to kisah_inspirasi."""
        hf = MagicMock()
        hf.zero_shot.return_value = {
            "sequence": "Dari budak kampung ke CEO — kisah kejayaan anak Kelantan",
            "labels": ["kisah_inspirasi", "berita", "borak_kawan", "pemerhati",
                       "makcik_bawang", "kedai_kopi", "viral_santai"],
            "scores": [0.65, 0.15, 0.08, 0.05, 0.04, 0.02, 0.01],
        }

        result = suggest_fb_persona(
            "Dari budak kampung ke CEO — kisah kejayaan anak Kelantan", hf
        )

        self.assertEqual(result.persona, "kisah_inspirasi")
        self.assertGreater(result.confidence, 0.5)

    def test_gossip_article_suggests_makcik_bawang(self):
        """A gossip-style article should route to makcik_bawang."""
        hf = MagicMock()
        hf.zero_shot.return_value = {
            "sequence": "Jiran sebelah kantoi buat bisnes haram depan rumah",
            "labels": ["makcik_bawang", "viral_santai", "kedai_kopi", "berita",
                       "borak_kawan", "pemerhati", "kisah_inspirasi"],
            "scores": [0.58, 0.18, 0.10, 0.06, 0.04, 0.03, 0.01],
        }

        result = suggest_fb_persona(
            "Jiran sebelah kantoi buat bisnes haram depan rumah", hf
        )

        self.assertEqual(result.persona, "makcik_bawang")

    def test_persona_suggestion_is_frozen(self):
        """PersonaSuggestion dataclass is immutable."""
        suggestion = PersonaSuggestion(persona="berita", confidence=0.9)
        with self.assertRaises(AttributeError):
            suggestion.persona = "other"


if __name__ == "__main__":
    unittest.main()
