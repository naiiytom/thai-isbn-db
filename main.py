#!/usr/bin/env python3
"""
Thai ISBN DB — CLI entry point.

Usage
-----
  # Fetch a single ISBN and store it in MongoDB
  python main.py fetch 9786161842714

  # Fetch a list of ISBNs from a file (one per line)
  python main.py fetch --batch isbn_list.txt

  # Show a stored record (requires MongoDB connection)
  python main.py show 9786161842714

  # Show a stored record without connecting to MongoDB (JSON output)
  python main.py fetch --no-db 9786161842714
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _get_collection():
    """Return the MongoDB books collection, or None if connection fails."""
    try:
        from app.database import get_books_collection
        return get_books_collection()
    except Exception as exc:
        logger.warning("MongoDB unavailable (%s) — running without persistence", exc)
        return None


def cmd_fetch(args):
    from app.orchestrator import Orchestrator

    collection = None if args.no_db else _get_collection()
    orch = Orchestrator(db_collection=collection)

    isbns = []
    if args.batch:
        try:
            with open(args.batch, encoding="utf-8") as fh:
                isbns = [line.strip() for line in fh if line.strip()]
        except OSError as exc:
            logger.error("Cannot open batch file: %s", exc)
            sys.exit(1)
    else:
        isbns = [args.isbn]

    results = []
    for isbn in isbns:
        logger.info("Fetching ISBN: %s", isbn)
        try:
            book = orch.fetch_book(isbn)
            d = asdict(book)
            results.append(d)
            print(json.dumps(d, ensure_ascii=False, default=str, indent=2))
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", isbn, exc)

    return results


def cmd_show(args):
    collection = _get_collection()
    if collection is None:
        logger.error("MongoDB connection required for 'show' command")
        sys.exit(1)

    from app.utils.isbn_formatter import IsbnFormatter
    hyphenated = IsbnFormatter.format(args.isbn)

    doc = collection.find_one({"_id": hyphenated})
    if doc is None:
        print(f"No record found for ISBN: {hyphenated}")
        sys.exit(1)

    doc["isbn"] = doc.pop("_id")
    print(json.dumps(doc, ensure_ascii=False, default=str, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Thai ISBN DB — fetch and store Thai book metadata"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # fetch
    p_fetch = sub.add_parser("fetch", help="Fetch metadata for one or more ISBNs")
    p_fetch.add_argument("isbn", nargs="?", help="ISBN-13 (digits or hyphenated)")
    p_fetch.add_argument("--batch", metavar="FILE", help="Text file with one ISBN per line")
    p_fetch.add_argument(
        "--no-db", action="store_true", help="Skip MongoDB persistence"
    )

    # show
    p_show = sub.add_parser("show", help="Show a stored book record from MongoDB")
    p_show.add_argument("isbn", help="ISBN-13 to look up")

    args = parser.parse_args()

    if args.command == "fetch":
        if not args.isbn and not args.batch:
            parser.error("Provide an ISBN or --batch FILE")
        cmd_fetch(args)
    elif args.command == "show":
        cmd_show(args)


if __name__ == "__main__":
    main()
