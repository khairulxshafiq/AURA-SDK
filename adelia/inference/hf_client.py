"""
HFClient — Thin wrapper over huggingface_hub.InferenceClient (serverless).

All inference runs on Hugging Face's hosted infrastructure via the Inference
API. NO local models, NO torch, NO transformers imported.

Env vars consumed:
    HF_TOKEN             – Hugging Face API token (required if USE_HF_INFERENCE=true)
    USE_HF_INFERENCE     – Global kill-switch ("true" to enable, default "false")
    HF_EMBED_MODEL       – Embedding model   (default: BAAI/bge-m3)
    HF_ZEROSHOT_MODEL    – Zero-shot model    (default: facebook/bart-large-mnli)
    HF_IMAGE_MODEL       – Image-gen model    (default: black-forest-labs/FLUX.1-schnell)
    HF_IMAGE_PROVIDER    – Routed provider    (default: hf-inference)
    HF_TIMEOUT           – Request timeout    (default: 60 seconds)
"""

from __future__ import annotations

import logging
import os
import time

from huggingface_hub import InferenceClient
from huggingface_hub.utils import HfHubHTTPError

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────

_DEFAULT_EMBED_MODEL = "BAAI/bge-m3"
_DEFAULT_ZEROSHOT_MODEL = "facebook/bart-large-mnli"
_DEFAULT_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
_DEFAULT_IMAGE_PROVIDER = "hf-inference"
_DEFAULT_TIMEOUT = 60
_MAX_RETRIES = 1


# ── Typed exceptions ──────────────────────────────────────────────────


class HFDisabled(RuntimeError):
    """Raised when USE_HF_INFERENCE is false — callers should fall back."""


class HFCreditsExhausted(RuntimeError):
    """Raised on HTTP 402 — inference credits depleted."""


class HFTokenForbidden(PermissionError):
    """Raised on HTTP 403 — token lacks required permissions."""


class HFInferenceError(RuntimeError):
    """Generic wrapper for unexpected HF Inference API errors."""


# ── Client ─────────────────────────────────────────────────────────────


