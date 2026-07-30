"""
ADELIA Service Client — HTTP Client for ADELIA Content Engine Microservice.

Provides async & sync helper functions for communicating with ADELIA service
at http://adelia-app:8001 (or ADELIA_SERVICE_URL).

Critical Guardrail:
AURA MUST resolve Telegram file_id -> public Telegram CDN URL using stage_image_telegram FIRST,
and pass ONLY the resolved public image_url to ADELIA. ADELIA never touches file_id.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from config import ADELIA_SERVICE_URL

logger = logging.getLogger("aura.tools.adelia_client")

_DEFAULT_TIMEOUT = 60.0


# ── Typed Exceptions ──────────────────────────────────────────────────


class AdeliaServiceError(Exception):
    """Base exception for ADELIA microservice errors."""


class AdeliaConnectionError(AdeliaServiceError):
    """Raised when connection to ADELIA service fails or times out."""


class AdeliaResponseError(AdeliaServiceError):
    """Raised when ADELIA returns a non-200 or error status response."""


# ── Helper ─────────────────────────────────────────────────────────────


def _get_base_url() -> str:
    url = os.getenv("ADELIA_SERVICE_URL", ADELIA_SERVICE_URL) or "http://adelia-app:8001"
    return url.rstrip("/")


# ── Core Client Functions ──────────────────────────────────────────────


async def generate_master(
    scraped_text: str,
    title: str = "Artikel Berita",
    source_url: str = "",
    image_url: str = "",
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call ADELIA POST /api/v1/generate-master to create a neutral Master Article."""
    url = f"{_get_base_url()}/api/v1/generate-master"
    payload = {
        "scraped_text": scraped_text,
        "title": title,
        "source_url": source_url,
        "image_url": image_url or "",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise AdeliaResponseError(
                    f"ADELIA generate-master error (HTTP {resp.status_code}): {resp.text}"
                )
            return resp.json()
    except httpx.RequestError as exc:
        raise AdeliaConnectionError(f"Failed to connect to ADELIA at {url}: {exc}") from exc


async def generate_content(
    master_article: str,
    platforms: list[str],
    fb_style: str | None = None,
    thread_style: str | None = None,
    thread_length: int | None = None,
    image_url: str | None = None,
    hashtags_on: bool = True,
    brand: str = "Sakluma",
    auto_persona: bool = False,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call ADELIA POST /api/v1/generate-content to generate social media drafts.

    CRITICAL: image_url MUST be a resolved public / Telegram CDN URL.
    Never pass a raw Telegram file_id.
    """
    url = f"{_get_base_url()}/api/v1/generate-content"
    payload = {
        "master_article": master_article,
        "platforms": platforms,
        "fb_style": fb_style,
        "thread_style": thread_style,
        "thread_length": thread_length,
        "image_url": image_url,
        "hashtags_on": hashtags_on,
        "brand": brand,
        "auto_persona": auto_persona,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise AdeliaResponseError(
                    f"ADELIA generate-content error (HTTP {resp.status_code}): {resp.text}"
                )
            return resp.json()
    except httpx.RequestError as exc:
        raise AdeliaConnectionError(f"Failed to connect to ADELIA at {url}: {exc}") from exc


async def publish(
    draft: dict[str, Any],
    content_type: str = "Post",
    extra_fields: dict[str, Any] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call ADELIA POST /api/v1/publish to push a draft to Airtable & Drive."""
    url = f"{_get_base_url()}/api/v1/publish"
    payload = {
        "draft": draft,
        "content_type": content_type,
        "extra_fields": extra_fields or {},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise AdeliaResponseError(
                    f"ADELIA publish error (HTTP {resp.status_code}): {resp.text}"
                )
            return resp.json()
    except httpx.RequestError as exc:
        raise AdeliaConnectionError(f"Failed to connect to ADELIA at {url}: {exc}") from exc


async def recall(
    query_text: str,
    k: int = 5,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Call ADELIA POST /api/v1/recall for semantic memory search."""
    url = f"{_get_base_url()}/api/v1/recall"
    payload = {
        "query_text": query_text,
        "k": k,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise AdeliaResponseError(
                    f"ADELIA recall error (HTTP {resp.status_code}): {resp.text}"
                )
            return resp.json()
    except httpx.RequestError as exc:
        raise AdeliaConnectionError(f"Failed to connect to ADELIA at {url}: {exc}") from exc
