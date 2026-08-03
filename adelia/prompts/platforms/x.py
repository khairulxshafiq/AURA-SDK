"""
ADELIA PROMPT ENGINE — X (Twitter) Platform Personas & Thread Counts
Contains X specific styles and prompt generation functions.
"""

from adelia.prompts.shared.global_rules import GLOBAL_RULES
from adelia.prompts.shared.hashtags import get_hashtags
from adelia.prompts.platforms.threads import THREAD_COUNTS, THREADS_STYLES

X_GLOBAL = f"""
PERATURAN AM (X / Twitter):
- Bahasa: Melayu santai Malaysia (boleh campur English kalau natural).
- OPTIMUM MASA BACA (3 SAAT): Setiap tweet <= 280 aksara. Tegas, laju, punchy.
- PERATURAN EMOJI STRICT: KURANGKAN EMOJI. Maksimum 0 hingga 1 emoji sahaja per tweet.
- Kalau bebenang (>1 tweet), pisahkan dengan "---" (dengan nombor 1/, 2/, 3/ di awal setiap tweet).
- Tweet 1: Hook super tajam.
- Output: teks tweet sahaja.
{GLOBAL_RULES}
"""


def build_x_prompt(style: str, count: str | int, raw_content: str, seed=None) -> tuple[str, str]:
    """Bina prompt (system, user) untuk X (Twitter).
    Raises KeyError jika style atau count tidak wujud.
    """
    ck = str(count).strip()
    if ck not in THREAD_COUNTS:
        valid_counts = ", ".join(f"'{k}'" for k in THREAD_COUNTS.keys())
        raise KeyError(f"Bilangan bebenang '{count}' tak wujud dalam prompts/platforms/x.py. Pilihan sah: {valid_counts}")

    sk = str(style).lower().strip()
    if sk not in THREADS_STYLES:
        valid_styles = ", ".join(f"'{k}'" for k in THREADS_STYLES.keys())
        raise KeyError(f"Gaya '{style}' tak wujud dalam prompts/platforms/x.py. Gaya sah: {valid_styles}")

    c = THREAD_COUNTS[ck]
    s = THREADS_STYLES[sk]
    tags = get_hashtags("x", count=2, seed=seed)

    system_prompt = f"""Kau ialah copywriter X (Twitter) profesional.
{s['guide']}

{c['guide']}

{X_GLOBAL.strip()}"""

    user_prompt = f"""INPUT / BAHAN MENTAH:
{raw_content}

Hasilkan hantaran X ({c['label']}) dalam gaya "{s['label']}".
Jika lebih daripada 1 bebenang, pisahkan dengan "---".
Akhiri post dengan hashtag ini di bahagian hujung: {tags}."""

    return system_prompt, user_prompt