class HFClient:
    """Serverless HF Inference client with retry, timeout, and kill-switch.

    Usage::

        client = HFClient()                       # reads env vars
        vecs   = client.embed(["hello world"])     # -> list[list[float]]
        result = client.zero_shot("text", ["a"])   # -> dict
        img    = client.generate_image("a cat")    # -> bytes (PNG)
    """

    def __init__(self) -> None:
        self._enabled = os.getenv("USE_HF_INFERENCE", "false").lower() == "true"

        self._token: str | None = os.getenv("HF_TOKEN")
        self._embed_model = os.getenv("HF_EMBED_MODEL", _DEFAULT_EMBED_MODEL)
        self._zeroshot_model = os.getenv("HF_ZEROSHOT_MODEL", _DEFAULT_ZEROSHOT_MODEL)
        self._image_model = os.getenv("HF_IMAGE_MODEL", _DEFAULT_IMAGE_MODEL)
        self._image_provider = os.getenv("HF_IMAGE_PROVIDER", _DEFAULT_IMAGE_PROVIDER)
        self._timeout = int(os.getenv("HF_TIMEOUT", str(_DEFAULT_TIMEOUT)))

        # Lazy-init: client is only created on first real call
        self._client: InferenceClient | None = None

    # ── Internal helpers ───────────────────────────────────────────────

    def _ensure_enabled(self) -> None:
        """Gate-check: raise HFDisabled if the global flag is off."""
        if not self._enabled:
            raise HFDisabled(
                "HF Inference is disabled (USE_HF_INFERENCE != 'true'). "
                "Caller should fall back to an alternative path."
            )

    def _get_client(self) -> InferenceClient:
        """Return (and lazily create) the underlying InferenceClient."""
        if self._client is None:
            self._client = InferenceClient(
                token=self._token,
                timeout=self._timeout,
            )
        return self._client

    @staticmethod
    def _classify_http_error(exc: HfHubHTTPError) -> None:
        """Re-raise as a typed exception based on HTTP status code."""
        status = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None

        if status == 402:
            raise HFCreditsExhausted(
                f"HF Inference API credits exhausted (402): {exc}"
            ) from exc
        if status == 403:
            raise HFTokenForbidden(
                f"HF token lacks required permissions (403): {exc}"
            ) from exc

        # Unknown HTTP error — wrap generically
        raise HFInferenceError(
            f"HF Inference API error (HTTP {status}): {exc}"
        ) from exc

    def _call_with_retry(self, fn, *args, **kwargs):
        """Execute *fn* with a single retry on transient failures.

        Re-raises typed errors (402, 403, HFDisabled) immediately — those
        are NOT retried.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except HfHubHTTPError as exc:
                status = (
                    getattr(exc.response, "status_code", None)
                    if hasattr(exc, "response")
                    else None
                )
                # Non-retryable status codes → raise immediately
                if status in (402, 403):
                    self._classify_http_error(exc)

                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(
                        "HF call failed (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
            except (TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(
                        "HF call timed out (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        wait,
                        exc,
                    )
                    time.sleep(wait)

        # Exhausted retries
        if isinstance(last_exc, HfHubHTTPError):
            self._classify_http_error(last_exc)
        raise HFInferenceError(f"HF call failed after {_MAX_RETRIES + 1} attempts: {last_exc}") from last_exc

    # ── Public API ─────────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via the HF Inference API (feature-extraction).

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input text).

        Raises:
            HFDisabled: If USE_HF_INFERENCE is false.
            HFCreditsExhausted: On HTTP 402.
            HFTokenForbidden: On HTTP 403.
            HFInferenceError: On other failures after retry.
        """
        self._ensure_enabled()
        client = self._get_client()

        results: list[list[float]] = []
        for text in texts:
            raw = self._call_with_retry(
                client.feature_extraction,
                text,
                model=self._embed_model,
            )

            # feature_extraction returns nested lists — normalise to list[float]
            vec = raw
            # Handle numpy arrays if returned
            if hasattr(vec, "tolist"):
                vec = vec.tolist()
            # Flatten if wrapped in extra dimension, e.g. [[...]] for single text
            while isinstance(vec, list) and len(vec) == 1 and isinstance(vec[0], list):
                vec = vec[0]

            results.append(vec)

        logger.debug("Embedded %d texts via %s", len(texts), self._embed_model)
        return results

    def zero_shot(self, text: str, labels: list[str]) -> dict:
        """Run zero-shot classification via the HF Inference API.

        Args:
            text: The input text to classify.
            labels: Candidate labels.

        Returns:
            Dict with keys 'sequence', 'labels', 'scores' (sorted by score desc).

        Raises:
            HFDisabled: If USE_HF_INFERENCE is false.
            HFCreditsExhausted: On HTTP 402.
            HFTokenForbidden: On HTTP 403.
            HFInferenceError: On other failures after retry.
        """
        self._ensure_enabled()
        client = self._get_client()

        result = self._call_with_retry(
            client.zero_shot_classification,
            text,
            labels=labels,
            model=self._zeroshot_model,
        )

        # InferenceClient returns a list of dicts [{label, score}, ...] sorted desc
        # Normalise to the canonical {sequence, labels, scores} shape
        if isinstance(result, list):
            return {
                "sequence": text,
                "labels": [r["label"] for r in result],
                "scores": [r["score"] for r in result],
            }

        # Already dict-shaped (older API format)
        return result

    def generate_image(self, prompt: str) -> bytes:
        """Generate an image via the HF Inference API (text-to-image).

        Args:
            prompt: Text description of the desired image.

        Returns:
            Raw image bytes (PNG).

        Raises:
            HFDisabled: If USE_HF_INFERENCE is false.
            HFCreditsExhausted: On HTTP 402.
            HFTokenForbidden: On HTTP 403.
            HFInferenceError: On other failures after retry.
        """
        self._ensure_enabled()
        client = self._get_client()

        image = self._call_with_retry(
            client.text_to_image,
            prompt,
            model=self._image_model,
            provider=self._image_provider,
        )

        # text_to_image returns a PIL Image — convert to PNG bytes
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
