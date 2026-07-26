import html
import urllib.parse
import xml.etree.ElementTree as ET
import re
import logging
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("aura.tools.search_engine")

def search_web(query: str, num_results: int = 5) -> dict:
    """Search the web for a given query and return top results with titles, links, and snippets.
    Uses DuckDuckGo HTML endpoint.
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

def fetch_gnews_articles(query: str = "Malaysia trending viral 2026", max_items: int = 6) -> list:
    """Fetch live news from Google News Malaysia RSS feed."""
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

DEFAULT_RSS_FEEDS = [
    ("https://www.hmetro.com.my/utama.xml", "Harian Metro"),
    ("https://www.astroawani.com/rss/berita-malaysia.xml", "Astro Awani"),
    ("http://feeds.bbci.co.uk/news/rss.xml", "BBC News")
]

def fetch_rss_articles(max_items: int = 6) -> list:
    """Fetch articles from direct RSS feeds as Tier 3 fallback."""
    articles = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for feed_url, default_source in DEFAULT_RSS_FEEDS:
        if len(articles) >= max_items:
            break
        try:
            with httpx.Client(timeout=8, follow_redirects=True, headers=headers) as client:
                res = client.get(feed_url)
                if res.status_code == 200:
                    root = ET.fromstring(res.text)
                    items = root.findall(".//item")
                    for item in items[:max_items - len(articles)]:
                        raw_title = item.find("title").text if item.find("title") is not None else ""
                        link = item.find("link").text if item.find("link") is not None else ""
                        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                        desc = item.find("description").text if item.find("description") is not None else ""

                        clean_title = html.unescape(raw_title).strip()
                        clean_desc = re.sub(r"<[^>]+>", "", html.unescape(desc or "")).strip()
                        if len(clean_desc) > 130:
                            clean_desc = clean_desc[:127] + "..."
                        if not clean_desc:
                            clean_desc = f"Berita daripada {default_source}."

                        if clean_title and link:
                            articles.append({
                                "title": clean_title,
                                "source": default_source,
                                "link": link,
                                "date": pub_date,
                                "desc": clean_desc
                            })
        except Exception as e:
            logger.warning(f"RSS fetch error for {feed_url}: {e}")
    return articles

def fetch_live_news_with_fallback(query: str = "Malaysia trending viral 2026", max_items: int = 6) -> tuple:
    """
    Executes live news search with strict priority sequence:
    1. Tier 1: GNews RSS (fetch_gnews_articles)
    2. Tier 2: Internet Search (search_web)
    3. Tier 3: Direct RSS Sources (fetch_rss_articles)
    Returns: (articles_list, source_tier_name)
    """
    # 1. Tier 1: GNews
    gnews_arts = fetch_gnews_articles(query, max_items=max_items)
    if gnews_arts:
        return gnews_arts, "GNews"

    # 2. Tier 2: Internet Search
    logger.info(f"[LiveNewsFallback] Tier 1 GNews empty for '{query}'. Trying Tier 2 (Internet Search)...")
    web_res = search_web(query, num_results=max_items)
    if web_res.get("status") == "success" and web_res.get("results"):
        web_arts = []
        for r in web_res["results"]:
            web_arts.append({
                "title": r.get("title", ""),
                "source": "Internet Search",
                "link": r.get("link", ""),
                "date": "",
                "desc": r.get("snippet", "")
            })
        return web_arts, "Internet Search"

    # 3. Tier 3: RSS Feeds
    logger.info(f"[LiveNewsFallback] Tier 2 Internet Search empty for '{query}'. Trying Tier 3 (RSS Feeds)...")
    rss_arts = fetch_rss_articles(max_items=max_items)
    if rss_arts:
        return rss_arts, "RSS Feeds"

    return [], "None"

