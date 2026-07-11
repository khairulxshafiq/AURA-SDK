import os
import re
import time
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
        if src.startswith("http") and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            images.append(src)
        if len(images) >= 3:
            break

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http"):
            links.append(href)
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

def scrape_url(url: str, max_content_length: int = 30000) -> dict:
    """Scrape a web page URL and return its title, main content, images, and links.
    Automatically tries Firecrawl (bot-bypass) first, falls back to native scraper.
    """
    firecrawl_enabled = os.environ.get("FIRECRAWL_ENABLED", "false").lower() == "true"
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")

    # TIER 1: Try Firecrawl first
    if firecrawl_enabled and firecrawl_key:
        logger.info(f"[TIER 1] Scraping via Firecrawl: {url}")
        result = _scrape_firecrawl(url, max_content_length)
        if result["status"] == "success":
            return result
        logger.warning(f"[TIER 1] Firecrawl failed ({result.get('error')}), falling back to native...")

    # TIER 2: Native scraper fallback
    logger.info(f"[TIER 2] Scraping natively: {url}")
    return _scrape_native(url, max_content_length)

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


def save_user_fact(fact_content: str, category: str = "general") -> str:
    """Simpan satu fakta penting atau maklumat baru yang dipelajari tentang pengguna (Matrol/Khairulshafiq) atau projek ke dalam memori jangka panjang SQLite.
    Gunakan tool ini apabila pengguna memberikan info peribadi yang penting untuk diingati di masa hadapan.
    """
    import memory
    success = memory.save_fact(fact_content, category)
    if success:
        return f"Berjaya menyimpan fakta baru ke dalam memori: '{fact_content}'"
    return f"Fakta tersebut sudah wujud di dalam memori."


def update_user_preference(key: str, value: str) -> str:
    """Kemaskini preferensi atau konfigurasi pengguna dalam memori jangka panjang SQLite (cth: owner_name, working_style, dsb).
    Gunakan tool ini apabila pengguna menukar tetapan atau cara kerja kegemaran mereka.
    """
    import memory
    memory.update_preference(key, value)
    return f"Berjaya mengemaskini preferensi '{key}' kepada '{value}'."

