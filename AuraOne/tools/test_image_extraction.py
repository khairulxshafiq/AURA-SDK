import unittest
from bs4 import BeautifulSoup
from tools.web_scraper import extract_article_image_url

class TestScraperImageExtraction(unittest.TestCase):

    def test_priority1_og_image(self):
        """Priority 1: og:image meta tag is extracted."""
        html = """
        <html>
          <head>
            <meta property="og:image" content="https://example.com/og.jpg" />
            <meta name="twitter:image" content="https://example.com/tw.jpg" />
          </head>
          <body>
            <article><img src="https://example.com/body.jpg" /></article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        img_url = extract_article_image_url(soup, "https://example.com/article")
        self.assertEqual(img_url, "https://example.com/og.jpg")

    def test_priority2_twitter_image(self):
        """Priority 2: twitter:image meta tag is extracted when og:image is missing."""
        html = """
        <html>
          <head>
            <meta name="twitter:image" content="https://example.com/tw.png" />
          </head>
          <body>
            <article><img src="https://example.com/body.jpg" /></article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        img_url = extract_article_image_url(soup, "https://example.com/article")
        self.assertEqual(img_url, "https://example.com/tw.png")

    def test_priority3_hero_image(self):
        """Priority 3: article hero image is extracted when meta tags are missing."""
        html = """
        <html>
          <body>
            <article>
              <figure class="hero">
                <img src="/hero_banner.jpg" />
              </figure>
              <p>Content text...</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        img_url = extract_article_image_url(soup, "https://example.com/news/1")
        self.assertEqual(img_url, "https://example.com/hero_banner.jpg")

    def test_priority4_first_valid_article_image(self):
        """Priority 4: first valid article image is extracted when no meta or hero img."""
        html = """
        <html>
          <body>
            <article>
              <p>Header text</p>
              <img src="/images/first_inline.webp" width="800" height="600" />
              <img src="/images/second_inline.jpg" />
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        img_url = extract_article_image_url(soup, "https://example.com/post")
        self.assertEqual(img_url, "https://example.com/images/first_inline.webp")

if __name__ == "__main__":
    unittest.main()
