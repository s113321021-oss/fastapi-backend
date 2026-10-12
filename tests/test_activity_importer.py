import unittest

import httpx

from app.services.activity_importer import (
    ActivityCandidate,
    _error_summary,
    _extract_detail_data,
    _parse_datetime,
    is_allowed_source_url,
    parse_listing,
)


class ActivityImporterTests(unittest.TestCase):
    def test_slll_listing_extracts_title_start_and_capacity(self):
        html = """
        <table>
          <tr><th></th><th>活動編號</th><th>主辦單位</th><th>活動名稱</th>
              <th>活動開始時間</th><th>對象</th><th>名額/報名/錄取</th></tr>
          <tr><td><a href="view.asp?RowID=4398">檢視</a></td><td>4398</td>
              <td>圖書館</td><td>校園講座</td><td>2026/10/14 13:30:00</td>
              <td>學生</td><td>50/2/2</td></tr>
        </table>
        """
        candidates = parse_listing("slll", html.encode())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].title, "校園講座")
        self.assertEqual(candidates[0].parsed_data["capacity"], 50)
        self.assertEqual(candidates[0].parsed_data["starts_at"], "2026-10-14T13:30+08:00")

    def test_ltrc_listing_deduplicates_status_links(self):
        html = """
        <a href="../quiz/quiz_sign_in.jsp?np_id=NP123">英語歌唱比賽</a>
        <a href="quiz_sign_in.jsp?np_id=NP123">我要報名</a>
        """
        candidates = parse_listing("ltrc", html.encode())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].title, "英語歌唱比賽")

    def test_ctld_listing_only_keeps_event_related_announcements(self):
        html = """
        <a href="/p/406-1062-1.php">教師知能活動講座</a>
        <a href="/p/406-1062-2.php">行政公告</a>
        """
        candidates = parse_listing("ctld", html.encode())
        self.assertEqual([candidate.title for candidate in candidates], ["教師知能活動講座"])

    def test_dates_support_gregorian_and_roc_years(self):
        self.assertEqual(_parse_datetime("2026/10/14 13:30:00"), "2026-10-14T13:30+08:00")
        self.assertEqual(
            _parse_datetime("115 年 10 月 15 日（四）14:00-16:00"),
            "2026-10-15T14:00+08:00",
        )

    def test_slll_detail_extracts_location_deadline_capacity_and_description(self):
        source_url = "https://ccweb.ncnu.edu.tw/SLLL/view.asp?RowID=1"
        candidate = ActivityCandidate(
            source_id="slll",
            source_name="暨大活動系統",
            source_url=source_url,
            title="校園講座",
            parsed_data={
                "title": "校園講座",
                "description": "",
                "location": "",
                "organizer": "圖書館",
                "category": "talk",
                "starts_at": None,
                "registration_deadline": None,
                "capacity": None,
                "duration": "",
            },
        )
        html = """
        <main>活動開始時間 2026/10/14 13:30:00 活動結束時間 2026/10/14 15:30:00
        報名結束時間 2026/10/13 23:59:59 時數 2 活動地點 圖書館 1F 展示區
        活動說明 介紹校園活動與服務。允許教職員參加 是 名額限制 50</main>
        """
        parsed = _extract_detail_data("slll", html.encode(), candidate)
        self.assertEqual(parsed["location"], "圖書館 1F 展示區")
        self.assertEqual(parsed["registration_deadline"], "2026-10-13T23:59+08:00")
        self.assertEqual(parsed["capacity"], 50)
        self.assertIn("介紹校園活動", parsed["description"])
        self.assertEqual(parsed["parse_errors"], [])

    def test_source_url_requires_https_and_allowlisted_host(self):
        self.assertTrue(is_allowed_source_url("https://ctld.ncnu.edu.tw/p/406-1.php", "ctld"))
        self.assertFalse(is_allowed_source_url("http://ctld.ncnu.edu.tw/p/406-1.php", "ctld"))
        self.assertFalse(is_allowed_source_url("https://example.com/", "ctld"))
        self.assertFalse(is_allowed_source_url("https://user@ctld.ncnu.edu.tw/", "ctld"))

    def test_error_summary_keeps_http_status_and_timeout_reason(self):
        request = httpx.Request("GET", "https://ctld.ncnu.edu.tw/")
        response = httpx.Response(503, request=request)
        self.assertEqual(
            _error_summary(httpx.HTTPStatusError("failed", request=request, response=response)),
            "HTTP 503",
        )
        self.assertEqual(_error_summary(httpx.ReadTimeout("timed out")), "連線逾時")


if __name__ == "__main__":
    unittest.main()