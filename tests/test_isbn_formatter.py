import pytest
from app.utils.isbn_formatter import IsbnFormatter


class TestIsbnFormatterStrip:
    def test_strip_hyphens(self):
        assert IsbnFormatter.strip("978-616-18-4271-4") == "9786161842714"

    def test_strip_spaces(self):
        assert IsbnFormatter.strip("978 616 18 4271 4") == "9786161842714"

    def test_already_digits(self):
        assert IsbnFormatter.strip("9786161842714") == "9786161842714"


class TestIsbnFormatterFormat978616:
    """Tests for the dominant Thai ISBN prefix 978-616."""

    # publisher range 00–19 → 2-digit publisher, 4-digit title, 1-digit check
    # 978(3) + 616(3) + pub(2) + title(4) + check(1) = 13
    def test_2digit_publisher(self):
        # "9786160412345": publisher=04, title=1234, check=5
        raw = "9786160412345"
        result = IsbnFormatter.format(raw)
        assert result == "978-616-04-1234-5"

    # publisher range 200–699 → 3-digit publisher, 3-digit title, 1-digit check
    def test_3digit_publisher(self):
        # "9786162001234": publisher=200, title=123, check=4
        raw = "9786162001234"
        result = IsbnFormatter.format(raw)
        assert result == "978-616-200-123-4"

    # publisher range 7000–8999 → 4-digit publisher, 2-digit title, 1-digit check
    def test_4digit_publisher(self):
        # "9786167000123": publisher=7000, title=12, check=3
        raw = "9786167000123"
        result = IsbnFormatter.format(raw)
        assert result == "978-616-7000-12-3"

    # publisher range 90000–99999 → 5-digit publisher, 1-digit title, 1-digit check
    def test_5digit_publisher(self):
        # "9786169000012": publisher=90000, title=1, check=2
        raw = "9786169000012"
        result = IsbnFormatter.format(raw)
        assert result == "978-616-90000-1-2"

    def test_known_isbn(self):
        """The ISBN from the spec should hyphenate correctly."""
        # 978-616-18-4271-4 → publisher group "18" (range 0–19, 2 digits)
        result = IsbnFormatter.format("9786161842714")
        assert result == "978-616-18-4271-4"

    def test_hyphenated_input_idempotent(self):
        """Already-hyphenated ISBN should round-trip cleanly."""
        result = IsbnFormatter.format("978-616-18-4271-4")
        assert result == "978-616-18-4271-4"

    def test_parts_count(self):
        """Result must have exactly 5 hyphen-separated parts."""
        result = IsbnFormatter.format("9786161842714")
        assert len(result.split("-")) == 5


class TestIsbnFormatterEdgeCases:
    def test_invalid_length_returns_digits(self):
        assert IsbnFormatter.format("12345") == "12345"

    def test_non_thai_prefix_does_not_crash(self):
        # Should not raise even if isbnlib is unavailable for this prefix
        result = IsbnFormatter.format("9780306406157")
        assert isinstance(result, str)
        assert "978" in result
