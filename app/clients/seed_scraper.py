"""
SeedScraper — scrapes the SE-ED Book Center mobile site for book cover images.

Endpoint: https://m.se-ed.com/Product/Search?keyword={isbn}

The cover image is contained in the Open Graph meta tag:
  <meta property="og:image" content="https://...cover.jpg">

This is used as a fallback when the Naiin API does not return a cover.
"""

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from app.config import REQUEST_TIMEOUT, REQUEST_RETRIES, RATE_LIMIT_DELAY
from app.utils.isbn_formatter import IsbnFormatter

logger = logging.getLogger(__name__)

SEED_SEARCH_URL = "https://m.se-ed.com/Product/Search"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://m.se-ed.com/",
}


class SeedScraper:
    """Fetches book cover images from the SE-ED mobile website."""

    def __init__(
        self,
        timeout: int = REQUEST_TIMEOUT,
        retries: int = REQUEST_RETRIES,
        rate_limit_delay: float = RATE_LIMIT_DELAY,
    ):
        self.timeout = timeout
        self.retries = retries
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_cover(self, isbn: str) -> Optional[str]:
        """Return the cover image URL for *isbn* or None if not found."""
        digits = IsbnFormatter.strip(isbn)
        html = self._get(digits)
        if html is None:
            return None
        return self._parse_og_image(html)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_og_image(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")

        # Primary: og:image meta tag
        og_tag = soup.find("meta", property="og:image")
        if og_tag and og_tag.get("content"):
            url = og_tag["content"].strip()
            if url.startswith("http"):
                return url
            if url.startswith("//"):
                return "https:" + url

        # Fallback: twitter:image
        tw_tag = soup.find("meta", attrs={"name": "twitter:image"})
        if tw_tag and tw_tag.get("content"):
            url = tw_tag["content"].strip()
            if url.startswith("http"):
                return url
            if url.startswith("//"):
                return "https:" + url

        # Fallback: first product image found in the page
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if "product" in src.lower() or "cover" in src.lower():
                if src.startswith("http"):
                    return src
                if src.startswith("//"):
                    return "https:" + src

        return None

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get(self, isbn_digits: str) -> Optional[str]:
        params = {"keyword": isbn_digits}
        delay = 1.0
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(
                    SEED_SEARCH_URL,
                    params=params,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                resp.encoding = "utf-8"
                if resp.status_code == 200:
                    return resp.text
                logger.warning(
                    "SE-ED GET %s → HTTP %s (attempt %d/%d)",
                    SEED_SEARCH_URL,
                    resp.status_code,
                    attempt,
                    self.retries,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "SE-ED GET failed (attempt %d/%d): %s", attempt, self.retries, exc
                )
            if attempt < self.retries:
                time.sleep(delay)
                delay *= 2
        return None
