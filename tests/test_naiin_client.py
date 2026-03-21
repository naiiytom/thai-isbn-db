import responses as resp_mock
import pytest
from app.clients.naiin_client import NaiinClient, NAIIN_SEARCH_URL, NAIIN_BASE_URL

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

# Search page that already contains og:image (fast path)
SEARCH_HTML_WITH_OG = """
<html>
<head>
  <meta property="og:image" content="https://cdn.naiin.com/covers/9786161842714.jpg">
  <meta property="og:title" content="หนังสือทดสอบ">
  <meta property="og:description" content="รายละเอียดหนังสือ">
</head>
<body><p>search results</p></body>
</html>
"""

# Search page without og:image but with a product link (slow path)
SEARCH_HTML_WITH_LINK = """
<html><body>
  <a href="/product/thai-book-9786161842714">หนังสือทดสอบ</a>
</body></html>
"""

# Detail page returned after following the product link
DETAIL_HTML = """
<html>
<head>
  <meta property="og:image" content="https://cdn.naiin.com/detail/cover.jpg">
  <meta property="og:title" content="หนังสือ Detail">
  <meta property="og:description" content="รายละเอียด Detail">
</head>
<body></body>
</html>
"""

NO_IMAGE_HTML = "<html><head></head><body><p>ไม่พบ</p></body></html>"


# ---------------------------------------------------------------------------
# Tests: _parse_og_image
# ---------------------------------------------------------------------------

class TestParseOgImage:
    def setup_method(self):
        self.client = NaiinClient()

    def test_extracts_og_image(self):
        url = self.client._parse_og_image(SEARCH_HTML_WITH_OG)
        assert url == "https://cdn.naiin.com/covers/9786161842714.jpg"

    def test_returns_none_when_absent(self):
        url = self.client._parse_og_image(NO_IMAGE_HTML)
        assert url is None


# ---------------------------------------------------------------------------
# Tests: _parse_og_title_desc
# ---------------------------------------------------------------------------

class TestParseOgTitleDesc:
    def setup_method(self):
        self.client = NaiinClient()

    def test_extracts_title_and_description(self):
        title, desc = self.client._parse_og_title_desc(SEARCH_HTML_WITH_OG)
        assert title == "หนังสือทดสอบ"
        assert desc == "รายละเอียดหนังสือ"

    def test_returns_none_when_absent(self):
        title, desc = self.client._parse_og_title_desc(NO_IMAGE_HTML)
        assert title is None
        assert desc is None


# ---------------------------------------------------------------------------
# Tests: _parse_first_product_url
# ---------------------------------------------------------------------------

class TestParseFirstProductUrl:
    def setup_method(self):
        self.client = NaiinClient()

    def test_finds_relative_product_link(self):
        url = self.client._parse_first_product_url(SEARCH_HTML_WITH_LINK)
        assert url == f"{NAIIN_BASE_URL}/product/thai-book-9786161842714"

    def test_returns_none_when_no_link(self):
        url = self.client._parse_first_product_url(NO_IMAGE_HTML)
        assert url is None

    def test_absolute_href_returned_unchanged(self):
        html = '<html><body><a href="https://www.naiin.com/product/abc">book</a></body></html>'
        url = self.client._parse_first_product_url(html)
        assert url == "https://www.naiin.com/product/abc"


# ---------------------------------------------------------------------------
# Tests: full fetch flow (mocked HTTP)
# ---------------------------------------------------------------------------

class TestNaiinClientFetch:
    def setup_method(self):
        self.client = NaiinClient(rate_limit_delay=0)

    @resp_mock.activate
    def test_fast_path_og_image_on_search_page(self):
        resp_mock.add(resp_mock.GET, NAIIN_SEARCH_URL, body=SEARCH_HTML_WITH_OG, status=200)
        result = self.client.fetch("9786161842714")
        assert result is not None
        assert result.cover_url == "https://cdn.naiin.com/covers/9786161842714.jpg"
        assert result.title == "หนังสือทดสอบ"
        assert len(resp_mock.calls) == 1  # only search page fetched

    @resp_mock.activate
    def test_slow_path_follows_product_link(self):
        resp_mock.add(resp_mock.GET, NAIIN_SEARCH_URL, body=SEARCH_HTML_WITH_LINK, status=200)
        resp_mock.add(
            resp_mock.GET,
            f"{NAIIN_BASE_URL}/product/thai-book-9786161842714",
            body=DETAIL_HTML,
            status=200,
        )
        result = self.client.fetch("9786161842714")
        assert result is not None
        assert result.cover_url == "https://cdn.naiin.com/detail/cover.jpg"
        assert len(resp_mock.calls) == 2

    @resp_mock.activate
    def test_fetch_cover_returns_url_string(self):
        resp_mock.add(resp_mock.GET, NAIIN_SEARCH_URL, body=SEARCH_HTML_WITH_OG, status=200)
        url = self.client.fetch_cover("9786161842714")
        assert url == "https://cdn.naiin.com/covers/9786161842714.jpg"

    @resp_mock.activate
    def test_returns_none_on_http_403(self):
        resp_mock.add(resp_mock.GET, NAIIN_SEARCH_URL, status=403)
        result = self.client.fetch("9786161842714")
        assert result is None

    @resp_mock.activate
    def test_returns_none_when_no_image_anywhere(self):
        resp_mock.add(resp_mock.GET, NAIIN_SEARCH_URL, body=NO_IMAGE_HTML, status=200)
        result = self.client.fetch("9786161842714")
        assert result is None

    @resp_mock.activate
    def test_returns_none_when_detail_page_also_missing_image(self):
        resp_mock.add(resp_mock.GET, NAIIN_SEARCH_URL, body=SEARCH_HTML_WITH_LINK, status=200)
        resp_mock.add(
            resp_mock.GET,
            f"{NAIIN_BASE_URL}/product/thai-book-9786161842714",
            body=NO_IMAGE_HTML,
            status=200,
        )
        result = self.client.fetch("9786161842714")
        assert result is not None
        assert result.cover_url is None
