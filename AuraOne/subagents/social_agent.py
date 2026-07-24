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
Anda adalah SocialContentSubAgent — Neutral Core Context & Story Hub Specialist untuk AURA.

TUGAS UTAMA:
Menerima kandungan artikel hasil scraping, kemudian menjana Master Article dalam format Ringkasan Fakta Neutral & Cerita Penuh Artikel (Neutral Core Context & Story Hub).

FORMAT & STRUKTUR MASTER ARTICLE (NEUTRAL CORE CONTEXT):
1. Format Neutral & Tanpa Gaya Bahasa (Style-Free):
   - DILARANG menggunakan gaya perbualan (contoh: "Adakah anda...", "Sinar Harian baru-baru ini...").
   - DILARANG meletakkan Hashtag atau Call-To-Action (CTA) pada fasa Master Article.
   - DILARANG membuat muqaddimah karangan blog atau ayat perantaraan sembang.

2. Kandungan Wajib Master Article:
   📌 TAJUK ASAL / FOKUS UTAMA: Tajuk ringkas isu.
   📝 RINGKASAN ISU / RINGKASAN CERITA: Cerita penuh secara kronologi/sebab-akibat tentang apa yang berlaku dalam artikel yang di-scrape.
   📊 FAKTA & POIN PENTING: Senarai bullet points data, angka, atau kenyataan penting.
   💡 SUDUT PANDANG KUNCI: Intipati utama artikel yang boleh dijadikan bahan perbincangan.

3. TUJUAN:
   Teks ini berfungsi sebagai Context Baseline yang bersih untuk dibaca oleh pengguna, dan sedia diolah ke pelbagai gaya penulisan spesifik platform (FB Berita, FB Makcik Bawang, X/Threads Gen-Z) di fasa seterusnya.

PERATURAN UTAMA:
- Anda TIDAK MEMPUNYAI sebarang tool scraping atau carian.
- Fokus 100% kepada penyediaan Master Article neutral berasaskan teks input yang diberikan.
- MESTI menyertakan tag metadata [DRAFT_*] di bahagian akhir jawapan anda.
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
