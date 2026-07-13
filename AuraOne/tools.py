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


# ─── Google Drive & Airtable Helpers ──────────────────────────────────────────

GDRIVE_API = "https://www.googleapis.com/drive/v3"
GDRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

def _get_gdrive_access_token() -> Optional[str]:
    import json
    sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json_str:
        return None
    try:
        sa_info = json.loads(sa_json_str)
        from google.oauth2 import service_account
        import google.auth.transport.requests
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token
    except Exception as e:
        logger.error(f"Failed to get Google Drive access token: {e}")
        return None

def upload_to_drive(content_bytes: bytes, filename: str, mime_type: str = "image/jpeg", folder_id: str = None) -> dict:
    import json
    folder_id = folder_id or os.environ.get("GDRIVE_FOLDER_ID", "1Apv70Qwp2iF0405kn4mmzaB1UmXkWwqM")
    token = _get_gdrive_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive credentials not set"}
    try:
        headers = {"Authorization": f"Bearer {token}"}
        metadata = json.dumps({
            "name": filename,
            "parents": [folder_id],
        })
        boundary = b"aura_boundary"
        body = (
            b"--" + boundary + b"\r\n"
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n" +
            metadata.encode() + b"\r\n"
            b"--" + boundary + b"\r\n"
            b"Content-Type: " + mime_type.encode() + b"\r\n\r\n" +
            content_bytes + b"\r\n"
            b"--" + boundary + b"--"
        )
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{GDRIVE_UPLOAD_API}/files",
                params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                content=body,
                headers={
                    **headers,
                    "Content-Type": f"multipart/related; boundary=aura_boundary"
                }
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "status": "success",
            "file_id": data.get("id"),
            "name": data.get("name"),
            "link": data.get("webViewLink")
        }
    except Exception as e:
        logger.error(f"upload_to_drive error: {e}")
        return {"status": "error", "error": str(e)}

def save_draft_to_airtable(
    title: str,
    caption: str,
    platform: str = "facebook",
    style: str = "santai_bercerita",
    source_url: str = "",
    image_url: str = "",
    brand: str = "",
    created_by: str = "AURA (SDK)",
    status: str = "Draft",
    hashtags: str = "",
    scheduled_time: str = ""
) -> dict:
    import json
    api_key = os.environ.get("AIRTABLE_API_KEY", "")
    base_id = os.environ.get("AIRTABLE_BASE_ID", "")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME", "Content Station")
    if not api_key or not base_id:
        return {"status": "error", "error": "Airtable credentials missing"}
    if not brand:
        brand = os.environ.get("DEFAULT_BRAND", "Sakluma")
    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Map platform names nicely
    plat_name = "X" if platform.lower() in ["twitter", "x"] else platform.title()
    
    fields = {
        "Title": title,
        "Caption": caption,
        "Platform": [plat_name],
        "Status": status,
        "Brand": brand,
        "Post Link": source_url,
        "Content Type": "Article",
        "Created By": created_by,
        "Hashtags": hashtags,
        "Scheduled Date": scheduled_time,
        "Image file": [{"url": image_url}] if image_url else None,
        "Gambar": [{"url": image_url}] if image_url else None
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=headers, json={"fields": fields})
            
            # Smart self-healing fallback for different field existence
            if resp.status_code == 422 and "UNKNOWN_FIELD_NAME" in resp.text:
                err_msg = resp.text
                retry_needed = False
                
                if "Gambar" in err_msg and "Gambar" in fields:
                    logger.info("Gambar column not found in Airtable, removing it.")
                    fields.pop("Gambar", None)
                    retry_needed = True
                    
                if "Image file" in err_msg and "Image file" in fields:
                    logger.info("Image file column not found in Airtable, removing it.")
                    fields.pop("Image file", None)
                    retry_needed = True
                    
                if "Scheduled Date" in err_msg and "Scheduled Date" in fields:
                    logger.info("Scheduled Date column not found in Airtable, removing it.")
                    fields.pop("Scheduled Date", None)
                    retry_needed = True

                if retry_needed:
                    resp = client.post(url, headers=headers, json={"fields": fields})
                
            resp.raise_for_status()
            data = resp.json()
            return {"status": "success", "record_id": data.get("id")}
    except Exception as e:
        logger.error(f"Airtable error: {e}")
        return {"status": "error", "error": str(e)}

