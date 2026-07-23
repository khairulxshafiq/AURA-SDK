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
Anda adalah ScraperSubAgent — ejen khas untuk mengekstrak (scrape) kandungan laman web dan membuat carian web.

PERATURAN MUTLAK EXECUTION TOOLS:
1. Anda WAJIB TERUS memanggil tool `scrape_url` ATAU `search_web` secara TERUS untuk mengambil data.
2. DILARANG SAMA SEKALI memulangkan ayat perantaraan seperti "Saya telah delegasikan...", "ScraperSubAgent sedang bertugas...", atau "Sila tunggu...".
3. DILARANG SAMA SEKALI cuba mencipta sub-agent atau memanggil `invoke_subagent` / `start_subagent`. Anda tidak mempunyai kebenaran sub-agent.
4. Apabila menerima pautan URL spesifik, TERUS panggil `scrape_url(url=...)`.
5. Selepas tool memulangkan hasil, kembalikan HASIL KANDUNGAN BERSIH (Tajuk Utama, Teks Penuh Artikel, dan URL Imej Utama) secara terus kepada Parent Supervisor dalam format markdown.
6. JANGAN SEKALI-KALI menjana draf media sosial, Facebook, X, atau Lemon8. Tugas penulisan draf dikendalikan oleh ejen lain.
"""

def get_scraper_agent_config(conv_id: str | None = None):
    """Return LocalAgentConfig for ScraperSubAgent with strict direct tool execution and zero subagent capabilities."""
    if LocalAgentConfig is None:
        logger.warning("google-antigravity package not installed in environment.")
        return None
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=False, disabled_tools=["start_subagent"]),
        tools=[scrape_url, search_web],
        policies=[policy.allow_all()],
        system_instructions=SCRAPER_SYSTEM_INSTRUCTIONS,
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)
