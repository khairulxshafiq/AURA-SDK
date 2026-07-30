"""
ADELIA Content Engine — FastAPI Server.

RESTful microservice for multi-platform content generation, zero-shot persona
routing, semantic memory (bge-m3 + sqlite-vec), and publishing.

Routes:
- POST /api/v1/generate-master  -> generate_master_article
- POST /api/v1/generate-content -> generate_platform_drafts
- POST /api/v1/publish          -> save_draft_to_airtable & save_thread_posts
- POST /api/v1/recall           -> memory.recall
- GET  /health                  -> system health & status report
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, status
except ImportError:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class _Status:
        HTTP_500_INTERNAL_SERVER_ERROR = 500

    status = _Status()

    class FastAPI:
        def __init__(self, **kwargs):
            self.routes = {}

        def get(self, path: str, **kwargs):
            def decorator(func):
                self.routes[("GET", path)] = func
                return func
            return decorator

        def post(self, path: str, **kwargs):
            def decorator(func):
                self.routes[("POST", path)] = func
                return func
            return decorator
from pydantic import BaseModel, Field

from adelia.core.master_article import generate_master_article
from adelia.core.social_engine import generate_platform_drafts
from adelia.inference.hf_client import HFClient
from adelia.memory.content_memory import ContentMemory
from adelia.memory.vector_store import ContentVectorStore
from adelia.personas.persona_router import PersonaRouter
from adelia.publishers.airtable_gdrive import (
    save_draft_to_airtable,
    save_thread_posts_to_airtable,
)
from adelia.schemas.models import (
    ContentRequest,
    ContentResponse,
    MemoryHit,
    PublishRequest,
    PublishResponse,
)

logger = logging.getLogger("adelia.main")

# ── App State Container ────────────────────────────────────────────────


class AppState:
    """Dependency-injection container for ADELIA services."""

    hf_client: HFClient
    vector_store: ContentVectorStore
    memory: ContentMemory
    persona_router: PersonaRouter


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise services on startup and clean up resources on shutdown."""
    logger.info("Initialising ADELIA Content Engine services...")

    state.hf_client = HFClient()
    state.vector_store = ContentVectorStore()
    state.memory = ContentMemory(hf=state.hf_client, store=state.vector_store)
    state.persona_router = PersonaRouter(hf_client=state.hf_client)

    logger.info(
        "ADELIA initialised (USE_HF_INFERENCE=%s, vec_enabled=%s)",
        state.hf_client._enabled,
        state.vector_store._vec_enabled,
    )
    yield
    logger.info("Shutting down ADELIA services...")
    state.vector_store.close()


app = FastAPI(
    title="ADELIA Content Engine",
    description="Autonomous Content Generation & Semantic Memory Microservice",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Additional Request Models ──────────────────────────────────────────


class MasterArticleRequest(BaseModel):
    """Inbound request for Master Article generation."""

    scraped_text: str = Field(..., description="Raw text extracted from web page.")
    title: str = Field(default="Artikel Berita", description="Article title.")
    source_url: str = Field(default="", description="Source URL.")
    image_url: str = Field(default="", description="Image URL if available.")


class RecallRequest(BaseModel):
    """Inbound request for semantic memory search."""

    query_text: str = Field(..., description="Natural language search query.")
    k: int = Field(default=5, ge=1, le=50, description="Number of results to return.")


# ── Routes ─────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health & status report endpoint."""
    use_hf = os.getenv("USE_HF_INFERENCE", "false").lower() == "true"
    hf_reachable = False
    if use_hf and hasattr(state, "hf_client"):
        try:
            # Quick non-blocking status check
            hf_reachable = state.hf_client._enabled
        except Exception:
            hf_reachable = False

    vec_enabled = getattr(state.vector_store, "_vec_enabled", False)
    db_path = str(getattr(state.vector_store, "_db_path", ""))

    return {
        "status": "ok",
        "service": "ADELIA Content Engine",
        "use_hf_inference": use_hf,
        "hf_reachability": hf_reachable,
        "sqlite_vec_enabled": vec_enabled,
        "vector_store_db": db_path,
    }


@app.post("/api/v1/generate-master")
async def api_generate_master(req: MasterArticleRequest) -> dict[str, Any]:
    """Generate a neutral Master Article from raw scraped text."""
    try:
        result = await generate_master_article(
            scraped_text=req.scraped_text,
            title=req.title,
            source_url=req.source_url,
            image_url=req.image_url,
        )
        return result
    except Exception as err:
        logger.error("Error in /api/v1/generate-master: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Master article generation failed: {err}",
        ) from err


@app.post("/api/v1/generate-content", response_model=ContentResponse)
async def api_generate_content(req: ContentRequest) -> ContentResponse:
    """Generate multi-platform social media drafts from a ContentRequest."""
    try:
        response = await generate_platform_drafts(
            req=req,
            memory=state.memory,
            router=state.persona_router,
        )
        return response
    except Exception as err:
        logger.error("Error in /api/v1/generate-content: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content generation failed: {err}",
        ) from err


@app.post("/api/v1/publish", response_model=PublishResponse)
async def api_publish(req: PublishRequest) -> PublishResponse:
    """Publish an approved draft to Airtable and Google Drive."""
    try:
        draft = req.draft
        extra = req.extra_fields or {}

        # 1. Publish main draft to Content Station table
        res = save_draft_to_airtable(
            title=extra.get("title", f"Draft {draft.platform.title()}"),
            caption=draft.caption,
            platform=draft.platform,
            image_url=draft.image_url or "",
            brand=extra.get("brand", "Sakluma"),
            status=extra.get("status", "Draft"),
            hashtags=extra.get("hashtags", ""),
            content_type=req.content_type,
            hf_client=state.hf_client,
        )

        if res.get("status") != "success":
            error_msg = res.get("error", "Airtable save failed")
            return PublishResponse(status="error", error=error_msg)

        record_id = res.get("record_id")

        # 2. Publish thread posts to Thread Posts table if present
        if record_id and draft.thread_posts and len(draft.thread_posts) > 1:
            thread_res = save_thread_posts_to_airtable(
                parent_record_id=record_id,
                posts=draft.thread_posts,
                platform=draft.platform,
            )
            if thread_res.get("status") != "success":
                logger.warning("Thread posts save warning: %s", thread_res.get("error"))

        return PublishResponse(status="published", record_id=record_id)
    except Exception as err:
        logger.error("Error in /api/v1/publish: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publishing failed: {err}",
        ) from err


@app.post("/api/v1/recall", response_model=list[MemoryHit])
async def api_recall(req: RecallRequest) -> list[MemoryHit]:
    """Perform semantic search against past stored content in memory."""
    try:
        hits = state.memory.recall(query_text=req.query_text, k=req.k)
        return hits
    except Exception as err:
        logger.error("Error in /api/v1/recall: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic recall failed: {err}",
        ) from err
