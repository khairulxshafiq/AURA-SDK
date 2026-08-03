"""
AURA Telegram UI Handler & Supervisor Orchestrator Router.
Slim modular routing shell that delegates pipeline execution to modular pipeline modules in AuraOne/pipelines/.
"""
import os
import re
import json
import logging
import asyncio
import httpx
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)

from config import (
    OPENROUTER_API_KEY, OPENROUTER_FALLBACK_MODEL,
    SESSION_MAP_PATH, SESSIONS_DIR
)
import storage.memory_repository as memory
import storage.location_repository as location_repo
import storage.draft_repository as draft_repo

from tools.web_scraper import scrape_url
from ui.keyboards import (
    _get_platform_keyboard, _get_sub_options_keyboard, _get_gnews_keyboard,
    _get_viral_confessions_keyboard, _get_location_keyboard
)
from ui.formatters import _clean_response, _send_telegram_msg

# Import Pipeline Modules
from pipelines.llm_caller import call_supervisor_chat_model, audit_gemini_keys_async
from pipelines.scrape_pipeline import execute_scrape_pipeline, handle_scrape_shortcut
from pipelines.news_pipeline import send_gnews_trending, send_viral_confessions
from pipelines.draft_pipeline import (
    generate_all_platform_drafts, confirm_platform_push, handle_confirm_command
)
from pipelines.trade_pipeline import handle_stock_command, handle_screener_command
from pipelines.location_pipeline import handle_location, handle_sethome, handle_sethq

logger = logging.getLogger("aura.ui.telegram_bot")


# ─── OpenRouter Proxy ─────────────────────────────────────────────────────────

class OpenRouterProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_length)
        api_key = OPENROUTER_API_KEY
        if not api_key:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"OPENROUTER_API_KEY not configured")
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aura-sdk.local",
            "X-Title": "AURA-SDK"
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    content=post_body
                )
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ['content-length', 'transfer-encoding', 'content-encoding']:
                    self.send_header(k, v)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp.content)
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


DEBUG_USERS: dict = {}


# ─── Session Helpers ──────────────────────────────────────────────────────────

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
        db_path = os.path.join(SESSIONS_DIR, f"{conv_id}.db")
        if os.path.exists(session_path) or os.path.exists(db_path):
            return conv_id
        logger.warning(f"Session data missing for user {user_id} ({prefix}), starting fresh.")
    return None


def _register_conv_id_for_user(user_id: int, conv_id: str, prefix: str = "") -> None:
    session_map = _load_session_map()
    session_map[f"{prefix}{user_id}"] = conv_id
    _save_session_map(session_map)


# ─── Basic Commands ───────────────────────────────────────────────────────────

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


