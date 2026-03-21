import responses as resp_mock
import pytest
from app.clients.nlt_client import NltClient, NLT_SEARCH_URL, NLT_DETAIL_URL

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

SEARCH_HTML_WITH_LINK = """
<html><body>
<table>
  <tr>
    <td><a href="/ISBNReq/Detail/42">978-616-18-4271-4</a></td>
    <td>ชื่อหนังสือทดสอบ</td>
  </tr>
</table>
</body></html>
"""

SEARCH_HTML_NO_MATCH = "<html><body><p>ไม่พบข้อมูล</p></body></html>"

DETAIL_HTML = """
<html><body>
<dl>
  <dt>ชื่อเรื่อง</dt><dd>หนังสือทดสอบ</dd>
  <dt>ผู้แต่ง</dt><dd>ผู้เขียนทดสอบ</dd>
  <dt>สำนักพิมพ์</dt><dd>สำนักพิมพ์ทดสอบ</dd>
  <dt>จำนวนหน้า</dt><dd>320 หน้า</dd>
  <dt>เลขมาตรฐาน</dt><dd>978-616-18-4271-4</dd>
</dl>
</body></html>
"""

DETAIL_HTML_TABLE = """
<html><body>
<table>
  <tr><th>ชื่อเรื่อง</th><td>หนังสือตาราง</td></tr>
  <tr><th>ผู้แต่ง</th><td>ผู้เขียนตาราง</td></tr>
  <tr><th>สำนักพิมพ์</th><td>สำนักพิมพ์ตาราง</td></tr>
  <tr><th>จำนวนหน้า</th><td>256</td></tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# Tests: _parse_running_number
# ---------------------------------------------------------------------------

class TestParseRunningNumber:
    def setup_method(self):
        self.client = NltClient()

    def test_finds_link_in_search_results(self):
        result = self.client._parse_running_number(
            SEARCH_HTML_WITH_LINK, "978-616-18-4271-4"
        )
        assert result == 42

    def test_returns_none_when_no_link(self):
        result = self.client._parse_running_number(
            SEARCH_HTML_NO_MATCH, "978-616-18-4271-4"
        )
        assert result is None


# ---------------------------------------------------------------------------
# Tests: _parse_detail (dl layout)
# ---------------------------------------------------------------------------

class TestParseDetailDl:
    def setup_method(self):
        self.client = NltClient()

    def test_title(self):
        meta = self.client._parse_detail(DETAIL_HTML)
        assert meta.title == "หนังสือทดสอบ"

    def test_author(self):
        meta = self.client._parse_detail(DETAIL_HTML)
        assert meta.author == "ผู้เขียนทดสอบ"

    def test_publisher(self):
        meta = self.client._parse_detail(DETAIL_HTML)
        assert meta.publisher == "สำนักพิมพ์ทดสอบ"

    def test_page_count(self):
        meta = self.client._parse_detail(DETAIL_HTML)
        assert meta.page_count == 320

    def test_isbn(self):
        meta = self.client._parse_detail(DETAIL_HTML)
        assert meta.isbn == "978-616-18-4271-4"


# ---------------------------------------------------------------------------
# Tests: _parse_detail (table layout)
# ---------------------------------------------------------------------------

class TestParseDetailTable:
    def setup_method(self):
        self.client = NltClient()

    def test_title_from_table(self):
        meta = self.client._parse_detail(DETAIL_HTML_TABLE)
        assert meta.title == "หนังสือตาราง"

    def test_page_count_from_table(self):
        meta = self.client._parse_detail(DETAIL_HTML_TABLE)
        assert meta.page_count == 256


# ---------------------------------------------------------------------------
# Tests: full fetch flow (mocked HTTP)
# ---------------------------------------------------------------------------

class TestNltClientFetch:
    def setup_method(self):
        self.client = NltClient(rate_limit_delay=0)

    @resp_mock.activate
    def test_fetch_returns_metadata_on_success(self):
        resp_mock.add(
            resp_mock.GET,
            NLT_SEARCH_URL,
            body=SEARCH_HTML_WITH_LINK,
            status=200,
        )
        resp_mock.add(
            resp_mock.GET,
            f"{NLT_DETAIL_URL}/42",
            body=DETAIL_HTML,
            status=200,
        )
        meta = self.client.fetch("9786161842714")
        assert meta is not None
        assert meta.title == "หนังสือทดสอบ"
        assert meta.author == "ผู้เขียนทดสอบ"
        assert meta.page_count == 320

    @resp_mock.activate
    def test_fetch_returns_none_when_search_fails(self):
        resp_mock.add(
            resp_mock.GET,
            NLT_SEARCH_URL,
            body=SEARCH_HTML_NO_MATCH,
            status=200,
        )
        meta = self.client.fetch("9786161842714")
        assert meta is None

    @resp_mock.activate
    def test_fetch_returns_none_on_http_error(self):
        resp_mock.add(
            resp_mock.GET,
            NLT_SEARCH_URL,
            status=403,
        )
        meta = self.client.fetch("9786161842714")
        assert meta is None
