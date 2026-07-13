import os
import re
import json
import logging
import threading
import datetime
import time
import httpx
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
import urllib.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from typing import Optional



from dotenv import load_dotenv
from google.genai import types as genai_types
from google.antigravity.tools.tool_runner import ToolWithSchema


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

from tools import scrape_url, search_web, save_user_fact, update_user_preference

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
OPENROUTER_FALLBACK_MODEL = os.environ.get("OPENROUTER_FALLBACK_MODEL", os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash"))
OPENROUTER_BASE_URL = "http://127.0.0.1:18080"

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

def _get_dynamic_instructions() -> str:
    """Inject current date, time, and day of the week dynamically into SYSTEM_INSTRUCTIONS."""
    now = datetime.datetime.now()
    day_names = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]
    day_of_week = day_names[now.weekday()]
    time_str = now.strftime("%I:%M %p")
    date_str = now.strftime("%d %B %Y")
    
    dynamic_prefix = (
        f"PENTING: Maklumat Waktu Semasa Sistem:\n"
        f"- Hari ini: {day_of_week}\n"
        f"- Tarikh hari ini: {date_str}\n"
        f"- Waktu sekarang: {time_str} (Waktu Malaysia, UTC+8)\n"
        f"Sila gunakan maklumat ini sebagai rujukan utama waktu/tarikh semasa.\n\n"
    )
    
    # Load Long-term Memory summary from SQLite database
    try:
        from memory import get_memory_summary
        ltm_summary = get_memory_summary()
        memory_block = ltm_summary + "\n\n"
    except Exception as e:
        logger.error(f"Failed to load long-term memory summary: {e}")
        memory_block = ""
        
    return dynamic_prefix + memory_block + SYSTEM_INSTRUCTIONS


def _build_gemini_config(conv_id: str | None) -> LocalAgentConfig:
    kwargs = dict(
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
        tools=[scrape_url, search_web, save_user_fact, update_user_preference],
        policies=[policy.allow_all()],
        system_instructions=_get_dynamic_instructions(),
    )
    if conv_id:
        kwargs["conversation_id"] = conv_id
    return LocalAgentConfig(**kwargs)


def _to_openai_tool(fn):
    """Converts Gemini uppercase type schema to OpenAI-compatible lowercase type schema."""
    decl = genai_types.FunctionDeclaration.from_callable_with_api_option(
        callable=fn,
        api_option="GEMINI_API"
    )
    schema = decl.parameters.model_dump(exclude_none=True) if decl.parameters else {"type": "OBJECT", "properties": {}}
    
    def _lowercase_types(node):
        if isinstance(node, dict):
            if "type" in node and isinstance(node["type"], str):
                node["type"] = node["type"].lower()
            for key, val in node.items():
                _lowercase_types(val)
        elif isinstance(node, list):
            for item in node:
                _lowercase_types(item)
                
    _lowercase_types(schema)
    return ToolWithSchema(fn, schema)


