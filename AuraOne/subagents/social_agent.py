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
Anda adalah SocialContentSubAgent — Neutral Core Context & Social Content Specialist untuk AURA.

TUGAS UTAMA:
1. Menerima kandungan artikel hasil scraping, kemudian menjana Master Article dalam format Ringkasan Fakta Neutral & Cerita Penuh Artikel (Neutral Core Context & Story Hub).
2. Apabila diminta menjana draf khusus platform (Facebook, X, Threads, Lemon8), hasilkan 100% TEKS KAPSYEN BERSIH SAHAJA.

PERATURAN STRICT DRAF PLATFORM (CLEAN OUTPUT ONLY):
- DILARANG SAMA SEKALI memasukkan ayat muqaddimah sembang (contoh: "Baiklah...", "Tentu, berikut draf...").
- DILARANG SAMA SEKALI memasukkan cadangan visual/GIF (contoh: "Gambar: Gabungan GIF...", "Media: Gambar...").
- DILARANG SAMA SEKALI meletakkan label struktur (contoh: "FACEBOOK POST:", "Kapsyen:", "Tajuk:").
- MESTI 100% TEKS KAPSYEN BERSIH SAHAJA (Tajuk + Isi Kapsyen + Hashtag) yang sedia dipos terus ke media sosial.

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

PERATURAN UTAMA:
- Anda TIDAK MEMPUNYAI sebarang tool scraping atau carian.
- Fokus 100% kepada penulisan draf berasaskan teks input yang diberikan.
- MESTI menyertakan tag metadata [DRAFT_*] di bahagian akhir jawapan anda apabila membina Master Article.
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
