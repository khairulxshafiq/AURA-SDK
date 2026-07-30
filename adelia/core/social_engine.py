"""
ADELIA Core — Social Engine (Draft Generator & Memory Integrator).

Generates multi-platform social media drafts (Facebook, Threads, X, Lemon8)
from a ContentRequest using:
1. Zero-shot PersonaRouter (bart-large-mnli) if auto_persona=True.
2. Prompt Engine registry + LLM caller.
3. Pure text cleaning (stripping visual notes, intro fluff, thread index numbers, hashtag toggles).
4. ContentMemory dedup checking (bge-m3 cosine similarity).
5. Automatic memory storage (remember) for future recall.

Pure I/O logic — NO Telegram dependencies, NO database calls.
"""

from __future__ import annotations

import logging
import re

from adelia.inference.exceptions import HFDisabled
from adelia.llm.llm_caller import call_llm
from adelia.memory.content_memory import ContentMemory
from adelia.personas.persona_router import PersonaRouter, suggest_fb_persona
from adelia.prompts import build_prompt, enforce_fb_length_limits, sanitize_hashtags
from adelia.schemas.models import ContentRequest, ContentResponse, PlatformDraft

logger = logging.getLogger("adelia.core.social_engine")


def clean_draft_text(text: str, hashtags_on: bool = True) -> str:
    """Post-process and clean draft text output to guarantee pure caption content.

    Strips:
    - Visual/media notes: [Gambar: ...], (Visual: ...)
    - Conversational intro lines
    - Structural header labels: FACEBOOK POST:, THREADS POST:, etc.
    - Hashtags if hashtags_on is False
    """
    if not text:
        return ""

    # 1. Remove visual/GIF recommendations
    cleaned = re.sub(r"\[?(?:Gambar|Media|Visual|Cadangan GIF|GIF):\s*.*?\]?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\((?:Gambar|Media|Visual|Cadangan GIF|GIF):\s*.*?\)", "", cleaned, flags=re.IGNORECASE)

    # 2. Line-by-line header and conversational fluff removal
    lines = []
    for line in cleaned.split("\n"):
        line_strip = line.strip()
        # Skip intro conversational fluff lines
        if re.match(r"^(?:Baiklah|Tentu|Berikut|Ini|Semoga|Cadangan)\b.*", line_strip, re.IGNORECASE) and len(line_strip) < 70 and (
            "draf" in line_strip.lower() or "hantaran" in line_strip.lower() or "berikut" in line_strip.lower()
        ):
            continue
        # Strip structural prefixes
        line_clean = re.sub(
            r"^(?:FACEBOOK POST|FB POST|THREADS POST|X POST|TWITTER POST|LEMON8 POST|KAPSYEN|TAJUK|TITLE|POST):\s*",
            "",
            line,
            flags=re.IGNORECASE,
        )
        lines.append(line_clean)

    cleaned_text = "\n".join(lines).strip()
    cleaned_text = sanitize_hashtags(cleaned_text)

    # 3. Strip hashtags if disabled by request
    if not hashtags_on:
        cleaned_text = re.sub(r"#\w+", "", cleaned_text)
        cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text).strip()

    return cleaned_text.strip()


def parse_thread_posts(draft_text: str) -> list[str]:
    """Split multi-post thread draft by '---' and clean individual post items."""
    if "---" not in draft_text:
        return [draft_text.strip()]

    raw_posts = draft_text.split("---")
    cleaned_posts: list[str] = []

    for post in raw_posts:
        post_strip = post.strip()
        if not post_strip:
            continue

        # Strip thread index prefix, e.g. "1/", "2/", "1.", "Thread 1:", "Post 1:"
        post_clean = re.sub(r"^(?:Thread|Post|Bebenang)?\s*\d+[\/\.\:]\s*", "", post_strip, flags=re.IGNORECASE).strip()
        if post_clean:
            cleaned_posts.append(post_clean)

    return cleaned_posts or [draft_text.strip()]


