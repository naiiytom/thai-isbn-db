"""
RobustHttpMixin — shared HTTP retry logic for all scraper clients.

Provides a _get() method with:
  - Exponential back-off with ±20% jitter on every retry
  - HTTP 429 handling: reads Retry-After header (integer seconds or HTTP-date),
    sleeps that duration (capped at _RETRY_AFTER_CAP seconds)
  - Distinct log messages for network errors vs HTTP errors

Subclasses must provide: self._crawler_thread, self._run_config,
self.timeout, self.retries
"""

import asyncio
import datetime
import logging
import random
import threading
import time
from typing import Optional
from urllib.parse import urlencode

from crawl4ai import AsyncWebCrawler, BrowserConfig

logger = logging.getLogger(__name__)

_RETRY_AFTER_CAP = 120  # never sleep more than 2 minutes on a 429


class _AsyncCrawlerThread:
    """
    Runs one AsyncWebCrawler on a dedicated daemon-thread event loop.

    This lets synchronous client code submit coroutines to a persistent
    browser instance without requiring an async call stack.
    """

    def __init__(self, browser_config: BrowserConfig):
        self._browser_config = browser_config
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self.crawler: Optional[AsyncWebCrawler] = None

    def start(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._thread.start()
        future = asyncio.run_coroutine_threadsafe(self._start_crawler(), self.loop)
        future.result(timeout=30)

    async def _start_crawler(self) -> None:
        self.crawler = AsyncWebCrawler(config=self._browser_config)
        await self.crawler.__aenter__()

    def submit(self, coro):
        """Run *coro* on the background loop and return its result synchronously."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def stop(self) -> None:
        if self.crawler and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.crawler.__aexit__(None, None, None), self.loop
            ).result(timeout=10)
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._thread:
            self._thread.join(timeout=5)


class RobustHttpMixin:
    """
    Mixin that provides a robust _get() method backed by crawl4ai.

    Requires the subclass to set in __init__:
      self._crawler_thread  — a started _AsyncCrawlerThread instance
      self._run_config      — a crawl4ai CrawlerRunConfig instance
      self.timeout          — request timeout in seconds (int)
      self.retries          — number of attempts (int)
    """

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        """
        GET *url* with retries, jitter, and 429-aware back-off.
        Returns the response HTML on HTTP 200, or None after all attempts fail.
        """
        full_url = url + ("?" + urlencode(params)) if params else url
        delay = 1.0
        for attempt in range(1, self.retries + 1):
            try:
                result = self._crawler_thread.submit(
                    self._crawler_thread.crawler.arun(
                        full_url, config=self._run_config
                    )
                )

                if result.success and result.status_code == 200:
                    return result.html

                if result.status_code == 429:
                    wait = _parse_retry_after(result.response_headers or {}, delay)
                    logger.warning(
                        "GET %s → 429 Too Many Requests (attempt %d/%d); "
                        "sleeping %.1fs before retry",
                        url, attempt, self.retries, wait,
                    )
                    if attempt < self.retries:
                        time.sleep(wait)
                    continue

                logger.warning(
                    "GET %s → HTTP %s (attempt %d/%d)",
                    url, result.status_code, attempt, self.retries,
                )

            except Exception as exc:
                logger.warning(
                    "GET %s — error (attempt %d/%d): %s",
                    url, attempt, self.retries, exc,
                )

            if attempt < self.retries:
                jittered = delay * random.uniform(0.8, 1.2)
                time.sleep(jittered)
                delay *= 2

        return None

    def close(self) -> None:
        self._crawler_thread.stop()

    def __enter__(self):
        return self

    def __exit__(self, *_) -> None:
        self.close()


def _parse_retry_after(headers, fallback: float) -> float:
    """
    Parse the Retry-After response header into a sleep duration (seconds).

    Accepts:
      - Integer string: "30"
      - HTTP-date string: "Wed, 21 Oct 2015 07:28:00 GMT"

    Falls back to *fallback* if the header is absent or unparseable.
    The result is always capped at _RETRY_AFTER_CAP.
    """
    raw = headers.get("Retry-After")
    if raw is None:
        return min(fallback, _RETRY_AFTER_CAP)

    # Try plain integer seconds first.
    try:
        return min(float(raw), _RETRY_AFTER_CAP)
    except ValueError:
        pass

    # Try HTTP-date format.
    try:
        from email.utils import parsedate_to_datetime
        retry_dt = parsedate_to_datetime(raw)
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = (retry_dt - now).total_seconds()
        if delta > 0:
            return min(delta, _RETRY_AFTER_CAP)
    except Exception:
        pass

    return min(fallback, _RETRY_AFTER_CAP)