def _build_openrouter_config(conv_id: str | None) -> LocalOpenAIAgentConfig:
    kwargs = dict(
        model=OPENROUTER_FALLBACK_MODEL,
        base_url=OPENROUTER_BASE_URL,
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
        tools=[
            _to_openai_tool(scrape_url),
            _to_openai_tool(search_web),
            _to_openai_tool(save_user_fact),
            _to_openai_tool(update_user_preference),
        ],
        policies=[policy.allow_all()],
        system_instructions=_get_dynamic_instructions(),
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


# ─── Gemini Keys for Rotation ────────────────────────────────────────────────
GEMINI_KEYS = []
main_key = os.environ.get("GEMINI_API_KEY", "")
if main_key:
    GEMINI_KEYS.append(main_key)
for i in range(1, 11):
    val = os.environ.get(f"GEMINI_API_KEY_{i}", "")
    if val and val not in GEMINI_KEYS:
        GEMINI_KEYS.append(val)

# Default fallback if no keys configured
if not GEMINI_KEYS:
    GEMINI_KEYS.append("DUMMY_KEY")

current_key_idx = 0
logger.info(f"Loaded {len(GEMINI_KEYS)} Gemini API keys for rotation.")


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


# ─── OpenRouter Local Proxy ──────────────────────────────────────────────────

class OpenRouterProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        # Inject API Key from env
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        req = urllib.request.Request(
            url,
            data=post_data,
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                self.send_response(response.status)
                for key, val in response.headers.items():
                    if key.lower() not in ('content-encoding', 'transfer-encoding', 'connection'):
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(response.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress logging proxy requests to keep stdout clean
        pass


def _start_openrouter_proxy(port: int = 18080):
    server = HTTPServer(('127.0.0.1', port), OpenRouterProxyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _send_safe_message(text: str, max_length: int = 4000) -> str:
    """Guard Telegram message length to avoid BadRequest text too long errors."""
    if len(text) > max_length:
        return text[:max_length] + "\n\n⚠️ *(Respon dipotong kerana melebihi had Telegram)*"
    return text


async def _send_telegram_msg(update: Update, text: str, parse_mode: str = None):
    """Send Telegram message with markdown support, automatically falling back to plain text if parsing fails."""
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except BadRequest as e:
        if parse_mode and "can't parse entities" in str(e).lower():
            logger.warning(f"Telegram Markdown parsing failed, falling back to plain text. Error: {e}")
            await update.message.reply_text(text)
        else:
            raise e


def _get_platform_keyboard(state_data: dict) -> InlineKeyboardMarkup:

    selected = state_data.get("selected", [])
    platforms = [
        ("Facebook", "facebook"),
        ("X (Twitter)", "x"),
        ("Threads", "threads"),
        ("Lemon8", "lemon8"),
        ("Instagram", "instagram")
    ]
    
    keyboard = []
    row = []
    for label, val in platforms:
        status = "✅ " if val in selected else "⬜ "
        row.append(InlineKeyboardButton(f"{status}{label}", callback_data=f"toggle:{val}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("Next ➡️", callback_data="platform_next")])
    return InlineKeyboardMarkup(keyboard)


def _get_sub_options_keyboard(state_data: dict) -> InlineKeyboardMarkup:
    selected = state_data.get("selected", [])
    options = state_data.get("options", {})
    
    keyboard = []
    
    if "facebook" in selected:
        curr_fb = options.get("facebook", "")
        fb_bercerita_status = "✅ " if curr_fb == "bercerita" else "⬜ "
        fb_berita_status = "✅ " if curr_fb == "berita" else "⬜ "
        keyboard.append([
            InlineKeyboardButton(f"{fb_bercerita_status}FB: Bercerita 📖", callback_data="sub:fb:bercerita"),
            InlineKeyboardButton(f"{fb_berita_status}FB: Berita 📰", callback_data="sub:fb:berita")
        ])
        
    if "x" in selected:
        curr_x = options.get("x", "")
        keyboard.append([
            InlineKeyboardButton(f"{'✅ ' if curr_x == 3 else '⬜ '}X: 3 Twit", callback_data="sub:x:3"),
            InlineKeyboardButton(f"{'✅ ' if curr_x == 5 else '⬜ '}X: 5 Twit", callback_data="sub:x:5"),
            InlineKeyboardButton(f"{'✅ ' if curr_x == 8 else '⬜ '}X: 8 Twit", callback_data="sub:x:8")
        ])
        
    if "threads" in selected:
        curr_threads = options.get("threads", "")
        keyboard.append([
            InlineKeyboardButton(f"{'✅ ' if curr_threads == 3 else '⬜ '}Threads: 3 Post", callback_data="sub:threads:3"),
            InlineKeyboardButton(f"{'✅ ' if curr_threads == 5 else '⬜ '}Threads: 5 Post", callback_data="sub:threads:5"),
            InlineKeyboardButton(f"{'✅ ' if curr_threads == 8 else '⬜ '}Threads: 8 Post", callback_data="sub:threads:8")
        ])
        
    keyboard.append([InlineKeyboardButton("Generate Drafts ⚡", callback_data="sub_next")])
    return InlineKeyboardMarkup(keyboard)


async def _call_draft_generator_model(plat: str, draft: dict, fb_style: str = "", thread_length: int = 0) -> str:
    global current_key_idx
    style_instruction = ""
    if plat == "facebook":
        if fb_style == "bercerita":
            style_instruction = (
                "Tulis semula dalam gaya BERCERITA (Editorial). Ikuti peraturan berikut secara ketat:\n"
                "- Mulakan post dengan CTA HOOK yang sangat menarik dan berimpak tinggi untuk membuatkan pembaca berhenti skrol dan membaca.\n"
                "- Tulis kandungan dalam bentuk perenggan bercerita yang santai dan mengalir.\n"
                "- Di bahagian bawah sekali, letakkan hashtag yang relevan dan WAJIB sertakan hashtag: #saklumastory"
            )
        else:
            style_instruction = (
                "Tulis semula dalam gaya BERITA (News Report). Ikuti peraturan berikut secara ketat:\n"
                "- Mulakan perenggan pertama dengan format laporan berita Malaysia (cth: 'Kuala Lumpur - ...' atau 'Dungun - Seorang lelaki dipercayai...').\n"
                "- Gunakan laras bahasa pemberitaan yang formal tetapi mudah difahami.\n"
                "- Di bahagian bawah sekali, letakkan hashtag yang relevan dan WAJIB sertakan hashtag: #saklumanews"
            )
    elif plat in ["threads", "x"]:
        style_instruction = (
            f"Tulis semula dalam bentuk BEBENANG (Thread) sebanyak tepat {thread_length} bahagian (di-nombor sebagai 1/{thread_length}, 2/{thread_length}, ... hingga {thread_length}/{thread_length}).\n"
            f"- Terjemahkan fakta artikel asal kepada bahasa rojak santai Malaysia yang sangat mudah difahami oleh pelbagai kaum (Melayu, Cina, India).\n"
            f"- Jaga nada penulisan agar neutral (tidak berat sebelah).\n"
            f"- Selang-selikan maklumat dengan soalan ringkas kepada pembaca untuk memancing respon/komen (CTA), tetapi jangan buat pada setiap bahagian bebenang (cukup sekadar 1-2 soalan di tempat yang sesuai).\n"
            f"- Sertakan hashtag di bahagian akhir bebenang."
        )
    elif plat == "lemon8":
        style_instruction = (
            "Tulis semula untuk platform Lemon8. Gaya Lemon8 mestilah sangat aesthetic, berstruktur, bermaklumat, dan mempunyai huraian yang lebih panjang (detail) berserta emoji-emoji yang menarik."
        )
    elif plat in ["instagram", "ig"]:
        style_instruction = (
            "Tulis semula untuk Instagram. Gaya Instagram mestilah pendek, ringkas, padat, visual-driven, dan terus menarik minat pembaca."
        )

    prompt = (
        f"Anda adalah Editor Konten Sakluma. Tugas anda adalah menulis draf hantaran untuk platform {plat.upper()}.\n\n"
        f"ARAHAN KHAS GAYA PENULISAN:\n{style_instruction}\n\n"
        f"ARTIKEL ASAL:\n"
        f"Tajuk: {draft['title']}\n"
        f"Kandungan:\n{draft['master_article']}\n\n"
        f"Hashtags Asal: {draft['hashtags']}\n\n"
        f"Sila pulangkan draf hantaran untuk {plat.upper()} sahaja, tiada mukadimah, ulasan atau ulasan sampingan. Balas dengan format teks terus."
    )

    gemini_success = False
    response_text = ""
    num_keys = len(GEMINI_KEYS)

    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        os.environ["GEMINI_API_KEY"] = active_key

        try:
            logger.info(f"[Gemini] Generating platform draft using key index {current_key_idx}...")
            from google import genai
            client = genai.Client(api_key=active_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            response_text = response.text
            gemini_success = True
            break
        except Exception as gemini_err:
            if _is_rate_limit_error(gemini_err):
                logger.warning(f"[Gemini] Rate limit hit during draft. Rotating...")
                current_key_idx = (current_key_idx + 1) % num_keys
                continue
            else:
                logger.error(f"[Gemini] Draft generation error: {gemini_err}")
                break

    if not gemini_success and OPENROUTER_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": OPENROUTER_FALLBACK_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                response_text = data["choices"][0]["message"]["content"]
        except Exception as or_err:
            logger.error(f"[OpenRouter] Draft generation fallback error: {or_err}")
            return ""

    return response_text


async def _generate_all_platform_drafts(
    user_id: int, 
    chat_id: int, 
    selected_platforms: list, 
    options: dict, 
    draft: dict, 
    context, 
    message
):
    import memory
    import json
    
    generated_drafts = {}
    
    for plat in selected_platforms:
        fb_style = options.get("facebook", "") if plat == "facebook" else ""
        thread_length = options.get(plat, 0) if plat in ["x", "threads"] else 0
        
        draft_text = await _call_draft_generator_model(plat, draft, fb_style, thread_length)
        if draft_text:
            generated_drafts[plat] = draft_text
            
    # Save the drafts in SQLite
    memory.update_platform_draft(user_id, ",".join(selected_platforms), json.dumps(generated_drafts), state="")
    
    # Format a beautiful review message
    review_text = "✨ *DRAF MEDIA SOSIAL YANG DIJANA* ✨\n\n"
    
    keyboard = []
    for plat, text in generated_drafts.items():
        review_text += f"📱 *{plat.upper()}*:\n{text}\n\n"
        # Add a confirm button for this platform
        keyboard.append([InlineKeyboardButton(f"Confirm & Push {plat.upper()} ✅", callback_data=f"confirm_platform:{plat}")])
        
    review_text += "Sila klik butang di bawah untuk muat naik ke Google Drive & tolak ke Airtable."
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(review_text, parse_mode="Markdown", reply_markup=reply_markup)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    data = query.data

    import memory
    import json

    draft = memory.get_draft(user_id)
    if not draft:
        await query.message.reply_text("⚠️ Tiada draf aktif ditemui.")
        return

    state_str = draft.get("state") or "{}"
    try:
        state_data = json.loads(state_str)
    except Exception:
        state_data = {}

    if data.startswith("toggle:"):
        platform = data.split(":")[1]
        selected = state_data.get("selected", [])
        if platform in selected:
            selected.remove(platform)
        else:
            selected.append(platform)
        
        state_data["selected"] = selected
        new_state_str = json.dumps(state_data)
        
        memory.update_draft_state(user_id, new_state_str)
        
        reply_markup = _get_platform_keyboard(state_data)
        try:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Error editing reply markup: {e}")

    elif data == "platform_next":
        selected = state_data.get("selected", [])
        if not selected:
            await query.answer("Sila pilih sekurang-kurangnya satu platform! ⚠️", show_alert=True)
            return

        needs_sub = any(p in selected for p in ["facebook", "x", "threads"])
        if needs_sub:
            state_data["phase"] = "select_sub_options"
            state_data["options"] = state_data.get("options", {})
            
            if "facebook" in selected and "facebook" not in state_data["options"]:
                state_data["options"]["facebook"] = "bercerita"
            if "x" in selected and "x" not in state_data["options"]:
                state_data["options"]["x"] = 5
            if "threads" in selected and "threads" not in state_data["options"]:
                state_data["options"]["threads"] = 5

            new_state_str = json.dumps(state_data)
            memory.update_draft_state(user_id, new_state_str)
            
            reply_markup = _get_sub_options_keyboard(state_data)
            await query.message.reply_text(
                "Pilih pilihan sub-platform boss:",
                reply_markup=reply_markup
            )
        else:
            await query.message.reply_text("⏳ Menjana semua draf platform terpilih...")
            await _generate_all_platform_drafts(user_id, chat_id, selected, {}, draft, context, query.message)

    elif data.startswith("sub:"):
        parts = data.split(":")
        plat = parts[1]
        val = parts[2]
        if val.isdigit():
            val = int(val)

        options = state_data.get("options", {})
        options[plat] = val
        state_data["options"] = options
        
        new_state_str = json.dumps(state_data)
        memory.update_draft_state(user_id, new_state_str)
        
        reply_markup = _get_sub_options_keyboard(state_data)
        try:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Error editing reply markup for sub-options: {e}")

    elif data == "sub_next":
        selected = state_data.get("selected", [])
        options = state_data.get("options", {})
        
        await query.message.reply_text("⏳ Menjana semua draf platform terpilih...")
        await _generate_all_platform_drafts(user_id, chat_id, selected, options, draft, context, query.message)

    elif data.startswith("confirm_platform:"):
        parts = data.split(":")
        plat_to_confirm = parts[1]
        
        try:
            platform_drafts = json.loads(draft.get("platform_draft") or "{}")
        except Exception:
            platform_drafts = {}

        specific_draft = platform_drafts.get(plat_to_confirm, "")
        if not specific_draft:
            await query.answer("⚠️ Tiada draf dijumpai untuk platform ini.", show_alert=True)
            return

        await query.message.reply_text(f"🚀 Memulakan proses memuat naik gambar & menyimpan draf {plat_to_confirm.upper()} ke Airtable...")
        
        drive_link = ""
        image_url = draft["image_url"]
        if image_url:
            try:
                logger.info(f"Downloading main image from: {image_url}")
                async with httpx.AsyncClient(timeout=30) as client:
                    img_resp = await client.get(image_url)
                    img_resp.raise_for_status()
                    img_bytes = img_resp.content

                from tools import upload_to_drive
                filename = f"aura_{int(time.time())}.jpg"
                if ".png" in image_url.lower():
                    filename = f"aura_{int(time.time())}.png"
                    mime = "image/png"
                elif ".webp" in image_url.lower():
                    filename = f"aura_{int(time.time())}.webp"
                    mime = "image/webp"
                else:
                    mime = "image/jpeg"

                drive_res = upload_to_drive(img_bytes, filename, mime)
                if drive_res["status"] == "success":
                    drive_link = drive_res["link"]
                    logger.info(f"Image uploaded to Google Drive: {drive_link}")
                else:
                    logger.error(f"Google Drive upload failed: {drive_res.get('error')}")
            except Exception as e:
                logger.error(f"Failed to process image for Google Drive: {e}")

        from tools import save_draft_to_airtable
        final_image_url = drive_link if drive_link else image_url

        res = save_draft_to_airtable(
            title=draft["title"],
            caption=specific_draft,
            platform=plat_to_confirm,
            source_url=draft["source_url"],
            image_url=final_image_url,
            status="Draft",
            hashtags=draft["hashtags"]
        )

        if res["status"] == "success":
            platform_drafts.pop(plat_to_confirm, None)
            if platform_drafts:
                memory.update_platform_draft(user_id, draft["selected_platform"], json.dumps(platform_drafts), state="")
            else:
                memory.clear_draft(user_id)
                
            reply_msg = (
                f"✅ *Draf Hantaran {plat_to_confirm.upper()} Berjaya Disahkan!*\n\n"
                f"• *Tajuk*: {draft['title']}\n"
                f"• *Platform*: {plat_to_confirm.upper()}\n"
                f"• *Google Drive File*: {f'[Buka Gambar]({drive_link})' if drive_link else 'Tiada / Gagal diupload'}\n"
                f"• *Airtable Record*: Berjaya disimpan [Content Station] (Status: Draft) ✈️\n\n"
                f"Semua draf telah berjaya masuk ke Airtable! Yeayy! 🎉"
            )
            await query.message.reply_text(reply_msg, parse_mode="Markdown")
        else:
            await query.message.reply_text(f"⚠️ Gagal menyimpan ke Airtable: {res.get('error')}")


async def _process_response_draft(user_id: int, chat_id: int, response_text: str, context, update) -> str:
    """Parse draft metadata tags from response_text, save the draft in SQLite,
    send the preview image to Telegram, and return the cleaned response text."""
    import re
    import memory
    import json

    image_match = re.search(r"\[DRAFT_IMAGE:\s*(https?://[^\s\]]+)\]", response_text, re.IGNORECASE)
    title_match = re.search(r"\[DRAFT_TITLE:\s*(.+?)\]", response_text, re.IGNORECASE)
    source_match = re.search(r"\[DRAFT_SOURCE_URL:\s*(https?://[^\s\]]+)\]", response_text, re.IGNORECASE)
    master_match = re.search(r"\[DRAFT_MASTER_ARTICLE:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
    hashtags_match = re.search(r"\[DRAFT_HASHTAGS:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)

    if title_match or master_match:
        image_url = image_match.group(1).strip() if image_match else ""
        title = title_match.group(1).strip() if title_match else "Artikel Tanpa Tajuk"
        source_url = source_match.group(1).strip() if source_match else ""
        master_article = master_match.group(1).strip() if master_match else ""
        hashtags = hashtags_match.group(1).strip() if hashtags_match else ""

        # Save draft in SQLite with interactive state: select_platforms
        initial_state = json.dumps({"phase": "select_platforms", "selected": []})
        memory.save_draft(
            user_id=user_id,
            title=title,
            master_article=master_article,
            hashtags=hashtags,
            image_url=image_url,
            source_url=source_url,
            state=initial_state
        )
        logger.info(f"Saved content draft for user {user_id}: {title}")

        # Send image to Telegram first as a preview
        if image_url:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=image_url)
            except Exception as e:
                logger.warning(f"Could not send photo preview: {e}")

        # Clean response_text from these tags
        clean_text = response_text
        clean_text = re.sub(r"\[DRAFT_IMAGE:\s*https?://[^\s\]]+\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_TITLE:\s*.+?\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_SOURCE_URL:\s*https?://[^\s\]]+\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_MASTER_ARTICLE:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r"\[DRAFT_HASHTAGS:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)

        # Prepare platform inline keyboard
        clean_text = clean_text.strip()
        reply_markup = _get_platform_keyboard({"selected": []})
        
        await update.message.reply_text(
            clean_text, 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
        
        return "[DRAFT_SENT_WITH_KEYBOARD]"

    return response_text

async def _parse_schedule_time(natural_text: str) -> Optional[str]:
    """Parse Malaysian/English natural language dates (e.g. 'esok 10 pagi')
    to ISO 8601 UTC+8 format using a quick Gemini model call."""
    global current_key_idx
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    day_name = datetime.datetime.now().strftime("%A")
    prompt = (
        f"Tukarkan tarikh/masa dalam bahasa semula jadi berikut ke dalam format ISO 8601 (tarikh dan masa penuh, cth: '2026-07-15T14:30:00+08:00' - gunakan zon waktu Asia/Kuala Lumpur UTC+8).\n"
        f"Waktu sistem sekarang (UTC+8): {now_str}\n"
        f"Hari ini adalah hari: {day_name}\n\n"
        f"Input tarikh dari user: \"{natural_text}\"\n\n"
        f"Sila pulangkan tarikh hasil tukaran sahaja dalam format ISO 8601 (YYYY-MM-DDTHH:MM:SS+08:00). JANGAN letak sebarang perkataan lain, markdown, atau ulasan. Jika tidak sah atau gagal tukar, balas dengan 'NONE'."
    )

    gemini_success = False
    response_text = ""
    num_keys = len(GEMINI_KEYS)

    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        os.environ["GEMINI_API_KEY"] = active_key

        try:
            from google import genai
            client = genai.Client(api_key=active_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            response_text = response.text.strip()
            gemini_success = True
            break
        except Exception as e:
            if _is_rate_limit_error(e):
                current_key_idx = (current_key_idx + 1) % num_keys
                continue
            else:
                logger.error(f"[Gemini] Error parsing schedule time: {e}")
                break

    if not gemini_success and OPENROUTER_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": OPENROUTER_FALLBACK_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                if resp.status_code == 200:
                    response_text = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"[OpenRouter] Error parsing schedule time fallback: {e}")

    if response_text and response_text.upper() != "NONE":
        # Extract ISO string using regex if model wraps it in tags
        iso_match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?)", response_text)
        if iso_match:
            return iso_match.group(1)
    return None



async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    import memory
    draft = memory.get_draft(user_id)
    if not draft:
        await update.message.reply_text("⚠️ Tiada draf aktif dijumpai. Sila paste link artikel terlebih dahulu untuk membuat draf baru.")
        return

    title = draft["title"]
    master_article = draft["master_article"]
    hashtags = draft["hashtags"]
    image_url = draft["image_url"]
    source_url = draft["source_url"]
    selected_platform = draft["selected_platform"]
    platform_draft = draft["platform_draft"]

    if not selected_platform or not platform_draft:
        await update.message.reply_text("⚠️ Sila pilih platform draf terlebih dahulu (cth: taip 'Facebook', 'Threads', 'X', atau 'Lemon8') sebelum melakukan pengesahan.")
        return

    # Check if user message contains scheduling request
    user_text = update.message.text or ""
    schedule_match = re.search(r"(?:schedule|scheduling|tarikh|masa|pukul|jam)\s+(.+)", user_text, re.IGNORECASE)
    scheduled_time_iso = ""
    status = "Draft"

    if schedule_match:
        natural_time = schedule_match.group(1).strip()
        await update.message.reply_text(f"⏳ Meneliti tarikh penjadualan: \"{natural_time}\"...")
        parsed_iso = await _parse_schedule_time(natural_time)
        if parsed_iso:
            scheduled_time_iso = parsed_iso
            status = "Scheduled"
            logger.info(f"Parsed schedule time for user {user_id}: {scheduled_time_iso}")
        else:
            await update.message.reply_text("⚠️ Format tarikh/masa tidak dicam. Hantaran akan dimasukkan ke Airtable dengan status 'Draft' tanpa jadual.")

    # 1. Download image and upload to Google Drive
    drive_link = ""
    if image_url:
        try:
            logger.info(f"Downloading main image from: {image_url}")
            async with httpx.AsyncClient(timeout=30) as client:
                img_resp = await client.get(image_url)
                img_resp.raise_for_status()
                img_bytes = img_resp.content

            from tools import upload_to_drive
            filename = f"aura_{int(time.time())}.jpg"
            if ".png" in image_url.lower():
                filename = f"aura_{int(time.time())}.png"
                mime = "image/png"
            elif ".webp" in image_url.lower():
                filename = f"aura_{int(time.time())}.webp"
                mime = "image/webp"
            else:
                mime = "image/jpeg"

            drive_res = upload_to_drive(img_bytes, filename, mime)
            if drive_res["status"] == "success":
                drive_link = drive_res["link"]
                logger.info(f"Image uploaded to Google Drive: {drive_link}")
            else:
                logger.error(f"Google Drive upload failed: {drive_res.get('error')}")
        except Exception as e:
            logger.error(f"Failed to process image for Google Drive: {e}")

    # 2. Save the draft to Airtable
    from tools import save_draft_to_airtable
    final_image_url = drive_link if drive_link else image_url

    res = save_draft_to_airtable(
        title=title,
        caption=platform_draft,
        platform=selected_platform,
        source_url=source_url,
        image_url=final_image_url,
        status=status,
        hashtags=hashtags,
        scheduled_time=scheduled_time_iso
    )

    if res["status"] == "success":
        # Clear draft on success
        memory.clear_draft(user_id)
        
        sched_info = f"• *Status*: Scheduled 📅\n• *Tarikh Siaran*: {scheduled_time_iso}" if status == "Scheduled" else "• *Status*: Draft (Sedia Berlepas) ✈️"
        
        reply_msg = (
            f"✅ *Draf Hantaran {selected_platform.upper()} Berjaya Disahkan!*\n\n"
            f"• *Tajuk*: {title}\n"
            f"• *Platform*: {selected_platform.upper()}\n"
            f"{sched_info}\n"
            f"• *Google Drive File*: {f'[Buka Gambar]({drive_link})' if drive_link else 'Tiada / Gagal diupload'}\n"
            f"• *Airtable Record*: Berjaya disimpan [Content Station]\n\n"
            f"Sedia untuk fasa posting!"
        )
        await _send_telegram_msg(update, reply_msg, parse_mode="Markdown")
    else:
        await _send_telegram_msg(update, f"⚠️ Gagal menyimpan ke Airtable: {res.get('error')}")




async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_key_idx
    user_message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    is_debug = DEBUG_USERS.get(user_id, False)

    if user_message:
        msg_clean = user_message.strip().lower()
        if msg_clean.startswith("confirm") or msg_clean.startswith("/confirm"):
            await confirm_command(update, context)
            return


    await context.bot.send_chat_action(chat_id=chat_id, action="typing")




    conv_id = _get_conv_id_for_user(user_id)

    gemini_success = False
    response_text = ""
    num_keys = len(GEMINI_KEYS)

    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        os.environ["GEMINI_API_KEY"] = active_key
        gemini_config = _build_gemini_config(conv_id)

        try:
            logger.info(f"[Gemini] Attempting chat using key index {current_key_idx}/{num_keys}...")
            async with Agent(gemini_config) as agent:
                response = await agent.chat(user_message)
                response_text = await response.text()

                if not conv_id:
                    new_id = agent.conversation_id
                    if new_id:
                        _register_conv_id_for_user(user_id, new_id)
                        logger.info(f"[Gemini] New session for user {user_id}: {new_id}")
            gemini_success = True
            break
        except Exception as gemini_err:
            if _is_rate_limit_error(gemini_err):
                logger.warning(f"[Gemini] Rate limit hit for key index {current_key_idx}. Rotating...")
                current_key_idx = (current_key_idx + 1) % num_keys
                continue
            else:
                logger.error(f"[Gemini] Error for user {user_id}: {gemini_err}", exc_info=True)
                await _send_telegram_msg(update, _send_safe_message(f"⚠️ Ralat berlaku: {str(gemini_err)}"))
                return

    if gemini_success:
        response_text = await _process_response_draft(user_id, chat_id, response_text, context, update)
        if response_text == "[DRAFT_SENT_WITH_KEYBOARD]":
            return
        if is_debug:
            final_text = _send_safe_message(f"🔧 *\\[DEBUG: Gemini\\]*\n\n{response_text}")
            await _send_telegram_msg(update, final_text, parse_mode="MarkdownV2")
        else:
            await _send_telegram_msg(update, _send_safe_message(_clean_response(response_text)), parse_mode="Markdown")
        return



    # If we reach here, all Gemini free keys hit rate limits. Fallback to OpenRouter.
    logger.warning(f"[Gemini] All {num_keys} keys rate limited. Switching to OpenRouter...")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Attempt 2: OpenRouter Fallback ────────────────────────────────────────
    if not OPENROUTER_API_KEY:
        await update.message.reply_text(
            "⚠️ Gemini telah mencapai had penggunaan dan OPENROUTER_API_KEY tidak dikonfigurasi."
        )
        return

    or_config = _build_openrouter_config(conv_id)

    try:
        async with Agent(or_config) as agent:
            response = await agent.chat(user_message)
            response_text = await response.text()

            if not conv_id:
                new_id = agent.conversation_id
                if new_id:
                    _register_conv_id_for_user(user_id, new_id)
                    logger.info(f"[OpenRouter] New session for user {user_id}: {new_id}")

        response_text = await _process_response_draft(user_id, chat_id, response_text, context, update)
        if response_text == "[DRAFT_SENT_WITH_KEYBOARD]":
            return
        if is_debug:
            final_text = _send_safe_message(f"🔧 *[DEBUG: OpenRouter — {OPENROUTER_FALLBACK_MODEL}]*\n\n{response_text}")
            await _send_telegram_msg(update, final_text, parse_mode="Markdown")
        else:
            clean = _clean_response(response_text)
            final_text = _send_safe_message(f"_({OPENROUTER_FALLBACK_MODEL})_\n\n{clean}")
            await _send_telegram_msg(update, final_text, parse_mode="Markdown")




    except Exception as or_err:
        logger.error(f"[OpenRouter] Fallback error for user {user_id}: {or_err}", exc_info=True)
        err_msg = _send_safe_message(
            f"⚠️ Kedua-dua model gagal:\n• Gemini: Had penggunaan\n• OpenRouter: {str(or_err)}"
        )
        await _send_telegram_msg(update, err_msg)



# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not configured in the .env file.")
        return

    # Start local OpenRouter reverse proxy to inject API keys in localharness requests
    logger.info("Starting local OpenRouter reverse proxy on port 18080...")
    _start_openrouter_proxy(port=18080)

    # Initialize SQLite long-term memory database
    try:
        from memory import init_db
        init_db()
        logger.info("Long-term SQLite memory database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize long-term memory database on startup: {e}")


    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(CommandHandler("confirm", confirm_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))



    logger.info(f"AURA Bot starting. Primary: Gemini | Fallback: OpenRouter ({OPENROUTER_FALLBACK_MODEL})")
    application.run_polling()


if __name__ == '__main__':
    main()
