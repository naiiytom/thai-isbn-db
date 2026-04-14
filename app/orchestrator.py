"""
Orchestrator — executes the Hybrid Metadata Strategy.

Resolution order
----------------
Text metadata (source field):
  1. NLT e-service scraper (NltClient)  — primary, Thailand-specific
  2. (extensible: add additional scrapers here if needed later)

Cover image:
  1. Naiin JSON API (NaiinClient)        — primary, high-res
  2. SE-ED HTML scraper (SeedScraper)    — fallback

Persistence:
  - Upserts the final BookDocument into MongoDB (`books` collection).
  - Returns the BookDocument regardless of whether DB persistence succeeded.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.clients.naiin_client import NaiinClient
from app.clients.nlt_client import NltClient
from app.clients.seed_scraper import SeedScraper
from app.models import BookDocument
from app.utils.isbn_formatter import IsbnFormatter

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        nlt_client: Optional[NltClient] = None,
        naiin_client: Optional[NaiinClient] = None,
        seed_scraper: Optional[SeedScraper] = None,
        db_collection=None,
    ):
        self.nlt = nlt_client or NltClient()
        self.naiin = naiin_client or NaiinClient()
        self.seed = seed_scraper or SeedScraper()
        self._collection = db_collection  # pymongo Collection or None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_isbn(isbn: str) -> None:
        """
        Raise ValueError if *isbn* is not a valid ISBN-13.
        Accepts hyphenated or plain digit input.
        """
        digits = IsbnFormatter.strip(isbn)
        if not digits.isdigit() or len(digits) != 13:
            raise ValueError(
                f"Invalid ISBN: {isbn!r} — must be 13 digits (hyphens allowed)"
            )
        total = sum(
            int(d) * (1 if i % 2 == 0 else 3)
            for i, d in enumerate(digits)
        )
        if total % 10 != 0:
            raise ValueError(f"Invalid ISBN-13 check digit in: {isbn!r}")

    def fetch_book(self, isbn: str) -> BookDocument:
        """
        Fetch, merge, persist, and return a BookDocument for *isbn*.

        Raises ValueError for malformed ISBNs.
        Errors from individual sources are logged and skipped.
        """
        self._validate_isbn(isbn)
        hyphenated = IsbnFormatter.format(isbn)
        digits = IsbnFormatter.strip(isbn)

        # 1. Text metadata
        book = self._fetch_text_metadata(hyphenated, digits)

        # 2. Cover image
        cover_url, cover_source = self._fetch_cover(digits)
        book.cover_url = cover_url
        book.cover_source = cover_source

        # 3. Persist
        self._save(book)

        return book

    # ------------------------------------------------------------------
    # Step 1: text metadata
    # ------------------------------------------------------------------

    def _fetch_text_metadata(
        self, hyphenated_isbn: str, digits: str
    ) -> BookDocument:
        # --- NLT ---
        try:
            nlt_meta = self.nlt.fetch(hyphenated_isbn)
        except Exception as exc:
            logger.error("NltClient raised unexpectedly: %s", exc)
            nlt_meta = None

        if nlt_meta and (nlt_meta.title or nlt_meta.author):
            logger.info("Text metadata sourced from NLT for %s", hyphenated_isbn)
            return BookDocument(
                isbn=digits,
                title=nlt_meta.title,
                author=nlt_meta.author,
                publisher=nlt_meta.publisher,
                page_count=nlt_meta.page_count,
                source="nlt",
            )

        logger.info(
            "NLT returned no metadata for %s — no further fallback configured",
            hyphenated_isbn,
        )
        return BookDocument(isbn=digits, source=None)

    # ------------------------------------------------------------------
    # Step 2: cover image
    # ------------------------------------------------------------------

    def _fetch_cover(self, digits: str) -> tuple[Optional[str], Optional[str]]:
        # --- Naiin (primary) ---
        try:
            url = self.naiin.fetch_cover(digits)
        except Exception as exc:
            logger.error("NaiinClient raised unexpectedly: %s", exc)
            url = None

        if url:
            logger.info("Cover sourced from Naiin for ISBN %s", digits)
            return url, "naiin"

        # --- SE-ED (fallback) ---
        try:
            url = self.seed.fetch_cover(digits)
        except Exception as exc:
            logger.error("SeedScraper raised unexpectedly: %s", exc)
            url = None

        if url:
            logger.info("Cover sourced from SE-ED for ISBN %s", digits)
            return url, "seed"

        logger.info("No cover found for ISBN %s", digits)
        return None, None

    # ------------------------------------------------------------------
    # Step 3: persistence
    # ------------------------------------------------------------------

    def _save(self, book: BookDocument) -> None:
        if self._collection is None:
            logger.debug("No DB collection provided — skipping persistence")
            return
        try:
            book.updated_at = datetime.now(timezone.utc)
            doc = book.to_mongo()
            self._collection.replace_one(
                {"_id": doc["_id"]}, doc, upsert=True
            )
            logger.info("Saved book %s to MongoDB", book.isbn)
        except Exception as exc:
            logger.error("Failed to save book %s to MongoDB: %s", book.isbn, exc)
