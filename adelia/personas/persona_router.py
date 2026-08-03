"""
Persona Router — Zero-shot persona suggestion for Facebook content.

Uses HFClient.zero_shot (bart-large-mnli) to classify article text against
a fixed set of FB persona labels. The result is ADVISORY only — it populates
PlatformDraft.suggested_persona, but the user's explicit fb_style always
takes priority if provided.

If USE_HF_INFERENCE is disabled, returns None (never blocks).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from adelia.inference.exceptions import HFDisabled

logger = logging.getLogger(__name__)

# ── FB Persona Labels ──────────────────────────────────────────────────
# These map to the writing styles in AuraOne's draft pipeline.

FB_PERSONA_LABELS: list[str] = [
    "berita",            # straight news / factual reporting
    "pemerhati",         # observer / analytical commentary
    "kedai_kopi",        # casual café talk style
    "viral_santai",      # viral / laid-back / meme-adjacent
    "makcik_bawang",     # gossip / community storytelling
    "kisah_inspirasi",   # inspirational / motivational
    "borak_kawan",       # friend-to-friend conversational
]


# ── Result ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PersonaSuggestion:
    """Advisory persona recommendation from zero-shot classification."""

    persona: str
    """Top-scoring persona label."""

    confidence: float
    """Classification confidence score (0.0–1.0)."""


# ── Router ─────────────────────────────────────────────────────────────


def suggest_fb_persona(
    article_text: str,
    hf_client,
    labels: list[str] | None = None,
) -> PersonaSuggestion | None:
    """Suggest the best FB persona for the given article text.

    Args:
        article_text: The source article / master content.
        hf_client: An HFClient instance (or any object with a
                   ``zero_shot(text, labels)`` method).
        labels: Override the default persona label set. Defaults to
                ``FB_PERSONA_LABELS``.

    Returns:
        A PersonaSuggestion with the top label and confidence,
        or None if HF inference is disabled.
    """
    if labels is None:
        labels = FB_PERSONA_LABELS

    try:
        result = hf_client.zero_shot(article_text, labels)
    except HFDisabled:
        logger.info("HF disabled — persona routing skipped.")
        return None

    # result shape: {"sequence": ..., "labels": [...], "scores": [...]}
    top_label = result["labels"][0]
    top_score = result["scores"][0]

    suggestion = PersonaSuggestion(persona=top_label, confidence=round(top_score, 4))

    logger.info(
        "Persona suggestion: %s (%.2f%%) for: %.80s…",
        suggestion.persona,
        suggestion.confidence * 100,
        article_text,
    )

    return suggestion


class PersonaRouter:
    """Class wrapper for zero-shot persona routing using an HFClient."""

    def __init__(self, hf_client=None) -> None:
        self.hf_client = hf_client

    def suggest_fb_persona(
        self,
        article_text: str,
        labels: list[str] | None = None,
    ) -> PersonaSuggestion | None:
        """Suggest the best FB persona using the injected HFClient."""
        if self.hf_client is None:
            return None
        return suggest_fb_persona(article_text, self.hf_client, labels=labels)

