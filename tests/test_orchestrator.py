"""
Tests for the Orchestrator — verifies cascade logic with mocked clients.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.orchestrator import Orchestrator
from app.clients.nlt_client import NltBookMetadata
from app.clients.naiin_client import NaiinBookData


def make_nlt_meta(**kwargs):
    defaults = dict(title="NLT Title", author="NLT Author", publisher="NLT Pub", page_count=200)
    defaults.update(kwargs)
    return NltBookMetadata(**defaults)


def _naiin_mock(cover_url=None, description=None):
    """Return a MagicMock for NaiinClient whose .fetch() returns NaiinBookData."""
    naiin = MagicMock()
    naiin.fetch.return_value = NaiinBookData(cover_url=cover_url, description=description)
    return naiin


class TestOrchestratorTextMetadata:
    def _make(self, nlt_return=None, naiin_cover=None, seed_return=None):
        nlt = MagicMock()
        nlt.fetch.return_value = nlt_return
        naiin = _naiin_mock(cover_url=naiin_cover)
        seed = MagicMock()
        seed.fetch_cover.return_value = seed_return
        orch = Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)
        return orch, nlt, naiin, seed

    def test_nlt_success_populates_text_fields(self):
        orch, *_ = self._make(nlt_return=make_nlt_meta())
        book = orch.fetch_book("9786161842710")
        assert book.title == "NLT Title"
        assert book.author == "NLT Author"
        assert book.publisher == "NLT Pub"
        assert book.page_count == 200
        assert book.source == "nlt"

    def test_nlt_failure_produces_empty_metadata(self):
        orch, *_ = self._make(nlt_return=None)
        book = orch.fetch_book("9786161842710")
        assert book.title is None
        assert book.source is None

    def test_nlt_empty_title_treated_as_failure(self):
        orch, *_ = self._make(nlt_return=NltBookMetadata(title=None, author=None))
        book = orch.fetch_book("9786161842710")
        assert book.source is None

    def test_nlt_exception_is_caught(self):
        nlt = MagicMock()
        nlt.fetch.side_effect = Exception("network timeout")
        naiin = _naiin_mock()
        seed = MagicMock(); seed.fetch_cover.return_value = None
        orch = Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)
        book = orch.fetch_book("9786161842710")
        assert book.isbn == "9786161842710"  # still returns a document
        assert book.title is None


class TestOrchestratorCover:
    def _make(self, nlt_return=None, naiin_cover=None, seed_return=None):
        nlt = MagicMock(); nlt.fetch.return_value = nlt_return
        naiin = _naiin_mock(cover_url=naiin_cover)
        seed = MagicMock(); seed.fetch_cover.return_value = seed_return
        return Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed), naiin, seed

    def test_naiin_cover_used_when_available(self):
        orch, naiin, seed = self._make(naiin_cover="https://naiin.com/cover.jpg")
        book = orch.fetch_book("9786161842710")
        assert book.cover_url == "https://naiin.com/cover.jpg"
        assert book.cover_source == "naiin"
        seed.fetch_cover.assert_not_called()

    def test_seed_cover_used_as_fallback(self):
        orch, naiin, seed = self._make(
            naiin_cover=None, seed_return="https://se-ed.com/cover.jpg"
        )
        book = orch.fetch_book("9786161842710")
        assert book.cover_url == "https://se-ed.com/cover.jpg"
        assert book.cover_source == "seed"

    def test_no_cover_when_both_fail(self):
        orch, *_ = self._make(naiin_cover=None, seed_return=None)
        book = orch.fetch_book("9786161842710")
        assert book.cover_url is None
        assert book.cover_source is None

    def test_naiin_exception_falls_through_to_seed(self):
        nlt = MagicMock(); nlt.fetch.return_value = None
        naiin = MagicMock(); naiin.fetch.side_effect = Exception("timeout")
        seed = MagicMock(); seed.fetch_cover.return_value = "https://se-ed.com/fallback.jpg"
        orch = Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)
        book = orch.fetch_book("9786161842710")
        assert book.cover_source == "seed"


class TestOrchestratorSynopsis:
    def test_synopsis_populated_from_naiin(self):
        nlt = MagicMock(); nlt.fetch.return_value = make_nlt_meta()
        naiin = _naiin_mock(cover_url="https://naiin.com/cover.jpg", description="A great book")
        seed = MagicMock()
        orch = Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)
        book = orch.fetch_book("9786161842710")
        assert book.synopsis == "A great book"

    def test_synopsis_none_when_naiin_returns_no_description(self):
        nlt = MagicMock(); nlt.fetch.return_value = None
        naiin = _naiin_mock(cover_url="https://naiin.com/cover.jpg", description=None)
        seed = MagicMock()
        orch = Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)
        book = orch.fetch_book("9786161842710")
        assert book.synopsis is None

    def test_synopsis_none_when_seed_used(self):
        nlt = MagicMock(); nlt.fetch.return_value = None
        naiin = _naiin_mock(cover_url=None)
        seed = MagicMock(); seed.fetch_cover.return_value = "https://se-ed.com/cover.jpg"
        orch = Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)
        book = orch.fetch_book("9786161842710")
        assert book.synopsis is None


class TestOrchestratorIsbn:
    def _make(self):
        nlt = MagicMock(); nlt.fetch.return_value = None
        naiin = _naiin_mock()
        seed = MagicMock(); seed.fetch_cover.return_value = None
        return Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)

    def test_isbn_stored_as_digits(self):
        orch = self._make()
        book = orch.fetch_book("9786161842710")
        assert book.isbn == "9786161842710"

    def test_hyphenated_isbn_input_stripped_to_digits(self):
        orch = self._make()
        book = orch.fetch_book("978-616-18-4271-0")
        assert book.isbn == "9786161842710"


class TestOrchestratorPersistence:
    def test_saves_to_mongo_collection(self):
        nlt = MagicMock(); nlt.fetch.return_value = make_nlt_meta()
        naiin = _naiin_mock(cover_url="https://naiin.com/c.jpg")
        seed = MagicMock()
        collection = MagicMock()
        orch = Orchestrator(
            nlt_client=nlt, naiin_client=naiin, seed_scraper=seed,
            db_collection=collection,
        )
        orch.fetch_book("9786161842710")
        collection.replace_one.assert_called_once()
        call_args = collection.replace_one.call_args
        assert call_args[1]["upsert"] is True

    def test_skips_persistence_when_no_collection(self):
        nlt = MagicMock(); nlt.fetch.return_value = None
        naiin = _naiin_mock()
        seed = MagicMock(); seed.fetch_cover.return_value = None
        orch = Orchestrator(nlt_client=nlt, naiin_client=naiin, seed_scraper=seed)
        # Should not raise
        book = orch.fetch_book("9786161842710")
        assert book is not None
