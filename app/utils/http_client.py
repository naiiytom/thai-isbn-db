"""
RobustHttpMixin — shared HTTP retry logic for all scraper clients.

Provides a _get() method with:
  - Exponential back-off with ±20% jitter on every retry
  - HTTP 429 handling: reads Retry-After header (integer seconds or HTTP-date),
    sleeps that duration (capped at _RETRY_AFTER_CAP seconds)
  - Distinct log messages for network errors vs HTTP errors

Subclasses must provide: self.session, self.timeout, self.retries
"""

import datetime
import logging
import random
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_RETRY_AFTER_CAP = 120  # never sleep more than 2 minutes on a 429


class RobustHttpMixin:
    """
    Mixin that provides a robust _get() method.

    Requires the subclass to set in __init__:
      self.session   — a requests.Session instance
      self.timeout   — request timeout in seconds (int)
      self.retries   — number of attempts (int)
    """

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        """
        GET *url* with retries, jitter, and 429-aware back-off.
        Returns the response text on HTTP 200, or None after all attempts fail.
        """
        delay = 1.0
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.timeout, allow_redirects=True
                )
                resp.encoding = "utf-8"

                if resp.status_code == 200:
                    return resp.text

                if resp.status_code == 429:
                    wait = _parse_retry_after(resp.headers, delay)
                    logger.warning(
                        "GET %s → 429 Too Many Requests (attempt %d/%d); "
                        "sleeping %.1fs before retry",
                        url, attempt, self.retries, wait,
                    )
                    if attempt < self.retries:
                        time.sleep(wait)
                    continue  # skip the shared delay block below

                logger.warning(
                    "GET %s → HTTP %s (attempt %d/%d)",
                    url, resp.status_code, attempt, self.retries,
                )

            except requests.RequestException as exc:
                logger.warning(
                    "GET %s — network error (attempt %d/%d): %s",
                    url, attempt, self.retries, exc,
                )

            if attempt < self.retries:
                jittered = delay * random.uniform(0.8, 1.2)
                time.sleep(jittered)
                delay *= 2

        return None


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
