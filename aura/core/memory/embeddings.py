"""Local CPU Embedding Engine for AuraOne (paraphrase-multilingual-MiniLM-L12-v2)."""

from __future__ import annotations

import logging
from typing import Sequence
import structlog

logger = structlog.get_logger("aura.core.memory.embeddings")

# Default lightweight multilingual model (384-dimensional, ~220 MB RAM)
DEFAULT_EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBED_DIM = 384


class LocalEmbeddingEngine:
    """Computes dense vector embeddings locally on CPU using fastembed or fallback."""

    def __init__(self, model_name: str = DEFAULT_EMBED_MODEL) -> None:
        self.model_name = model_name
        self.dimension = DEFAULT_EMBED_DIM
        self._model = None
        self._initialized = False

    def _lazy_init(self) -> None:
        if self._initialized:
            return
        try:
            from fastembed import TextEmbedding

            logger.info("Initializing fastembed local model", model=self.model_name)
            self._model = TextEmbedding(model_name=self.model_name)
            self._initialized = True
        except (ImportError, Exception) as exc:
            logger.warning(
                "fastembed unavailable or failed to load model. Operating in fallback mode",
                error=str(exc),
            )
            self._initialized = True

    def embed_text(self, text: str) -> list[float]:
        """Generate float vector embedding for a single text string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate float vector embeddings for a list of text strings."""
        self._lazy_init()
        if self._model is not None:
            try:
                embeddings = list(self._model.embed(texts))
                return [vec.tolist() for vec in embeddings]
            except Exception as exc:
                logger.error("fastembed generation failed", error=str(exc))

        # Pure Python fallback embedding (dummy normalized vector for offline testing)
        logger.warning("Using offline mock embedding vector fallback")
        dummy_vec = [0.01] * self.dimension
        return [dummy_vec for _ in texts]


# Global singleton instance
embeddings_engine = LocalEmbeddingEngine()
