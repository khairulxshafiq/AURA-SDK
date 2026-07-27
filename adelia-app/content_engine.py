"""
ADELIA Content Engine — Decoupled Content Microservice Core
Handles 3-Tier Scraping (Firecrawl -> Jina -> Native), GNews/Search, and Multi-Platform Persona Draft Generation (FB, Threads, X, Lemon8).
"""
import os
import re
import urllib.parse
import logging
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("adelia.content_engine")

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"
JINA_READER_BASE = "https://r.jina.ai"

def resolve_gnews_url(url: str) -> str:
    if not url or "news.google.com" not in url.lower():
        return url
    try:
        import base64
        match = re.search(r"/articles/([^/?]+)", url)
        if match:
            art_id = match.group(1)
            missing_padding = len(art_id) % 4
            if missing_padding:
                art_id += '=' * (4 - missing_padding)
            decoded_bytes = base64.urlsafe_b64decode(art_id)
            http_matches = re.findall(rb"https?://[^\s\x00-\x1f\x7f-\xff]+", decoded_bytes)
            if http_matches:
                final_url = http_matches[0].decode('utf-8', errors='ignore')
                final_url = re.sub(r"[^\w\-\.\/\?\=\&\%\:\#\+\~]+$", "", final_url)
                if final_url.startswith("http") and "news.google.com" not in final_url:
                    return final_url
    except Exception as e:
        logger.warning(f"GNews b64 decode error: {e}")
        
    try:
        from googlenewsdecoder import gnewsdecoder
        res = gnewsdecoder(url)
        if isinstance(res, dict) and res.get("status") and res.get("decoded_url"):
            decoded_url = res["decoded_url"]
            if decoded_url.startswith("http") and "news.google.com" not in decoded_url:
                return decoded_url
    except Exception as e:
        logger.warning(f"GNews decoder error: {e}")
        
    return url

def _ensure_https(url_str: str) -> str:
    if not url_str:
        return ""
    url_str = url_str.strip()
    if url_str.startswith("http://"):
        return "https://" + url_str[7:]
    return url_str

def extract_article_image_url(soup: BeautifulSoup, page_url: str) -> str:
    if not soup:
        return ""
    og_meta = (
        soup.find("meta", property="og:image") or
        soup.find("meta", attrs={"name": "og:image"}) or
        soup.find("meta", property="og:image:secure_url")
    )
    if og_meta and og_meta.get("content"):
        content = og_meta["content"].strip()
        if content:
            abs_url = urllib.parse.urljoin(page_url, content)
            if abs_url.startswith("http"):
                return _ensure_https(abs_url)

    tw_meta = (
        soup.find("meta", attrs={"name": "twitter:image"}) or
        soup.find("meta", property="twitter:image")
    )
    if tw_meta and tw_meta.get("content"):
        content = tw_meta["content"].strip()
        if content:
            abs_url = urllib.parse.urljoin(page_url, content)
            if abs_url.startswith("http"):
                return _ensure_https(abs_url)
    return ""

def scrape_url(url: str, max_content_length: int = 30000) -> dict:
    resolved_target_url = resolve_gnews_url(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    
    # Try Jina first for speed & markdown parsing
    try:
        jina_url = f"{JINA_READER_BASE}/{resolved_target_url}"
        with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
            resp = client.get(jina_url)
            if resp.status_code == 200 and len(resp.text) > 100:
                content = resp.text[:max_content_length]
                lines = content.splitlines()
                title = lines[0].replace("#", "").strip() if lines else "Scraped Article"
                img_match = re.search(r"!\[.*?\]\((https?://[^\s\)]+)\)", content)
                article_img = _ensure_https(img_match.group(1)) if img_match else ""
                return {
                    "status": "success",
                    "tier": "jina",
                    "title": title,
                    "content": content,
                    "article_image_url": article_img,
                    "image_url": article_img,
                    "url": resolved_target_url
                }
    except Exception as e:
        logger.warning(f"Jina scrape failed: {e}")
        
    # Native fallback
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = client.get(resolved_target_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            title = soup.title.string.strip() if soup.title else "Scraped Article"
            article_img = extract_article_image_url(soup, resolved_target_url)
            main = soup.find("article") or soup.find("main") or soup.find("body")
            content = main.get_text(separator="\n", strip=True)[:max_content_length] if main else ""
            return {
                "status": "success",
                "tier": "native",
                "title": title,
                "content": content,
                "article_image_url": article_img,
                "image_url": article_img,
                "url": resolved_target_url
            }
    except Exception as e:
        return {"status": "error", "error": f"Scrape failed: {str(e)}", "url": resolved_target_url}

def build_fb_prompt(style: str, master_draft: str) -> str:
    styles = {
        "fb_berita": "Gaya Berita / Laporan Rasmi (Dateline Kuala Lumpur, neutral reporting).",
        "fb_pemerhati": "Gaya Pemerhati / Pengajaran Kampung (Storytelling, ikhtibar kehidupan).",
        "fb_kedai_kopi": "Gaya Sembang Kedai Kopi (Logik rakyat, lontaran pendapat santai).",
        "fb_viral_santai": "Gaya Viral Santai (Hook 'Wehh', 'Korang perasan tak', mesra).",
        "fb_makcik_bawang": "Gaya Makcik Bawang (Gossip bersahaja, suspens, soalan audiens).",
        "fb_kisah_inspirasi": "Gaya Kisah Inspirasi (Menyentuh jiwa, nilai murni)."
    }
    chosen = styles.get(style.lower(), "Gaya penceritaan Facebook santai bermaklumat.")
    return f"""Bertindak sebagai Copywriter Facebook Sakluma. Tulis semula artikel berikut ke dalam gaya {style.upper()}:

{chosen}

Syarat Wajib:
1. Max 2 hashtag.
2. Tajuk/Hook utama yang menarik perhatian.
3. Clean markdown output tanpa conversational intro.

TEKS ASAL:
{master_draft}
"""
