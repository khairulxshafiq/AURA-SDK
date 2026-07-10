import os
import re
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import Antigravity SDK
try:
    from google.antigravity import Agent, LocalAgentConfig, LocalOpenAIAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError as e:
    logger.error("=" * 80)
    logger.error("RALAT IMPORT: Pustaka 'google-antigravity' tidak dapat diimport.")
    logger.error("Kod ini AKAN BERJALAN SEMPURNA apabila di-deploy ke VPS Linux (Tencent SG)!")
    logger.error("=" * 80)
    raise e

from tools import scrape_web

# ─── Directories ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(SKILLS_DIR, exist_ok=True)

SESSION_MAP_PATH = os.path.join(SESSIONS_DIR, "user_session_map.json")

# ─── Per-user Debug State ─────────────────────────────────────────────────────
# Stores user_id -> True/False. Default: False (debug off)
DEBUG_USERS: dict = {}

# ─── Model Config ─────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_FALLBACK_MODEL = os.environ.get("OPENROUTER_FALLBACK_MODEL", "openai/gpt-4o-mini")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ─── Session Map Helpers ───────────────────────────────────────────────────────

def _load_session_map() -> dict:
    if os.path.exists(SESSION_MAP_PATH):
        try:
            with open(SESSION_MAP_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_session_map(session_map: dict) -> None:
    try:
        with open(SESSION_MAP_PATH, "w") as f:
            json.dump(session_map, f)
    except OSError as e:
        logger.error(f"Failed to save session map: {e}")


def _get_conv_id_for_user(user_id: int, prefix: str = "") -> str | None:
    session_map = _load_session_map()
    key = f"{prefix}{user_id}"
    conv_id = session_map.get(key)
    if conv_id:
        session_path = os.path.join(SESSIONS_DIR, conv_id)
        if os.path.isdir(session_path):
            return conv_id
        logger.warning(f"Session folder missing for user {user_id} ({prefix}), starting fresh.")
    return None


def _register_conv_id_for_user(user_id: int, conv_id: str, prefix: str = "") -> None:
    session_map = _load_session_map()
    session_map[f"{prefix}{user_id}"] = conv_id
    _save_session_map(session_map)


# ─── Response Cleaner ─────────────────────────────────────────────────────────

# Strip markdown headers that expose internal reasoning in normal mode
_REASONING_PATTERN = re.compile(
    r"^#{1,3}\s*(Ringkasan Penaakulan|Proses Delegasi|Analisis|Reasoning|"
    r"Keputusan|Delegation|Tool Call|Internal Analysis|Chain.of.Thought|"
    r"Debug|Langkah|Delegasi)[^\n]*\n?",
    re.IGNORECASE | re.MULTILINE
)


def _clean_response(text: str) -> str:
    """Strip internal reasoning headers for normal (non-debug) users."""
    cleaned = _REASONING_PATTERN.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ─── Build Agent Configs ───────────────────────────────────────────────────────

def _build_gemini_config(conv_id: str | None) -> LocalAgentConfig:
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
        tools=[scrape_web],
        policies=[policy.allow_all()],
        system_instructions=SYSTEM_INSTRUCTIONS,
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)


