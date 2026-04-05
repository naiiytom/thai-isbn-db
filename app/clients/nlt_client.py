"""
NltClient — scrapes the National Library of Thailand (NLT) e-service.

Flow:
  1. POST/GET the ISBN search form at NLT_SEARCH_URL to obtain the running
     number of the matching record.
  2. GET /ISBNReq/Detail/{running_number} to parse the full metadata page.

The site is accessible from Thai IPs.  When running outside Thailand a VPN or
proxy is required.  All network errors are caught and returned as None so the
orchestrator can fall through to the next source.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

from app.config import REQUEST_TIMEOUT, REQUEST_RETRIES, RATE_LIMIT_DELAY
from app.utils.isbn_formatter import IsbnFormatter

logger = logging.getLogger(__name__)

NLT_BASE_URL = "https://e-service.nlt.go.th"
NLT_SEARCH_URL = f"{NLT_BASE_URL}/ISBNReq"
NLT_DETAIL_URL = f"{NLT_BASE_URL}/ISBNReq/Detail"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class NltBookMetadata:
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    page_count: Optional[int] = None
    isbn: Optional[str] = None
    detail_url: Optional[str] = None


class NltClient:
    """Fetches book metadata from the NLT e-service by ISBN."""

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

    def fetch(self, isbn: str) -> Optional[NltBookMetadata]:
        """Return metadata for *isbn* scraped from NLT, or None on failure."""
        hyphenated = IsbnFormatter.format(isbn)
        running_number = self._search(hyphenated)
        if running_number is None:
            logger.info("NLT: no running number found for ISBN %s", hyphenated)
            return None

        time.sleep(self.rate_limit_delay)
        return self._fetch_detail(running_number, hyphenated)

    # ------------------------------------------------------------------
    # Step 1: search → running number
    # ------------------------------------------------------------------

    def _search(self, hyphenated_isbn: str) -> Optional[int]:
        """Query the NLT search page and return the detail-page running number."""
        params = {"isbn": hyphenated_isbn}
        html = self._get(NLT_SEARCH_URL, params=params)
        if html is None:
            return None
        return self._parse_running_number(html, hyphenated_isbn)

    def _parse_running_number(
        self, html: str, hyphenated_isbn: str
    ) -> Optional[int]:
        """
        Extract the running number from the search results page.

        The NLT search page typically renders a table where each row links to
        /ISBNReq/Detail/{id}.  We grab the first matching href.

        If the page instead redirects directly to the detail page (HTTP 302),
        the running number is already in the final URL — handled by _get().
        """
        soup = BeautifulSoup(html, "lxml")

        # Strategy A: anchor tags pointing to /ISBNReq/Detail/{id}
        pattern = re.compile(r"/ISBNReq/Detail/(\d+)", re.IGNORECASE)
        for tag in soup.find_all("a", href=pattern):
            match = pattern.search(tag["href"])
            if match:
                return int(match.group(1))

        # Strategy B: the page itself might be the detail page (direct redirect)
        # Check for a canonical link tag
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            match = pattern.search(canonical["href"])
            if match:
                return int(match.group(1))

        # Strategy D: og:url meta tag (same intent as canonical link)
        og_url = soup.find("meta", property="og:url")
        if og_url and og_url.get("content"):
            match = pattern.search(og_url["content"])
            if match:
                return int(match.group(1))

        # Strategy C: look for ISBN text near a link — coarser fallback
        isbn_digits = IsbnFormatter.strip(hyphenated_isbn)
        for tag in soup.find_all("a", href=True):
            if isbn_digits in tag.get_text(strip=True).replace("-", ""):
                match = pattern.search(tag["href"])
                if match:
                    return int(match.group(1))

        logger.debug("NLT search HTML snippet:\n%s", html[:2000])
        return None

    # ------------------------------------------------------------------
    # Step 2: detail page → metadata
    # ------------------------------------------------------------------

    def fetch_by_id(self, running_number: int) -> Optional[NltBookMetadata]:
        """Directly fetch a detail page by its running number."""
        return self._fetch_detail(running_number, isbn=None)

    def _fetch_detail(
        self, running_number: int, isbn: Optional[str]
    ) -> Optional[NltBookMetadata]:
        url = f"{NLT_DETAIL_URL}/{running_number}"
        html = self._get(url)
        if html is None:
            return None
        metadata = self._parse_detail(html)
        metadata.detail_url = url
        if isbn and not metadata.isbn:
            metadata.isbn = isbn
        return metadata

    def _parse_detail(self, html: str) -> NltBookMetadata:
        """
        Parse the NLT detail page HTML.

        The page uses a definition-list or table layout with Thai field labels:
          ชื่อเรื่อง   → title
          ผู้แต่ง      → author
          สำนักพิมพ์  → publisher
          จำนวนหน้า  → page_count
          เลขมาตรฐาน  → ISBN (may contain "ISBN" prefix)
        """
        soup = BeautifulSoup(html, "lxml")
        meta = NltBookMetadata()

        # Build a label→value map from <dt>/<dd> pairs or two-column <tr> rows.
        label_map: dict[str, str] = {}

        def _clean(text: str) -> str:
            """Collapse internal whitespace/newlines to a single space."""
            return " ".join(text.split())

        # Try <dl> / <dt> + <dd>
        for dt in soup.find_all("dt"):
            label = _clean(dt.get_text(separator=" ", strip=True))
            dd = dt.find_next_sibling("dd")
            if dd:
                label_map[label] = _clean(dd.get_text(separator=" ", strip=True))

        # Try two-column table rows
        for tr in soup.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) >= 2:
                label = _clean(cells[0].get_text(separator=" ", strip=True))
                value = _clean(cells[1].get_text(separator=" ", strip=True))
                if label:
                    label_map[label] = value

        # Also try label/value divs or spans (common in Bootstrap-style layouts)
        for label_el in soup.find_all(class_=re.compile(r"label|field-label", re.I)):
            value_el = label_el.find_next_sibling()
            if value_el:
                label_map[_clean(label_el.get_text(strip=True))] = _clean(
                    value_el.get_text(separator=" ", strip=True)
                )

        # Map Thai labels to fields
        for label, value in label_map.items():
            lc = label.lower()
            if "ชื่อเรื่อง" in label or "title" in lc:
                meta.title = value or meta.title
            elif "ผู้แต่ง" in label or "author" in lc:
                meta.author = value or meta.author
            elif "สำนักพิมพ์" in label or "publisher" in lc:
                meta.publisher = value or meta.publisher
            elif "จำนวนหน้า" in label or "page" in lc:
                digits = re.sub(r"\D", "", value)
                if digits:
                    meta.page_count = int(digits)
            elif "เลขมาตรฐาน" in label or "isbn" in lc:
                cleaned = re.sub(r"[^\d\-]", "", value).strip("-")
                if cleaned:
                    meta.isbn = cleaned

        return meta

    # ------------------------------------------------------------------
    # HTTP helper with retry + exponential back-off
    # ------------------------------------------------------------------

    def _get(
        self, url: str, params: Optional[dict] = None
    ) -> Optional[str]:
        delay = 1.0
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.timeout, allow_redirects=True
                )
                resp.encoding = "utf-8"
                if resp.status_code == 200:
                    return resp.text
                logger.warning(
                    "NLT GET %s → HTTP %s (attempt %d/%d)",
                    url,
                    resp.status_code,
                    attempt,
                    self.retries,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "NLT GET %s failed (attempt %d/%d): %s",
                    url,
                    attempt,
                    self.retries,
                    exc,
                )
            if attempt < self.retries:
                time.sleep(delay)
                delay *= 2
        return None
