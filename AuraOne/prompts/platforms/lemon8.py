"""
AURA PROMPT ENGINE — Lemon8 Platform Personas & Layout
Contains Lemon8 style prompts and layout structure.
"""

from prompts.shared.global_rules import GLOBAL_RULES
from prompts.shared.hashtags import get_hashtags

LEMON8_GLOBAL = f"""
PERATURAN AM (Lemon8):
- Bahasa: Melayu santai, estetik, bersemangat dan mesra komuniti Lemon8.
- Format: Gunakan sub-tajuk menarik, emojifikasi berskala (2-4 emoji per seksyen), dan perenggan mesra baca.
- Output: teks hantaran Lemon8 sahaja.
{GLOBAL_RULES}
"""


def build_lemon8_prompt(style: str, raw_content: str, with_hashtags: bool = True, seed=None) -> tuple[str, str]:
    """Bina prompt (system, user) untuk Lemon8."""
    if with_hashtags:
        tags = get_hashtags("lemon8", count=2, seed=seed)
        hashtag_instruction = f"Akhiri post dengan 1 baris kosong dan hashtag ini: {tags}."
    else:
        hashtag_instruction = "PERATURAN HASHTAG (OFF): DILARANG SAMA SEKALI meletakkan sebarang hashtag (#) dalam hantaran ini."

    system_prompt = f"""Kau ialah pencipta kandungan Lemon8 profesional.
TUGAS: Olah INPUT menjadi hantaran Lemon8 yang estetik, informatif, dan mesra pembaca.

{LEMON8_GLOBAL.strip()}"""

    user_prompt = f"""INPUT / BAHAN MENTAH:
{raw_content}

Hasilkan hantaran Lemon8 berasaskan bahan di atas.
{hashtag_instruction}"""

    return system_prompt, user_prompt
