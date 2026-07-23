import os
import re
import json
import logging
import datetime
import asyncio
import httpx
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
)

from config import (
    GEMINI_KEYS, OPENROUTER_API_KEY, OPENROUTER_FALLBACK_MODEL,
    SESSION_MAP_PATH, SESSIONS_DIR
)
import storage.memory_repository as memory
import storage.location_repository as location_repo
import storage.draft_repository as draft_repo

from tools.web_scraper import scrape_url
from tools.search_engine import fetch_gnews_articles, search_web
from tools.location_service import (
    reverse_geocode_location, _get_weather_forecast, _get_extended_weather_forecast
)
from tools.publisher_service import (
    save_draft_to_airtable, save_thread_posts_to_airtable, _prepare_drive_image_for_airtable
)
from ui.keyboards import (
    _get_platform_keyboard, _get_sub_options_keyboard, _get_gnews_keyboard,
    _get_viral_confessions_keyboard, _get_location_keyboard
)
from ui.formatters import (
    _clean_response, _send_safe_message, _send_telegram_msg, _process_response_draft
)

logger = logging.getLogger("aura.ui.telegram_bot")

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

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
current_key_idx = 0

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

# ─── Commands ─────────────────────────────────────────────────────────────────

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

async def sethome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    loc = location_repo.get_user_location(user_id)
    if not loc:
        await update.message.reply_text("⚠️ Sila hantar lokasi (location pin) anda di Telegram terlebih dahulu sebelum menanda tempat Rumah.")
        return
    location_repo.save_user_place(user_id, "home", loc["latitude"], loc["longitude"], loc["address"])
    await update.message.reply_text(
        f"🏠 *LOKASI RUMAH BERJAYA DISIMPAN!*\n"
        f"───────────────\n\n"
        f"• *Alamat*: `{loc['address']}`\n"
        f"• *Koordinat*: `{loc['latitude']}, {loc['longitude']}`\n\n"
        f"Kini setiap kali anda menghantar lokasi di Telegram, butang *[🏠 Navigasi Ke Rumah]* akan dipaparkan secara automatik!",
        parse_mode="Markdown"
    )

async def sethq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    loc = location_repo.get_user_location(user_id)
    if not loc:
        await update.message.reply_text("⚠️ Sila hantar lokasi (location pin) anda di Telegram terlebih dahulu sebelum menanda HQ Sakluma.")
        return
    location_repo.save_user_place(user_id, "hq", loc["latitude"], loc["longitude"], loc["address"])
    await update.message.reply_text(
        f"🏢 *LOKASI HQ SAKLUMA BERJAYA DISIMPAN!*\n"
        f"───────────────\n\n"
        f"• *Alamat*: `{loc['address']}`\n"
        f"• *Koordinat*: `{loc['latitude']}, {loc['longitude']}`\n\n"
        f"Kini setiap kali anda menghantar lokasi di Telegram, butang *[🏢 Navigasi Ke HQ]* akan dipaparkan secara automatik!",
        parse_mode="Markdown"
    )

