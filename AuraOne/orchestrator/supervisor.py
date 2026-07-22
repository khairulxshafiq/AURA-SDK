import os
import datetime
import logging

try:
    from google.antigravity import LocalAgentConfig, LocalOpenAIAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError:
    LocalAgentConfig = None
    LocalOpenAIAgentConfig = None
    types = None
    policy = None

from config import SESSIONS_DIR, SKILLS_DIR, BASE_DIR, OPENROUTER_FALLBACK_MODEL, OPENROUTER_BASE_URL

logger = logging.getLogger("aura.orchestrator.supervisor")

SUPERVISOR_PERSONA_PATH = os.path.join(BASE_DIR, "orchestrator", "persona.txt")

def get_supervisor_instructions() -> str:
    """Load Supervisor persona instructions and inject current datetime and memory summary."""
    now = datetime.datetime.now()
    day_names = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]
    day_of_week = day_names[now.weekday()]
    time_str = now.strftime("%I:%M %p")
    date_str = now.strftime("%d %B %Y")

    dynamic_prefix = (
        f"PENTING: Maklumat Waktu Semasa Sistem:\n"
        f"- Hari ini: {day_of_week}\n"
        f"- Tarikh hari ini: {date_str}\n"
        f"- Waktu sekarang: {time_str} (Waktu Malaysia, UTC+8)\n\n"
    )

    try:
        from storage.memory_repository import get_memory_summary
        ltm_summary = get_memory_summary()
        memory_block = ltm_summary + "\n\n"
    except Exception as e:
        logger.error(f"Failed to load memory summary: {e}")
        memory_block = ""

    persona_content = ""
    if os.path.exists(SUPERVISOR_PERSONA_PATH):
        with open(SUPERVISOR_PERSONA_PATH, "r", encoding="utf-8") as f:
            persona_content = f.read()
    else:
        persona_content = "You are AURA — a silent, sharp personal AI supervisor."

    return dynamic_prefix + memory_block + persona_content

def get_supervisor_gemini_config(conv_id: str | None = None):
    """Return LocalAgentConfig for Main Supervisor Agent with subagents enabled and NO heavy scraping tools."""
    if LocalAgentConfig is None:
        logger.warning("google-antigravity package not installed in environment.")
        return None
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
        tools=[],  # Holds NO heavy scraping tools directly; delegates via subagents
        policies=[policy.allow_all()],
        system_instructions=get_supervisor_instructions(),
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)

def get_supervisor_openrouter_config(conv_id: str | None = None):
    """Return LocalOpenAIAgentConfig for Main Supervisor Agent fallback."""
    if LocalOpenAIAgentConfig is None:
        logger.warning("google-antigravity package not installed in environment.")
        return None
    kwargs = dict(
        model=OPENROUTER_FALLBACK_MODEL,
        base_url=OPENROUTER_BASE_URL,
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
        tools=[],  # Holds NO heavy scraping tools directly
        policies=[policy.allow_all()],
        system_instructions=get_supervisor_instructions(),
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalOpenAIAgentConfig(**kwargs)
