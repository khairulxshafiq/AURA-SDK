"""
AURA PROMPT ENGINE — Single Source Registry & Loader

Usage:
    from prompts import build_prompt, sanitize_hashtags

    # FB example
    system, user = build_prompt(
        platform="facebook",
        style="viral_santai",
        length="pendek",
        raw=master_article,
        seed=draft_counter
    )

    # Threads example
    system, user = build_prompt(
        platform="threads",
        count="8",
        style="genz",
        raw=master_article,
        seed=draft_counter
    )
"""

from prompts.platforms.facebook import build_facebook_prompt, FB_PERSONAS
from prompts.platforms.threads import build_threads_prompt, THREAD_COUNTS, THREADS_STYLES
from prompts.platforms.x import build_x_prompt
from prompts.platforms.lemon8 import build_lemon8_prompt
from prompts.modifiers.length import enforce_fb_length_limits, get_length_instruction
from prompts.shared.hashtags import get_hashtags, sanitize_hashtags, SAKLUMA_HASHTAGS, SAKLUMA_POOL

SUPPORTED_PLATFORMS = ["facebook", "fb", "threads", "x", "twitter", "lemon8"]

def build_prompt(
    platform: str,
    raw: str = "",
    style: str = "",
    length: str = "panjang",
    count: str | int = "5",
    show_title: bool = False,
    raw_content: str = "",
    seed=None
) -> tuple[str, str]:
    """Bina prompt (system_prompt, user_prompt) mengikut platform, style, length, count, dan rotation seed.
    
    Raises:
        KeyError: Jika platform, style, length, atau count tidak wujud dalam registry.
    """
    plat = platform.lower().strip() if platform else ""
    master_article = raw or raw_content

    if plat in ["facebook", "fb"]:
        st = style or "viral_santai"
        return build_facebook_prompt(style=st, raw_content=master_article, length=length, show_title=show_title, seed=seed)
    
    elif plat == "threads":
        st = style or "genz"
        ct = str(count) if count else "5"
        return build_threads_prompt(style=st, count=ct, raw_content=master_article, seed=seed)
    
    elif plat in ["x", "twitter"]:
        st = style or "genz"
        ct = str(count) if count else "1"
        return build_x_prompt(style=st, count=ct, raw_content=master_article, seed=seed)
    
    elif plat == "lemon8":
        st = style or "estetik"
        return build_lemon8_prompt(style=st, raw_content=master_article, seed=seed)
    
    else:
        valid = ", ".join(f"'{p}'" for p in ["facebook", "threads", "x", "lemon8"])
        raise KeyError(f"Platform '{platform}' tak wujud dalam prompts registry. Platform sah: {valid}")

__all__ = [
    "build_prompt",
    "enforce_fb_length_limits",
    "get_length_instruction",
    "get_hashtags",
    "sanitize_hashtags",
    "FB_PERSONAS",
    "THREAD_COUNTS",
    "THREADS_STYLES",
    "SAKLUMA_HASHTAGS",
    "SAKLUMA_POOL"
]
