"""
AURA-SDK Application Entrypoint
Decoupled modular architecture powered by Telegram UI handlers & Supervisor Orchestrator.
"""
import logging
from telegram.ext import Application
from config import TELEGRAM_BOT_TOKEN, OPENROUTER_PROXY_PORT
from storage.db import init_db
from ui.telegram_bot import register_telegram_handlers, _start_openrouter_proxy

logger = logging.getLogger("aura.main")

def main():
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not configured in the environment.")
        return

    # 1. Start local OpenRouter reverse proxy on port 18080
    _start_openrouter_proxy(port=OPENROUTER_PROXY_PORT)

    # 2. Initialize SQLite long-term memory & draft database
    try:
        init_db()
        logger.info("SQLite database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database on startup: {e}")

    # 3. Build Telegram Application & register UI handlers
    application = Application.builder().token(token).build()
    register_telegram_handlers(application)

    logger.info("AURA Agent Bot starting via modular UI & Supervisor Orchestrator...")
    application.run_polling()

if __name__ == '__main__':
    main()