async def _execute_direct_scrape_pipeline(url: str, user_id: int, chat_id: int, context, update):
    """Direct Execution Pipeline for URL Scraping -> Master Article Generation -> UI Keyboards.
    Bypasses SDK async subagent loop to avoid intermediate metadata JSON output."""
    global current_key_idx
    logger.info(f"[DirectPipeline] Executing direct scrape pipeline for {url} (user {user_id})...")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # 1. Direct Web Scraping using 3-Tier Scraper (Firecrawl -> Native -> Jina)
    scraped = scrape_url(url)
    if not isinstance(scraped, dict) or scraped.get("status") != "success":
        err_msg = scraped.get("error", "Gagal mengekstrak kandungan laman web.") if isinstance(scraped, dict) else "Scrape failed"
        await update.message.reply_text(f"⚠️ *Gagal mengekstrak URL*: {err_msg}", parse_mode="Markdown")
        return

    raw_title = scraped.get("title", "Artikel Berita")
    raw_content = scraped.get("content", "")
    image_url = scraped.get("image_url", "")
    source_url = scraped.get("url", url)

    if not raw_content or len(raw_content) < 50:
        await update.message.reply_text("⚠️ Artikel yang di-scrape tidak mengandungi teks kandungan yang mencukupi.")
        return

    # 2. Direct Master Article Generation Prompt
    prompt = (
        f"Anda adalah Editor Konten Sakluma profesional.\n"
        f"Tugas anda: Hasilkan Master Article (Format Sakluma) yang menarik, mesra pembaca, dan berkualiti tinggi berdasarkan kandungan artikel berikut.\n\n"
        f"TAJUK ASAL: {raw_title}\n"
        f"URL ASAL: {source_url}\n\n"
        f"KANDUNGAN ARTIKEL:\n{raw_content[:4000]}\n\n"
        f"Sila kembalikan Master Article dan MESTI menyertakan tag metadata [DRAFT_*] di bahagian AKHIR jawapan anda mengikut format tepat berikut:\n\n"
        f"[DRAFT_TITLE: {raw_title}]\n"
        f"[DRAFT_SOURCE_URL: {source_url}]\n"
        f"[DRAFT_IMAGE: {image_url}]\n"
        f"[DRAFT_HASHTAGS: #Sakluma #Trending #IsuSemasa]\n"
        f"[DRAFT_MASTER_ARTICLE: Teks Master Article Sakluma lengkap di sini...]"
    )

    # 3. Call LLM directly (Gemini or OpenRouter Fallback)
    generated_text = ""
    num_keys = len(GEMINI_KEYS)
    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        if memory.is_key_on_cooldown(active_key):
            current_key_idx = (current_key_idx + 1) % num_keys
            continue
        try:
            from google import genai
            client = genai.Client(api_key=active_key)
            res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            if res and res.text:
                generated_text = res.text
                break
        except Exception as err:
            logger.warning(f"Direct pipeline Gemini key #{current_key_idx + 1} failed ({err})")
            if "429" in str(err) or "quota" in str(err).lower():
                memory.set_key_cooldown(active_key, 600.0)
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

    if not generated_text and OPENROUTER_API_KEY:
        try:
            logger.info("Direct pipeline: falling back to OpenRouter for Master Article generation...")
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": OPENROUTER_FALLBACK_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    generated_text = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Direct pipeline OpenRouter fallback error: {e}")

    if not generated_text:
        generated_text = (
            f"📰 *{raw_title}*\n\n{raw_content[:800]}...\n\n"
            f"[DRAFT_TITLE: {raw_title}]\n"
            f"[DRAFT_SOURCE_URL: {source_url}]\n"
            f"[DRAFT_IMAGE: {image_url}]\n"
            f"[DRAFT_HASHTAGS: #Sakluma #Berita]\n"
            f"[DRAFT_MASTER_ARTICLE: {raw_content[:1500]}]"
        )

    # 4. Process draft tags, save to SQLite DB, send Photo Preview & Inline Keyboards
    res = await _process_response_draft(user_id, chat_id, generated_text, context, update)
    if res == "[DRAFT_SENT_WITH_KEYBOARD]":
        return
    clean = _clean_response(generated_text)
    await _send_telegram_msg(update, clean, parse_mode="Markdown")

async def scrape_shortcut_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        idx = int(text.replace("/s", ""))
    except ValueError:
        return

    urls = context.user_data.get("scrape_urls", {})
    if idx in urls:
        url = urls[idx]
        await update.message.reply_text(f"⚡ *Memproses Artikel {idx}...*\n_{url}_", parse_mode="Markdown", disable_web_page_preview=True)
        await _execute_direct_scrape_pipeline(url, update.effective_user.id, update.effective_chat.id, context, update)
    else:
        await update.message.reply_text("⚠️ URL tidak dijumpai dalam memori sesi. Sila minta senarai berita baru.")

