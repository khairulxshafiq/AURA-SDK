"""
AURA PROMPT ENGINE — Sakluma Branded Hashtag System & Rotation Logic
Single source of truth for persona hashtags.
"""

import random
import re

SAKLUMA_HASHTAGS = {
    # Facebook personas
    "fb_berita":          ["#saklumanews", "#saklumainfo"],
    "fb_pemerhati":       ["#saklumainfo", "#saklumanews"],
    "fb_kedai_kopi":      ["#saklumastreet", "#saklumaviral"],
    "fb_viral_santai":    ["#saklumaviral", "#saklumalifestyle"],
    "fb_makcik_bawang":   ["#saklumastreet", "#saklumaviral"],
    "fb_kisah_inspirasi": ["#saklumaprihatin", "#saklumalifestyle"],
    # Short aliases for FB
    "berita":             ["#saklumanews", "#saklumainfo"],
    "pemerhati":          ["#saklumainfo", "#saklumanews"],
    "kedai_kopi":         ["#saklumastreet", "#saklumaviral"],
    "viral_santai":       ["#saklumaviral", "#saklumalifestyle"],
    "makcik_bawang":      ["#saklumastreet", "#saklumaviral"],
    "kisah_inspirasi":    ["#saklumaprihatin", "#saklumalifestyle"],
    # Platform lain
    "threads":            ["#saklumaviral", "#saklumalifestyle", "#saklumainfo"],
    "x":                  ["#saklumanews", "#saklumaviral", "#saklumainfo"],
    "twitter":            ["#saklumanews", "#saklumaviral", "#saklumainfo"],
    "lemon8":             ["#saklumalifestyle", "#saklumaviral"],
}

# Pool umum untuk rotate tambahan / fallback kalau key tak jumpa
SAKLUMA_POOL = [
    "#saklumanews", "#saklumaprihatin", "#saklumalifestyle",
    "#saklumastreet", "#saklumainfo", "#saklumaviral",
]

_FORBIDDEN_TAG = "#" + "MFS"

def get_hashtags(persona_key: str, count: int = 2, seed=None) -> str:
    """
    Pulangkan string hashtag Sakluma untuk persona.
    - Ambil dari pool persona dulu, rotate secara rawak (guna seed jika diberi).
    - Top-up dengan SAKLUMA_POOL untuk variasi dan rotasi berbeza antara draf.
    - Kalau persona_key tak wujud -> fallback SAKLUMA_POOL.
    """
    key = str(persona_key).lower().strip() if persona_key else ""
    persona_pool = SAKLUMA_HASHTAGS.get(key, SAKLUMA_POOL)
    
    combined = list(dict.fromkeys(persona_pool + SAKLUMA_POOL))
    rng = random.Random(seed) if seed is not None else random
    
    primary = rng.choice(persona_pool)
    remaining = [h for h in combined if h != primary]
    
    needed = min(count - 1, len(remaining))
    secondary = rng.sample(remaining, needed) if needed > 0 else []
    
    picks = [primary] + secondary
    return " ".join(picks)

def sanitize_hashtags(text: str) -> str:
    """Sanitize output text to strip any unwanted deprecated hashtags."""
    if not text:
        return ""
    pattern = re.compile(re.escape(_FORBIDDEN_TAG) + r"\b", re.IGNORECASE)
    cleaned = pattern.sub("", text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()

def strip_hashtags(text: str) -> str:
    """Strip all hashtags (words starting with #) from text."""
    if not text:
        return ""
    cleaned = re.sub(r"#\w+", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)

