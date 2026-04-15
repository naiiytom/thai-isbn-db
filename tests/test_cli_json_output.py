"""
Tests for the CLI JSON output helpers:
  - _load_existing_isbns
  - _write_source_json_files
"""

import json
import pathlib
import pytest

from app.cli import _load_existing_isbns, _write_source_json_files


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_book(isbn: str, source: str | None = "nlt") -> dict:
    return {
        "isbn": isbn,
        "title": f"Book {isbn}",
        "author": "Author",
        "publisher": "Publisher",
        "page_count": 100,
        "synopsis": None,
        "cover_url": None,
        "source": source,
        "cover_source": None,
        "created_at": "2026-04-15T00:00:00+00:00",
        "updated_at": "2026-04-15T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# _load_existing_isbns
# ---------------------------------------------------------------------------

class TestLoadExistingIsbns:
    def test_returns_empty_set_when_no_files(self, tmp_path):
        result = _load_existing_isbns(tmp_path, "nlt")
        assert result == set()

    def test_loads_isbns_from_single_file(self, tmp_path):
        books = [_make_book("9786161842710"), _make_book("9786161842727")]
        (tmp_path / "nlt_20260415_120000.json").write_text(
            json.dumps(books), encoding="utf-8"
        )
        result = _load_existing_isbns(tmp_path, "nlt")
        assert result == {"9786161842710", "9786161842727"}

    def test_loads_isbns_from_multiple_files(self, tmp_path):
        (tmp_path / "nlt_20260415_120000.json").write_text(
            json.dumps([_make_book("9786161842710")]), encoding="utf-8"
        )
        (tmp_path / "nlt_20260415_130000.json").write_text(
            json.dumps([_make_book("9786161842727")]), encoding="utf-8"
        )
        result = _load_existing_isbns(tmp_path, "nlt")
        assert result == {"9786161842710", "9786161842727"}

    def test_ignores_files_of_different_source(self, tmp_path):
        (tmp_path / "unknown_20260415_120000.json").write_text(
            json.dumps([_make_book("9786161842710", source=None)]), encoding="utf-8"
        )
        result = _load_existing_isbns(tmp_path, "nlt")
        assert result == set()

    def test_skips_unreadable_file_without_raising(self, tmp_path):
        (tmp_path / "nlt_20260415_bad.json").write_text("not valid json", encoding="utf-8")
        # Should not raise
        result = _load_existing_isbns(tmp_path, "nlt")
        assert result == set()


# ---------------------------------------------------------------------------
# _write_source_json_files
# ---------------------------------------------------------------------------

class TestWriteSourceJsonFiles:
    def test_creates_file_for_each_source(self, tmp_path):
        books = [
            _make_book("9786161842710", source="nlt"),
            _make_book("9786161842727", source=None),
        ]
        _write_source_json_files(books, tmp_path, "20260415_120000")

        nlt_file = tmp_path / "nlt_20260415_120000.json"
        unknown_file = tmp_path / "unknown_20260415_120000.json"
        assert nlt_file.exists()
        assert unknown_file.exists()

        nlt_data = json.loads(nlt_file.read_text(encoding="utf-8"))
        assert len(nlt_data) == 1
        assert nlt_data[0]["isbn"] == "9786161842710"

        unknown_data = json.loads(unknown_file.read_text(encoding="utf-8"))
        assert len(unknown_data) == 1
        assert unknown_data[0]["isbn"] == "9786161842727"

    def test_deduplicates_against_existing_files(self, tmp_path):
        # Pre-existing file already has one ISBN
        existing = [_make_book("9786161842710", source="nlt")]
        (tmp_path / "nlt_20260415_110000.json").write_text(
            json.dumps(existing), encoding="utf-8"
        )

        # New run includes both the existing ISBN and a new one
        new_books = [
            _make_book("9786161842710", source="nlt"),  # duplicate
            _make_book("9786161842727", source="nlt"),  # new
        ]
        _write_source_json_files(new_books, tmp_path, "20260415_120000")

        out_file = tmp_path / "nlt_20260415_120000.json"
        assert out_file.exists()
        saved = json.loads(out_file.read_text(encoding="utf-8"))
        assert len(saved) == 1
        assert saved[0]["isbn"] == "9786161842727"

    def test_no_file_written_when_all_duplicates(self, tmp_path):
        existing = [_make_book("9786161842710", source="nlt")]
        (tmp_path / "nlt_20260415_110000.json").write_text(
            json.dumps(existing), encoding="utf-8"
        )

        # Try to write the same ISBN again
        _write_source_json_files(existing, tmp_path, "20260415_120000")

        assert not (tmp_path / "nlt_20260415_120000.json").exists()

    def test_output_file_is_valid_json_list(self, tmp_path):
        books = [_make_book("9786161842710", source="nlt")]
        _write_source_json_files(books, tmp_path, "20260415_120000")

        out_file = tmp_path / "nlt_20260415_120000.json"
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data[0]["isbn"] == "9786161842710"

    def test_timestamp_appears_in_filename(self, tmp_path):
        books = [_make_book("9786161842710", source="nlt")]
        _write_source_json_files(books, tmp_path, "20991231_235959")

        assert (tmp_path / "nlt_20991231_235959.json").exists()

    def test_none_source_maps_to_unknown(self, tmp_path):
        books = [_make_book("9786161842710", source=None)]
        _write_source_json_files(books, tmp_path, "20260415_120000")

        assert (tmp_path / "unknown_20260415_120000.json").exists()
        assert not (tmp_path / "None_20260415_120000.json").exists()

    def test_empty_results_writes_no_files(self, tmp_path):
        _write_source_json_files([], tmp_path, "20260415_120000")
        assert list(tmp_path.iterdir()) == []
