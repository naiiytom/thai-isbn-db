"""
Thai ISBN DB — CLI entry point (importable module for uv script entry point).

Usage via uv:
  uv run thai-isbn fetch 9786161842714
  uv run thai-isbn fetch --batch isbn_list.txt
  uv run thai-isbn show 9786161842714

Usage via python:
  python main.py fetch 9786161842714
"""

import argparse
import json
import logging
import pathlib
import shutil
import sys
from dataclasses import asdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _bootstrap_env() -> None:
    """Copy .env.example → .env if .env does not yet exist."""
    root = pathlib.Path(__file__).parent.parent
    env_file = root / ".env"
    example_file = root / ".env.example"
    if not env_file.exists() and example_file.exists():
        shutil.copy(example_file, env_file)
        logger.info("Created .env from .env.example — edit it before running.")


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
    from app.utils.isbn_formatter import IsbnFormatter

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

    total = len(isbns)
    succeeded = 0
    failed = 0
    skipped = 0
    results = []

    for idx, isbn in enumerate(isbns, start=1):
        # --skip-existing: check MongoDB before fetching
        if args.skip_existing and collection is not None:
            digits = IsbnFormatter.strip(isbn)
            if collection.find_one({"_id": digits}, projection={"_id": 1}):
                logger.info("[%d/%d] Skipping existing ISBN: %s", idx, total, isbn)
                skipped += 1
                continue

        logger.info("[%d/%d] Fetching ISBN: %s", idx, total, isbn)
        try:
            book = orch.fetch_book(isbn)
            d = asdict(book)
            results.append(d)
            print(json.dumps(d, ensure_ascii=False, default=str, indent=2))
            succeeded += 1
        except Exception as exc:
            logger.error("[%d/%d] Failed to fetch %s: %s", idx, total, isbn, exc)
            failed += 1

    # Write output file if requested
    if args.output:
        out_path = pathlib.Path(args.output)
        out_path.write_text(
            json.dumps(results, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        logger.info("Results written to %s", args.output)

    # Batch summary
    if total > 1:
        logger.info(
            "Batch complete: %d succeeded, %d failed, %d skipped (total: %d)",
            succeeded, failed, skipped, total,
        )

    return results


def cmd_show(args):
    collection = _get_collection()
    if collection is None:
        logger.error("MongoDB connection required for 'show' command")
        sys.exit(1)

    from app.utils.isbn_formatter import IsbnFormatter
    digits = IsbnFormatter.strip(args.isbn)

    doc = collection.find_one({"_id": digits})
    if doc is None:
        print(f"No record found for ISBN: {digits}")
        sys.exit(1)

    doc["isbn"] = doc.pop("_id")
    print(json.dumps(doc, ensure_ascii=False, default=str, indent=2))


def main():
    _bootstrap_env()

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
    p_fetch.add_argument(
        "--skip-existing", action="store_true",
        help="Skip ISBNs that already have a record in MongoDB",
    )
    p_fetch.add_argument(
        "--output", metavar="FILE",
        help="Write all fetched results to this JSON file",
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