# ─── Callback Router ──────────────────────────────────────────────────────────

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat.id
    data = query.data

    if data.startswith("viral_menu:"):
        offset = int(data.split(":")[1]) if data.split(":")[1].isdigit() else 0
        await query.answer("🔥 Mengambil 6 cerita sensasi & confession terkini...")
        await send_viral_confessions(update, context, offset=offset)
        return

    if data == "gnews_back":
        await query.answer("◀️ Kembali ke menu utama Berita Trending...")
        await send_gnews_trending(update, context, category="trending", max_items=6)
        return

    if data.startswith("gnews_cat:"):
        cat = data.split(":")[1]
        await send_gnews_trending(update, context, category=cat, max_items=10)
        return

    if data.startswith("loc_action:"):
        act = data.split(":")[1]
        loc = location_repo.get_user_location(user_id)
        if not loc:
            await query.answer("⚠️ Tiada lokasi tersimpan.", show_alert=True)
            return

        if act == "set_home":
            location_repo.save_user_place(user_id, "home", loc["latitude"], loc["longitude"], loc["address"])
            await query.answer("✅ Lokasi RUMAH berjaya disimpan!", show_alert=True)
            await query.message.reply_text(f"🏠 *LOKASI RUMAH BERJAYA DISIMPAN!*\n\n• Alamat: `{loc['address']}`", parse_mode="Markdown")

        elif act == "set_hq":
            location_repo.save_user_place(user_id, "hq", loc["latitude"], loc["longitude"], loc["address"])
            await query.answer("✅ Lokasi HQ Sakluma berjaya disimpan!", show_alert=True)
            await query.message.reply_text(f"🏢 *LOKASI HQ SAKLUMA BERJAYA DISIMPAN!*\n\n• Alamat: `{loc['address']}`", parse_mode="Markdown")
        return

    if data.startswith("do_scrape:"):
        target_url = data.split("do_scrape:", 1)[1]
        await query.answer("🚀 Mula scrape artikel...")
        await query.message.reply_text(f"⚡ Mula scrape & olah kandungan daripada:\n`{target_url}`", parse_mode="Markdown")
        await execute_scrape_pipeline(target_url, user_id, chat_id, context, update)
        return

    if data.startswith("do_summarize:"):
        target_url = data.split("do_summarize:", 1)[1]
        await query.answer("🔍 Meringkaskan artikel...")
        scraped = scrape_url(target_url)
        content = scraped.get("content", "") if isinstance(scraped, dict) else ""
        title = scraped.get("title", "Artikel") if isinstance(scraped, dict) else "Artikel"
        img = scraped.get("article_image_url", "") or scraped.get("image_url", "") if isinstance(scraped, dict) else ""
        if img and img.startswith("http://"):
            img = "https://" + img[7:]
        summary_text = f"📰 *{title}*\n\n{content[:1200]}...\n\n🔗 `{target_url}`"
        if img:
            await query.message.reply_photo(photo=img, caption=summary_text, parse_mode="Markdown")
        else:
            await query.message.reply_text(summary_text, parse_mode="Markdown")
        return

    draft = draft_repo.get_draft(user_id)
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
        draft_repo.update_draft_state(user_id, json.dumps(state_data))
        reply_markup = _get_platform_keyboard(state_data)
        try:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

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
            if "facebook" in selected and "fb_len" not in state_data["options"]:
                state_data["options"]["fb_len"] = "panjang"
            if "facebook" in selected and "fb_show_title" not in state_data["options"]:
                state_data["options"]["fb_show_title"] = False
            if ("x" in selected or "threads" in selected) and "thread_len" not in state_data["options"]:
                state_data["options"]["thread_len"] = 5

            draft_repo.update_draft_state(user_id, json.dumps(state_data))
            reply_markup = _get_sub_options_keyboard(state_data)
            await query.message.reply_text("Pilih pilihan sub-platform boss:", reply_markup=reply_markup)

    elif data.startswith("sub:"):
        parts = data.split(":")
        if len(parts) >= 2:
            key = parts[1]
            val = parts[2] if len(parts) > 2 else ""
            options = state_data.get("options", {})
            if key == "thread_len":
                options["thread_len"] = int(val) if val.isdigit() else 5
            elif key == "fb_show_title":
                options["fb_show_title"] = not options.get("fb_show_title", False)
            else:
                options[key] = val
            state_data["options"] = options
            draft_repo.update_draft_state(user_id, json.dumps(state_data))
            reply_markup = _get_sub_options_keyboard(state_data)
            try:
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            except Exception:
                pass

    elif data in ["hashtag_on", "hashtag_off"]:
        with_hashtags = (data == "hashtag_on")
        state_data["hashtags"] = with_hashtags
        options = state_data.get("options", {})
        options["hashtags"] = with_hashtags
        options["with_hashtags"] = with_hashtags
        state_data["options"] = options
        draft_repo.update_draft_state(user_id, json.dumps(state_data))

        reply_markup = _get_sub_options_keyboard(state_data)
        try:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Failed to edit reply markup for hashtag toggle: {e}")

        selected = state_data.get("selected", [])
        if selected and draft.get("platform_draft"):
            status_text = "🔄 Mengemaskini pratonton (Dengan Hashtag)..." if with_hashtags else "🔄 Mengemaskini pratonton (Tanpa Hashtag)..."
            await query.message.reply_text(status_text)
            await generate_all_platform_drafts(user_id, chat_id, selected, options, draft, context, query.message)

    elif data == "sub_next":
        selected = state_data.get("selected", [])
        options = state_data.get("options", {})
        await query.message.reply_text("⏳ Menjana semua draf platform terpilih...")
        await generate_all_platform_drafts(user_id, chat_id, selected, options, draft, context, query.message)

    elif data.startswith("confirm_platform:"):
        plat_to_confirm = data.split(":")[1]
        await confirm_platform_push(user_id, draft, plat_to_confirm, context, query.message)


# ─── Intent Router Helpers ───────────────────────────────────────────────────

URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
SCRAPE_TRIGGER_RE = re.compile(r'\bscrape\b', re.IGNORECASE)

def _is_bare_url(text: str) -> bool:
    """Return True if text consists of a URL with 3 or fewer additional words."""
    stripped = URL_RE.sub('', text).strip()
    return len(stripped.split()) <= 3


LIVE_SEARCH_KEYWORDS = [
    "berita terkini", "current news", "headline", "trending malaysia",
    "trending dunia", "cerita menarik", "cerita semasa", "apa berlaku hari ini",
    "top stories", "berita", "trending", "viral", "gnews", "/news"
]

TRADING_KEYWORDS = ["analisa", "saham", "harga", "tp", "sl", "bursa", "kaunter"]

