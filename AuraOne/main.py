import os
import logging
import hashlib
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
    from google.antigravity import Agent, LocalAgentConfig, types
    from google.antigravity.hooks import policy
except ImportError as e:
    logger.error("=" * 80)
    logger.error("RALAT IMPORT: Pustaka 'google-antigravity' tidak dapat diimport.")
    logger.error("Punca Utama: macOS anda menggunakan cip Intel (x86_64).")
    logger.error("Google hanya menerbitkan wheel SDK untuk macOS Apple Silicon (arm64) sahaja.")
    logger.error("TETAPI, Google menerbitkan wheel untuk Linux x86_64.")
    logger.error("Jadi, kod ini AKAN BERJALAN SEMPURNA apabila di-deploy ke VPS Linux (Tencent SG) anda!")
    logger.error("=" * 80)
    raise e

from tools import scrape_web

# Ensure save and skills directories exist
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(SKILLS_DIR, exist_ok=True)

# Load persona from persona.txt
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Salam {user.mention_html()}! Saya AURA, personal operating system supervisor anda. "
        rf"Sila hantar sebarang mesej atau pautan (URL) untuk saya periksa menggunakan scrape_web tool."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pass incoming user messages to the Antigravity Agent and respond back."""
    user_message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Send typing status
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Configure Antigravity Agent with persistence and skills
    # Generated deterministic 64-character hash of user_id to satisfy 32-character minimum constraint
    conv_id = hashlib.sha256(f"tg_{user_id}".encode()).hexdigest()
    config = LocalAgentConfig(
        conversation_id=conv_id,
        save_dir=SESSIONS_DIR,
        skills_paths=[SKILLS_DIR],
        capabilities=types.CapabilitiesConfig(
            enable_subagents=True,
        ),
        tools=[scrape_web],
        policies=[policy.allow_all()],
        system_instructions=SYSTEM_INSTRUCTIONS,
    )
    
    try:
        async with Agent(config) as agent:
            response = await agent.chat(user_message)
            response_text = await response.text()
            
            # Send the final response to the user
            await update.message.reply_text(response_text)
            
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await update.message.reply_text(f"Minta maaf bos, ralat berlaku: {str(e)}")

def main():
    """Start the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not configured in the .env file.")
        print("Please configure TELEGRAM_BOT_TOKEN in AuraOne/.env first!")
        return

    # Create the Application
    application = Application.builder().token(token).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot
    print("AURA Bot is running... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
