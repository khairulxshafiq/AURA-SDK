import os
import logging
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram.ext import Application

from config import TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY, OPENROUTER_PROXY_PORT
from storage.db import init_db
from ui.telegram_bot import register_telegram_handlers

logger = logging.getLogger("aura.main")

# ─── OpenRouter Local Reverse Proxy ──────────────────────────────────────────

class OpenRouterProxyHandler(BaseHTTPRequestHandler):
    """Local reverse proxy handler to inject OpenRouter credentials into local requests."""
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        api_key = OPENROUTER_API_KEY
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
            err_body = e.read()
            logger.error(f"[OpenRouter Proxy] HTTPError {e.code}: {err_body}")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            logger.error(f"[OpenRouter Proxy] Exception: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def log_message(self, format, *args):
        logger.info(f"[OpenRouter Proxy] {format % args}")

def _start_openrouter_proxy(port: int = 18080):
    """Start local OpenRouter reverse proxy in a background daemon thread."""
    server = HTTPServer(('127.0.0.1', port), OpenRouterProxyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"OpenRouter reverse proxy server started on port {port}.")
    return server

# ─── Application Entrypoint ───────────────────────────────────────────────────

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
