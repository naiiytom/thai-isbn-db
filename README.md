# thai-isbn-db

A Python backend pipeline that fetches Thai book metadata from multiple sources and stores it in MongoDB.

## Motivation

Global registries (Google Books, OpenLibrary) have poor coverage of Thai publishers such as Salmon Books, Phoenix, and Jamsai.  This pipeline implements a **Hybrid Metadata Strategy**: official library sources for text metadata, Thai e-commerce sites for high-resolution covers.

## Architecture

```
ISBN input
    │
    ▼
┌─────────────────────────────────────┐
│           Orchestrator              │
│                                     │
│  Text metadata (priority order):    │
│    1. NLT e-service scraper         │
│                                     │
│  Cover image (priority order):      │
│    1. Naiin JSON API (primary)      │
│    2. SE-ED HTML scraper (fallback) │
│                                     │
│  Persistence: MongoDB               │
└─────────────────────────────────────┘
    │
    ▼
 BookDocument → MongoDB `books` collection
```

### Data Sources

| Source | Role | Access |
|--------|------|--------|
| [NLT e-service](https://e-service.nlt.go.th/ISBNReq/Detail/) | Primary text metadata (title, author, publisher, pages) | HTML scraping; Thai IP required |
| [Naiin API](https://api.naiin.com/products) | Primary cover image | JSON API |
| [SE-ED](https://m.se-ed.com/Product/Search) | Cover image fallback | HTML scraping (`og:image`) |

> **Note:** NLT and Naiin are accessible from Thai IP addresses. Use a Thai VPN when running outside Thailand.

## Setup

```bash
# 1. Clone and install dependencies
pip install -r requirements.txt

# 2. Copy and edit environment config
cp .env.example .env
# Edit MONGO_URI if your MongoDB is not on localhost:27017
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | `thai_isbn_db` | Database name |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout in seconds |
| `REQUEST_RETRIES` | `3` | Retry attempts per request |
| `RATE_LIMIT_DELAY` | `1.0` | Seconds to wait between requests to the same host |

## Usage

```bash
# Fetch a single ISBN (stores result in MongoDB)
python main.py fetch 9786161842714

# Fetch without persisting to MongoDB
python main.py fetch --no-db 9786161842714

# Batch fetch from a file (one ISBN per line)
python main.py fetch --batch isbn_list.txt

# Show a stored record
python main.py show 9786161842714
```

### Example output

```json
{
  "isbn": "978-616-18-4271-4",
  "title": "...",
  "author": "...",
  "publisher": "...",
  "page_count": 320,
  "description": null,
  "cover_url": "https://cdn.naiin.com/...",
  "metadata_source": "nlt",
  "cover_source": "naiin",
  "created_at": "2026-03-21T00:00:00+00:00",
  "updated_at": "2026-03-21T00:00:00+00:00"
}
```

## Project Structure

```
thai-isbn-db/
├── main.py                      # CLI entry point
├── requirements.txt
├── .env.example
├── app/
│   ├── config.py                # Environment-based configuration
│   ├── database.py              # MongoDB connection helpers
│   ├── models.py                # BookDocument dataclass
│   ├── orchestrator.py          # Hybrid resolution logic
│   ├── utils/
│   │   └── isbn_formatter.py    # ISBN-13 hyphenation utility
│   └── clients/
│       ├── nlt_client.py        # NLT e-service scraper
│       ├── naiin_client.py      # Naiin JSON API client
│       └── seed_scraper.py      # SE-ED og:image scraper
└── tests/
    ├── test_isbn_formatter.py
    ├── test_nlt_client.py
    ├── test_naiin_client.py
    ├── test_seed_scraper.py
    └── test_orchestrator.py
```

## ISBN Formatter

The `IsbnFormatter` utility converts raw 13-digit ISBNs to the hyphenated format required by the NLT (`978-616-18-4271-4`).  It uses the Thai ISBN Agency's publisher-group ranges for `978-616` prefixed ISBNs and delegates to `isbnlib` for other prefixes.

```python
from app.utils.isbn_formatter import IsbnFormatter

IsbnFormatter.format("9786161842714")     # → "978-616-18-4271-4"
IsbnFormatter.strip("978-616-18-4271-4")  # → "9786161842714"
```

## Running Tests

```bash
pytest tests/ -v
```

All tests mock HTTP calls with the `responses` library — no real network access required.

## Maintenance

- **Brittle HTML:** NLT and SE-ED selectors may break if the sites redesign their pages.  Check `app/clients/nlt_client.py:_parse_detail` and `app/clients/seed_scraper.py:_parse_og_image`.
- **Rate limiting:** Adjust `RATE_LIMIT_DELAY` if your IP gets blocked.
- **NLT access:** The NLT e-service is only reachable from Thailand.  Requests from other regions will return HTTP 403.
