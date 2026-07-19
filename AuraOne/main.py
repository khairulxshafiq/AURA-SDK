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

from tools import scrape_url, search_web, save_user_fact, update_user_preference, run_apify_actor

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
        tools=[scrape_url, search_web, save_user_fact, update_user_preference, run_apify_actor],
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
            _to_openai_tool(run_apify_actor),
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
    target_parse_mode = parse_mode
    target_text = text
    
    if parse_mode in ["Markdown", "MarkdownV2", "markdown", "markdownv2"]:
        import re
        import html
        
        # Escape HTML characters first
        escaped = html.escape(text)
        
        # Convert **bold** to <b>bold</b>
        escaped = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
        
        # Convert [text](url) to <a href="url">text</a>
        escaped = re.sub(r"\[(.*?)\]\((https?://.*?)\)", r'<a href="\2">\1</a>', escaped)
        
        target_text = escaped
        target_parse_mode = "HTML"

    thread_id = None
    if update.message:
        thread_id = getattr(update.message, "message_thread_id", None)
    elif update.callback_query and update.callback_query.message:
        thread_id = getattr(update.callback_query.message, "message_thread_id", None)

    try:
        if update.message:
            await update.message.reply_text(target_text, parse_mode=target_parse_mode, message_thread_id=thread_id)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(target_text, parse_mode=target_parse_mode, message_thread_id=thread_id)
    except BadRequest as e:
        logger.warning(f"Telegram parse mode {target_parse_mode} failed. Falling back to plain text. Error: {e}")
        try:
            if update.message:
                await update.message.reply_text(text, message_thread_id=thread_id)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(text, message_thread_id=thread_id)
        except Exception as fallback_err:
            logger.error(f"Fallback text send failed: {fallback_err}")



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
        curr_fb = options.get("facebook", "viral_santai")
        personas = [
            ("berita", "FB: Berita 📰"),
            ("pemerhati", "FB: Pemerhati 👀"),
            ("kedai_kopi", "FB: Kedai Kopi ☕"),
            ("viral_santai", "FB: Viral Santai 🔥"),
            ("makcik_bawang", "FB: Makcik Bawang 😆"),
            ("kisah_inspirasi", "FB: Kisah Inspirasi ❤️"),
            ("borak_kawan", "FB: Borak Kawan 🫱🏻🫲🏻")
        ]
        
        row = []
        for code, label in personas:
            status = "✅ " if curr_fb == code else "⬜ "
            row.append(InlineKeyboardButton(f"{status}{label}", callback_data=f"sub:facebook:{code}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
    if "x" in selected or "threads" in selected:
        curr_len = options.get("thread_len", 5)
        keyboard.append([
            InlineKeyboardButton(f"{'✅ ' if curr_len == 3 else '⬜ '}Bebenang: 3 Post", callback_data="sub:thread_len:3"),
            InlineKeyboardButton(f"{'✅ ' if curr_len == 5 else '⬜ '}Bebenang: 5 Post", callback_data="sub:thread_len:5"),
            InlineKeyboardButton(f"{'✅ ' if curr_len == 8 else '⬜ '}Bebenang: 8 Post", callback_data="sub:thread_len:8")
        ])
        
    keyboard.append([InlineKeyboardButton("Generate Drafts ⚡", callback_data="sub_next")])
    return InlineKeyboardMarkup(keyboard)


async def _call_draft_generator_model(plat: str, draft: dict, fb_style: str = "", thread_length: int = 0) -> str:
    global current_key_idx
    style_instruction = ""
    if plat == "facebook":
        if fb_style == "berita":
            style_instruction = (
                "Tulis semula dalam gaya BERITA (News Report). Ikuti peraturan berikut secara ketat:\n"
                "- Mulakan perenggan pertama dengan format laporan berita Malaysia (cth: 'Kuala Lumpur - ...' atau 'Dungun - Seorang lelaki dipercayai...').\n"
                "- Gunakan laras bahasa pemberitaan yang formal tetapi mudah difahami.\n"
                "- JANGAN gunakan sebarang tulisan bold (cth: **teks**). Tulis semuanya dalam teks biasa.\n"
                "- Gunakan sedikit hashtag sahaja (maksimum 2), contohnya: #saklumanews #saklumaprihatin. Tiada hashtag yang panjang lebar."
            )
        elif fb_style == "pemerhati":
            style_instruction = (
                "Anda ialah seorang pemerhati masyarakat. Ikuti peraturan berikut secara ketat:\n"
                "- JANGAN menulis seperti wartawan atau portal berita formal.\n"
                "- JANGAN tulis fakta berita di awal perenggan. Mulakan dengan perkara paling menarik yang anda nampak berdasarkan kisah ini.\n"
                "- Gunakan ayat pendek dan gaya bahasa manusia biasa yang berkongsi pemerhatian di Facebook.\n"
                "- Formula: Apa aku nampak -> Apa yang menarik -> Apa yang kita boleh belajar -> Penutup ringkas.\n"
                "- Nada: Santai, ringkas, human, berbentuk refleksi, tidak terlalu emosional atau dramatik.\n"
                "- JANGAN gunakan sebarang tulisan bold (cth: **teks**).\n"
                "- Hadkan panjang draf sekitar 80–150 patah perkataan.\n"
                "- Gunakan sedikit hashtag sahaja (maksimum 2), contohnya: #saklumanews #saklumaprihatin. Tiada hashtag yang panjang lebar."
            )
        elif fb_style == "kedai_kopi":
            style_instruction = (
                "Anda ialah seorang pengguna Facebook yang berkongsi pendapat peribadi (Opinion Mode). Ikuti peraturan berikut secara ketat:\n"
                "- JANGAN menjadi neutral seperti wartawan. Berikan pandangan peribadi yang tegas dan berani berdasarkan fakta kisah ini.\n"
                "- Gunakan laras bahasa rakyat biasa dan ayat-ayat pendek yang mudah dihadam.\n"
                "- JANGAN mengulang kata pemula pendapat yang sama di dalam satu post (cth: jangan mulakan perenggan pertama dengan 'Pada aku' dan perenggan seterusnya dengan 'Bagi aku'). Pelbagaikan gaya bahasa agar tidak berulang.\n"
                "- Gunakan ungkapan ekspresif masyarakat yang santai tetapi menarik ('ayat bombastik masyarakat') seperti: 'Sampai bila nak...', 'Cuba bayangkan...', 'Aduh, pening kepala...', 'Persoalannya...', 'Hakikatnya...', 'Benda macam ni tak sepatutnya...'.\n"
                "- Formula: Pendirian -> Bukti -> Pemerhatian -> Penutup.\n"
                "- Nada: Santai, berani, ekspresif, tidak kasar, tidak provokatif.\n"
                "- JANGAN gunakan sebarang tulisan bold (cth: **teks**).\n"
                "- Hadkan panjang draf sekitar 100–200 patah perkataan.\n"
                "- Gunakan sedikit hashtag sahaja (maksimum 2), contohnya: #saklumanews #saklumaprihatin. Tiada hashtag yang panjang lebar."
            )
        elif fb_style == "makcik_bawang":
            style_instruction = (
                "Tulis seperti pengguna Facebook (Makcik Bawang Premium) yang sedang berkongsi berita viral kepada rakan-rakan. Ikuti peraturan berikut secara ketat:\n"
                "- Mulakan dengan HOOK pendek yang dramatik/selamba (cth: 'Wehh.', 'Eh.', 'Serius la.', 'Aku je ke rasa pelik?').\n"
                "- JANGAN menulis seperti wartawan, jangan ulang tajuk berita, jangan tulis terlalu panjang.\n"
                "- Berikan reaksi manusia yang kelakar/selamba/terkejut terhadap kisah/berita ini.\n"
                "- Pilih hanya 2-4 fakta paling menarik untuk diulas.\n"
                "- Akhiri dengan soalan kepada audiens untuk memancing komen (cth: 'Korang rasa macam mana?', 'Kalau jadi dekat korang?').\n"
                "- JANGAN gunakan sebarang tulisan bold (cth: **teks**).\n"
                "- Hadkan panjang draf sekitar 80-150 patah perkataan.\n"
                "- Gunakan sedikit hashtag sahaja (maksimum 2), contohnya: #saklumanews #saklumaprihatin."
            )
        elif fb_style == "kisah_inspirasi":
            style_instruction = (
                "Tulis dalam gaya yang menyentuh hati dan memberi inspirasi kepada pembaca. Ikuti peraturan berikut secara ketat:\n"
                "- Fokus kepada perjuangan, kejayaan, kebaikan manusia, atau nilai murni yang terdapat dalam kisah ini.\n"
                "- Nada: Hangat, prihatin, menyentuh jiwa, positif.\n"
                "- JANGAN menulis seperti portal berita formal. Gunakan bahasa santai Malaysia yang ikhlas dan menyentuh emosi pembaca.\n"
                "- Akhiri dengan pengajaran positif atau kata-kata semangat.\n"
                "- JANGAN gunakan sebarang tulisan bold (cth: **teks**).\n"
                "- Hadkan panjang draf sekitar 80-150 patah perkataan.\n"
                "- Gunakan sedikit hashtag sahaja (maksimum 2), contohnya: #saklumainspirasi #saklumaprihatin."
            )
        elif fb_style == "borak_kawan":
            style_instruction = (
                "Anda sedang bercerita kepada kawan-kawan Facebook secara terus terang (Coffee Talk). Ikuti peraturan berikut secara ketat:\n"
                "- Tulis seperti sembang santai di kedai kopi.\n"
                "- Boleh guna kata seru seperti: 'Wehh', 'Ohoiii', 'Hahaha', 'Tengok ni', 'Aku rasa', 'Korang perasan tak'.\n"
                "- Gunakan ayat pendek. Tidak perlu terlalu tersusun. Boleh ada gurauan ringan.\n"
                "- Fokus kepada pengalaman manusia dan cerita kecil dalam kehidupan daripada kisah tersebut.\n"
                "- Formula: Reaction -> Cerita -> Observation -> Penutup santai.\n"
                "- JANGAN gunakan sebarang tulisan bold (cth: **teks**).\n"
                "- Hadkan panjang draf sekitar 50–120 patah perkataan.\n"
                "- Gunakan sedikit hashtag sahaja (maksimum 2), contohnya: #saklumanews #saklumaprihatin."
            )
        else: # Default is viral_santai
            style_instruction = (
                "Tulis seperti pengguna Facebook Malaysia yang sedang berkongsi berita viral kepada rakan-rakan. Ikuti peraturan berikut secara ketat:\n"
                "- JANGAN menulis seperti wartawan atau portal berita. JANGAN ulang tajuk berita.\n"
                "- Formula:\n"
                "  1. Mulakan dengan HOOK pendek (contoh: 'Wehh.', 'Eh.', 'Serius la.', 'Korang tengok ni.', 'Aku respect part ni.').\n"
                "  2. Beri reaksi manusia terhadap berita.\n"
                "  3. Pilih hanya 2-4 fakta paling menarik.\n"
                "  4. Tambahkan pandangan santai atau refleksi kehidupan.\n"
                "  5. Akhiri dengan soalan untuk engagement.\n"
                "- Gaya bahasa: Bahasa Malaysia santai, ayat pendek, human, Facebook style, sedikit emosi dan reaksi, tidak terlalu formal.\n"
                "- JANGAN gunakan sebarang tulisan bold (cth: **teks**).\n"
                "- Hadkan panjang draf sekitar 80-150 patah perkataan.\n"
                "- Gunakan sedikit hashtag sahaja (maksimum 2), contohnya: #saklumanews #saklumaprihatin."
            )
    elif plat in ["threads", "x"]:
        # Translate global persona style to fast-paced X/Threads equivalent
        style_title = fb_style.upper()
        if fb_style == "makcik_bawang":
            style_title = "GENZ BAWANG (Gossipy, fast-paced Gen Z style)"
            style_details = (
                "- Gunakan gaya 'GenZ Bawang' yang sangat laju dan santai (gaya gosip Gen Z: 'weh', 'gila ah', 'spill the tea', 'kantoi', 'serius lah').\n"
                "- Hook gempak di post pertama untuk tangkap perhatian dalam 2.9 saat!"
            )
        elif fb_style == "kedai_kopi":
            style_details = (
                "- Gaya sembang kedai kopi/pendapat ringkas yang berani, terus ke point, dan tidak neutral.\n"
                "- Gunakan ungkapan rakyat Malaysia yang ringkas ('Pada aku', 'Persoalannya', 'Sampai bila')."
            )
        elif fb_style == "pemerhati":
            style_details = (
                "- Gaya pemerhati masyarakat. Post pertama mulakan dengan pemerhatian visual yang menarik, bukan fakta berita.\n"
                "- Kongsi moral/pengajaran hidup secara santai di post akhir."
            )
        elif fb_style == "viral_santai":
            style_details = (
                "- Gaya viral sempoi dengan hook padat di post pertama ('Wehh.', 'Korang tengok ni.').\n"
                "- Tulis seperti kawan kongsi cerita viral."
            )
        elif fb_style == "borak_kawan":
            style_details = (
                "- Gaya sembang kedai kopi paling santai ('Wehh', 'Hahaha', 'Aku rasa'). Tidak tersusun tetapi sangat human."
            )
        elif fb_style == "kisah_inspirasi":
            style_details = (
                "- Gaya menyentuh hati dan inspirasi ringkas yang positif."
            )
        else: # berita atau default
            style_details = (
                "- Gaya penyampaian berita ringkas, santai, dan padat."
            )

        # Image placement position: 2 if thread length is 3, else 3
        img_pos = 2 if thread_length == 3 else 3

        style_instruction = (
            f"Tulis semula dalam bentuk BEBENANG (Thread) {plat.upper()} sebanyak tepat {thread_length} perenggan/bahagian.\n"
            f"Gunakan gaya persona: {style_title}.\n"
            f"PERATURAN BEBENANG LAJU & HUMAN (Maksimum perhatian 2.9 saat):\n"
            f"1. Post pertama (Thread #1) WAJIB berupa HOOK yang sangat pendek, padat, dan mencuri perhatian pembaca dengan pantas. Jangan tulis panjang lebar di post pertama!\n"
            f"{style_details}\n"
            f"2. JANGAN sesekali meletakkan nombor bahagian seperti '1/{thread_length}', '1.', atau sebarang indeks nombor di permulaan perenggan. Mulakan setiap bahagian/perenggan secara terus dengan teks bersih.\n"
            f"3. WAJIB letakkan tag '[ATTACH_IMAGE]' secara literal di hujung draf Post #{img_pos} sahaja (Post #2 untuk bebenang 3, Post #3 untuk bebenang 5 atau 8) untuk menandakan kedudukan gambar.\n"
            f"4. Bahasa: Terjemahkan fakta kepada bahasa rojak santai Malaysia yang sangat mudah difahami dan humanized.\n"
            f"5. JANGAN gunakan sebarang tulisan bold (cth: **teks**). Tulis semuanya dalam teks biasa.\n"
            f"6. Akhiri post terakhir dengan CTA/soalan santai pendek untuk memancing komen audiens."
        )
    elif plat == "lemon8":
        style_instruction = (
            "Tulis semula untuk platform Lemon8. Gaya Lemon8 mestilah sangat aesthetic, berstruktur, bermaklumat, dan mempunyai huraian yang lebih panjang (detail) berserta emoji-emoji yang menarik.\n"
            "JANGAN gunakan sebarang tulisan bold (cth: **teks**) di dalam draf ini. Tulis semuanya dalam teks biasa."
        )
    elif plat in ["instagram", "ig"]:
        style_instruction = (
            "Tulis semula untuk Instagram. Gaya Instagram mestilah pendek, ringkas, padat, visual-driven, dan terus menarik minat pembaca.\n"
            "JANGAN gunakan sebarang tulisan bold (cth: **teks**) di dalam draf ini. Tulis semuanya dalam teks biasa."
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
        fb_style = options.get("facebook", "viral_santai")
        thread_length = options.get("thread_len", 5) if plat in ["x", "threads"] else 0
        
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
                state_data["options"]["facebook"] = "viral_santai"
            if ("x" in selected or "threads" in selected) and "thread_len" not in state_data["options"]:
                state_data["options"]["thread_len"] = 5


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

        await query.message.reply_text(f"🚀 Menyimpan draf {plat_to_confirm.upper()} ke Airtable...")
        
        image_url = draft["image_url"]
        telegram_file_id = draft.get("telegram_file_id", "")
        counter = draft.get("counter_val", 0)
        final_image_url = await _prepare_drive_image_for_airtable(image_url, telegram_file_id, counter, context)
        from tools import save_draft_to_airtable

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
            thread_saved_status = ""
            if plat_to_confirm.lower() in ["x", "twitter", "threads"]:
                posts = [p.strip() for p in specific_draft.split("\n\n") if p.strip()]
                if len(posts) > 1:
                    from tools import save_thread_posts_to_airtable
                    thread_res = save_thread_posts_to_airtable(
                        parent_record_id=res["record_id"],
                        posts=posts,
                        platform=plat_to_confirm
                    )
                    if thread_res["status"] == "success":
                        thread_saved_status = f"\n• *Thread Posts*: Berjaya dipecahkan kepada {len(posts)} bahagian di jadual [Thread Posts]! 🧵"
                    else:
                        thread_saved_status = (
                            f"\n⚠️ *Pecahan Bebenang*: Gagal disimpan ke jadual 'Thread Posts' ({thread_res.get('error')}). "
                            "Sila pastikan anda telah mencipta jadual 'Thread Posts' dengan kolum: "
                            "Content Station (Link), Post Text (Long Text), Sequence (Number), dan Platform (Select)."
                        )

            platform_drafts.pop(plat_to_confirm, None)
            if platform_drafts:
                memory.update_platform_draft(user_id, draft["selected_platform"], json.dumps(platform_drafts), state="")
            else:
                memory.clear_draft(user_id)
                
            reply_msg = (
                f"✅ *Draf Hantaran {plat_to_confirm.upper()} Berjaya Disahkan!*\n\n"
                f"• *Tajuk*: {draft['title']}\n"
                f"• *Platform*: {plat_to_confirm.upper()}\n"
                f"• *Airtable Record*: Berjaya disimpan [Content Station] (Status: Draft) ✈️{thread_saved_status}\n\n"
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
    type_match = re.search(r"\[DRAFT_CONTENT_TYPE:\s*(.+?)\]", response_text, re.IGNORECASE)
    price_match = re.search(r"\[DRAFT_ORIGINAL_PRICE:\s*(.+?)\]", response_text, re.IGNORECASE)
    location_match = re.search(r"\[DRAFT_SELLER_LOCATION:\s*(.+?)\]", response_text, re.IGNORECASE)

    if title_match or master_match:
        image_url = image_match.group(1).strip() if image_match else ""
        title = title_match.group(1).strip() if title_match else "Artikel Tanpa Tajuk"
        source_url = source_match.group(1).strip() if source_match else ""
        master_article = master_match.group(1).strip() if master_match else ""
        hashtags = hashtags_match.group(1).strip() if hashtags_match else ""

        # Increment standard image/article counter in SQLite
        import memory
        prefs = memory.get_preferences()
        counter_str = prefs.get("image_counter", "0")
        try:
            counter = int(counter_str)
        except ValueError:
            counter = 0
        counter += 1
        memory.update_preference("image_counter", str(counter))

        telegram_file_id = ""
        # Send image to Telegram first as a preview and cache its Telegram file_id
        if image_url:
            try:
                photo_msg = await context.bot.send_photo(chat_id=chat_id, photo=image_url)
                if photo_msg and photo_msg.photo:
                    telegram_file_id = photo_msg.photo[-1].file_id
                    logger.info(f"Successfully sent preview. Cached Telegram file_id: {telegram_file_id}")
            except Exception as e:
                logger.warning(f"Could not send photo preview: {e}")

        # Save draft in SQLite with interactive state: select_platforms & metadata
        state_dict = {
            "phase": "select_platforms",
            "selected": [],
            "shopee_metadata": {
                "content_type": type_match.group(1).strip() if type_match else "Article",
                "original_price": price_match.group(1).strip() if price_match else "",
                "seller_location": location_match.group(1).strip() if location_match else ""
            }
        }
        initial_state = json.dumps(state_dict)
        memory.save_draft(
            user_id=user_id,
            title=title,
            master_article=master_article,
            hashtags=hashtags,
            image_url=image_url,
            telegram_file_id=telegram_file_id,
            counter_val=counter,
            source_url=source_url,
            state=initial_state
        )
        logger.info(f"Saved content draft for user {user_id}: {title} (counter_val={counter})")

        # Upload text dump to GitHub in the background
        import threading
        threading.Thread(
            target=_upload_article_dump_to_github,
            args=(title, master_article, hashtags, source_url, response_text, counter),
            daemon=True
        ).start()



        # Clean response_text from these tags
        clean_text = response_text
        clean_text = re.sub(r"\[DRAFT_IMAGE:\s*https?://[^\s\]]+\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_TITLE:\s*.+?\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_SOURCE_URL:\s*https?://[^\s\]]+\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_MASTER_ARTICLE:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r"\[DRAFT_HASHTAGS:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r"\[DRAFT_CONTENT_TYPE:\s*.+?\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_ORIGINAL_PRICE:\s*.+?\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_SELLER_LOCATION:\s*.+?\]", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\[DRAFT_FB:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r"\[DRAFT_THREADS:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r"\[DRAFT_TWITTER:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)
        clean_text = re.sub(r"\[DRAFT_LEMON8:\s*.+?\]", "", clean_text, flags=re.IGNORECASE | re.DOTALL)


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



def _get_next_image_filename(image_url: str, counter: int) -> tuple[str, str]:
    """Return a standardized filename (e.g. web-1.jpg) and its mime type for the given counter."""
    # Detect extension and mime type
    ext = "jpg"
    mime = "image/jpeg"
    
    url_lower = image_url.lower()
    if ".png" in url_lower:
        ext = "png"
        mime = "image/png"
    elif ".webp" in url_lower:
        ext = "webp"
        mime = "image/webp"
        
    filename = f"web-{counter}.{ext}"
    return filename, mime


async def _prepare_drive_image_for_airtable(image_url: str, telegram_file_id: str, counter: int, context) -> str:
    """Download image (via Telegram cache if available, or direct fallback) and host it on GitHub to return a public URL for Airtable compatibility."""
    if not image_url and not telegram_file_id:
        return ""
    try:
        img_bytes = None
        
        # 1. Try downloading via Telegram file cache first (bypasses all 403 blocks)
        if telegram_file_id and context:
            try:
                logger.info(f"Downloading image from Telegram cache using file_id: {telegram_file_id}")
                telegram_file = await context.bot.get_file(telegram_file_id)
                file_bytearray = await telegram_file.download_as_bytearray()
                img_bytes = bytes(file_bytearray)
                logger.info(f"Downloaded {len(img_bytes)} bytes from Telegram cache.")
            except Exception as tg_err:
                logger.warning(f"Telegram file download failed, falling back to HTTP: {tg_err}")

        # 2. HTTP Fallback if Telegram cache is empty or failed
        if not img_bytes and image_url:
            import httpx
            logger.info(f"Downloading image via direct HTTP request: {image_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            with httpx.Client(timeout=30) as client:
                resp = client.get(image_url, headers=headers)
                resp.raise_for_status()
                img_bytes = resp.content

        if not img_bytes:
            return image_url

        filename, mime = _get_next_image_filename(image_url, counter)
        logger.info(f"Standardized filename for GitHub: {filename}")

        # Host image on GitHub (bypasses GDrive quota issues)
        github_link = _host_on_github(img_bytes, filename, "images")
        if github_link:
            return github_link
    except Exception as e:
        logger.error(f"Failed to process image bypass: {e}")
    return image_url


def _host_on_github(content_bytes: bytes, filename: str, subfolder: str) -> str:
    """Save content locally in AuraOne/{subfolder}/ and push to GitHub repository to host it publicly."""
    import os
    import subprocess
    import time
    
    target_dir = f"/home/ubuntu/projects/AURA-SDK/AuraOne/{subfolder}"
    os.makedirs(target_dir, exist_ok=True)
    
    filepath = os.path.join(target_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content_bytes)
        
    try:
        # Run git commands to commit and push the file
        subprocess.run(["git", "add", f"AuraOne/{subfolder}/{filename}"], cwd="/home/ubuntu/projects/AURA-SDK", check=True)
        subprocess.run(["git", "commit", "-m", f"chore: host {subfolder}/{filename}"], cwd="/home/ubuntu/projects/AURA-SDK", check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd="/home/ubuntu/projects/AURA-SDK", check=True)
        
        # Give GitHub raw CDN 2 seconds to update
        time.sleep(2)
        
        # Return the public GitHub raw URL
        raw_url = f"https://raw.githubusercontent.com/khairulxshafiq/AURA-SDK/main/AuraOne/{subfolder}/{filename}"
        logger.info(f"File successfully hosted on GitHub: {raw_url}")
        return raw_url
    except Exception as git_err:
        logger.error(f"GitHub hosting failed for {subfolder}/{filename}: {git_err}")
        return ""


def _upload_article_dump_to_github(
    title: str,
    master_article: str,
    hashtags: str,
    source_url: str,
    response_text: str,
    counter: int
) -> None:
    """Formulate the full article dump containing master article and drafts, and host it on GitHub dumps/ folder."""
    try:
        import re
        
        # Parse platform drafts from response_text using regex
        fb_match = re.search(r"\[DRAFT_FB:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
        threads_match = re.search(r"\[DRAFT_THREADS:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
        twitter_match = re.search(r"\[DRAFT_TWITTER:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
        lemon8_match = re.search(r"\[DRAFT_LEMON8:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
        
        fb_draft = fb_match.group(1).strip() if fb_match else "N/A"
        threads_draft = threads_match.group(1).strip() if threads_match else "N/A"
        twitter_draft = twitter_match.group(1).strip() if twitter_match else "N/A"
        lemon8_draft = lemon8_match.group(1).strip() if lemon8_match else "N/A"
        
        dump_content = (
            f"SOURCE URL: {source_url}\n"
            f"TITLE: {title}\n"
            f"HASHTAGS: {hashtags}\n\n"
            f"=========================================\n"
            f"MASTER ARTICLE:\n{master_article}\n\n"
            f"=========================================\n"
            f"FACEBOOK DRAFT:\n{fb_draft}\n\n"
            f"=========================================\n"
            f"THREADS DRAFT:\n{threads_draft}\n\n"
            f"=========================================\n"
            f"X / TWITTER DRAFT:\n{twitter_draft}\n\n"
            f"=========================================\n"
            f"LEMON8 DRAFT:\n{lemon8_draft}\n"
        )
        
        filename = f"web-{counter}.txt"
        _host_on_github(dump_content.encode("utf-8"), filename, "dumps")
    except Exception as e:
        logger.error(f"Error in _upload_article_dump_to_github: {e}")



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
    content_type = "Article"
    original_price = ""
    seller_location = ""
    try:
        import json
        state_data = json.loads(draft.get("state", "{}"))
        meta = state_data.get("shopee_metadata", {})
        content_type = meta.get("content_type", "Article")
        original_price = meta.get("original_price", "")
        seller_location = meta.get("seller_location", "")
    except Exception:
        pass

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

    # Save the draft to Airtable
    telegram_file_id = draft.get("telegram_file_id", "")
    counter = draft.get("counter_val", 0)
    final_image_url = await _prepare_drive_image_for_airtable(image_url, telegram_file_id, counter, context)
    from tools import save_draft_to_airtable

    res = save_draft_to_airtable(
        title=title,
        caption=platform_draft,
        platform=selected_platform,
        source_url=source_url,
        image_url=final_image_url,
        status=status,
        hashtags=hashtags,
        scheduled_time=scheduled_time_iso,
        content_type=content_type,
        original_price=original_price,
        seller_location=seller_location
    )

    if res["status"] == "success":
        thread_saved_status = ""
        if selected_platform.lower() in ["x", "twitter", "threads"]:
            posts = [p.strip() for p in platform_draft.split("\n\n") if p.strip()]
            if len(posts) > 1:
                from tools import save_thread_posts_to_airtable
                thread_res = save_thread_posts_to_airtable(
                    parent_record_id=res["record_id"],
                    posts=posts,
                    platform=selected_platform
                )
                if thread_res["status"] == "success":
                    thread_saved_status = f"\n• *Thread Posts*: Berjaya dipecahkan kepada {len(posts)} bahagian di jadual [Thread Posts]! 🧵"
                else:
                    thread_saved_status = (
                        f"\n⚠️ *Pecahan Bebenang*: Gagal disimpan ke jadual 'Thread Posts' ({thread_res.get('error')}). "
                        "Sila pastikan anda telah mencipta jadual 'Thread Posts' dengan kolum: "
                        "Content Station (Link), Post Text (Long Text), Sequence (Number), dan Platform (Select)."
                    )

        # Clear draft on success
        memory.clear_draft(user_id)
        
        sched_info = f"• *Status*: Scheduled 📅\n• *Tarikh Siaran*: {scheduled_time_iso}" if status == "Scheduled" else "• *Status*: Draft (Sedia Berlepas) ✈️"
        
        reply_msg = (
            f"✅ *Draf Hantaran {selected_platform.upper()} Berjaya Disahkan!*\n\n"
            f"• *Tajuk*: {title}\n"
            f"• *Platform*: {selected_platform.upper()}\n"
            f"{sched_info}\n"
            f"• *Airtable Record*: Berjaya disimpan [Content Station]{thread_saved_status}\n\n"
            f"Sedia untuk fasa posting!"
        )
        await _send_telegram_msg(update, reply_msg, parse_mode="Markdown")
    else:
        await _send_telegram_msg(update, f"⚠️ Gagal menyimpan ke Airtable: {res.get('error')}")





async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message = update.message or update.edited_message
    if not message or not message.location:
        return

    lat = message.location.latitude
    lon = message.location.longitude

    logger.info(f"Received location update from user {user_id}: {lat}, {lon}")
    
    address = "Lokasi Tidak Diketahui"
    try:
        headers = {"User-Agent": "AuraTelegramBot/1.0 (khairulxshafiq)"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json"},
                headers=headers
            )
            if resp.status_code == 200:
                data = resp.json()
                address = data.get("display_name", address)
    except Exception as e:
        logger.error(f"Error reverse geocoding location: {e}")

    import memory
    memory.save_user_location(user_id, lat, lon, address)
    
    if update.edited_message:
        logger.info(f"Quietly updated live location in database: {address}")
        return
        
    reply_text = (
        f"📍 *Lokasi boss berjaya dikemaskini!*\n\n"
        f"• *Alamat*: {address}\n"
        f"• *Koordinat*: `{lat}, {lon}`\n\n"
        f"Sekarang AURA tahu boss berada di sini. Boss boleh tanya AURA tentang tempat menarik, kedai makan, barang/perkhidmatan berdekatan, atau tanya *\"Saya dekat mana sekarang?\"*! 🗺️"
    )
    await _send_telegram_msg(update, reply_text, parse_mode="Markdown")


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

        import memory
        loc = memory.get_user_location(user_id)
        if loc:
            user_message += (
                f"\n\n[SISTEM: Lokasi semasa user ialah {loc['address']} (Lat: {loc['latitude']}, Lon: {loc['longitude']}). "
                f"Gunakan maklumat ini jika user mencari kedai makan, barang, tukang urut, rating, arah, atau jika bertanya 'saya dekat mana sekarang'. "
                f"Untuk carian kedai/barang, gunakan kebolehan Search Web / Google Search yang anda miliki untuk mencari tempat terdekat dengan koordinat ini.]"
            )



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
            clean = _clean_response(response_text)
            prefix = f"[F{current_key_idx + 1}] gemini-2.5-flash\n\n"
            final_text = _send_safe_message(f"{prefix}{clean}")
            await _send_telegram_msg(update, final_text, parse_mode="Markdown")
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
            prefix = f"[P1] {OPENROUTER_FALLBACK_MODEL}\n\n"
            final_text = _send_safe_message(f"{prefix}{clean}")
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
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.LOCATION, handle_location))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))




    logger.info(f"AURA Bot starting. Primary: Gemini | Fallback: OpenRouter ({OPENROUTER_FALLBACK_MODEL})")
    application.run_polling()


if __name__ == '__main__':
    main()
