import pytest
from app.utils.http_client import _AsyncCrawlerThread


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    """Prevent any test from launching a real browser via _AsyncCrawlerThread."""
    monkeypatch.setattr(_AsyncCrawlerThread, "start", lambda self: None)
    monkeypatch.setattr(_AsyncCrawlerThread, "stop", lambda self: None)
