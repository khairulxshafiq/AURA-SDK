"""
AURA v5 — THREADS & X (TWITTER) PERSONA PROMPTS (Backward compatibility wrapper)
Delegates prompt generation directly to AuraOne/prompts/ module.
"""

from prompts import build_prompt, THREAD_COUNTS, THREADS_STYLES
from prompts.platforms.threads import THREADS_GLOBAL
from prompts.platforms.x import X_GLOBAL

def build_threads_prompt(count_key: str | int, style_key: str, raw_content: str) -> dict:
    """Compatibility wrapper calling prompts.build_prompt for Threads."""
    sys_p, usr_p = build_prompt(
        platform="threads",
        style=style_key,
        count=count_key,
        raw=raw_content
    )
    ck = str(count_key).strip()
    sk = str(style_key).lower().strip()
    c = THREAD_COUNTS.get(ck, THREAD_COUNTS["5"])
    s = THREADS_STYLES.get(sk, THREADS_STYLES["genz"])
    return {"system": sys_p, "user": usr_p, "label": s["label"], "count_label": c["label"]}

def build_x_prompt(style_key: str, raw_content: str, count_key: str | int = "1") -> dict:
    """Compatibility wrapper calling prompts.build_prompt for X."""
    sys_p, usr_p = build_prompt(
        platform="x",
        style=style_key,
        count=count_key,
        raw=raw_content
    )
    sk = str(style_key).lower().strip()
    s = THREADS_STYLES.get(sk, THREADS_STYLES["genz"])
    return {"system": sys_p, "user": usr_p, "label": s["label"]}

__all__ = ["build_threads_prompt", "build_x_prompt", "THREAD_COUNTS", "THREADS_STYLES", "THREADS_GLOBAL", "X_GLOBAL"]
