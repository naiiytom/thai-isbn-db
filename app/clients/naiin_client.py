"""
NaiinClient — fetches book cover images from www.naiin.com via HTML scraping.

The internal api.naiin.com endpoint blocks unauthenticated requests, so we
scrape the public website instead:

  1. Search: GET https://www.naiin.com/search?keyword={isbn}
     - Parse the first product link from the search results.
  2. Detail: GET https://www.naiin.com/product/{slug}
     - Extract the cover URL from <meta property="og:image">.

If the search page already contains the og:image for the first result (some
sites embed it in the listing), we skip the detail fetch.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from crawl4ai import BrowserConfig, CrawlerRunConfig, CacheMode

from app.config import REQUEST_TIMEOUT, REQUEST_RETRIES, RATE_LIMIT_DELAY
from app.utils.http_client import RobustHttpMixin, _AsyncCrawlerThread
from app.utils.isbn_formatter import IsbnFormatter

logger = logging.getLogger(__name__)

NAIIN_BASE_URL = "https://www.naiin.com"
NAIIN_SEARCH_URL = f"{NAIIN_BASE_URL}/search"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": NAIIN_BASE_URL,
}

# Matches product detail paths like /product/..., /book/..., /item/..., or /p/...
_PRODUCT_PATH_RE = re.compile(r"/(product|book|item|p)/[^\"'\s]+", re.IGNORECASE)


@dataclass
class NaiinBookData:
    cover_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class NaiinClient(RobustHttpMixin):
    """Scrapes www.naiin.com for book cover images."""

    def __init__(
        self,
        timeout: int = REQUEST_TIMEOUT,
        retries: int = REQUEST_RETRIES,
        rate_limit_delay: float = RATE_LIMIT_DELAY,
    ):
        self.timeout = timeout
        self.retries = retries
        self.rate_limit_delay = rate_limit_delay
        browser_config = BrowserConfig(
            headless=True,
            user_agent=_HEADERS["User-Agent"],
            headers={k: v for k, v in _HEADERS.items() if k != "User-Agent"},
        )
        self._run_config = CrawlerRunConfig(
            page_timeout=self.timeout * 1000,
            cache_mode=CacheMode.BYPASS,
        )
        self._crawler_thread = _AsyncCrawlerThread(browser_config)
        self._crawler_thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, isbn: str) -> Optional[NaiinBookData]:
        """Return cover URL (and optional supplementary fields) for *isbn*."""
        digits = IsbnFormatter.strip(isbn)

        search_html = self._get(NAIIN_SEARCH_URL, params={"keyword": digits})
        if search_html is None:
            return None

        # Fast path: og:image embedded in the search results page
        cover_url = self._parse_og_image(search_html)
        title, description = self._parse_og_title_desc(search_html)
        if cover_url:
            return NaiinBookData(
                cover_url=cover_url, title=title, description=description
            )

        # Slow path: follow first product link to the detail page
        product_url = self._parse_first_product_url(search_html)
        if not product_url:
            logger.info("Naiin: no product link found for ISBN %s", digits)
            return None

        time.sleep(self.rate_limit_delay)
        detail_html = self._get(product_url)
        if detail_html is None:
            return None

        cover_url = self._parse_og_image(detail_html)
        title, description = self._parse_og_title_desc(detail_html)
        return NaiinBookData(
            cover_url=cover_url, title=title, description=description
        )

    def fetch_cover(self, isbn: str) -> Optional[str]:
        """Convenience method — returns just the cover URL or None."""
        result = self.fetch(isbn)
        return result.cover_url if result else None

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_og_image(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")

        # Primary: og:image
        tag = soup.find("meta", property="og:image")
        if tag and tag.get("content"):
            url = tag["content"].strip()
            if url.startswith("http"):
                return url
            if url.startswith("//"):
                return "https:" + url

        # Secondary: twitter:image
        tw_tag = soup.find("meta", attrs={"name": "twitter:image"})
        if tw_tag and tw_tag.get("content"):
            url = tw_tag["content"].strip()
            if url.startswith("http"):
                return url
            if url.startswith("//"):
                return "https:" + url

        return None

    @staticmethod
    def _parse_og_title_desc(html: str) -> tuple[Optional[str], Optional[str]]:
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("meta", property="og:title")
        desc_tag = soup.find("meta", property="og:description")
        title = title_tag["content"].strip() if title_tag and title_tag.get("content") else None
        desc = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else None
        return title, desc

    def _parse_first_product_url(self, html: str) -> Optional[str]:
        """Extract the absolute URL of the first product in search results."""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("a", href=_PRODUCT_PATH_RE):
            href = tag["href"].strip()
            if href.startswith("http"):
                return href
            return NAIIN_BASE_URL + href
        return None

    # _get() is provided by RobustHttpMixin
