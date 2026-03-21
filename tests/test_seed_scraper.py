import responses as resp_mock
import pytest
from app.clients.seed_scraper import SeedScraper, SEED_SEARCH_URL


OG_IMAGE_HTML = """
<html>
<head>
  <meta property="og:image" content="https://www.se-ed.com/covers/9786161842714.jpg">
  <meta property="og:title" content="หนังสือทดสอบ">
</head>
<body><p>Product page</p></body>
</html>
"""

TWITTER_IMAGE_HTML = """
<html>
<head>
  <meta name="twitter:image" content="https://www.se-ed.com/tw/9786161842714.jpg">
</head>
<body></body>
</html>
"""

NO_IMAGE_HTML = "<html><head></head><body><p>ไม่พบสินค้า</p></body></html>"

PRODUCT_IMG_HTML = """
<html><body>
  <img src="https://www.se-ed.com/product/9786161842714_cover.jpg" alt="cover">
</body></html>
"""


class TestSeedScraperParseOgImage:
    def setup_method(self):
        self.scraper = SeedScraper()

    def test_extracts_og_image(self):
        url = self.scraper._parse_og_image(OG_IMAGE_HTML)
        assert url == "https://www.se-ed.com/covers/9786161842714.jpg"

    def test_extracts_twitter_image_fallback(self):
        url = self.scraper._parse_og_image(TWITTER_IMAGE_HTML)
        assert url == "https://www.se-ed.com/tw/9786161842714.jpg"

    def test_returns_none_when_no_image_tags(self):
        url = self.scraper._parse_og_image(NO_IMAGE_HTML)
        assert url is None

    def test_extracts_product_img_fallback(self):
        url = self.scraper._parse_og_image(PRODUCT_IMG_HTML)
        assert url == "https://www.se-ed.com/product/9786161842714_cover.jpg"


class TestSeedScraperFetchCover:
    def setup_method(self):
        self.scraper = SeedScraper(rate_limit_delay=0)

    @resp_mock.activate
    def test_fetch_cover_success(self):
        resp_mock.add(
            resp_mock.GET,
            SEED_SEARCH_URL,
            body=OG_IMAGE_HTML,
            status=200,
        )
        url = self.scraper.fetch_cover("9786161842714")
        assert url == "https://www.se-ed.com/covers/9786161842714.jpg"

    @resp_mock.activate
    def test_fetch_cover_returns_none_on_404(self):
        resp_mock.add(resp_mock.GET, SEED_SEARCH_URL, status=404)
        url = self.scraper.fetch_cover("9786161842714")
        assert url is None

    @resp_mock.activate
    def test_fetch_cover_returns_none_when_no_image_in_page(self):
        resp_mock.add(resp_mock.GET, SEED_SEARCH_URL, body=NO_IMAGE_HTML, status=200)
        url = self.scraper.fetch_cover("9786161842714")
        assert url is None
