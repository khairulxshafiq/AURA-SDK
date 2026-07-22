<<<<<<< HEAD
import os
import re
import time
import base64
import logging
import urllib.parse
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("aura.tools.web")

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"

def _scrape_firecrawl(url: str, max_content_length: int = 30000) -> dict:
    """Scrape using Firecrawl API (bot-bypass capable)."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    timeout_ms = int(os.environ.get("FIRECRAWL_TIMEOUT_MS", "30000"))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "url": url,
        "formats": ["markdown", "links"],
        "onlyMainContent": True,
        "waitFor": 1000,
    }

    try:
        with httpx.Client(timeout=timeout_ms / 1000 + 5) as client:
            resp = client.post(f"{FIRECRAWL_BASE}/scrape", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            return {"status": "error", "error": f"Firecrawl unsuccessful: {data.get('error', 'Unknown')}"}

        fc_data = data.get("data", {})
        content = fc_data.get("markdown", "") or fc_data.get("content", "")
        if len(content) > max_content_length:
            content = content[:max_content_length]

        metadata = fc_data.get("metadata", {})
        title = metadata.get("title", "") or metadata.get("ogTitle", "")
        images = [metadata.get("ogImage", "")] if metadata.get("ogImage") else []
        links = fc_data.get("links", [])[:20]

        return {
            "status": "success",
            "tier": "firecrawl",
            "title": title,
            "content": content,
            "images": images,
            "links": links,
            "url": url
        }

    except httpx.HTTPStatusError as e:
        return {"status": "error", "tier": "firecrawl", "error": f"Firecrawl HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "tier": "firecrawl", "error": str(e)}

def _scrape_native(url: str, max_content_length: int = 30000) -> dict:
    """Scrape using httpx + BeautifulSoup4 (free, no API key needed)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ms;q=0.8",
    }

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (403, 429):
            return {
                "status": "error",
                "tier": "native",
                "error": f"BlockedByBotProtection — HTTP {e.response.status_code}"
            }
        return {"status": "error", "tier": "native", "error": f"HTTP {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"status": "error", "tier": "native", "error": "TIMEOUT"}
    except Exception as e:
        return {"status": "error", "tier": "native", "error": str(e)}

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    title = ""
    if soup.title:
        title = (soup.title.string or "").strip()
    if not title and soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    main = soup.find("article") or soup.find("main") or soup.find("body")
    content = ""
    if main:
        content = main.get_text(separator="\n", strip=True)
    if len(content) > max_content_length:
        content = content[:max_content_length]


    images = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        abs_src = urllib.parse.urljoin(url, src)
        if abs_src.startswith("http") and any(ext in abs_src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            images.append(abs_src)
        if len(images) >= 3:
            break

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        abs_href = urllib.parse.urljoin(url, href)
        if abs_href.startswith("http"):
            links.append(abs_href)
        if len(links) >= 20:
            break


    return {
        "status": "success",
        "tier": "native",
        "title": title,
        "content": content,
        "images": images,
        "links": links,
        "url": url
    }

def resolve_gnews_url(url: str) -> str:
    """Resolve base64-encoded Google News redirect/wrapper URL to the final destination URL."""
    if "news.google.com" not in url:
        return url

    # Method 1: Direct Base64 Payload Byte Decoding (Sub-millisecond, zero network overhead)
    try:
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
                    logger.info(f"[GNewsResolver] Method 1 (base64) resolved: {url[:45]}... -> {final_url}")
                    return final_url
    except Exception as b64_err:
        logger.warning(f"[GNewsResolver] Method 1 base64 decode failed: {b64_err}")

    # Method 2: Use googlenewsdecoder library
    try:
        from googlenewsdecoder import gnewsdecoder
        res = gnewsdecoder(url)
        if isinstance(res, dict) and res.get("status") and res.get("decoded_url"):
            decoded_url = res["decoded_url"]
            if decoded_url.startswith("http") and "news.google.com" not in decoded_url:
                logger.info(f"[GNewsResolver] Method 2 (decoder) resolved: {url[:45]}... -> {decoded_url}")
                return decoded_url
    except Exception as dec_err:
        logger.warning(f"[GNewsResolver] Method 2 decoder failed: {dec_err}")

    # Method 3: HTTP GET with follow_redirects=True & HTML canonical parsing
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(timeout=10, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            final_url = str(resp.url)
            if final_url.startswith("http") and "news.google.com" not in final_url:
                logger.info(f"[GNewsResolver] Method 3 (redirect) resolved: {url[:45]}... -> {final_url}")
                return final_url

            soup = BeautifulSoup(resp.text, "html.parser")
            canonical = soup.find("link", rel="canonical")
            if canonical and canonical.get("href"):
                can_href = canonical["href"]
                if can_href.startswith("http") and "news.google.com" not in can_href:
                    logger.info(f"[GNewsResolver] Method 3 (canonical) resolved: {url[:45]}... -> {can_href}")
                    return can_href

            og_url = soup.find("meta", property="og:url")
            if og_url and og_url.get("content"):
                og_href = og_url["content"]
                if og_href.startswith("http") and "news.google.com" not in og_href:
                    logger.info(f"[GNewsResolver] Method 3 (og:url) resolved: {url[:45]}... -> {og_href}")
                    return og_href
    except Exception as http_err:
        logger.warning(f"[GNewsResolver] Method 3 HTTP fetch failed: {http_err}")

    return url

def _scrape_jina(url: str, max_content_length: int = 30000) -> dict:
    """Scrape using Jina Reader API (free Cloudflare bot-bypass)."""
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get(jina_url, headers=headers)
            resp.raise_for_status()
            text = resp.text

        title = ""
        title_m = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
        if title_m:
            title = title_m.group(1).strip()

        images = re.findall(r"!\[.*?\]\((https?://[^\s\)]+)\)", text)
        images = [img for img in images if any(ext in img.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"])]

        content = text
        if len(content) > max_content_length:
            content = content[:max_content_length]

        if len(content) < 100:
            return {"status": "error", "tier": "jina", "error": "Gagal mengekstrak isi kandungan artikel."}

        return {
            "status": "success",
            "tier": "jina",
            "title": title or "Scraped Article",
            "content": content,
            "images": images[:3],
            "links": [],
            "url": url
        }
    except Exception as e:
        return {"status": "error", "tier": "jina", "error": str(e)}

def scrape_url(url: str, max_content_length: int = 30000) -> dict:
    """Scrape a web page URL and return its title, main content, images, and links.
    Automatically un-wraps Google News RSS redirect links, tries Firecrawl (bot-bypass) first, falls back to native scraper, then Jina Reader Cloudflare bypass.
    """
    if "news.google.com" in url:
        url = resolve_gnews_url(url)

    firecrawl_enabled = os.environ.get("FIRECRAWL_ENABLED", "false").lower() == "true"
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")

    # TIER 1: Try Firecrawl first
    if firecrawl_enabled and firecrawl_key:
        logger.info(f"[TIER 1] Scraping via Firecrawl: {url}")
        result = _scrape_firecrawl(url, max_content_length)
        if result["status"] == "success" and len(result.get("content", "")) > 100:
            return result
        logger.warning(f"[TIER 1] Firecrawl failed ({result.get('error')}), falling back to native...")

    # TIER 2: Native scraper fallback
    logger.info(f"[TIER 2] Scraping natively: {url}")
    result = _scrape_native(url, max_content_length)
    if result["status"] == "success" and len(result.get("content", "")) > 100:
        return result

    # TIER 3: Jina Reader Cloudflare Bypass
    logger.info(f"[TIER 3] Native scraper hit bot protection or empty content. Scraping via Jina Reader: {url}")
    jina_res = _scrape_jina(url, max_content_length)
    if jina_res["status"] == "success":
        return jina_res

    # Error Fallback
    logger.error(f"All scraping tiers failed for {url}")
    return {
        "status": "error",
        "error": "Gagal mengekstrak isi kandungan artikel dari pautan tersebut.",
        "url": url
    }

def search_web(query: str, num_results: int = 5) -> dict:
    """Search the web for a given query and return top results with titles, links, and snippets.
    Uses DuckDuckGo (free, no API key needed).
    """
    encoded = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AURA-Research/1.0)",
        "Accept-Language": "en-US,en;q=0.9,ms;q=0.8",
    }

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
    except Exception as e:
        return {"status": "error", "error": f"Search failed: {str(e)}"}

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    for result in soup.select(".result"):
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        link = title_el.get("href", "")
        if "uddg=" in link:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
            link = parsed.get("uddg", [""])[0]
        if link.startswith("/"):
            link = ""

        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        if title and link.startswith("http"):
            results.append({"title": title, "link": link, "snippet": snippet})

        if len(results) >= min(num_results, 10):
            break

    return {
        "status": "success",
        "query": query,
        "results": results,
        "count": len(results)
    }
=======
# Façade module for backward compatibility
# Re-exports all atomic tools from tools.*

import storage.memory_repository as memory_repo
>>>>>>> fae0967 (refactor(core): complete Phase 1 foundation, storage repository pattern & atomic tools layer)

from tools.web_scraper import (
    _scrape_firecrawl,
    _scrape_jina,
    _scrape_native,
    resolve_gnews_url,
    scrape_url,
)
from tools.search_engine import (
    search_web,
    fetch_gnews_articles,
)
from tools.location_service import (
    reverse_geocode_location,
    _get_weather_forecast,
    _get_extended_weather_forecast,
)
from tools.apify_service import (
    run_apify_actor,
)
from tools.publisher_service import (
    _get_gdrive_access_token,
    upload_to_drive,
    save_draft_to_airtable,
    save_thread_posts_to_airtable,
    _host_on_github,
    _upload_article_dump_to_github,
    _prepare_drive_image_for_airtable,
)

# Tool wrappers for LLM invocation
def save_user_fact(fact_content: str, category: str = "general") -> str:
    """Simpan satu fakta penting atau maklumat baru yang dipelajari tentang pengguna ke memori jangka panjang."""
    success = memory_repo.save_fact(fact_content, category)
    if success:
        return f"Berjaya menyimpan fakta baru ke dalam memori: '{fact_content}'"
    return "Fakta tersebut sudah wujud di dalam memori."

def update_user_preference(key: str, value: str) -> str:
    """Kemaskini preferensi atau konfigurasi pengguna dalam memori jangka panjang."""
    memory_repo.update_preference(key, value)
    return f"Berjaya mengemaskini preferensi '{key}' kepada '{value}'."

__all__ = [
    "_scrape_firecrawl",
    "_scrape_jina",
    "_scrape_native",
    "resolve_gnews_url",
    "scrape_url",
    "search_web",
    "fetch_gnews_articles",
    "reverse_geocode_location",
    "_get_weather_forecast",
    "_get_extended_weather_forecast",
    "run_apify_actor",
    "_get_gdrive_access_token",
    "upload_to_drive",
    "save_draft_to_airtable",
    "save_thread_posts_to_airtable",
    "_host_on_github",
    "_upload_article_dump_to_github",
    "_prepare_drive_image_for_airtable",
    "save_user_fact",
    "update_user_preference",
]
