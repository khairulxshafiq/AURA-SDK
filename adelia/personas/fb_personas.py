"""
ADELIA — FB SUB-PLATFORM PERSONA PROMPTS (Backward compatibility wrapper)
Delegates prompt generation directly to adelia/prompts/ module.
"""

from adelia.prompts import build_prompt, enforce_fb_length_limits, FB_PERSONAS
from adelia.prompts.shared.global_rules import GLOBAL_RULES
from adelia.prompts.platforms.facebook import FB_PERSONAS as SUB_PLATFORM_PROMPTS

def build_fb_prompt(sub_platform_key: str, raw_content: str, length_option: str = "panjang", show_title: bool = False) -> dict:
    """Compatibility wrapper calling prompts.build_prompt."""
    key = sub_platform_key.lower().strip()
    if key.startswith("fb_"):
        key = key[3:]
    
    sys_p, usr_p = build_prompt(
        platform="facebook",
        style=key,
        length=length_option,
        show_title=show_title,
        raw=raw_content
    )
    
    p = FB_PERSONAS.get(key, FB_PERSONAS.get("viral_santai", {}))
    return {
        "system": sys_p,
        "user": usr_p,
        "label": p.get("label", "FB: Viral Santai 🍿"),
        "hashtag": p.get("hashtag", "#SaklumaViral")
    }

__all__ = ["build_fb_prompt", "enforce_fb_length_limits", "GLOBAL_RULES", "FB_PERSONAS", "SUB_PLATFORM_PROMPTS"]
