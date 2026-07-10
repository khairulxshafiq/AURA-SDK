import os
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

# ─── Model Config ─────────────────────────────────────────────────────────────
# Primary: Gemini via Antigravity SDK
# Fallback: OpenRouter with a cheap model (OpenAI-compatible endpoint)
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
    """Return saved conversation_id for a user only if session folder exists."""
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


# ─── Build Agent Config ────────────────────────────────────────────────────────

def _build_gemini_config(conv_id: str | None) -> LocalAgentConfig:
    """Primary config: Gemini via LocalAgentConfig."""
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
    """Fallback config: OpenRouter (OpenAI-compatible) via LocalOpenAIAgentConfig."""
    # OpenRouter requires the API key as a Bearer token in the base URL header.
    # The SDK passes it via the Authorization header automatically when we
    # use the OpenAI-compatible format: base_url + api_key embedded model name.
    # We embed the key into the base_url as a workaround for SDK compatibility.
    base_url = OPENROUTER_BASE_URL
    model = f"{OPENROUTER_FALLBACK_MODEL}"

    kwargs = dict(
        model=model,
        base_url=base_url,
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
        "You are AURA (powered by Google Antigravity SDK), a personal operating system supervisor. "
        "Your role is to act as the conductor/orchestrator of tasks. You have subagent capabilities "
        "to delegate complex subtasks, and you have access to the scrape_web tool to extract webpage information. "
        "Respond in a clear, concise, and professional manner, using Malay or English based on the user's input."
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
        rf"Salam {user.mention_html()}! Saya <b>AURA</b>, personal operating system supervisor anda. "
        rf"Hantar sebarang mesej, arahan, atau pautan untuk saya bantu!"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Attempt 1: Gemini (Primary) ──────────────────────────────────────────
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

        await update.message.reply_text(response_text)
        return  # Success — no need for fallback

    except Exception as gemini_err:
        if _is_rate_limit_error(gemini_err):
            logger.warning(f"[Gemini] Rate limit hit for user {user_id}. Switching to OpenRouter fallback...")
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        else:
            # Non-rate-limit Gemini error — report to user
            logger.error(f"[Gemini] Error for user {user_id}: {gemini_err}", exc_info=True)
            await update.message.reply_text(f"Minta maaf bos, ralat berlaku: {str(gemini_err)}")
            return

    # ── Attempt 2: OpenRouter Fallback ───────────────────────────────────────
    if not OPENROUTER_API_KEY:
        await update.message.reply_text(
            "⚠️ Gemini telah mencapai had penggunaan dan OPENROUTER_API_KEY tidak dikonfigurasi dalam .env untuk fallback."
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

        # Notify user that fallback model is being used
        await update.message.reply_text(
            f"_(Nota: Gemini sedang mencapai had penggunaan. Menggunakan model {OPENROUTER_FALLBACK_MODEL} sebagai gantian.)_\n\n{response_text}",
            parse_mode="Markdown"
        )

    except Exception as or_err:
        logger.error(f"[OpenRouter] Fallback error for user {user_id}: {or_err}", exc_info=True)
        await update.message.reply_text(
            f"Minta maaf bos, kedua-dua Gemini dan OpenRouter gagal:\n• Gemini: Had penggunaan\n• OpenRouter: {str(or_err)}"
        )


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not configured in the .env file.")
        return

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"AURA Bot starting. Primary: Gemini | Fallback: OpenRouter ({OPENROUTER_FALLBACK_MODEL})")
    application.run_polling()


if __name__ == '__main__':
    main()
