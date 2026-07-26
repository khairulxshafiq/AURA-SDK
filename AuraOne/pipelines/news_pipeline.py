"""
News Pipeline — GNews trending articles & viral confessions.
Extracted from ui/telegram_bot.py (send_gnews_trending, send_viral_confessions).
"""
import re
import datetime
import logging

from tools.search_engine import fetch_gnews_articles, search_web, fetch_live_news_with_fallback
from ui.keyboards import _get_gnews_keyboard, _get_viral_confessions_keyboard
from ui.formatters import _send_telegram_msg

logger = logging.getLogger("aura.pipelines.news_pipeline")


async def send_viral_confessions(update, context, offset: int = 0):
    """Fetch and display 6 viral confession/luahan stories with pagination."""
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


async def send_gnews_trending(update, context, category: str = "trending", max_items: int = 6):
    """Fetch and display trending news articles by category with inline keyboard navigation."""
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
    articles, source_tier = fetch_live_news_with_fallback(q, max_items)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    if not articles:
        reply_text = f"⚠️ Tiada berita terkini dijumpai untuk kategori ini dari carian terus."
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
