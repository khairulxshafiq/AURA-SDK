import os
import urllib.parse
import logging
import httpx
from bs4 import BeautifulSoup
from config import FIRECRAWL_API_KEY, FIRECRAWL_ENABLED, FIRECRAWL_TIMEOUT_MS

logger = logging.getLogger("aura.tools.web_scraper")

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"
JINA_READER_BASE = "https://r.jina.ai"

def resolve_gnews_url(url: str) -> str:
    """Resolve Google News redirect/rss URLs to the final destination article URL."""
    if not url or "news.google.com" not in url.lower():
        return url
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        with httpx.Client(timeout=10, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resolved = str(resp.url)
            logger.info(f"Resolved Google News URL: {url} -> {resolved}")
            return resolved
    except Exception as e:
        logger.warning(f"Could not resolve GNews redirect for {url}: {e}")
        return url

def _scrape_firecrawl(url: str, max_content_length: int = 30000) -> dict:
    """Scrape using Firecrawl API (bot-bypass capable)."""
    if not FIRECRAWL_API_KEY:
        return {"status": "error", "tier": "firecrawl", "error": "Firecrawl API key not set"}

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "url": url,
        "formats": ["markdown", "links"],
        "onlyMainContent": True,
        "waitFor": 1000,
    }

    try:
        with httpx.Client(timeout=FIRECRAWL_TIMEOUT_MS / 1000 + 5) as client:
            resp = client.post(f"{FIRECRAWL_BASE}/scrape", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            return {"status": "error", "tier": "firecrawl", "error": f"Firecrawl unsuccessful: {data.get('error', 'Unknown')}"}

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

def _scrape_jina(url: str, max_content_length: int = 30000) -> dict:
    """Scrape using Jina Reader API (https://r.jina.ai/{url})."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "X-No-Cache": "true"
    }
    jina_url = f"{JINA_READER_BASE}/{url}"

    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            resp = client.get(jina_url, headers=headers)
            resp.raise_for_status()
            content = resp.text

        if not content or len(content.strip()) < 50:
            return {"status": "error", "tier": "jina", "error": "Jina returned empty response"}

        if len(content) > max_content_length:
            content = content[:max_content_length]

        # Basic title extraction from first markdown header
        title = ""
        lines = content.splitlines()
        for line in lines:
            if line.startswith("# "):
                title = line.replace("# ", "").strip()
                break

        return {
            "status": "success",
            "tier": "jina",
            "title": title,
            "content": content,
            "images": [],
            "links": [],
            "url": url
        }
    except Exception as e:
        return {"status": "error", "tier": "jina", "error": str(e)}

def _scrape_native(url: str, max_content_length: int = 30000) -> dict:
    """Scrape using httpx + BeautifulSoup4 (free fallback)."""
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

def scrape_url(url: str, max_content_length: int = 30000) -> dict:
    """Scrape a web page URL and return its title, main content, images, and links.
    Automatically resolves GNews redirects, then tries Firecrawl -> Jina -> Native fallback.
    """
    resolved_target_url = resolve_gnews_url(url)

    # TIER 1: Try Firecrawl first (if enabled)
    if FIRECRAWL_ENABLED and FIRECRAWL_API_KEY:
        logger.info(f"[TIER 1] Scraping via Firecrawl: {resolved_target_url}")
        result = _scrape_firecrawl(resolved_target_url, max_content_length)
        if result["status"] == "success":
            return result
        logger.warning(f"[TIER 1] Firecrawl failed ({result.get('error')}), falling back to Jina/Native...")

    # TIER 2: Try Jina Reader
    logger.info(f"[TIER 2] Scraping via Jina Reader: {resolved_target_url}")
    jina_res = _scrape_jina(resolved_target_url, max_content_length)
    if jina_res["status"] == "success":
        return jina_res
    logger.warning(f"[TIER 2] Jina failed ({jina_res.get('error')}), falling back to native...")

    # TIER 3: Native scraper fallback
    logger.info(f"[TIER 3] Scraping natively: {resolved_target_url}")
    return _scrape_native(resolved_target_url, max_content_length)
