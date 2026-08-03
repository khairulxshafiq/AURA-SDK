"""
ContentMemory — High-level semantic memory layer for ADELIA.

Composes HFClient (embedding) + ContentVectorStore (persistence) into a
simple remember / recall / dedup API. Gracefully degrades when HF Inference
is disabled: recall returns empty, dedup always greenlights.
"""

from __future__ import annotations

import logging

from adelia.inference.exceptions import HFDisabled
from adelia.memory.vector_store import ContentVectorStore
from adelia.schemas.models import MemoryHit

logger = logging.getLogger(__name__)


class ContentMemory:
    """Semantic content memory backed by HF embeddings + sqlite-vec.

    Args:
        hf: HFClient instance for generating embeddings.
        store: ContentVectorStore instance for persistence and search.
    """

    def __init__(self, hf: HFClient, store: ContentVectorStore) -> None:
        self._hf = hf
        self._store = store

    # ── Public API ─────────────────────────────────────────────────────

    def remember(self, text: str, metadata: dict | None = None) -> int | None:
        """Embed and store a text chunk in semantic memory.

        Args:
            text: The content to remember.
            metadata: Optional dict with keys ``source_url``, ``platform``.

        Returns:
            Row ID on success, or None if HF is disabled.
        """
        try:
            vectors = self._hf.embed([text])
        except HFDisabled:
            logger.info("HF disabled — skipping memory storage for: %.60s…", text)
            return None

        embedding = vectors[0]
        row_id = self._store.add(text, embedding, metadata or {})
        logger.debug("Stored memory row %d (%.60s…)", row_id, text)
        return row_id

    def recall(self, query_text: str, k: int = 5) -> list[MemoryHit]:
        """Find the k most similar stored memories to the query.

        Args:
            query_text: Natural-language search query.
            k: Number of results to return.

        Returns:
            List of MemoryHit sorted by similarity (descending).
            Empty list if HF is disabled.
        """
        try:
            vectors = self._hf.embed([query_text])
        except HFDisabled:
            logger.info("HF disabled — recall returning empty for: %.60s…", query_text)
            return []

        return self._store.search(vectors[0], k=k)

    def dedup_check(
        self,
        candidate_text: str,
        threshold: float = 0.92,
    ) -> tuple[bool, MemoryHit | None]:
        """Check if candidate content is too similar to existing memories.

        Args:
            candidate_text: The new content to check.
            threshold: Similarity score above which content is flagged
                       as duplicate (0.0–1.0). Default 0.92.

        Returns:
            Tuple of (is_duplicate, closest_hit).
            - ``(True, MemoryHit)`` if the closest match exceeds threshold.
            - ``(False, MemoryHit)`` if matches exist but below threshold.
            - ``(False, None)`` if no matches found or HF is disabled.
        """
        try:
            vectors = self._hf.embed([candidate_text])
        except HFDisabled:
            logger.info(
                "HF disabled — dedup greenlit (no blocking) for: %.60s…",
                candidate_text,
            )
            return False, None

        hits = self._store.search(vectors[0], k=1)

        if not hits:
            return False, None

        closest = hits[0]
        is_duplicate = closest.similarity >= threshold

        if is_duplicate:
            logger.warning(
                "Dedup FLAGGED (%.4f >= %.2f): %.60s…",
                closest.similarity,
                threshold,
                candidate_text,
            )
        else:
            logger.debug(
                "Dedup passed (%.4f < %.2f): %.60s…",
                closest.similarity,
                threshold,
                candidate_text,
            )

        return is_duplicate, closest
