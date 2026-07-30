"""
Parity tests for ADELIA prompts vs LUMA_MEMORY.md spec.

Asserts that every persona, thread count, and thread style exists in the
ADELIA prompt registry with correct keys and labels.
"""

from __future__ import annotations

import unittest

from adelia.prompts.platforms.facebook import FB_PERSONAS, build_facebook_prompt
from adelia.prompts.platforms.threads import THREAD_COUNTS, THREADS_STYLES, build_threads_prompt
from adelia.prompts.platforms.x import build_x_prompt
from adelia.prompts.platforms.lemon8 import build_lemon8_prompt
from adelia.prompts import build_prompt
from adelia.prompts.shared.hashtags import SAKLUMA_HASHTAGS


# ── Expected sets (from LUMA_MEMORY.md + user spec) ────────────────────

EXPECTED_FB_PERSONAS = {
    "berita",
    "pemerhati",
    "kedai_kopi",
    "viral_santai",
    "makcik_bawang",
    "kisah_inspirasi",
    "borak_kawan",  # Added per LUMA spec
}

EXPECTED_THREAD_COUNTS = {"1", "3", "5", "8"}

EXPECTED_THREADS_STYLES = {
    "genz",
    "informative",
    "kepoh",
    "catchy",
    "hook_memanggil",
}


class TestFBPersonaParity(unittest.TestCase):
    """FB personas must match the LUMA_MEMORY.md spec exactly."""

    def test_all_fb_personas_exist(self):
        """Every expected FB persona key exists in FB_PERSONAS."""
        for persona in EXPECTED_FB_PERSONAS:
            self.assertIn(persona, FB_PERSONAS, f"Missing FB persona: {persona}")

    def test_no_extra_fb_personas(self):
        """No unexpected FB personas are present."""
        actual = set(FB_PERSONAS.keys())
        extra = actual - EXPECTED_FB_PERSONAS
        self.assertEqual(extra, set(), f"Unexpected FB personas: {extra}")

    def test_every_fb_persona_has_system_prompt(self):
        """Every FB persona has a non-empty systemPrompt."""
        for key, persona in FB_PERSONAS.items():
            self.assertIn("systemPrompt", persona, f"{key} missing systemPrompt")
            self.assertTrue(
                len(persona["systemPrompt"].strip()) > 50,
                f"{key} systemPrompt is too short",
            )

    def test_every_fb_persona_has_label(self):
        """Every FB persona has a non-empty label."""
        for key, persona in FB_PERSONAS.items():
            self.assertIn("label", persona, f"{key} missing label")
            self.assertTrue(len(persona["label"]) > 0, f"{key} label is empty")

    def test_borak_kawan_label(self):
        """borak_kawan must have the correct LUMA-specified label."""
        self.assertIn("borak_kawan", FB_PERSONAS)
        self.assertIn("Borak Kawan", FB_PERSONAS["borak_kawan"]["label"])

    def test_borak_kawan_word_limit_in_prompt(self):
        """borak_kawan systemPrompt must mention 50-120 word limit per LUMA spec."""
        prompt = FB_PERSONAS["borak_kawan"]["systemPrompt"]
        self.assertIn("50", prompt)
        self.assertIn("120", prompt)

    def test_build_facebook_prompt_all_personas(self):
        """build_facebook_prompt succeeds for every expected persona."""
        for persona in EXPECTED_FB_PERSONAS:
            sys_p, usr_p = build_facebook_prompt(
                style=persona, raw_content="Test article content."
            )
            self.assertTrue(len(sys_p) > 0, f"{persona} system_prompt is empty")
            self.assertTrue(len(usr_p) > 0, f"{persona} user_prompt is empty")

    def test_fb_hashtags_exist_for_all_personas(self):
        """Every FB persona has hashtag entries in SAKLUMA_HASHTAGS."""
        for persona in EXPECTED_FB_PERSONAS:
            self.assertIn(
                persona, SAKLUMA_HASHTAGS,
                f"Missing short alias hashtag for {persona}",
            )
            self.assertIn(
                f"fb_{persona}", SAKLUMA_HASHTAGS,
                f"Missing fb_ prefixed hashtag for {persona}",
            )


class TestThreadCountParity(unittest.TestCase):
    """Thread counts must match the spec: 1, 3, 5, 8."""

    def test_all_thread_counts_exist(self):
        """Every expected thread count key exists."""
        for count in EXPECTED_THREAD_COUNTS:
            self.assertIn(count, THREAD_COUNTS, f"Missing thread count: {count}")

    def test_no_extra_thread_counts(self):
        """No unexpected thread counts are present."""
        actual = set(THREAD_COUNTS.keys())
        extra = actual - EXPECTED_THREAD_COUNTS
        self.assertEqual(extra, set(), f"Unexpected thread counts: {extra}")


class TestThreadsStyleParity(unittest.TestCase):
    """Threads/X styles must match: genz, informative, kepoh, catchy, hook_memanggil."""

    def test_all_threads_styles_exist(self):
        """Every expected style key exists in THREADS_STYLES."""
        for style in EXPECTED_THREADS_STYLES:
            self.assertIn(style, THREADS_STYLES, f"Missing threads style: {style}")

    def test_no_extra_threads_styles(self):
        """No unexpected styles are present."""
        actual = set(THREADS_STYLES.keys())
        extra = actual - EXPECTED_THREADS_STYLES
        self.assertEqual(extra, set(), f"Unexpected threads styles: {extra}")

    def test_build_threads_prompt_all_combos(self):
        """build_threads_prompt succeeds for every count × style combo."""
        for count in EXPECTED_THREAD_COUNTS:
            for style in EXPECTED_THREADS_STYLES:
                sys_p, usr_p = build_threads_prompt(
                    style=style, count=count, raw_content="Test content."
                )
                self.assertTrue(len(sys_p) > 0)
                self.assertTrue(len(usr_p) > 0)

    def test_build_x_prompt_all_combos(self):
        """build_x_prompt succeeds for every count × style combo."""
        for count in EXPECTED_THREAD_COUNTS:
            for style in EXPECTED_THREADS_STYLES:
                sys_p, usr_p = build_x_prompt(
                    style=style, count=count, raw_content="Test content."
                )
                self.assertTrue(len(sys_p) > 0)
                self.assertTrue(len(usr_p) > 0)


class TestRegistryBuildPrompt(unittest.TestCase):
    """Test the top-level build_prompt registry."""

    def test_build_prompt_facebook(self):
        sys_p, usr_p = build_prompt(platform="facebook", style="borak_kawan", raw="Test")
        self.assertIn("BORAK KAWAN", sys_p)

    def test_build_prompt_threads(self):
        sys_p, usr_p = build_prompt(platform="threads", style="genz", count="3", raw="Test")
        self.assertIn("GEN Z", sys_p)

    def test_build_prompt_x(self):
        sys_p, usr_p = build_prompt(platform="x", style="kepoh", count="1", raw="Test")
        self.assertIn("KEPOH", sys_p)

    def test_build_prompt_lemon8(self):
        sys_p, usr_p = build_prompt(platform="lemon8", raw="Test")
        self.assertIn("Lemon8", sys_p)

    def test_build_prompt_invalid_platform(self):
        with self.assertRaises(KeyError):
            build_prompt(platform="tiktok", raw="Test")


if __name__ == "__main__":
    unittest.main()
