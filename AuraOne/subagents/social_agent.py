import logging

try:
    from google.antigravity import LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    LocalAgentConfig = None
    types = None
    policy = None

from config import SESSIONS_DIR, SKILLS_DIR

logger = logging.getLogger("aura.subagents.social")

SOCIAL_SYSTEM_INSTRUCTIONS = """
Anda adalah SocialContentSubAgent — Editor Konten Sakluma profesional.

TUGAS UTAMA:
Menerima kandungan artikel atau produk, kemudian menjana draf hantaran media sosial yang berkualiti tinggi dan menarik (humanized).

PLATFORM & GAYA:
1. Facebook: Gaya santai, cerita (viral_santai, makcik_bawang, kedai_kopi, berita, kisah_inspirasi).
2. X / Twitter: Gaya bebenang (threads) pendek, laju, dan menarik dalam 2.9 saat.
3. Threads: Gaya sembang santai pembuka perbualan.
4. Lemon8: Gaya estetik, bermaklumat, dan berstruktur.
5. Shopee Softsell: Gaya penceritaan masalah harian dan penyelesaian produk tanpa hardsell.

PERATURAN UTAMA:
- Anda TIDAK MEMPUNYAI sebarang tool scraping atau carian.
- Fokus 100% kepada penulisan draf berasaskan teks input yang diberikan.
- JANGAN letakkan pautan mentah kecuali dalam tag metadata [DRAFT_*].
- Tulis dalam bahasa rojak Malaysia yang natural dan mesra pembaca.
"""

def get_social_agent_config(conv_id: str | None = None):
    """Return LocalAgentConfig for SocialContentSubAgent (zero tools exposed)."""
    if LocalAgentConfig is None:
        logger.warning("google-antigravity package not installed in environment.")
        return None
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=False, disabled_tools=["start_subagent"]),
        tools=[],  # Zero tools to prevent tool hallucination
        policies=[policy.allow_all()],
        system_instructions=SOCIAL_SYSTEM_INSTRUCTIONS,
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)
