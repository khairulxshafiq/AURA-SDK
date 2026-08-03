"""
ADELIA Core — Master Article Generator.

Transforms raw scraped article text into a neutral, style-free Master Article
(Neutral Core Context & Story Hub) + metadata tags.

Pure I/O logic — NO Telegram dependencies, NO database calls.
Uses adelia.llm.llm_caller for LLM generation.
"""

from __future__ import annotations

import logging
import re

from adelia.llm.llm_caller import call_llm

logger = logging.getLogger("adelia.core.master_article")

# Default prompt template for neutral master article generation
MASTER_ARTICLE_PROMPT_TEMPLATE = (
    "Anda adalah Editor Konten & Analyst Sakluma profesional.\n"
    "Tugas anda: Tulis kandungan Master Article penuh dalam format Ringkasan Fakta Neutral & Cerita Penuh Artikel (Neutral Core Context & Story Hub) berdasarkan kandungan artikel berikut.\n\n"
    "SYARAT & STRUKTUR MASTER ARTICLE:\n"
    "1. Format Neutral & Tanpa Gaya Bahasa (Style-Free): DILARANG menggunakan gaya perbualan ('Adakah anda...', 'Sinar Harian baru-baru ini...'), DILARANG meletakkan Hashtag atau CTA dalam Master Article, DILARANG membuat muqaddimah karangan blog.\n"
    "2. Struktur Wajib:\n"
    "   📌 TAJUK ASAL / FOKUS UTAMA: Tajuk ringkas isu\n"
    "   📝 RINGKASAN ISU / RINGKASAN CERITA: Cerita penuh secara kronologi/sebab-akibat tentang apa yang berlaku\n"
    "   📊 FAKTA & POIN PENTING: Senarai bullet points data, angka, atau kenyataan penting\n"
    "   💡 SUDUT PANDANG KUNCI: Intipati utama artikel yang boleh dijadikan bahan perbincangan\n\n"
    "TAJUK ASAL: {title}\n"
    "URL ASAL: {source_url}\n\n"
    "KANDUNGAN ARTIKEL:\n{content}\n\n"
    "Sila tulis kandungan Master Article neutral secara lengkap dan terperinci. Di bahagian AKHIR jawapan anda, MESTI sertakan tag metadata [DRAFT_*] mengikut format berikut:\n\n"
    "[DRAFT_TITLE: {title}]\n"
    "[DRAFT_SOURCE_URL: {source_url}]\n"
    "[DRAFT_IMAGE: {image_url}]\n"
    "[DRAFT_HASHTAGS: #Sakluma #Trending #IsuSemasa]"
)


def extract_metadata_tags(raw_text: str) -> dict[str, str]:
    """Extract metadata tags formatted as [DRAFT_KEY: value] from LLM response."""
    tags = {}
    pattern = re.compile(r"\[DRAFT_([A-Z_]+):\s*(.*?)\]")
    for match in pattern.finditer(raw_text):
        key = match.group(1).lower()
        val = match.group(2).strip()
        tags[key] = val
    return tags


def clean_master_article_text(raw_text: str) -> str:
    """Remove [DRAFT_*] metadata tags from the master article content."""
    cleaned = re.sub(r"\[DRAFT_[A-Z_]+:\s*.*?\]", "", raw_text)
    return cleaned.strip()


async def generate_master_article(
    scraped_text: str,
    title: str = "Artikel Berita",
    source_url: str = "",
    image_url: str = "",
    timeout: float = 10.0,
) -> dict:
    """Generate a neutral Master Article from raw scraped web content.

    Args:
        scraped_text: The main text body extracted from web page.
        title: Title of the source article.
        source_url: Source URL of the article.
        image_url: Optional image URL extracted from page.
        timeout: Timeout in seconds for LLM call.

    Returns:
        Dict containing:
        - master_article (str): Cleaned neutral article text
        - title (str): Final article title
        - source_url (str): Source URL
        - image_url (str): Image URL
        - hashtags (list[str]): List of hashtag strings
        - raw_generated (str): Unedited raw response from LLM
    """
    if not scraped_text or len(scraped_text.strip()) < 50:
        logger.warning("Scraped text is too short (< 50 chars) for master article generation.")
        return {
            "master_article": scraped_text.strip(),
            "title": title,
            "source_url": source_url,
            "image_url": image_url,
            "hashtags": ["#Sakluma", "#IsuSemasa"],
            "raw_generated": scraped_text,
        }

    # Truncate input content to 4000 characters (matching AuraOne pipeline)
    content_snippet = scraped_text[:4000]

    prompt = MASTER_ARTICLE_PROMPT_TEMPLATE.format(
        title=title or "Artikel Berita",
        source_url=source_url or "",
        image_url=image_url or "",
        content=content_snippet,
    )

    generated_text = await call_llm(prompt, timeout=timeout)

    # Fallback if LLM returns empty result
    if not generated_text:
        logger.warning("LLM returned empty text for master article. Using fallback template.")
        fallback_article = (
            f"📌 TAJUK ASAL: {title}\n\n"
            f"📝 RINGKASAN ISU:\n{scraped_text[:1500]}\n\n"
            f"💡 SUDUT PANDANG KUNCI: Isu semasa memerlukan perhatian awam."
        )
        return {
            "master_article": fallback_article,
            "title": title,
            "source_url": source_url,
            "image_url": image_url,
            "hashtags": ["#Sakluma", "#Berita"],
            "raw_generated": fallback_article,
        }

    metadata = extract_metadata_tags(generated_text)
    clean_article = clean_master_article_text(generated_text)

    # Parse hashtags into list
    raw_hashtags = metadata.get("hashtags", "#Sakluma #Trending #IsuSemasa")
    hashtags_list = [h.strip() for h in raw_hashtags.split() if h.startswith("#")]
    if not hashtags_list:
        hashtags_list = ["#Sakluma", "#Trending", "#IsuSemasa"]

    resolved_title = metadata.get("title", title)
    resolved_source_url = metadata.get("source_url", source_url)
    resolved_image_url = metadata.get("image", image_url)

    return {
        "master_article": clean_article,
        "title": resolved_title,
        "source_url": resolved_source_url,
        "image_url": resolved_image_url,
        "hashtags": hashtags_list,
        "raw_generated": generated_text,
    }