# ─── News Handlers ────────────────────────────────────────────────────────────

async def send_viral_confessions(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0):
    queries = [
        "viral confession luahan rumah tangga curang Malaysia 2026",
        "IIUM Confessions luahan rumah tangga skandal 2026",
        "Reddit Bolehland Malaysia luahan isteri suami curang 2026",
        "Lowyat Kopitiam luahan confession rumah tangga viral 2026"
    ]

    q = queries[(offset // 6) % len(queries)]
    search_res = search_web(q)

    results = search_res.get("results", []) if isinstance(search_res, dict) else []
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    articles = []
    if results:
        for item in results:
            link = item.get("link", "").strip()
            if "facebook.com" in link.lower() or "fb.com" in link.lower():
                continue

            title = item.get("title", "Luahan Sensasi").strip()
            snippet = item.get("snippet", "").strip()
            snippet = re.sub(r"\s+", " ", snippet)
            if len(snippet) > 130:
                snippet = snippet[:127] + "..."
            if not snippet:
                snippet = "Kisah luahan sensasi masyarakat & netizen Malaysia."

            source_name = "Portal Luahan"
            if "iiumc" in link.lower():
                source_name = "IIUM Confessions"
            elif "reddit.com" in link.lower():
                source_name = "Reddit Malaysia"
            elif "lowyat" in link.lower():
                source_name = "Lowyat Forum"

            articles.append({
                "title": title,
                "source": source_name,
                "link": link,
                "desc": snippet
            })
            if len(articles) >= 6:
                break

    if len(articles) < 6:
        gnews_items = fetch_gnews_articles("confession luahan rumah tangga viral Malaysia 2026", max_items=10)
        for g in gnews_items:
            if not any(a["link"] == g["link"] for a in articles):
                articles.append(g)
            if len(articles) >= 6:
                break

    if "scrape_urls" not in context.user_data:
        context.user_data["scrape_urls"] = {}

    import html as _h
    lines = []
    for idx, a in enumerate(articles, start=offset + 1):
        t = _h.escape(a.get('title', 'Luahan Sensasi'))
        s = _h.escape(a['source']) if a.get('source') else ""
        d = _h.escape(a.get('desc', ''))
        lnk = a.get('link', '')
        source_str = f" • Sumber: {s}\n" if s else ""
        context.user_data["scrape_urls"][idx] = lnk
        lines.append(
            f"<b>{idx}. {t}</b>\n"
            f"{source_str}"
            f"   • <i>{d}</i>\n"
            f"   👉 <a href=\"{lnk}\">Baca Sini</a> | 🔄 /s{idx}"
        )

    body = "\n\n".join(lines)
    reply = (
        f"🔥 <b>VIRAL &amp; CONFESSION SENSASI [{today_str}]</b>\n"
        f"───────────────\n"
        f"📌 <b>Koleksi</b>: <code>Reddit (r/Bolehland, r/malaysia), IIUMC &amp; Lowyat Forum</code>\n\n"
        f"{body}\n\n"
        f"───────────────\n"
        f"💡 <b>Tekan [More Confessions] untuk 6 cerita seterusnya, atau [Back] untuk ke menu utama:</b> "
    )

    reply_markup = _get_viral_confessions_keyboard(offset)
    await _send_telegram_msg(update, reply, reply_markup=reply_markup, parse_mode="HTML", disable_preview=True)

async def send_gnews_trending(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str = "trending", max_items: int = 6):
    cat_queries = {
        "trending": ("Malaysia trending viral 2026", "VIRAL & TRENDING"),
        "gajet": ("gajet teknologi telefon pintar Malaysia 2026", "GAJET & TEKNOLOGI"),
        "korporat": ("korporat ekonomi perniagaan saham Malaysia 2026", "KORPORAT & EKONOMI"),
        "artis": ("artis hiburan selebriti drama Malaysia 2026", "ARTIS & HIBURAN"),
        "sukan": ("sukan bola sepak badminton harimau malaya 2026", "SUKAN MALAYSIA"),
        "viral": ("viral panas isu sensasi luahan confession Malaysia 2026", "VIRAL & CONFESSION"),
        "nasional": ("isu semasa nasional kerajaan politik Malaysia 2026", "ISU SEMASA NASIONAL")
    }

    q, cat_title = cat_queries.get(category, (f"{category} Malaysia 2026", category.upper()))
    articles = fetch_gnews_articles(q, max_items)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    if not articles:
        reply_text = f"⚠️ Tiada berita terkini dijumpai untuk kategori ini dari Google News."
        await update.message.reply_text(reply_text, parse_mode=None, reply_markup=_get_gnews_keyboard())
        return

    if "scrape_urls" not in context.user_data:
        context.user_data["scrape_urls"] = {}

    import html as _h
    lines = []
    for idx, a in enumerate(articles, start=1):
        t = _h.escape(a['title'])
        s = _h.escape(a['source']) if a['source'] else ""
        d = _h.escape(a['desc'])
        lnk = a['link']
        source_str = f" • Sumber: {s}\n" if s else ""
        context.user_data["scrape_urls"][idx] = lnk
        lines.append(
            f"<b>{idx}. {t}</b>\n"
            f"{source_str}"
            f"   • <i>{d}</i>\n"
            f"   👉 <a href=\"{lnk}\">Baca Sini</a> | 🔄 /s{idx}"
        )

    body = "\n\n".join(lines)
    cat_title_esc = _h.escape(cat_title)

    reply = (
        f"🔥 <b>{cat_title_esc} [{today_str}]</b>\n"
        f"───────────────\n\n"
        f"{body}\n\n"
        f"───────────────\n"
        f"💡 <b>Pilih Kategori Berita Tambahan (Tekan Butang Di Bawah)</b>:"
    )

    reply_markup = _get_gnews_keyboard()
    await _send_telegram_msg(update, reply, reply_markup=reply_markup, parse_mode="HTML", disable_preview=True)

# ─── Location Handler ─────────────────────────────────────────────────────────

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message or update.edited_message
    if not message or not message.location:
        return

    lat = message.location.latitude
    lon = message.location.longitude

    address = await reverse_geocode_location(lat, lon)
    location_repo.save_user_location(user_id, lat, lon, address)

    if update.edited_message:
        logger.info(f"Quietly updated live location in database: {address}")
        return

    maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    weather_info = await _get_weather_forecast(lat, lon)
    reply_markup = _get_location_keyboard(user_id, lat, lon)

    reply_text = (
        f"📍 *LOCATION UPDATE;*\n"
        f"───────────────\n\n"
        f"🏢 *Alamat Semasa*:\n`{address}`\n\n"
        f"📌 *Koordinat GPS*:\n`{lat}, {lon}`\n\n"
        f"🌤️ *Ramalan Cuaca Hari Ini*:\n{weather_info}\n\n"
        f"🗺️ *Pautan Peta*:\n[Buka Dalam Google Maps]({maps_url})\n\n"
        f"───────────────\n"
        f"💡 *Pilihan Pantas (Tekan butang di bawah)*:"
    )

    import html
    escaped = html.escape(reply_text)
    escaped = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.*?)\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.*?)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[(.*?)\]\((https?://.*?)\)", r'<a href="\2">\1</a>', escaped)

    thread_id = getattr(update.message, "message_thread_id", None) if update.message else None
    await update.message.reply_text(escaped, parse_mode="HTML", reply_markup=reply_markup, message_thread_id=thread_id)

# ─── Draft Generation & Confirmation Helpers ─────────────────────────────────

async def _call_draft_generator_model(plat: str, draft: dict, fb_style: str = "", thread_length: int = 0) -> str:
    global current_key_idx
    style_info = f" (Gaya: {fb_style})" if fb_style else ""
    len_info = f" (Jumlah bebenang: {thread_length})" if thread_length > 0 else ""
    prompt = (
        f"Anda adalah Editor Konten Sakluma profesional. Tulis draf hantaran media sosial yang humanized dan menarik untuk platform {plat.upper()}{style_info}{len_info}.\n\n"
        f"TAJUK: {draft['title']}\n"
        f"HASHTAGS: {draft.get('hashtags', '')}\n"
        f"MASTER ARTIKEL:\n{draft['master_article']}"
    )

    num_keys = len(GEMINI_KEYS)
    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        if memory.is_key_on_cooldown(active_key):
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

        os.environ["GEMINI_API_KEY"] = active_key
        try:
            from google import genai
            client = genai.Client(api_key=active_key)
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            if response and response.text:
                return response.text
        except Exception as err:
            logger.warning(f"Gemini key #{current_key_idx + 1} draft gen failed ({err})")
            if "429" in str(err) or "quota" in str(err).lower():
                memory.set_key_cooldown(active_key, 600.0)
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

    # OpenRouter Fallback
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"Generating draft for {plat.upper()} using OpenRouter fallback ({OPENROUTER_FALLBACK_MODEL})...")
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": OPENROUTER_FALLBACK_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    return content
                else:
                    logger.error(f"OpenRouter draft gen error ({r.status_code}): {r.text[:200]}")
        except Exception as or_err:
            logger.error(f"OpenRouter draft gen exception: {or_err}")

    return ""

async def _generate_all_platform_drafts(user_id: int, chat_id: int, selected_platforms: list, options: dict, draft: dict, context, message):
    generated_drafts = {}
    for plat in selected_platforms:
        fb_style = options.get("facebook", "viral_santai")
        thread_length = options.get("thread_len", 5) if plat in ["x", "threads"] else 0
        draft_text = await _call_draft_generator_model(plat, draft, fb_style, thread_length)
        if draft_text:
            generated_drafts[plat] = draft_text

    draft_repo.update_platform_draft(user_id, ",".join(selected_platforms), json.dumps(generated_drafts), state="")

    review_text = "✨ *DRAF MEDIA SOSIAL YANG DIJANA* ✨\n\n"
    keyboard = []
    for plat, text in generated_drafts.items():
        review_text += f"📱 *{plat.upper()}*:\n{text}\n\n"
        keyboard.append([InlineKeyboardButton(f"Confirm & Push {plat.upper()} ✅", callback_data=f"confirm_platform:{plat}")])

    review_text += "Sila klik butang di bawah untuk muat naik ke Google Drive & tolak ke Airtable."
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(review_text, parse_mode="Markdown", reply_markup=reply_markup)

async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    draft = draft_repo.get_draft(user_id)
    if not draft:
        await update.message.reply_text("⚠️ Tiada draf aktif dijumpai.")
        return

    title = draft["title"]
    hashtags = draft["hashtags"]
    image_url = draft["image_url"]
    source_url = draft["source_url"]
    selected_platform = draft["selected_platform"]
    platform_draft = draft["platform_draft"]

    if not selected_platform or not platform_draft:
        await update.message.reply_text("⚠️ Sila pilih platform draf terlebih dahulu.")
        return

    telegram_file_id = draft.get("telegram_file_id", "")
    counter = draft.get("counter_val", 0)
    final_image_url = await _prepare_drive_image_for_airtable(image_url, telegram_file_id, counter, context)

    specific_draft = platform_draft
    try:
        draft_dict = json.loads(platform_draft)
        if isinstance(draft_dict, dict):
            specific_draft = draft_dict.get(selected_platform, platform_draft)
    except Exception:
        pass

    res = save_draft_to_airtable(
        title=title,
        caption=specific_draft,
        platform=selected_platform,
        source_url=source_url,
        image_url=final_image_url,
        status="Draft",
        hashtags=hashtags
    )

    if res["status"] == "success":
        draft_repo.clear_draft(user_id)
        reply_msg = (
            f"✅ *Draf Hantaran {selected_platform.upper()} Berjaya Disahkan!*\n\n"
            f"• *Tajuk*: {title}\n"
            f"• *Platform*: {selected_platform.upper()}\n"
            f"• *Airtable Record*: Berjaya disimpan [Content Station]\n\n"
            f"Sedia untuk fasa posting!"
        )
        await _send_telegram_msg(update, reply_msg, parse_mode="Markdown")
    else:
        await _send_telegram_msg(update, f"⚠️ Gagal menyimpan ke Airtable: {res.get('error')}")

# ─── Callback Query Handler ────────────────────────────────────────────────────

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
            if ("x" in selected or "threads" in selected) and "thread_len" not in state_data["options"]:
                state_data["options"]["thread_len"] = 5

            draft_repo.update_draft_state(user_id, json.dumps(state_data))
            reply_markup = _get_sub_options_keyboard(state_data)
            await query.message.reply_text("Pilih pilihan sub-platform boss:", reply_markup=reply_markup)
        else:
            await query.message.reply_text("⏳ Menjana semua draf platform terpilih...")
            await _generate_all_platform_drafts(user_id, chat_id, selected, {}, draft, context, query.message)

    elif data == "sub_next":
        selected = state_data.get("selected", [])
        options = state_data.get("options", {})
        await query.message.reply_text("⏳ Menjana semua draf platform terpilih...")
        await _generate_all_platform_drafts(user_id, chat_id, selected, options, draft, context, query.message)

    elif data.startswith("confirm_platform:"):
        plat_to_confirm = data.split(":")[1]
        try:
            platform_drafts = json.loads(draft.get("platform_draft") or "{}")
        except Exception:
            platform_drafts = {}

        specific_draft = platform_drafts.get(plat_to_confirm, "")
        if not specific_draft:
            await query.answer("⚠️ Tiada draf dijumpai.", show_alert=True)
            return

        await query.message.reply_text(f"🚀 Menyimpan draf {plat_to_confirm.upper()} ke Airtable...")
        final_image_url = await _prepare_drive_image_for_airtable(draft["image_url"], draft.get("telegram_file_id", ""), draft.get("counter_val", 0), context)

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
            draft_repo.clear_draft(user_id)
            await query.message.reply_text(f"✅ *Draf {plat_to_confirm.upper()} Berjaya Disimpan ke Airtable!* 🎉", parse_mode="Markdown")
        else:
            await query.message.reply_text(f"⚠️ Gagal menyimpan ke Airtable: {res.get('error')}")

# ─── Message Handler Router ───────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_text: str = None):
    global current_key_idx
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    is_debug = DEBUG_USERS.get(user_id, False)

    user_message = override_text or update.message.text or ""
    if not user_message and not update.message.photo:
        return

    agent_message = user_message
    if user_message:
        msg_clean = user_message.strip().lower()
        if msg_clean.startswith("confirm") or msg_clean.startswith("/confirm"):
            await confirm_command(update, context)
            return

        if "http://" in msg_clean or "https://" in msg_clean or msg_clean.startswith("scrape"):
            url_match = re.search(r"https?://\S+", user_message)
            if url_match:
                target_url = url_match.group(0)
                await _execute_direct_scrape_pipeline(target_url, user_id, chat_id, context, update)
                return
        elif any(k in msg_clean for k in ["berita menarik", "berita viral", "berita trending", "gnews", "/news"]):
            await send_gnews_trending(update, context, category="trending", max_items=6)
            return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    conv_id = _get_conv_id_for_user(user_id)

    num_keys = len(GEMINI_KEYS)
    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        if memory.is_key_on_cooldown(active_key):
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

        os.environ["GEMINI_API_KEY"] = active_key
        try:
            from orchestrator.supervisor import get_supervisor_gemini_config
            from google.antigravity import Agent
            config = get_supervisor_gemini_config(conv_id)
            if config is None:
                break
            async with Agent(config) as agent:
                response = await asyncio.wait_for(agent.chat(agent_message), timeout=12.0)
                response_text = await response.text()
                if not conv_id and agent.conversation_id:
                    _register_conv_id_for_user(user_id, agent.conversation_id)

            response_text = await _process_response_draft(user_id, chat_id, response_text, context, update)
            if response_text == "[DRAFT_SENT_WITH_KEYBOARD]":
                return
            clean = _clean_response(response_text)
            await _send_telegram_msg(update, clean, parse_mode="Markdown")
            return
        except asyncio.TimeoutError:
            logger.warning(f"Gemini key #{current_key_idx + 1} timed out after 12s (429 backoff retry loop), placing on 10-min cooldown...")
            memory.set_key_cooldown(active_key, 600.0)
            current_key_idx = (current_key_idx + 1) % num_keys
            continue
        except Exception as err:
            logger.warning(f"Gemini key #{current_key_idx + 1} failed ({err}), trying next key...")
            if "429" in str(err) or "quota" in str(err).lower() or "resource_exhausted" in str(err).lower():
                memory.set_key_cooldown(active_key, 600.0)
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

    # ─── OpenRouter Proxy Fallback ──────────────────────────────────────────────
    try:
        logger.info(f"All Gemini keys in cooldown/failed. Falling back to OpenRouter ({OPENROUTER_FALLBACK_MODEL}) for user {user_id}...")
        os.environ["GEMINI_API_KEY"] = ""
        os.environ["OPENAI_API_KEY"] = OPENROUTER_API_KEY or "sk-or-v1-dummy"
        from orchestrator.supervisor import get_supervisor_openrouter_config
        from google.antigravity import Agent
        or_config = get_supervisor_openrouter_config(conv_id)
        if or_config is not None:
            async with Agent(or_config) as agent:
                response = await asyncio.wait_for(agent.chat(agent_message), timeout=45.0)
                response_text = await response.text()
                if not conv_id and agent.conversation_id:
                    _register_conv_id_for_user(user_id, agent.conversation_id)

            response_text = await _process_response_draft(user_id, chat_id, response_text, context, update)
            if response_text == "[DRAFT_SENT_WITH_KEYBOARD]":
                return
            clean = _clean_response(response_text)
            final_text = f"[P1] {OPENROUTER_FALLBACK_MODEL}\n\n{clean}" if not is_debug else f"🔧 *[DEBUG: OpenRouter]*\n\n{clean}"
            await _send_telegram_msg(update, final_text, parse_mode="Markdown")
            return
    except Exception as or_err:
        logger.error(f"[OpenRouter Fallback Error] {or_err}", exc_info=True)

    await update.message.reply_text("⚠️ Semua Gemini API Key & OpenRouter Fallback sedang bercuti/cooldown. Sila cuba sebentar lagi!")

# ─── Handler Registration ─────────────────────────────────────────────────────

def _audit_gemini_keys_async():
    """Non-blocking background check of Gemini API keys to seed 429 cooldown state."""
    def _check():
        for key in GEMINI_KEYS:
            if not memory.is_key_on_cooldown(key):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
                    r = httpx.post(url, json={"contents": [{"parts": [{"text": "ping"}]}]}, timeout=5)
                    if r.status_code == 429:
                        logger.info(f"[KeyAuditor] Gemini key {key[:8]}... returned 429, setting 10-min cooldown.")
                        memory.set_key_cooldown(key, 600.0)
                except Exception as e:
                    logger.warning(f"[KeyAuditor] Key audit ping error for {key[:8]}...: {e}")
    threading.Thread(target=_check, daemon=True).start()

def register_telegram_handlers(application: Application):
    """Register all Telegram bot command, callback, location, and message handlers."""
    _audit_gemini_keys_async()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(CommandHandler("confirm", confirm_command))
    application.add_handler(CommandHandler("sethome", sethome_command))
    application.add_handler(CommandHandler("sethq", sethq_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(MessageHandler(filters.Regex(r"^/s\d+$"), scrape_shortcut_command))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))
    logger.info("Telegram UI handlers registered successfully.")
