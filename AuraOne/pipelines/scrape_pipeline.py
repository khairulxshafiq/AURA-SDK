"""
Scrape Pipeline — URL scrape → Master Article generation → save draft → preview.
Extracted from ui/telegram_bot.py (_execute_direct_scrape_pipeline, scrape_shortcut_command).
"""
import logging

from tools.web_scraper import scrape_url
from pipelines.llm_caller import call_llm
from ui.formatters import _process_response_draft, _clean_response, _send_telegram_msg

logger = logging.getLogger("aura.pipelines.scrape_pipeline")


async def execute_scrape_pipeline(url: str, user_id: int, chat_id: int, context, update):
    """Direct Execution Pipeline for URL Scraping -> Master Article Generation -> UI Keyboards.
    Bypasses SDK async subagent loop to avoid intermediate metadata JSON output."""
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
    image_url = scraped.get("article_image_url", "") or scraped.get("image_url", "")
    if image_url and image_url.startswith("http://"):
        image_url = "https://" + image_url[7:]
    source_url = scraped.get("url", url)

    if not raw_content or len(raw_content) < 50:
        await update.message.reply_text("⚠️ Artikel yang di-scrape tidak mengandungi teks kandungan yang mencukupi.")
        return

    # 2. Direct Master Article Generation Prompt (Neutral Core Context & Story Hub)
    prompt = (
        f"Anda adalah Editor Konten & Analyst Sakluma profesional.\n"
        f"Tugas anda: Tulis kandungan Master Article penuh dalam format Ringkasan Fakta Neutral & Cerita Penuh Artikel (Neutral Core Context & Story Hub) berdasarkan kandungan artikel berikut.\n\n"
        f"SYARAT & STRUKTUR MASTER ARTICLE:\n"
        f"1. Format Neutral & Tanpa Gaya Bahasa (Style-Free): DILARANG menggunakan gaya perbualan ('Adakah anda...', 'Sinar Harian baru-baru ini...'), DILARANG meletakkan Hashtag atau CTA dalam Master Article, DILARANG membuat muqaddimah karangan blog.\n"
        f"2. Struktur Wajib:\n"
        f"   📌 TAJUK ASAL / FOKUS UTAMA: Tajuk ringkas isu\n"
        f"   📝 RINGKASAN ISU / RINGKASAN CERITA: Cerita penuh secara kronologi/sebab-akibat tentang apa yang berlaku\n"
        f"   📊 FAKTA & POIN PENTING: Senarai bullet points data, angka, atau kenyataan penting\n"
        f"   💡 SUDUT PANDANG KUNCI: Intipati utama artikel yang boleh dijadikan bahan perbincangan\n\n"
        f"TAJUK ASAL: {raw_title}\n"
        f"URL ASAL: {source_url}\n\n"
        f"KANDUNGAN ARTIKEL:\n{raw_content[:4000]}\n\n"
        f"Sila tulis kandungan Master Article neutral secara lengkap dan terperinci. Di bahagian AKHIR jawapan anda, MESTI sertakan tag metadata [DRAFT_*] mengikut format berikut:\n\n"
        f"[DRAFT_TITLE: {raw_title}]\n"
        f"[DRAFT_SOURCE_URL: {source_url}]\n"
        f"[DRAFT_IMAGE: {image_url}]\n"
        f"[DRAFT_HASHTAGS: #Sakluma #Trending #IsuSemasa]"
    )

    # 3. Call LLM (Gemini with key rotation + OpenRouter fallback)
    generated_text = await call_llm(prompt, timeout=10.0)

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


async def handle_scrape_shortcut(update, context):
    """Handle /s1, /s2, /s3... shortcut commands to scrape a previously listed article."""
    text = update.message.text.strip()
    try:
        idx = int(text.replace("/s", ""))
    except ValueError:
        return

    urls = context.user_data.get("scrape_urls", {})
    if idx in urls:
        url = urls[idx]
        await update.message.reply_text(f"⚡ *Memproses Artikel {idx}...*\n_{url}_", parse_mode="Markdown", disable_web_page_preview=True)
        await execute_scrape_pipeline(url, update.effective_user.id, update.effective_chat.id, context, update)
    else:
        await update.message.reply_text("⚠️ URL tidak dijumpai dalam memori sesi. Sila minta senarai berita baru.")
