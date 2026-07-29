"""
ADELIA Data Contracts — Pure Pydantic models, zero Telegram dependencies.

These schemas define the API boundary between AURA (Telegram router) and
ADELIA (content generation microservice). AURA resolves all Telegram
file_ids → public CDN URLs before calling ADELIA; ADELIA never sees
a file_id or telegram.Update object.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Request: content generation ────────────────────────────────────────

class ContentRequest(BaseModel):
    """Inbound request from AURA to generate platform-specific drafts."""

    master_article: str = Field(
        ...,
        description="Raw scraped/summarised article text that serves as the source material.",
    )
    platforms: list[str] = Field(
        ...,
        description="Target platforms, e.g. ['facebook', 'x_thread', 'instagram'].",
    )
    fb_style: str | None = Field(
        default=None,
        description="Optional Facebook writing-style override (e.g. 'storytelling', 'listicle').",
    )
    thread_style: str | None = Field(
        default=None,
        description="Optional X/Twitter thread style (e.g. 'punchy', 'educational').",
    )
    thread_length: int | None = Field(
        default=None,
        ge=1,
        description="Max number of posts in an X thread. None = let ADELIA decide.",
    )
    image_url: str | None = Field(
        default=None,
        description=(
            "Resolved public / Telegram-CDN image URL passed BY AURA. "
            "ADELIA never handles raw file_id values."
        ),
    )
    hashtags_on: bool = Field(
        default=True,
        description="Whether to include hashtags in generated captions.",
    )
    brand: str = Field(
        default="Sakluma",
        description="Brand identity to apply across all generated content.",
    )
    auto_persona: bool = Field(
        default=False,
        description=(
            "If True, ADELIA runs zero-shot persona routing (bart-large-mnli) "
            "to pick the best persona automatically."
        ),
    )


# ── Response: generated drafts ─────────────────────────────────────────

class PlatformDraft(BaseModel):
    """A single platform-specific draft produced by ADELIA."""

    platform: str = Field(
        ...,
        description="Target platform identifier, e.g. 'facebook', 'x_thread'.",
    )
    caption: str = Field(
        ...,
        description="Generated caption / post body for the platform.",
    )
    thread_posts: list[str] | None = Field(
        default=None,
        description="Ordered list of thread posts (X threads only). None for single-post platforms.",
    )
    image_url: str | None = Field(
        default=None,
        description="Image URL to attach (passed through or generated via FLUX fallback).",
    )
    suggested_persona: str | None = Field(
        default=None,
        description="Persona selected by zero-shot routing, if auto_persona was enabled.",
    )
    dedup_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Semantic similarity score against memory (bge-m3). "
            "High values (>0.85) signal potential duplicate content."
        ),
    )


class ContentResponse(BaseModel):
    """Outbound response from ADELIA back to AURA after content generation."""

    status: str = Field(
        ...,
        description="Result status: 'ok', 'partial', or 'error'.",
    )
    drafts: list[PlatformDraft] = Field(
        default_factory=list,
        description="Generated drafts, one per requested platform.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (e.g. dedup alerts, persona fallback notices).",
    )


# ── Request/Response: publishing ───────────────────────────────────────

class PublishRequest(BaseModel):
    """Request from AURA to publish a finalised draft via ADELIA's publisher."""

    draft: PlatformDraft = Field(
        ...,
        description="The approved PlatformDraft to publish.",
    )
    content_type: str = Field(
        default="Post",
        description="Airtable content-type tag, e.g. 'Post', 'Thread', 'Story'.",
    )
    extra_fields: dict = Field(
        default_factory=dict,
        description="Additional key-value pairs to write to the Airtable record.",
    )


class PublishResponse(BaseModel):
    """Response after a publish attempt."""

    status: str = Field(
        ...,
        description="Result status: 'published', 'queued', or 'error'.",
    )
    record_id: str | None = Field(
        default=None,
        description="Airtable record ID on success.",
    )
    error: str | None = Field(
        default=None,
        description="Error message on failure.",
    )


# ── Memory: vector search results ─────────────────────────────────────

class MemoryHit(BaseModel):
    """A single result from the semantic memory (sqlite-vec) search."""

    text: str = Field(
        ...,
        description="The stored text chunk that matched the query.",
    )
    similarity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score from bge-m3 embeddings.",
    )
    source_url: str | None = Field(
        default=None,
        description="Original source URL the text was scraped from, if available.",
    )
    created_at: str = Field(
        ...,
        description="ISO-8601 timestamp of when this memory was stored.",
    )
