"""
ADELIA LLM Caller — Gemini primary + OpenRouter fallback.

Replicates AuraOne's llm_caller pattern (key rotation, cooldown, timeout)
but is fully self-contained. Zero imports from AuraOne.

Env vars consumed:
    GEMINI_API_KEY       – Primary Gemini key
    GEMINI_API_KEY_1..10 – Additional rotation keys
    GEMINI_MODEL         – Model name (default: gemini-2.5-flash)
    GEMINI_TIMEOUT       – Per-key timeout in seconds (default: 6)
    GEMINI_COOLDOWN      – Cooldown duration in seconds (default: 600)
    OPENROUTER_API_KEY   – Fallback API key (optional)
    OPENROUTER_FALLBACK_MODEL – Fallback model (default: google/gemini-2.5-flash)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger("adelia.llm.llm_caller")

# ── Configuration (env-injected, no config.py import) ──────────────────

_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "6"))
_COOLDOWN_SECS = float(os.getenv("GEMINI_COOLDOWN", "600"))
_OPENROUTER_TIMEOUT = 15.0
_DEFAULT_OR_MODEL = "google/gemini-2.5-flash"


def _load_gemini_keys() -> list[str]:
    """Load Gemini API keys from env vars (GEMINI_API_KEY, GEMINI_API_KEY_1..10)."""
    keys: list[str] = []
    main_key = os.getenv("GEMINI_API_KEY", "")
    if main_key:
        keys.append(main_key)
    for i in range(1, 11):
        val = os.getenv(f"GEMINI_API_KEY_{i}", "")
        if val and val not in keys:
            keys.append(val)
    return keys


# ── In-memory cooldown tracker (no SQLite dependency) ──────────────────

_cooldown_expiry: dict[str, float] = {}


def set_key_cooldown(api_key: str, duration: float = _COOLDOWN_SECS) -> None:
    """Place an API key on cooldown for *duration* seconds."""
    _cooldown_expiry[api_key] = time.time() + duration
    logger.info(
        "Key %s… placed on %.0fs cooldown.",
        api_key[:8],
        duration,
    )


def is_key_on_cooldown(api_key: str) -> bool:
    """Check if an API key is currently on cooldown."""
    expiry = _cooldown_expiry.get(api_key, 0.0)
    return expiry > time.time()


def clear_cooldowns() -> None:
    """Clear all cooldown state (useful for testing)."""
    _cooldown_expiry.clear()


# ── Shared rotation index ─────────────────────────────────────────────

_current_key_idx: int = 0


# ── Core LLM caller ───────────────────────────────────────────────────


async def call_llm(
    prompt: str,
    timeout: float | None = None,
    openrouter_messages: list[dict] | None = None,
) -> str:
    """Unified Gemini + OpenRouter LLM caller with key rotation and cooldown.

    Args:
        prompt: The full prompt text sent to Gemini.
        timeout: Timeout in seconds per key attempt. Defaults to GEMINI_TIMEOUT.
        openrouter_messages: Explicit message list for OpenRouter fallback.
            If None, defaults to [{"role": "user", "content": prompt}].

    Returns:
        Generated text, or empty string if all attempts fail.
    """
    global _current_key_idx

    if timeout is None:
        timeout = _GEMINI_TIMEOUT

    keys = _load_gemini_keys()
    if not keys:
        logger.warning("No GEMINI_API_KEY configured — jumping to OpenRouter fallback.")
        return await _openrouter_fallback(prompt, openrouter_messages)

    num_keys = len(keys)

    # ── Gemini key rotation loop ───────────────────────────────────────

    for _attempt in range(num_keys):
        active_key = keys[_current_key_idx % num_keys]

        if is_key_on_cooldown(active_key):
            _current_key_idx = (_current_key_idx + 1) % num_keys
            continue

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_sync_gemini_call, active_key, prompt),
                timeout=timeout,
            )
            if text:
                return text
        except asyncio.TimeoutError:
            logger.warning(
                "Gemini key #%d timed out after %.1fs, placing on cooldown.",
                _current_key_idx + 1,
                timeout,
            )
            set_key_cooldown(active_key)
            _current_key_idx = (_current_key_idx + 1) % num_keys
            continue
        except Exception as err:
            logger.warning("Gemini key #%d failed: %s", _current_key_idx + 1, err)
            if "429" in str(err) or "quota" in str(err).lower():
                set_key_cooldown(active_key)
            _current_key_idx = (_current_key_idx + 1) % num_keys
            continue

    # ── OpenRouter fallback ────────────────────────────────────────────

    return await _openrouter_fallback(prompt, openrouter_messages)


def _sync_gemini_call(api_key: str, prompt: str) -> str:
    """Synchronous Gemini call (runs in thread via asyncio.to_thread)."""
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=prompt,
    )
    return response.text if response and response.text else ""


async def _openrouter_fallback(
    prompt: str,
    openrouter_messages: list[dict] | None = None,
) -> str:
    """OpenRouter fallback when all Gemini keys are exhausted."""
    # Read at call time so test patches (os.environ / patch.dict) take effect
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    or_model = os.getenv("OPENROUTER_FALLBACK_MODEL", _DEFAULT_OR_MODEL)

    if not or_key:
        logger.error("All Gemini keys exhausted and no OPENROUTER_API_KEY configured.")
        return ""

    logger.info(
        "All Gemini keys in cooldown/failed. Using OpenRouter fallback (%s).",
        or_model,
    )

    headers = {
        "Authorization": f"Bearer {or_key}",
        "Content-Type": "application/json",
    }
    messages = openrouter_messages or [{"role": "user", "content": prompt}]
    payload = {
        "model": or_model,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=_OPENROUTER_TIMEOUT) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if r.status_code == 200:
                data = r.json()
                return data["choices"][0]["message"]["content"]
            else:
                logger.error("OpenRouter error (%d): %.200s", r.status_code, r.text)
    except Exception as exc:
        logger.error("OpenRouter exception: %s", exc)

    return ""
