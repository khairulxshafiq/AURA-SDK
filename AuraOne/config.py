import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logger setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("aura.config")

# ─── Directories & Paths ──────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
PERSONA_PATH = os.path.join(BASE_DIR, "persona.txt")
SESSION_MAP_PATH = os.path.join(SESSIONS_DIR, "user_session_map.json")
DB_PATH = os.path.join(SESSIONS_DIR, "aura_memory.db")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(SKILLS_DIR, exist_ok=True)

# ─── Model Config & Fallback Settings ──────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_FALLBACK_MODEL = os.environ.get("OPENROUTER_FALLBACK_MODEL", os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash"))
OPENROUTER_BASE_URL = "http://127.0.0.1:18080"
OPENROUTER_PROXY_PORT = 18080

# ─── External API Keys ────────────────────────────────────────────────────────
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "Content Station")
DEFAULT_BRAND = os.environ.get("DEFAULT_BRAND", "Sakluma")

APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "")

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_ENABLED = os.environ.get("FIRECRAWL_ENABLED", "false").lower() == "true"
FIRECRAWL_TIMEOUT_MS = int(os.environ.get("FIRECRAWL_TIMEOUT_MS", "30000"))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ─── Gemini Keys for Rotation ────────────────────────────────────────────────
GEMINI_KEYS = []
main_key = os.environ.get("GEMINI_API_KEY", "")
if main_key:
    GEMINI_KEYS.append(main_key)
for i in range(1, 11):
    val = os.environ.get(f"GEMINI_API_KEY_{i}", "")
    if val and val not in GEMINI_KEYS:
        GEMINI_KEYS.append(val)

if not GEMINI_KEYS:
    GEMINI_KEYS.append("DUMMY_KEY")

current_key_idx = 0

def get_active_gemini_key() -> str:
    """Return current active Gemini API key from rotation pool."""
    global current_key_idx
    return GEMINI_KEYS[current_key_idx]

def rotate_gemini_key() -> str:
    """Rotate to the next available Gemini API key in pool and return it."""
    global current_key_idx
    num_keys = len(GEMINI_KEYS)
    current_key_idx = (current_key_idx + 1) % num_keys
    logger.info(f"Rotated to Gemini API key index {current_key_idx}/{num_keys}")
    return GEMINI_KEYS[current_key_idx]

# ─── Persona Reader ───────────────────────────────────────────────────────────
def get_system_instructions_template() -> str:
    """Load base persona text instructions."""
    if os.path.exists(PERSONA_PATH):
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return (
        "You are AURA, a concise personal AI supervisor. "
        "Reply in short, clear answers. Never show reasoning or internal steps. "
        "Use emojis naturally. Speak Malay by default."
    )
