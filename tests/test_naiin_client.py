import responses as resp_mock
import pytest
from app.clients.naiin_client import NaiinClient, NAIIN_API_URL


NAIIN_RESPONSE_LIST = [
    {
        "isbn": "9786161842714",
        "title": "หนังสือ Naiin",
        "image_url": "https://cdn.naiin.com/covers/9786161842714.jpg",
        "description": "รายละเอียดหนังสือ",
    }
]

NAIIN_RESPONSE_NESTED_IMAGES = [
    {
        "isbn13": "9786161842714",
        "title": "หนังสือ Naiin 2",
        "images": [{"image_url": "https://cdn.naiin.com/img/alt.jpg"}],
    }
]

NAIIN_RESPONSE_NO_ISBN_MATCH = [
    {
        "isbn": "0000000000000",
        "title": "Wrong Book",
        "image_url": "https://cdn.naiin.com/wrong.jpg",
    }
]


class TestNaiinClientExtract:
    def setup_method(self):
        self.client = NaiinClient()

    def test_extracts_cover_url(self):
        result = self.client._extract(NAIIN_RESPONSE_LIST, "9786161842714")
        assert result is not None
        assert result.cover_url == "https://cdn.naiin.com/covers/9786161842714.jpg"

    def test_extracts_title(self):
        result = self.client._extract(NAIIN_RESPONSE_LIST, "9786161842714")
        assert result.title == "หนังสือ Naiin"

    def test_extracts_description(self):
        result = self.client._extract(NAIIN_RESPONSE_LIST, "9786161842714")
        assert result.description == "รายละเอียดหนังสือ"

    def test_nested_images(self):
        result = self.client._extract(NAIIN_RESPONSE_NESTED_IMAGES, "9786161842714")
        assert result is not None
        assert result.cover_url == "https://cdn.naiin.com/img/alt.jpg"

    def test_falls_back_to_first_product_when_no_isbn_match(self):
        result = self.client._extract(NAIIN_RESPONSE_NO_ISBN_MATCH, "9786161842714")
        # Falls back to first product since there's only one and query was specific
        assert result is not None
        assert result.cover_url == "https://cdn.naiin.com/wrong.jpg"

    def test_returns_none_for_empty_list(self):
        result = self.client._extract([], "9786161842714")
        assert result is None


class TestNaiinClientFetch:
    def setup_method(self):
        self.client = NaiinClient(rate_limit_delay=0)

    @resp_mock.activate
    def test_fetch_cover_success(self):
        resp_mock.add(
            resp_mock.GET,
            NAIIN_API_URL,
            json=NAIIN_RESPONSE_LIST,
            status=200,
        )
        url = self.client.fetch_cover("9786161842714")
        assert url == "https://cdn.naiin.com/covers/9786161842714.jpg"

    @resp_mock.activate
    def test_fetch_cover_returns_none_on_403(self):
        resp_mock.add(resp_mock.GET, NAIIN_API_URL, status=403)
        url = self.client.fetch_cover("9786161842714")
        assert url is None

    @resp_mock.activate
    def test_fetch_cover_returns_none_on_empty_response(self):
        resp_mock.add(resp_mock.GET, NAIIN_API_URL, json=[], status=200)
        url = self.client.fetch_cover("9786161842714")
        assert url is None
