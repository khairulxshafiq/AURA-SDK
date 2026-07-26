import unittest
from unittest.mock import patch
from ui.telegram_bot import route_intent, LIVE_SEARCH_KEYWORDS
from tools.search_engine import fetch_live_news_with_fallback, fetch_rss_articles, fetch_gnews_articles

class TestLiveSearchRouting(unittest.TestCase):

    def test_intent_keywords_trigger_live_news_search(self):
        """Verify all mandatory keywords trigger LIVE_NEWS_SEARCH intent."""
        mandatory_phrases = [
            "berita",
            "berita terkini",
            "current news",
            "headline",
            "trending",
            "viral",
            "cerita menarik",
            "cerita semasa",
            "apa berlaku hari ini",
            "top stories",
            "trending malaysia",
            "trending dunia",
            "Cerita menarik hari ni",
            "Apa berita viral hari ni?"
        ]
        for phrase in mandatory_phrases:
            intent = route_intent(phrase)
            self.assertEqual(intent, "LIVE_NEWS_SEARCH", f"Phrase '{phrase}' failed to trigger LIVE_NEWS_SEARCH intent!")

    @patch("tools.search_engine.fetch_gnews_articles")
    def test_tier1_gnews_success(self, mock_gnews):
        """Tier 1 GNews returns articles if available."""
        mock_gnews.return_value = [{"title": "GNews Article", "link": "http://gnews.com/1", "desc": "Desc", "source": "GNews"}]
        articles, tier = fetch_live_news_with_fallback("berita terkini", max_items=5)
        self.assertEqual(tier, "GNews")
        self.assertEqual(len(articles), 1)

    @patch("tools.search_engine.fetch_gnews_articles")
    @patch("tools.search_engine.search_web")
    def test_tier2_web_search_fallback(self, mock_search_web, mock_gnews):
        """Tier 2 Internet Search triggers when GNews returns empty."""
        mock_gnews.return_value = []
        mock_search_web.return_value = {
            "status": "success",
            "results": [{"title": "Web Search Article", "link": "http://web.com/1", "snippet": "Snippet"}]
        }
        articles, tier = fetch_live_news_with_fallback("top stories", max_items=5)
        self.assertEqual(tier, "Internet Search")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source"], "Internet Search")

    @patch("tools.search_engine.fetch_gnews_articles")
    @patch("tools.search_engine.search_web")
    @patch("tools.search_engine.fetch_rss_articles")
    def test_tier3_rss_fallback(self, mock_rss, mock_search_web, mock_gnews):
        """Tier 3 RSS Feeds trigger when GNews and Web Search return empty."""
        mock_gnews.return_value = []
        mock_search_web.return_value = {"status": "success", "results": []}
        mock_rss.return_value = [{"title": "RSS Article", "link": "http://rss.com/1", "desc": "RSS Desc", "source": "Astro Awani"}]
        
        articles, tier = fetch_live_news_with_fallback("trending malaysia", max_items=5)
        self.assertEqual(tier, "RSS Feeds")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source"], "Astro Awani")

if __name__ == "__main__":
    unittest.main()
