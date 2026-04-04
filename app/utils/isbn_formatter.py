"""
IsbnFormatter — converts raw 13-digit ISBNs into the hyphenated format
required by sources such as the National Library of Thailand (NLT).

Thai ISBNs almost exclusively fall under the 978-616 prefix (the Thai
registration group).  A small number of older titles use 974 (pre-ISBN-13
era), mapped here for completeness.

Hyphenation rules for 978-616 (source: ISBN registration agency tables):
  978-616-[publisher]-[title]-[check]

Publisher-group ranges used by Thai ISBN Agency:
  00–19   → 2-digit publisher prefix → 5-digit title
  200–699 → 3-digit publisher prefix → 4-digit title
  7000–8999 → 4-digit publisher prefix → 3-digit title
  90000–99999 → 5-digit publisher prefix → 2-digit title
"""

import re


class IsbnFormatter:
    # Strips any existing hyphens/spaces so we always start from digits only.
    _STRIP_RE = re.compile(r"[\s\-]")

    # Thai publisher-group ranges within the 978-616 registration group.
    # Each entry: (range_start, range_end, publisher_digits)
    _TH_978_GROUPS: list[tuple[int, int, int]] = [
        (0,     19,    2),
        (200,   699,   3),
        (7000,  8999,  4),
        (90000, 99999, 5),
    ]

    @classmethod
    def format(cls, isbn: str) -> str:
        """Return a hyphenated ISBN-13 string.

        Delegates to isbnlib for non-Thai prefixes; uses the hardcoded Thai
        agency table for 978-616 and 974 prefixes so results are reliable even
        without network access.

        Returns the original digits (no hyphens) if the format cannot be
        determined.
        """
        digits = cls._STRIP_RE.sub("", isbn)
        if len(digits) not in (10, 13):
            return digits

        # Normalise to 13 digits
        if len(digits) == 10:
            digits = "978" + digits[:-1] + cls._isbn10_check_to_isbn13(digits)

        if digits.startswith("978616"):
            return cls._format_978_616(digits)
        if digits.startswith("974"):
            return cls._format_974(digits)

        # Fall back to isbnlib for other prefixes
        try:
            import isbnlib
            masked = isbnlib.mask(digits)
            return masked if masked else digits
        except Exception:
            return digits

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _format_978_616(cls, digits: str) -> str:
        """Hyphenate a 978-616-… ISBN-13."""
        # digits[0:3]  = "978"
        # digits[3:6]  = "616"
        # digits[6:12] = publisher-group + title-number (6 digits)
        # digits[12]   = check digit
        group_and_title = digits[6:12]  # 6 digits

        for start, end, pub_len in cls._TH_978_GROUPS:
            publisher_candidate = int(group_and_title[:pub_len])
            if start <= publisher_candidate <= end:
                title_len = 6 - pub_len
                publisher = group_and_title[:pub_len]
                title = group_and_title[pub_len:pub_len + title_len]
                check = digits[12]
                return f"978-616-{publisher}-{title}-{check}"

        # Shouldn't happen for valid Thai ISBNs; return best-effort
        return f"978-616-{group_and_title}-{digits[12]}"

    @classmethod
    def _format_974(cls, digits: str) -> str:
        """Best-effort hyphenation for legacy 974-prefix Thai ISBNs."""
        # 974 is a 3-digit registration group; publisher ranges are similar.
        # digits[0:3] = "974", digits[3:12] = pub+title (9 digits), digits[12] = check
        try:
            import isbnlib
            masked = isbnlib.mask(digits)
            return masked if masked else digits
        except Exception:
            return digits

    @staticmethod
    def _isbn10_check_to_isbn13(isbn10: str) -> str:
        """Return the ISBN-13 check digit for a given ISBN-10."""
        base = "978" + isbn10[:9]
        total = sum((3 if i % 2 else 1) * int(d) for i, d in enumerate(base))
        check = (10 - (total % 10)) % 10
        return str(check)

    @classmethod
    def strip(cls, isbn: str) -> str:
        """Return only the digit string (removes hyphens and spaces)."""
        return cls._STRIP_RE.sub("", isbn)
