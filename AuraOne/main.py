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

def _send_safe_message(text: str, max_length: int = 4000) -> str:
    """Guard Telegram message length to avoid BadRequest text too long errors."""
    if len(text) > max_length:
        return text[:max_length] + "\n\n⚠️ *(Respon dipotong kerana melebihi had Telegram)*"
    return text


async def _send_telegram_msg(update: Update, text: str, parse_mode: str = None, reply_markup=None, disable_preview: bool = False):
    """Send Telegram message with markdown support, automatically falling back to plain text if parsing fails.
    Set disable_preview=True to suppress link preview cards (useful for news lists with many URLs)."""
    import html as _html_mod
    from telegram import LinkPreviewOptions

    target_parse_mode = parse_mode
    target_text = text
    
    # Build link preview options (PTB v20+)
    link_preview_opts = LinkPreviewOptions(is_disabled=True) if disable_preview else None
    
    # If caller already provides HTML content, pass through directly
    if parse_mode == "HTML":
        target_parse_mode = "HTML"
        target_text = text
    elif parse_mode in ["Markdown", "MarkdownV2", "markdown", "markdownv2"]:
        import re

        placeholder_map = {}
        counter = 0

        def store_link(match):
            nonlocal counter
            key = f"___LINK_PLACEHOLDER_{counter}___"
            counter += 1
            link_text = _html_mod.escape(match.group(1))
            url = match.group(2)
            placeholder_map[key] = f'<a href="{url}">{link_text}</a>'
            return key

        # Store markdown links first to prevent HTML escaping from corrupting URLs
        text_with_placeholders = re.sub(r"\[(.*?)\]\((https?://[^\s\)]+)\)", store_link, text)

        # Escape general HTML characters
        escaped = _html_mod.escape(text_with_placeholders)

        # Restore link placeholders
        for key, val in placeholder_map.items():
            escaped = escaped.replace(key, val)

        # Convert **bold** and *bold* to <b>bold</b>
        escaped = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"\*(.*?)\*", r"<b>\1</b>", escaped)

        # Convert _italic_ to <i>italic</i>
        escaped = re.sub(r"_(.*?)_", r"<i>\1</i>", escaped)

        # Convert `code` to <code>code</code>
        escaped = re.sub(r"`(.*?)`", r"<code>\1</code>", escaped)

        target_text = escaped
        target_parse_mode = "HTML"

    thread_id = None
    if update.message:
        thread_id = getattr(update.message, "message_thread_id", None)
    elif update.callback_query and update.callback_query.message:
        thread_id = getattr(update.callback_query.message, "message_thread_id", None)

    try:
        if update.message:
            await update.message.reply_text(target_text, parse_mode=target_parse_mode, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(target_text, parse_mode=target_parse_mode, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
    except BadRequest as e:
        logger.warning(f"Telegram parse mode {target_parse_mode} failed. Falling back. Error: {e}")
        # Fallback 1: strip ALL HTML/Markdown tags to produce clean plain text (no raw URLs)
        import re as _re_mod
        plain = _re_mod.sub(r"<[^>]+>", "", target_text)           # strip HTML tags
        plain = _re_mod.sub(r"\[(.*?)\]\(https?://[^\s\)]+\)", r"\1", plain)  # strip MD links keeping label
        plain = _re_mod.sub(r"https?://\S+", "", plain)            # remove any remaining raw URLs
        plain = _html_mod.unescape(plain)                          # decode &amp; etc
        plain = _re_mod.sub(r"\n{3,}", "\n\n", plain).strip()
        try:
            if update.message:
                await update.message.reply_text(plain, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(plain, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
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

    # ── GNews & Viral Confessions Callback Handlers (No content draft required) ─────
    if data.startswith("viral_menu:"):
        offset_str = data.split(":")[1]
        offset = int(offset_str) if offset_str.isdigit() else 0
        await query.answer("🔥 Mengambil 6 cerita sensasi & confession terkini...")
        await send_viral_confessions(update, context, offset=offset)
        return

    if data == "gnews_back":
        await query.answer("◀️ Kembali ke menu utama Berita Trending...")
        await send_gnews_trending(update, context, category="trending", max_items=6)
        return

    if data.startswith("gnews_cat:"):
        cat = data.split(":")[1]
        await query.answer("📰 Mengambil 10 berita Google News terkini...")
        
        cat_queries = {
            "gajet": ("gajet teknologi telefon pintar Malaysia 2026", "GAJET & TEKNOLOGI"),
            "korporat": ("korporat ekonomi perniagaan saham Malaysia 2026", "KORPORAT & EKONOMI"),
            "artis": ("artis hiburan selebriti drama Malaysia 2026", "ARTIS & HIBURAN"),
            "sukan": ("sukan bola sepak badminton harimau malaya 2026", "SUKAN MALAYSIA"),
            "viral": ("viral panas isu sensasi luahan confession Malaysia 2026", "VIRAL & CONFESSION"),
            "nasional": ("isu semasa nasional kerajaan politik Malaysia 2026", "ISU SEMASA NASIONAL")
        }

        q, cat_title = cat_queries.get(cat, (f"{cat} Malaysia 2026", cat.upper()))
        articles = fetch_gnews_articles(q, max_items=10)
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")

        if not articles:
            await query.message.reply_text("⚠️ Tiada berita terkini dijumpai untuk kategori ini.", parse_mode=None)
            return

        import html as _h
        lines = []
        for idx, a in enumerate(articles, start=1):
            t = _h.escape(a['title'])
            s = _h.escape(a['source']) if a['source'] else ""
            d = _h.escape(a['desc'])
            lnk = a['link']
            source_str = f" • Sumber: {s}\n" if s else ""
            lines.append(
                f"<b>{idx}. {t}</b>\n"
                f"{source_str}"
                f"   • <i>{d}</i>\n"
                f"   👉 <a href=\"{lnk}\">Baca Sini</a>"
            )
        
        body = "\n\n".join(lines)
        cat_title_esc = _h.escape(cat_title)
        reply = (
            f"📰 <b>{cat_title_esc} [{today_str}]</b>\n"
            f"───────────────\n\n"
            f"{body}\n\n"
            f"───────────────\n"
            f"💡 <b>Pilih Kategori Berita Tambahan (Tekan Butang Di Bawah)</b>:"
        )
        reply_markup = _get_gnews_keyboard()
        await _send_telegram_msg(update, reply, reply_markup=reply_markup, parse_mode="HTML", disable_preview=True)
        return

    # ── Location Callback Handlers (No content draft required) ──────────────
    if data.startswith("loc_search:"):
        category = data.split(":")[1]
        loc = memory.get_user_location(user_id)
        if not loc:
            await query.answer("⚠️ Tiada lokasi tersimpan. Sila hantar lokasi (location pin) anda terlebih dahulu!", show_alert=True)
            return
        
        cat_names = {
            "makan": "Kedai Makan / Restoran Sedap",
            "cafe": "Cafe Lepak Santai",
            "petrol": "Stesen Minyak",
            "hardware": "Kedai Perkakasan / Hardware"
        }
        cat_title = cat_names.get(category, category.title())
        await query.message.reply_text(f"🔍 Mencari *{cat_title}* berdekatan lokasi anda...", parse_mode="Markdown")
        
        from tools import search_web
        search_query = f"{cat_title} terdekat berdekatan {loc['address']}"
        search_res = search_web(search_query)
        
        reply = (
            f"📍 *HASIL CARIAN BERDEKATAN ({cat_title.upper()})*\n"
            f"───────────────\n\n"
            f"{search_res}\n\n"
            f"───────────────\n"
            f"✨ *AURA sedia bantu jika boss ada soalan lanjut!*"
        )
        await _send_telegram_msg(update, reply, parse_mode="Markdown")
        return

    elif data.startswith("loc_action:"):
        act = data.split(":")[1]
        loc = memory.get_user_location(user_id)
        if not loc:
            await query.answer("⚠️ Tiada lokasi tersimpan. Sila hantar lokasi (location pin) anda dahulu!", show_alert=True)
            return

        if act == "set_home":
            memory.save_user_place(user_id, "home", loc["latitude"], loc["longitude"], loc["address"])
            await query.answer("✅ Lokasi RUMAH berjaya disimpan!", show_alert=True)
            reply_markup = _get_location_keyboard(user_id, loc["latitude"], loc["longitude"])
            try:
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            except Exception:
                pass
            await query.message.reply_text(f"🏠 *LOKASI RUMAH BERJAYA DISIMPAN!*\n\n• Alamat: `{loc['address']}`", parse_mode="Markdown")

        elif act == "set_hq":
            memory.save_user_place(user_id, "hq", loc["latitude"], loc["longitude"], loc["address"])
            await query.answer("✅ Lokasi HQ Sakluma berjaya disimpan!", show_alert=True)
            reply_markup = _get_location_keyboard(user_id, loc["latitude"], loc["longitude"])
            try:
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            except Exception:
                pass
            await query.message.reply_text(f"🏢 *LOKASI HQ SAKLUMA BERJAYA DISIMPAN!*\n\n• Alamat: `{loc['address']}`", parse_mode="Markdown")

        elif act == "events_nearby":
            await query.answer("🎉 Mengesan acara & aktiviti berdekatan...")
            
            def _extract_city_area(address: str) -> str:
                if not address:
                    return "Malaysia"
                parts = [p.strip() for p in address.split(",")]
                for part in parts:
                    p_lower = part.lower()
                    if any(c in p_lower for c in [
                        "kuala lumpur", "seremban", "port dickson", "negeri sembilan", 
                        "shah alam", "petaling jaya", "subang jaya", "klang", "puchong", 
                        "cyberjaya", "putrajaya", "kajang", "bangi", "melaka", "johor bahru", 
                        "ipoh", "georgetown", "penang", "kuantan", "kota bharu", "kuala terengganu", 
                        "alor setar", "kangar", "kota kinabalu", "kuching", "selangor"
                    ]):
                        return part
                cleaned = [p for p in parts if not p.isdigit() and p.lower() not in ["malaysia", "singapore", "thailand"]]
                if len(cleaned) >= 2:
                    return f"{cleaned[-2]}, {cleaned[-1]}"
                elif cleaned:
                    return cleaned[0]
                return address

            city_area = _extract_city_area(loc["address"])
            await query.message.reply_text(f"🔍 Mengumpul & menyusun senarai event mengikut tarikh terkini di *{city_area}*...", parse_mode="Markdown")
            
            from tools import search_web
            search_query = f"event acara pesta aktiviti terkini {city_area} 2026"
            search_res = search_web(search_query)
            
            formatted_results = ""
            today_str = datetime.datetime.now().strftime("%Y-%m-%d (%A)")
            
            # Use Gemini to parse & sort events chronologically by date into exactly 8 clean items
            try:
                prompt = (
                    f"Hari ini: {today_str}.\n"
                    f"Hasil carian web terkini kawasan {city_area}:\n\n"
                    f"{search_res}\n\n"
                    f"ARAHAN KETAT:\n"
                    f"1. Hasilkan TEPAT 8 SENARAI ACARA/AKTIVITI terdekat mengikut urutan tarikh kronologi.\n"
                    f"2. GAYA SUPER SHORT & PACKED (NO WORDY PARAGRAPHS, NO LONG DESCRIPTIONS, NO INTRO/OUTRO TEXT):\n"
                    f"   Formatkan setiap item kepada 2 baris sahaja:\n"
                    f"   <no>. 📅 <Tarikh Ringkas> | <Emoji> *<Nama Event/Aktiviti Short>*\n"
                    f"      📍 <Lokasi Ringkas> | 🔗 <[Info](link) jika ada>\n"
                    f"3. Jika carian web kurang dari 8 item, pelbagaikan dengan tempat/aktiviti riadah & tumpuan popular kawasan {city_area}.\n"
                    f"4. TERUS PULANGKAN SENARAI 1 HINGGA 8 SAHAJA TANPA AYAT ALUTAN ATAU PENUTUP."
                )
                from google import genai
                active_key = GEMINI_KEYS[current_key_idx]
                client = genai.Client(api_key=active_key)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                if response and response.text:
                    formatted_results = response.text.strip()
            except Exception as e:
                logger.warning(f"Error date sorting events with Gemini: {e}")

            if not formatted_results or "error" in formatted_results.lower():
                formatted_results = (
                    f"1. 📅 25 Jul 2026 | 🏃‍♂️ *IMMI SELRUN 2026*\n"
                    f"   📍 Kompleks PKNS | 🔗 [Info](https://racexasia.com)\n\n"
                    f"2. 📅 28 Jul 2026 | 🛍️ *Bazaar Usahawan PKNS*\n"
                    f"   📍 Kompleks PKNS Shah Alam\n\n"
                    f"3. 📅 01 Ogos 2026 | ⚽ *Tayangan Skrin Gergasi FIFA*\n"
                    f"   📍 Aneka Walk, Seksyen 14\n\n"
                    f"4. 📅 05 Ogos 2026 | 🎨 *Pameran Seni Visual Laman 7*\n"
                    f"   📍 Laman Seni 7, Seksyen 7\n\n"
                    f"5. 📅 Harian (10am-10pm) | 🎭 *Muzium Sultan Alam Shah*\n"
                    f"   📍 Seksyen 14 Shah Alam\n\n"
                    f"6. 📅 Hujung Minggu | 🏞️ *Taman Tasik Shah Alam*\n"
                    f"   📍 Seksyen 14 Shah Alam\n\n"
                    f"7. 📅 Harian (6pm-12am) | 🎡 *I-City LED Park*\n"
                    f"   📍 Seksyen 7 Shah Alam\n\n"
                    f"8. 📅 Sabtu (5pm-10pm) | 🍢 *Pasar Malam Stadium*\n"
                    f"   📍 Tapak Stadium, Seksyen 13"
                )

            reply = (
                f"🎉 *8 ACARA & AKTIVITI TERKINI ({city_area.upper()})*\n"
                f"───────────────\n\n"
                f"📍 *Kawasan*: `{city_area}`\n"
                f"📆 *Tarikh*: `{today_str}`\n\n"
                f"{formatted_results}\n\n"
                f"───────────────\n"
                f"✨ *AURA Event Guide*"
            )
            await _send_telegram_msg(update, reply, parse_mode="Markdown")
        return

    # ── Content Draft Callback Handlers (Requires active content draft) ────────
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
        if update.message and update.message.photo:
            telegram_file_id = update.message.photo[-1].file_id
            logger.info(f"Using incoming Telegram photo file_id: {telegram_file_id}")

        # Send image to Telegram first as a preview and cache its Telegram file_id
        if image_url and not telegram_file_id:
            try:
                photo_msg = await context.bot.send_photo(chat_id=chat_id, photo=image_url)
                if photo_msg and photo_msg.photo:
                    telegram_file_id = photo_msg.photo[-1].file_id
                    logger.info(f"Successfully sent preview. Cached Telegram file_id: {telegram_file_id}")
            except Exception as e:
                logger.warning(f"Could not send photo preview: {e}")

        # Check if the user requested any platforms in their prompt message
        selected_platforms_list = []
        user_txt = (update.message.text or update.message.caption or "").lower()
        if "fb" in user_txt or "facebook" in user_txt:
            selected_platforms_list.append("facebook")
        if "threads" in user_txt:
            selected_platforms_list.append("threads")
        if "twitter" in user_txt or " x " in f" {user_txt} ":
            selected_platforms_list.append("x")
        if "lemon8" in user_txt:
            selected_platforms_list.append("lemon8")

        # Save draft in SQLite with interactive state: select_platforms & metadata
        state_dict = {
            "phase": "select_platforms",
            "selected": selected_platforms_list,
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

        # Upload text dump to Google Drive in the background
        from tools import upload_article_dump_to_drive
        import threading
        threading.Thread(
            target=upload_article_dump_to_drive,
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
        reply_markup = _get_platform_keyboard(state_dict)
        
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



from tools.publisher_service import _prepare_drive_image_for_airtable




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

    # Extract specific platform draft caption from JSON if platform_draft is a JSON dictionary
    specific_draft = platform_draft
    try:
        import json
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
            posts = [p.strip() for p in specific_draft.split("\n\n") if p.strip()]
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





def fetch_gnews_articles(query: str = "Malaysia trending viral 2026", max_items: int = 6) -> list:
    """Fetch live news from Google News Malaysia RSS feed."""
    import urllib.parse
    import xml.etree.ElementTree as ET
    import re
    import html

    encoded_q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ms&gl=MY&ceid=MY:ms"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    articles = []
    try:
        with httpx.Client(timeout=10, follow_redirects=True, headers=headers) as client:
            res = client.get(url)
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                items = root.findall(".//item")
                for item in items[:max_items]:
                    raw_title = item.find("title").text if item.find("title") is not None else "Berita Trending"
                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    description = item.find("description").text if item.find("description") is not None else ""
                    
                    # Unescape HTML entities in title BEFORE splitting source
                    raw_title = html.unescape(raw_title).strip()
                    
                    source_name = ""
                    if " - " in raw_title:
                        title_parts = raw_title.rsplit(" - ", 1)
                        title = title_parts[0].strip()
                        source_name = title_parts[1].strip()
                    else:
                        title = raw_title.strip()
                    
                    # Unescape HTML entities (&nbsp;, &amp;, &quot;, etc.) and remove HTML tags
                    clean_desc = html.unescape(description)
                    clean_desc = re.sub(r"<[^>]+>", "", clean_desc)
                    clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
                    
                    if clean_desc.startswith(title):
                        clean_desc = clean_desc[len(title):].strip()
                    if source_name and clean_desc.startswith(source_name):
                        clean_desc = clean_desc[len(source_name):].strip()

                    if len(clean_desc) > 130:
                        clean_desc = clean_desc[:127] + "..."
                    if not clean_desc or len(clean_desc) < 5:
                        clean_desc = f"Berita terbaharu dilaporkan oleh {source_name or 'Google News'}."
                        
                    articles.append({
                        "title": title,
                        "source": source_name,
                        "link": link,
                        "date": pub_date,
                        "desc": clean_desc
                    })
    except Exception as e:
        logger.warning(f"Error fetching GNews RSS: {e}")
    return articles


def _get_gnews_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [
        [
            InlineKeyboardButton("💻 Gajet & Tech", callback_data="gnews_cat:gajet"),
            InlineKeyboardButton("💼 Korporat", callback_data="gnews_cat:korporat")
        ],
        [
            InlineKeyboardButton("🎭 Artis & Hiburan", callback_data="gnews_cat:artis"),
            InlineKeyboardButton("⚽ Sukan", callback_data="gnews_cat:sukan")
        ],
        [
            InlineKeyboardButton("🔥 Viral & Confession", callback_data="viral_menu:0"),
            InlineKeyboardButton("⚡ Isu Semasa", callback_data="gnews_cat:nasional")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def _get_viral_confessions_keyboard(offset: int = 0):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    next_offset = offset + 6
    keyboard = [
        [
            InlineKeyboardButton("🔥 More Confessions", callback_data=f"viral_menu:{next_offset}"),
            InlineKeyboardButton("◀️ Back Ke Menu News", callback_data="gnews_back")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_viral_confessions(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0):
    """Fetch 6 sensational viral/confession articles from IIUMC, Reddit Bolehland/Malaysia, and forums with robust fallback."""
    queries = [
        "viral confession luahan rumah tangga curang Malaysia 2026",
        "IIUM Confessions luahan rumah tangga skandal 2026",
        "Reddit Bolehland Malaysia luahan isteri suami curang 2026",
        "Lowyat Kopitiam luahan confession rumah tangga viral 2026"
    ]
    
    q = queries[(offset // 6) % len(queries)]
    from tools import search_web
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
            elif "kosmo" in link.lower():
                source_name = "Kosmo Digital"
            elif "sinar" in link.lower():
                source_name = "Sinar Harian"

            articles.append({
                "title": title,
                "source": source_name,
                "link": link,
                "desc": snippet
            })
            if len(articles) >= 6:
                break

    # If web search returned less than 6 items, fill remaining items with GNews RSS
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
    """Send GNews articles with category buttons."""
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


async def _get_weather_forecast(lat: float, lon: float) -> str:
    """Fetch 1-day hourly weather forecast from Open-Meteo API."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,weathercode,precipitation_probability"
            f"&timezone=Asia%2FKuala_Lumpur&forecast_days=1"
        )
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                hourly = data.get("hourly", {})
                temps = hourly.get("temperature_2m", [])
                codes = hourly.get("weathercode", [])
                precip = hourly.get("precipitation_probability", [])

                def get_desc(c, p):
                    if c == 0: return "☀️ Cerah"
                    elif c in [1, 2, 3]: return "⛅ Berawan"
                    elif c in [45, 48]: return "🌫️ Kabus"
                    elif c in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return f"🌧️ Hujan ({p}%)"
                    elif c in [95, 96, 99]: return f"⛈️ Ribut ({p}%)"
                    return "🌤️ Redup"

                pagi = f"• *Pagi (9am)*: {get_desc(codes[9], precip[9])} | `{temps[9]}°C`"
                ptg = f"• *Petang (3pm)*: {get_desc(codes[15], precip[15])} | `{temps[15]}°C`"
                malam = f"• *Malam (9pm)*: {get_desc(codes[21], precip[21])} | `{temps[21]}°C`"
                return f"{pagi}\n{ptg}\n{malam}"
    except Exception as e:
        logger.warning(f"Weather forecast error: {e}")
    return "• *Cuaca*: Tidak dapat diproses"


async def _get_extended_weather_forecast(lat: float, lon: float) -> str:
    """Fetch 7-day daily weather forecast from Open-Meteo API."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Asia%2FKuala_Lumpur&forecast_days=7"
        )
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                daily = data.get("daily", {})
                times = daily.get("time", [])
                max_temps = daily.get("temperature_2m_max", [])
                min_temps = daily.get("temperature_2m_min", [])
                codes = daily.get("weathercode", [])
                precip = daily.get("precipitation_sum", [])

                def get_desc(c):
                    if c == 0: return "☀️ Cerah"
                    elif c in [1, 2, 3]: return "⛅ Berawan"
                    elif c in [45, 48]: return "🌫️ Kabus"
                    elif c in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "🌧️ Hujan"
                    elif c in [95, 96, 99]: return "⛈️ Ribut"
                    return "🌤️ Redup"

                lines = []
                for i in range(len(times)):
                    date_str = times[i]
                    lines.append(f"• `{date_str}`: {get_desc(codes[i])} | `{min_temps[i]}°C - {max_temps[i]}°C` (Hujan: `{precip[i]}mm`)")
                
                return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Extended weather forecast error: {e}")
    return "• *Cuaca 7 Hari*: Tidak dapat diproses"


def _get_location_keyboard(user_id: int, current_lat: float, current_lon: float):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    import memory
    places = memory.get_user_places(user_id)
    
    # Home button logic: direct Google Maps navigation URL if set, otherwise Set Home action
    if "home" in places:
        h_lat = places["home"]["lat"]
        h_lon = places["home"]["lon"]
        home_nav_url = f"https://www.google.com/maps/dir/?api=1&origin={current_lat},{current_lon}&destination={h_lat},{h_lon}"
        home_btn = InlineKeyboardButton("🏠 Home", url=home_nav_url)
    else:
        home_btn = InlineKeyboardButton("🏠 Set Home", callback_data="loc_action:set_home")
        
    # Work button logic: direct Google Maps navigation URL if set, otherwise Set Work action
    if "hq" in places:
        hq_lat = places["hq"]["lat"]
        hq_lon = places["hq"]["lon"]
        work_nav_url = f"https://www.google.com/maps/dir/?api=1&origin={current_lat},{current_lon}&destination={hq_lat},{hq_lon}"
        work_btn = InlineKeyboardButton("🏢 Work", url=work_nav_url)
    else:
        work_btn = InlineKeyboardButton("🏢 Set Work", callback_data="loc_action:set_hq")

    # Direct Google Maps Nearby Search URLs
    makan_url = f"https://www.google.com/maps/search/Kedai+Makan+Sedap/@{current_lat},{current_lon},15z"
    cafe_url = f"https://www.google.com/maps/search/Cafe/@{current_lat},{current_lon},15z"
    petrol_url = f"https://www.google.com/maps/search/Stesen+Minyak/@{current_lat},{current_lon},15z"
    hardware_url = f"https://www.google.com/maps/search/Kedai+Hardware/@{current_lat},{current_lon},15z"

    keyboard = [
        [
            home_btn,
            work_btn,
            InlineKeyboardButton("🎉 Events", callback_data="loc_action:events_nearby")
        ],
        [
            InlineKeyboardButton("🍽️ Makan Best", url=makan_url),
            InlineKeyboardButton("☕ Cafe Lepak", url=cafe_url),
        ],
        [
            InlineKeyboardButton("⛽ Stesen Minyak", url=petrol_url),
            InlineKeyboardButton("🛠️ Hardware", url=hardware_url)
        ]
    ]
        
    return InlineKeyboardMarkup(keyboard)


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


async def sethome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    import memory
    loc = memory.get_user_location(user_id)
    if not loc:
        await update.message.reply_text("⚠️ Sila hantar lokasi (location pin) anda di Telegram terlebih dahulu sebelum menanda tempat Rumah.")
        return
    memory.save_user_place(user_id, "home", loc["latitude"], loc["longitude"], loc["address"])
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
    import memory
    loc = memory.get_user_location(user_id)
    if not loc:
        await update.message.reply_text("⚠️ Sila hantar lokasi (location pin) anda di Telegram terlebih dahulu sebelum menanda HQ Sakluma.")
        return
    memory.save_user_place(user_id, "hq", loc["latitude"], loc["longitude"], loc["address"])
    await update.message.reply_text(
        f"🏢 *LOKASI HQ SAKLUMA BERJAYA DISIMPAN!*\n"
        f"───────────────\n\n"
        f"• *Alamat*: `{loc['address']}`\n"
        f"• *Koordinat*: `{loc['latitude']}, {loc['longitude']}`\n\n"
        f"Kini setiap kali anda menghantar lokasi di Telegram, butang *[🏢 Navigasi Ke HQ]* akan dipaparkan secara automatik!",
        parse_mode="Markdown"
    )


async def scrape_shortcut_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        idx = int(text.replace("/s", ""))
    except ValueError:
        return
    
    urls = context.user_data.get("scrape_urls", {})
    if idx in urls:
        url = urls[idx]
        await update.message.reply_text(f"⚡ *Memproses Artikel {idx}...*\n_{url}_\nSila tunggu...", parse_mode="Markdown", disable_web_page_preview=True)
        await handle_message(update, context, override_text=f"Scrape {url}")
    else:
        await update.message.reply_text("⚠️ URL tidak dijumpai dalam memori sesi. Sila minta senarai berita baru.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_text: str = None):
    global current_key_idx
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    is_debug = DEBUG_USERS.get(user_id, False)

    user_message = ""
    media_part = None

    if update.message.photo:
        photo = update.message.photo[-1]
        user_message = update.message.caption or "Analisis gambar ini."
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            telegram_file = await context.bot.get_file(photo.file_id)
            file_bytearray = await telegram_file.download_as_bytearray()
            img_bytes = bytes(file_bytearray)
            # Save to temp file for OpenRouter proxy image injection fallback
            try:
                with open("/tmp/last_user_media.jpg", "wb") as f:
                    f.write(img_bytes)
                with open("/tmp/last_user_media_mime.txt", "w") as f:
                    f.write("image/jpeg")
                logger.info("Saved incoming photo to /tmp/last_user_media.jpg for OpenRouter proxy injection fallback.")
            except Exception as tmp_err:
                logger.error(f"Failed to save temp photo for proxy injection: {tmp_err}")
            from google.antigravity import Image as AGImage
            media_part = AGImage(data=img_bytes, mime_type="image/jpeg")
            logger.info(f"Loaded user photo of {len(img_bytes)} bytes for Gemini multimodal processing.")
        except Exception as e:
            logger.error(f"Failed to download incoming Telegram photo: {e}")
            await update.message.reply_text(f"⚠️ Gagal memuat turun gambar: {e}")
            return

    elif update.message.video:
        video = update.message.video
        user_message = update.message.caption or "Analisis video ini."
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            telegram_file = await context.bot.get_file(video.file_id)
            file_bytearray = await telegram_file.download_as_bytearray()
            video_bytes = bytes(file_bytearray)
            from google.antigravity import Video as AGVideo
            # Fallback to standard MP4 if mime type not in SDK supported set
            mime_type = video.mime_type or "video/mp4"
            if mime_type not in ["video/3gpp", "video/avi", "video/mp4", "video/mpeg", "video/mpg", "video/quicktime", "video/webm", "video/wmv", "video/x-flv"]:
                mime_type = "video/mp4"
            media_part = AGVideo(data=video_bytes, mime_type=mime_type)
            logger.info(f"Loaded user video of {len(video_bytes)} bytes ({mime_type}) for Gemini multimodal processing.")
        except Exception as e:
            logger.error(f"Failed to download incoming Telegram video: {e}")
            await update.message.reply_text(f"⚠️ Gagal memuat turun video: {e}")
            return

    elif update.message.voice:
        voice = update.message.voice
        user_message = "Analisis audio/suara ini."
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            telegram_file = await context.bot.get_file(voice.file_id)
            file_bytearray = await telegram_file.download_as_bytearray()
            voice_bytes = bytes(file_bytearray)
            from google.antigravity import Audio as AGAudio
            mime_type = voice.mime_type or "audio/ogg"
            if mime_type not in ["audio/wav", "audio/mp3", "audio/aac", "audio/ogg", "audio/flac", "audio/opus", "audio/mpeg", "audio/m4a", "audio/l16"]:
                mime_type = "audio/ogg"
            media_part = AGAudio(data=voice_bytes, mime_type=mime_type)
            logger.info(f"Loaded user voice of {len(voice_bytes)} bytes ({mime_type}) for Gemini multimodal processing.")
        except Exception as e:
            logger.error(f"Failed to download incoming Telegram voice: {e}")
            await update.message.reply_text(f"⚠️ Gagal memuat turun mesej suara: {e}")
            return

    elif update.message.document:
        doc = update.message.document
        user_message = update.message.caption or "Analisis dokumen ini."
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            telegram_file = await context.bot.get_file(doc.file_id)
            file_bytearray = await telegram_file.download_as_bytearray()
            doc_bytes = bytes(file_bytearray)
            from google.antigravity import Document as AGDoc
            mime_type = doc.mime_type or "text/plain"
            if mime_type not in ["application/pdf", "application/json", "text/css", "text/csv", "text/html", "text/javascript", "text/plain", "text/rtf", "text/xml"]:
                mime_type = "text/plain"
            media_part = AGDoc(data=doc_bytes, mime_type=mime_type)
            logger.info(f"Loaded user document of {len(doc_bytes)} bytes ({mime_type}) for Gemini multimodal processing.")
        except Exception as e:
            logger.error(f"Failed to download incoming Telegram document: {e}")
            await update.message.reply_text(f"⚠️ Gagal memuat turun dokumen: {e}")
            return

    elif override_text:
        user_message = override_text
    else:
        user_message = update.message.text

    if not user_message and not media_part:
        return

    if user_message:
        msg_clean = user_message.strip().lower()
        if msg_clean.startswith("confirm") or msg_clean.startswith("/confirm"):
            await confirm_command(update, context)
            return

        if any(k in msg_clean for k in ["set rumah", "setkan rumah", "set koordinat", "set cordinat", "sebagai rumah"]):
            if "hq" not in msg_clean and "office" not in msg_clean:
                import memory
                loc = memory.get_user_location(user_id)
                if loc:
                    memory.save_user_place(user_id, "home", loc["latitude"], loc["longitude"], loc["address"])
                    reply_markup = _get_location_keyboard(user_id, loc["latitude"], loc["longitude"])
                    reply = (
                        f"🏠 *LOKASI RUMAH BERJAYA DISIMPAN!*\n"
                        f"───────────────\n\n"
                        f"• *Alamat*: `{loc['address']}`\n"
                        f"• *Koordinat*: `{loc['latitude']}, {loc['longitude']}`\n\n"
                        f"Setiap kali boss hantar lokasi baru, butang *[🚗 Ke Rumah]* akan dipaparkan secara automatik di Telegram!"
                    )
                    await update.message.reply_text(reply, parse_mode="Markdown", reply_markup=reply_markup)
                    return

        if "http://" not in msg_clean and "https://" not in msg_clean and not msg_clean.startswith("scrape"):
            if any(k in msg_clean for k in ["berita menarik", "berita viral", "berita trending", "berita malaysia", "gnews", "/news", "top news", "berita terkini", "berita harini", "berita hari ini"]):
                await send_gnews_trending(update, context, category="trending", max_items=6)
                return

        if any(k in msg_clean for k in ["set hq", "setkan hq", "set office", "sebagai hq"]):
            import memory
            loc = memory.get_user_location(user_id)
            if loc:
                memory.save_user_place(user_id, "hq", loc["latitude"], loc["longitude"], loc["address"])
                reply_markup = _get_location_keyboard(user_id, loc["latitude"], loc["longitude"])
                reply = (
                    f"🏢 *LOKASI HQ SAKLUMA BERJAYA DISIMPAN!*\n"
                    f"───────────────\n\n"
                    f"• *Alamat*: `{loc['address']}`\n"
                    f"• *Koordinat*: `{loc['latitude']}, {loc['longitude']}`\n\n"
                    f"Setiap kali boss hantar lokasi baru, butang *[🏎️ Ke HQ]* akan dipaparkan secara automatik di Telegram!"
                )
                await update.message.reply_text(reply, parse_mode="Markdown", reply_markup=reply_markup)
                return

        import memory
        loc = memory.get_user_location(user_id)
        if loc:
            user_message += (
                f"\n\n[SISTEM: Lokasi semasa user ialah {loc['address']} (Lat: {loc['latitude']}, Lon: {loc['longitude']}). "
                f"Gunakan maklumat ini jika user mencari kedai makan, barang, tukang urut, rating, arah, atau jika bertanya 'saya dekat mana sekarang'. "
                f"Untuk carian kedai/barang, gunakan carian web untuk mencari tempat terdekat dengan koordinat ini. "
                f"PENTING: JANGAN sekali-kali memaparkan, menyebut, atau membuat nota tentang alamat/lokasi ini dalam jawapan anda melainkan ditanya secara spesifik oleh user!]"
            )



    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    conv_id = _get_conv_id_for_user(user_id)
    gemini_success = False
    response_text = ""
    num_keys = len(GEMINI_KEYS)

    import time
    import memory
    
    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        
        # Check persistent cooldown from SQLite memory database
        prefs = memory.get_preferences()
        cooldown_expiry_str = prefs.get(f"cooldown:{active_key}", "0.0")
        try:
            cooldown_expiry = float(cooldown_expiry_str)
        except ValueError:
            cooldown_expiry = 0.0
            
        if cooldown_expiry > time.time():
            logger.info(f"[Gemini] Key index {current_key_idx} is on cooldown for another {int(cooldown_expiry - time.time())}s. Skipping...")
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

        os.environ["GEMINI_API_KEY"] = active_key
        gemini_config = _build_gemini_config(conv_id)

        try:
            logger.info(f"[Gemini] Attempting chat using key index {current_key_idx}/{num_keys}...")
            async with Agent(gemini_config) as agent:
                chat_input = [media_part, user_message] if media_part else user_message
                response = await agent.chat(chat_input)
                response_text = await response.text()

                if not conv_id:
                    new_id = agent.conversation_id
                    if new_id:
                        _register_conv_id_for_user(user_id, new_id)
                        logger.info(f"[Gemini] New session for user {user_id}: {new_id}")
            gemini_success = True
            break
        except Exception as gemini_err:
            err_str = str(gemini_err)
            if "429" in err_str:
                logger.warning(f"[Gemini] Key index {current_key_idx} hit 429 Rate Limit. Putting on 10-min cooldown and rotating...")
                memory.update_preference(f"cooldown:{active_key}", str(time.time() + 600.0))
            else:
                logger.warning(f"[Gemini] Key index {current_key_idx} error: {gemini_err}. Rotating...")
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

    if gemini_success:
        response_text = await _process_response_draft(user_id, chat_id, response_text, context, update)
        if response_text == "[DRAFT_SENT_WITH_KEYBOARD]":
            return
        if is_debug:
            final_text = _send_safe_message(f"🔧 *\\[DEBUG: Gemini\\]*\n\n{response_text}")
            await _send_telegram_msg(update, final_text, parse_mode="MarkdownV2")
        else:
            clean = _clean_response(response_text)
            final_text = _send_safe_message(f"[F{current_key_idx + 1}] google/gemini-2.5-flash\n\n{clean}")
            await _send_telegram_msg(update, final_text, parse_mode="Markdown")
        return

    # If all free keys hit rate limits, fall back to OpenRouter Proxy
    logger.warning(f"[Gemini] All {num_keys} keys rate limited or unavailable. Switching to OpenRouter Proxy...")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    if not OPENROUTER_API_KEY:
        await update.message.reply_text(
            "⚠️ Gemini telah mencapai had penggunaan dan OPENROUTER_API_KEY tidak dikonfigurasi."
        )
        return

    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]

    or_config = _build_openrouter_config(conv_id)

    try:
        async with Agent(or_config) as agent:
            chat_input = [media_part, user_message] if media_part else user_message
            response = await agent.chat(chat_input)
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
            final_text = _send_safe_message(f"[P1] {OPENROUTER_FALLBACK_MODEL}\n\n{clean}")
            await _send_telegram_msg(update, final_text, parse_mode="Markdown")

    except Exception as or_err:
        logger.error(f"[OpenRouter] Fallback error for user {user_id}: {or_err}", exc_info=True)
        err_msg = _send_safe_message(
            f"⚠️ Kedua-dua model gagal:\n• Gemini: Had penggunaan\n• OpenRouter: {str(or_err)}"
        )
        await _send_telegram_msg(update, err_msg)



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
