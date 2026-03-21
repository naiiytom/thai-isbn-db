"""
NaiinClient — fetches book cover images (and supplementary metadata) from
the Naiin internal JSON API.

Endpoint: https://api.naiin.com/products?q={isbn}

The API returns a JSON array of product objects.  We take the first result
whose ISBN matches and extract the cover image URL.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from app.config import REQUEST_TIMEOUT, REQUEST_RETRIES, RATE_LIMIT_DELAY
from app.utils.isbn_formatter import IsbnFormatter

logger = logging.getLogger(__name__)

NAIIN_API_URL = "https://api.naiin.com/products"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.naiin.com/",
    "Origin": "https://www.naiin.com",
}

# Candidate keys for cover image URL in the Naiin product JSON
_IMAGE_KEY_CANDIDATES = [
    "image_url",
    "imageUrl",
    "cover_image",
    "coverImage",
    "img",
    "image",
    "photo",
    "thumbnail",
]


@dataclass
class NaiinBookData:
    cover_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class NaiinClient:
    """Queries the Naiin API for book cover images."""

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

    def fetch(self, isbn: str) -> Optional[NaiinBookData]:
        """Return cover URL (and optional supplementary fields) for *isbn*."""
        digits = IsbnFormatter.strip(isbn)
        data = self._get_json(digits)
        if not data:
            return None

        products = data if isinstance(data, list) else data.get("products", [data])
        return self._extract(products, digits)

    def fetch_cover(self, isbn: str) -> Optional[str]:
        """Convenience method — returns just the cover URL or None."""
        result = self.fetch(isbn)
        return result.cover_url if result else None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _extract(self, products: list, isbn_digits: str) -> Optional[NaiinBookData]:
        for product in products:
            if not isinstance(product, dict):
                continue
            # Prefer the product whose ISBN matches
            if not self._isbn_matches(product, isbn_digits):
                continue
            return self._build(product)

        # If no exact match, take the first product (query was ISBN-specific)
        if products and isinstance(products[0], dict):
            return self._build(products[0])
        return None

    def _build(self, product: dict) -> NaiinBookData:
        cover_url = None
        for key in _IMAGE_KEY_CANDIDATES:
            val = product.get(key) or product.get(key.upper())
            if val and isinstance(val, str) and val.startswith("http"):
                cover_url = val
                break

        # Try nested image objects
        if not cover_url:
            for key in ("images", "media"):
                nested = product.get(key)
                if isinstance(nested, list) and nested:
                    first = nested[0]
                    if isinstance(first, dict):
                        for img_key in _IMAGE_KEY_CANDIDATES:
                            val = first.get(img_key)
                            if val and isinstance(val, str) and val.startswith("http"):
                                cover_url = val
                                break
                elif isinstance(nested, dict):
                    for img_key in _IMAGE_KEY_CANDIDATES:
                        val = nested.get(img_key)
                        if val and isinstance(val, str) and val.startswith("http"):
                            cover_url = val
                            break

        title = (
            product.get("title")
            or product.get("name")
            or product.get("book_title")
        )
        description = product.get("description") or product.get("detail")

        return NaiinBookData(
            cover_url=cover_url,
            title=str(title).strip() if title else None,
            description=str(description).strip() if description else None,
        )

    @staticmethod
    def _isbn_matches(product: dict, isbn_digits: str) -> bool:
        for key in ("isbn", "isbn13", "ISBN", "isbn_13", "barcode", "ean"):
            val = product.get(key)
            if val and IsbnFormatter.strip(str(val)) == isbn_digits:
                return True
        return False

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get_json(self, isbn_digits: str) -> Optional[object]:
        params = {"q": isbn_digits}
        delay = 1.0
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(
                    NAIIN_API_URL, params=params, timeout=self.timeout
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(
                    "Naiin GET %s → HTTP %s (attempt %d/%d)",
                    NAIIN_API_URL,
                    resp.status_code,
                    attempt,
                    self.retries,
                )
            except (requests.RequestException, ValueError) as exc:
                logger.warning(
                    "Naiin GET failed (attempt %d/%d): %s", attempt, self.retries, exc
                )
            if attempt < self.retries:
                time.sleep(delay)
                delay *= 2
        return None
