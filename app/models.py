"""
Book document schema for MongoDB.

The document is stored in the `books` collection keyed by the hyphenated
ISBN-13 string (e.g. "978-616-18-4271-4").
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BookDocument:
    isbn: str                          # hyphenated ISBN-13 (primary key / _id)
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    page_count: Optional[int] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None
    metadata_source: Optional[str] = None   # "nlt", "isbndb", etc.
    cover_source: Optional[str] = None      # "naiin", "seed", etc.
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        """Serialise for MongoDB insertion/update."""
        doc = asdict(self)
        doc["_id"] = doc.pop("isbn")
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "BookDocument":
        """Deserialise from a MongoDB document."""
        d = dict(doc)
        d["isbn"] = d.pop("_id")
        # Drop unknown fields gracefully
        known = {f for f in cls.__dataclass_fields__}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)
