"""
ADELIA Inference Exceptions — importable without huggingface_hub.

These typed exceptions are defined separately so that modules like
ContentMemory can import and catch them without triggering a transitive
import of huggingface_hub (which may not be installed in all environments).
"""

from __future__ import annotations


class HFDisabled(RuntimeError):
    """Raised when USE_HF_INFERENCE is false — callers should fall back."""


class HFCreditsExhausted(RuntimeError):
    """Raised on HTTP 402 — inference credits depleted."""


class HFTokenForbidden(PermissionError):
    """Raised on HTTP 403 — token lacks required permissions."""


class HFInferenceError(RuntimeError):
    """Generic wrapper for unexpected HF Inference API errors."""