async def generate_platform_drafts(
    req: ContentRequest,
    memory: ContentMemory,
    router: PersonaRouter | None = None,
) -> ContentResponse:
    """Generate social media platform drafts from a ContentRequest.

    Args:
        req: Inbound ContentRequest with master article & options.
        memory: ContentMemory instance for dedup checking & storage.
        router: Optional PersonaRouter instance for zero-shot routing.

    Returns:
        ContentResponse containing list of PlatformDraft items & warnings.
    """
    warnings: list[str] = []
    suggested_persona: str | None = None

    # 1. Zero-shot persona routing if auto_persona is True and no explicit fb_style
    if req.auto_persona and not req.fb_style:
        if router is not None:
            try:
                suggestion = router.suggest_fb_persona(req.master_article)
                if suggestion is not None:
                    suggested_persona = suggestion.persona
                    logger.info("Auto-persona suggested: %s (confidence: %.2f)", suggestion.persona, suggestion.confidence)
            except Exception as err:
                logger.warning("Auto-persona routing error: %s", err)
                warnings.append(f"Auto-persona routing failed: {err}")

    # Effective FB style resolution
    effective_fb_style = req.fb_style or suggested_persona or "viral_santai"

    drafts: list[PlatformDraft] = []

    # 2. Generate drafts for each requested platform
    for plat in req.platforms:
        plat_lower = plat.lower().strip()
        try:
            if plat_lower in ["facebook", "fb"]:
                sys_p, usr_p = build_prompt(
                    platform="facebook",
                    style=effective_fb_style,
                    length="panjang",
                    raw=req.master_article,
                )
            elif plat_lower == "threads":
                count_key = str(req.thread_length) if req.thread_length in [1, 3, 5, 8] else "5"
                style_key = req.thread_style or "genz"
                sys_p, usr_p = build_prompt(
                    platform="threads",
                    style=style_key,
                    count=count_key,
                    raw=req.master_article,
                )
            elif plat_lower in ["x", "twitter", "x_thread"]:
                count_key = str(req.thread_length) if req.thread_length in [1, 3, 5, 8] else "1"
                style_key = req.thread_style or "genz"
                sys_p, usr_p = build_prompt(
                    platform="x",
                    style=style_key,
                    count=count_key,
                    raw=req.master_article,
                )
            elif plat_lower == "lemon8":
                style_key = req.fb_style or "estetik"
                sys_p, usr_p = build_prompt(
                    platform="lemon8",
                    style=style_key,
                    raw=req.master_article,
                )
            else:
                # Default fallback platform
                sys_p, usr_p = build_prompt(
                    platform="facebook",
                    style="viral_santai",
                    raw=req.master_article,
                )
        except KeyError as k_err:
            logger.error("Prompt registry error for platform '%s': %s", plat, k_err)
            warnings.append(f"Invalid platform or style for '{plat}': {k_err}")
            continue

        prompt = f"{sys_p}\n\n{usr_p}"

        # Call LLM caller
        raw_output = await call_llm(prompt, timeout=15.0)

        if not raw_output:
            logger.warning("LLM returned empty text for platform '%s'. Using fallback.", plat)
            warnings.append(f"LLM generation returned empty output for platform '{plat}'. Used fallback.")
            raw_output = f"{req.master_article[:800]}"

        # Post-process & clean text
        cleaned_text = clean_draft_text(raw_output, hashtags_on=req.hashtags_on)

        # Parse thread posts if multi-post platform
        thread_posts: list[str] | None = None
        if plat_lower in ["threads", "x", "twitter", "x_thread"]:
            posts = parse_thread_posts(cleaned_text)
            if len(posts) > 1:
                thread_posts = posts
                cleaned_text = "\n\n---\n\n".join(posts)

        # 3. Memory Dedup Check
        dedup_score: float | None = None
        if memory is not None:
            try:
                is_dup, closest = memory.dedup_check(cleaned_text, threshold=0.85)
                if closest is not None:
                    dedup_score = round(closest.similarity, 4)
                if is_dup and closest is not None:
                    warning_msg = (
                        f"Duplicate content detected for platform '{plat}' "
                        f"(similarity {closest.similarity:.2f} >= 0.85)."
                    )
                    logger.warning(warning_msg)
                    warnings.append(warning_msg)
            except Exception as d_err:
                logger.warning("Dedup check error for platform '%s': %s", plat, d_err)

        draft = PlatformDraft(
            platform=plat_lower,
            caption=cleaned_text,
            thread_posts=thread_posts,
            image_url=req.image_url,
            suggested_persona=suggested_persona or (req.fb_style if req.auto_persona else None),
            dedup_score=dedup_score,
        )
        drafts.append(draft)

    # 4. Remember generated drafts in memory for future recall
    if drafts and memory is not None:
        try:
            remember_text = (
                f"MASTER ARTICLE:\n{req.master_article}\n\n"
                + "\n\n".join([f"[{d.platform.upper()}]\n{d.caption}" for d in drafts])
            )
            memory.remember(
                text=remember_text,
                metadata={
                    "platforms": ",".join(req.platforms),
                    "brand": req.brand,
                },
            )
        except Exception as r_err:
            logger.warning("Failed to store generated content in memory: %s", r_err)

    status = "ok" if len(drafts) == len(req.platforms) else ("partial" if drafts else "error")

    return ContentResponse(
        status=status,
        drafts=drafts,
        warnings=warnings,
    )