def _build_openrouter_config(conv_id: str | None) -> LocalOpenAIAgentConfig:
    kwargs = dict(
        model=OPENROUTER_FALLBACK_MODEL,
        base_url=OPENROUTER_BASE_URL,
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
        tools=[scrape_web],
        policies=[policy.allow_all()],
        system_instructions=SYSTEM_INSTRUCTIONS,
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalOpenAIAgentConfig(**kwargs)


# ─── Load Persona ──────────────────────────────────────────────────────────────

PERSONA_PATH = os.path.join(BASE_DIR, "persona.txt")
if os.path.exists(PERSONA_PATH):
    with open(PERSONA_PATH, "r") as f:
        SYSTEM_INSTRUCTIONS = f.read()
else:
    SYSTEM_INSTRUCTIONS = (
        "You are AURA, a concise personal AI supervisor. "
        "Reply in short, clear answers. Never show reasoning or internal steps. "
        "Use emojis naturally. Speak Malay by default."
    )

# ─── Rate Limit Detection ──────────────────────────────────────────────────────

RATE_LIMIT_SIGNALS = [
    "429", "quota", "rate limit", "resource_exhausted",
    "RESOURCE_EXHAUSTED", "too many requests", "quota exceeded"
]


def _is_rate_limit_error(error: Exception) -> bool:
    msg = str(error).lower()
    return any(sig.lower() in msg for sig in RATE_LIMIT_SIGNALS)


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"Salam {user.mention_html()}! Saya <b>AURA</b>, personal AI supervisor anda. "
        rf"Hantar sebarang mesej, arahan, atau pautan untuk saya bantu!"
    )


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle debug mode: /debug on | /debug off"""
    user_id = update.effective_user.id
    args = context.args

    if args and args[0].lower() == "on":
        DEBUG_USERS[user_id] = True
        await update.message.reply_text(
            "🔧 *Debug Mode: ON*\n\n"
            "Saya akan tunjukkan reasoning, tool calls, dan delegation flow dalam setiap jawapan.\n\n"
            "Taip `/debug off` untuk kembali ke format biasa.",
            parse_mode="Markdown"
        )
    elif args and args[0].lower() == "off":
        DEBUG_USERS[user_id] = False
        await update.message.reply_text(
            "✅ *Debug Mode: OFF*\n\n"
            "Kembali ke format jawapan standard — ringkas dan bersih.",
            parse_mode="Markdown"
        )
    else:
        status = "ON 🔧" if DEBUG_USERS.get(user_id) else "OFF ✅"
        await update.message.reply_text(
            f"Debug mode sekarang: *{status}*\n\n"
            f"Untuk tukar:\n`/debug on` — tunjuk reasoning & tool calls\n`/debug off` — format biasa",
            parse_mode="Markdown"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    is_debug = DEBUG_USERS.get(user_id, False)

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Attempt 1: Gemini (Primary) ───────────────────────────────────────────
    gemini_conv_id = _get_conv_id_for_user(user_id, prefix="g_")
    gemini_config = _build_gemini_config(gemini_conv_id)

    try:
        async with Agent(gemini_config) as agent:
            response = await agent.chat(user_message)
            response_text = await response.text()

            if not gemini_conv_id:
                new_id = agent.conversation_id
                if new_id:
                    _register_conv_id_for_user(user_id, new_id, prefix="g_")
                    logger.info(f"[Gemini] New session for user {user_id}: {new_id}")

        if is_debug:
            final_text = f"🔧 *\\[DEBUG: Gemini\\]*\n\n{response_text}"
            await update.message.reply_text(final_text, parse_mode="MarkdownV2")
        else:
            await update.message.reply_text(_clean_response(response_text))
        return

    except Exception as gemini_err:
        if _is_rate_limit_error(gemini_err):
            logger.warning(f"[Gemini] Rate limit for user {user_id}. Switching to OpenRouter...")
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        else:
            logger.error(f"[Gemini] Error for user {user_id}: {gemini_err}", exc_info=True)
            await update.message.reply_text(f"⚠️ Ralat berlaku: {str(gemini_err)}")
            return

    # ── Attempt 2: OpenRouter Fallback ────────────────────────────────────────
    if not OPENROUTER_API_KEY:
        await update.message.reply_text(
            "⚠️ Gemini telah mencapai had penggunaan dan OPENROUTER_API_KEY tidak dikonfigurasi."
        )
        return

    or_conv_id = _get_conv_id_for_user(user_id, prefix="or_")
    or_config = _build_openrouter_config(or_conv_id)

    try:
        async with Agent(or_config) as agent:
            response = await agent.chat(user_message)
            response_text = await response.text()

            if not or_conv_id:
                new_id = agent.conversation_id
                if new_id:
                    _register_conv_id_for_user(user_id, new_id, prefix="or_")
                    logger.info(f"[OpenRouter] New session for user {user_id}: {new_id}")

        if is_debug:
            final_text = f"🔧 *[DEBUG: OpenRouter — {OPENROUTER_FALLBACK_MODEL}]*\n\n{response_text}"
            await update.message.reply_text(final_text, parse_mode="Markdown")
        else:
            clean = _clean_response(response_text)
            await update.message.reply_text(
                f"_({OPENROUTER_FALLBACK_MODEL})_\n\n{clean}",
                parse_mode="Markdown"
            )

    except Exception as or_err:
        logger.error(f"[OpenRouter] Fallback error for user {user_id}: {or_err}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ Kedua-dua model gagal:\n• Gemini: Had penggunaan\n• OpenRouter: {str(or_err)}"
        )


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not configured in the .env file.")
        return

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"AURA Bot starting. Primary: Gemini | Fallback: OpenRouter ({OPENROUTER_FALLBACK_MODEL})")
    application.run_polling()


if __name__ == '__main__':
    main()
