import logging

try:
    from google.antigravity import LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    LocalAgentConfig = None
    types = None
    policy = None

from tools.web_scraper import scrape_url
from tools.search_engine import search_web
from config import SESSIONS_DIR, SKILLS_DIR

logger = logging.getLogger("aura.subagents.scraper")

SCRAPER_SYSTEM_INSTRUCTIONS = """
Anda adalah ScraperSubAgent — ejen khas untuk membuat carian web dan membaca (scrape) kandungan laman web.

PERATURAN UTAMA:
1. Tugas anda HANYA mencari info dan membaca pautan URL menggunakan tool `search_web` dan `scrape_url`.
2. Apabila diminta mengekstrak artikel dari URL, gunakan `scrape_url`.
3. Kembalikan HASIL KANDUNGAN BERSIH dalam format markdown beserta tajuk dan pautan imej utama artikel (jika ada).
4. JANGAN SEKALI-KALI menjana draf media sosial, Facebook, X, atau Lemon8. Tugas tersebut dikendalikan oleh ejen lain.
5. JANGAN SEKALI-KALI menggunakan imej lama atau poster dari memori lampau. Sentiasa gunakan imej terkini dari hasil scrape_url.
"""

def get_scraper_agent_config(conv_id: str | None = None):
    """Return LocalAgentConfig for ScraperSubAgent with isolated tools (scrape_url, search_web)."""
    if LocalAgentConfig is None:
        logger.warning("google-antigravity package not installed in environment.")
        return None
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=False),
        tools=[scrape_url, search_web],
        policies=[policy.allow_all()],
        system_instructions=SCRAPER_SYSTEM_INSTRUCTIONS,
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)
