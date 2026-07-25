"""
AURA PROMPT ENGINE — Lemon8 Platform Personas & Layout
Contains Lemon8 style prompts and layout structure.
"""

from prompts.shared.global_rules import GLOBAL_RULES

LEMON8_GLOBAL = f"""
PERATURAN AM (Lemon8):
- Bahasa: Melayu santai, estetik, bersemangat dan mesra komuniti Lemon8.
- Format: Gunakan sub-tajuk menarik, emojifikasi berskala (2-4 emoji per seksyen), dan perenggan mesra baca.
- Output: teks hantaran Lemon8 sahaja.
{GLOBAL_RULES}
"""


def build_lemon8_prompt(style: str, raw_content: str) -> tuple[str, str]:
    """Bina prompt (system, user) untuk Lemon8."""
    system_prompt = f"""Kau ialah pencipta kandungan Lemon8 profesional.
TUGAS: Olah INPUT menjadi hantaran Lemon8 yang estetik, informatif, dan mesra pembaca.

{LEMON8_GLOBAL.strip()}"""

    user_prompt = f"""INPUT / BAHAN MENTAH:
{raw_content}

Hasilkan hantaran Lemon8 berasaskan bahan di atas."""

    return system_prompt, user_prompt
