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

  # Fetch without persisting to MongoDB
  python main.py fetch --no-db 9786161842714
"""

from app.cli import main

if __name__ == "__main__":
    main()
