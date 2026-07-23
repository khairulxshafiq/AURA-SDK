import logging

try:
    from google.antigravity import LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    LocalAgentConfig = None
    types = None
    policy = None

from tools.location_service import reverse_geocode_location, _get_weather_forecast, _get_extended_weather_forecast
from config import SESSIONS_DIR, SKILLS_DIR

logger = logging.getLogger("aura.subagents.location")

LOCATION_SYSTEM_INSTRUCTIONS = """
Anda adalah LocationSubAgent — ejen khas untuk geokod lokasi dan ramalan cuaca.

PERATURAN UTAMA:
1. Mengendalikan pertanyaan berkaitan cuaca, suhu, hujan, dan alamat berasaskan koordinat GPS.
2. Gunakan `reverse_geocode_location` untuk menukar koordinat GPS ke alamat tempatan.
3. Gunakan `_get_weather_forecast` atau `_get_extended_weather_forecast` untuk ramalan cuaca.
4. Berikan maklumat lokasi dan cuaca yang ringkas dan padat.
"""

def get_location_agent_config(conv_id: str | None = None):
    """Return LocalAgentConfig for LocationSubAgent with location & weather tools."""
    if LocalAgentConfig is None:
        logger.warning("google-antigravity package not installed in environment.")
        return None
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=False, disabled_tools=["start_subagent"]),
        tools=[reverse_geocode_location, _get_weather_forecast, _get_extended_weather_forecast],
        policies=[policy.allow_all()],
        system_instructions=LOCATION_SYSTEM_INSTRUCTIONS,
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)
