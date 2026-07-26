import logging

try:
    from google.antigravity import LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    LocalAgentConfig = None
    types = None
    policy = None

from tools.trading_service import (
    get_stock_quote,
    get_financial_ratios,
    get_rsi,
    get_sma,
    resolve_stock_ticker,
)
from config import SESSIONS_DIR, SKILLS_DIR

logger = logging.getLogger("aura.subagents.trading")

TRADING_SYSTEM_INSTRUCTIONS = """
Anda adalah TradingSubAgent — ejen khas analisis saham, nisbah kewangan fundamental, dan indikator teknikal pasaran untuk AURA.

PERATURAN UTAMA EXECUTION TOOLS:
1. Apabila menerima nama syarikat atau simbol ticker saham (contoh: "Maybank", "1155.KL", "Tenaga", "AAPL"), panggil tools berikut secara TERUS:
   - `get_stock_quote(symbol=...)` untuk petikan harga live dan maklumat pasaran.
   - `get_financial_ratios(symbol=...)` untuk pertumbuhan kewangan, ROE, dan dividen.
   - `get_rsi(symbol=...)` untuk indikator momentum RSI-14.
   - `get_sma(symbol=...)` untuk indikator trend SMA-50.
2. DILARANG SAMA SEKALI memulangkan ayat perantaraan seperti "Saya sedang menyemak...", "TradingSubAgent sedang bertugas...", atau "Sila tunggu...".
3. DILARANG SAMA SEKALI mencuba meletakkan sub-agent lain atau memanggil `start_subagent`. Anda tidak mempunyai kebenaran sub-agent.
4. Selepas memanggil tools dan menerima data pasaran live, hasilkan **Laporan Analisis Trading 8-Bahagian** dalam Bahasa Melayu mengikut kemahiran `skills/trading/SKILL.md`.
5. Sekiranya symbol dikesan sebagai 4 digit angka (contoh: "1155"), pastikan ia dirujuk sebagai "1155.KL" untuk pasaran Bursa Malaysia.
"""

def get_trading_agent_config(conv_id: str | None = None):
    """Return LocalAgentConfig for TradingSubAgent equipped with real-time stock & technical analysis tools."""
    if LocalAgentConfig is None:
        logger.warning("google-antigravity package not installed in environment.")
        return None
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=False, disabled_tools=["start_subagent"]),
        tools=[get_stock_quote, get_financial_ratios, get_rsi, get_sma, resolve_stock_ticker],
        policies=[policy.allow_all()],
        system_instructions=TRADING_SYSTEM_INSTRUCTIONS,
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)