def route_intent(message_text: str) -> str:
    """Determine message intent: SCRAPE_PIPELINE, URL_SUGGEST, CONTEXTUAL_CHAT, LIVE_NEWS_SEARCH, or DAILY_CHAT."""
    text = message_text.strip()
    has_url = bool(URL_RE.search(text))
    is_s2 = text.lower().startswith('/s2') or bool(re.match(r'^/s\d+', text, re.IGNORECASE))
    has_scrape_word = bool(SCRAPE_TRIGGER_RE.search(text))

    if has_url and (is_s2 or has_scrape_word or _is_bare_url(text)):
        return "SCRAPE_PIPELINE"

    if has_url and not has_scrape_word:
        return "CONTEXTUAL_CHAT"

    text_clean = text.lower()
    trading_re = re.compile(r'\b(' + '|'.join(TRADING_KEYWORDS) + r')\b', re.IGNORECASE)
    if trading_re.search(text_clean):
        return "TRADING_PIPELINE"

    if any(kw in text_clean for kw in LIVE_SEARCH_KEYWORDS):
        return "LIVE_NEWS_SEARCH"

    return "DAILY_CHAT"


# ─── Message Handler Router ───────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_text: str = None):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    user_message = override_text or update.message.text or ""
    if not user_message and not update.message.photo:
        return

    agent_message = user_message
    if user_message:
        msg_clean = user_message.strip().lower()
        if msg_clean.startswith("confirm") or msg_clean.startswith("/confirm"):
            await handle_confirm_command(update, context)
            return

        intent = route_intent(user_message)
        logger.info(f"[IntentRouter] Message '{user_message[:40]}...' routed to intent: {intent}")

        if intent == "SCRAPE_PIPELINE":
            url_match = URL_RE.search(user_message)
            target_url = url_match.group(0) if url_match else user_message
            await execute_scrape_pipeline(target_url, user_id, chat_id, context, update)
            return

        elif intent == "URL_SUGGEST":
            url_match = URL_RE.search(user_message)
            target_url = url_match.group(0) if url_match else ""
            reply_text = (
                f"Aku nampak kau share link ni 🔗\n"
                f"`{target_url}`\n\n"
                f"Nak aku buat apa dengan dia?\n\n"
                f"• 📰 *Scrape jadi content* → taip: `Scrape {target_url}`\n"
                f"• 🔍 *Ringkas / info pantas* → tanya je apa kau nak tau\n"
                f"• 💬 *Sembang biasa pasal ni*\n\n"
                f"Bagitau je boss."
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📰 Scrape Jadi Content", callback_data=f"do_scrape:{target_url}"),
                    InlineKeyboardButton("🔍 Info Pantas", callback_data=f"do_summarize:{target_url}")
                ]
            ])
            await _send_telegram_msg(update, reply_text, reply_markup=keyboard, parse_mode="Markdown", disable_preview=True)
            return

        elif intent == "CONTEXTUAL_CHAT":
            url_match = URL_RE.search(user_message)
            target_url = url_match.group(0) if url_match else ""
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            response_text = await call_supervisor_chat_model(user_message, user_id=user_id)
            clean = _clean_response(response_text)
            if target_url and target_url not in clean:
                clean += f"\n\n_(Nota: Kalau nak aku jadikan content, taip `Scrape {target_url}` ye.)_"
            await _send_telegram_msg(update, clean, parse_mode="Markdown")
            return

        elif intent == "LIVE_NEWS_SEARCH":
            await send_gnews_trending(update, context, category="trending", max_items=6)
            return

        elif intent == "TRADING_PIPELINE":
            context.args = user_message.split()
            await handle_stock_command(update, context)
            return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response_text = await call_supervisor_chat_model(agent_message, user_id=user_id)
    clean = _clean_response(response_text)
    if clean:
        await _send_telegram_msg(update, clean, parse_mode="Markdown")


# ─── Handler Registration ─────────────────────────────────────────────────────

def register_telegram_handlers(application: Application):
    """Register all Telegram bot command, callback, location, and message handlers."""
    audit_gemini_keys_async()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(CommandHandler("confirm", handle_confirm_command))
    application.add_handler(CommandHandler("sethome", handle_sethome))
    application.add_handler(CommandHandler("sethq", handle_sethq))
    application.add_handler(CommandHandler("stock", handle_stock_command))
    application.add_handler(CommandHandler("trade", handle_stock_command))
    application.add_handler(CommandHandler("swing", handle_stock_command))
    application.add_handler(CommandHandler("position", handle_stock_command))
    application.add_handler(CommandHandler("screener", handle_screener_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(MessageHandler(filters.Regex(r"^/s\d+$"), handle_scrape_shortcut))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))
    logger.info("Telegram UI handlers registered successfully (modular pipelines active).")
