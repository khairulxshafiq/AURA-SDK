# Façade module for backward compatibility
# Re-exports all atomic tools from tools.*

import storage.memory_repository as memory_repo

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
    upload_file_to_drive,
    upload_to_drive,
    delete_file_from_drive,
    update_file_on_drive,
    upload_article_dump_to_drive,
    save_draft_to_airtable,
    save_thread_posts_to_airtable,
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
    "upload_file_to_drive",
    "upload_to_drive",
    "delete_file_from_drive",
    "update_file_on_drive",
    "upload_article_dump_to_drive",
    "save_draft_to_airtable",
    "save_thread_posts_to_airtable",
    "_prepare_drive_image_for_airtable",
    "save_user_fact",
    "update_user_preference",
]
