import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from crawl_company_news import (
    NewsCrawlerError,
    build_google_rss_params,
    crawl_google_news,
    crawl_naver_news,
    deduplicate_items,
    parse_date,
    parse_google_news_rss,
    parse_naver_news_html,
    validate_date_range,
    write_json,
)


NAVER_LEGACY_HTML = """
<ul class="list_news">
  <li>
    <div class="news_wrap api_ani_send">
      <a class="news_tit" href="https://example.com/a" title="Samsung update">Samsung update</a>
      <a class="info press" href="#">Example Press</a>
      <span class="info">2026.04.24.</span>
      <a class="api_txt_lines dsc_txt_wrap" href="#">Legacy summary.</a>
    </div>
  </li>
</ul>
"""

NAVER_SDS_HTML = """
<section class="sc_new sp_nnews">
  <div data-sds-comp="Profile">
    <span class="sds-comps-profile-info-title-text">
      <a href="https://press.example.com"><span>Example Daily</span></a>
    </span>
    <span>2025.12.31.</span>
  </div>
  <div>
    <a href="https://example.com/sds-title" data-heatmap-target=".tit">
      <span class="sds-comps-text">Samsung SDS title</span>
    </a>
    <a href="https://example.com/sds-title" data-heatmap-target=".body">
      <span>Samsung SDS summary text.</span>
    </a>
  </div>
</section>
"""

GOOGLE_RSS = """
<rss version="2.0">
  <channel>
    <item>
      <title>Samsung news</title>
      <link>https://news.google.com/rss/articles/abc</link>
      <source url="https://example.com">Example Press</source>
      <pubDate>Fri, 24 Apr 2026 01:02:03 GMT</pubDate>
      <description>&lt;a href=&quot;https://example.com&quot;&gt;summary&lt;/a&gt;</description>
    </item>
  </channel>
</rss>
"""


class CompanyNewsCrawlerTests(unittest.TestCase):
    def test_parse_date_rejects_bad_format(self):
        with self.assertRaises(NewsCrawlerError):
            parse_date("2026.04.25")

    def test_validate_date_range_rejects_reversed_dates(self):
        with self.assertRaises(NewsCrawlerError):
            validate_date_range(date(2026, 4, 25), date(2026, 1, 1))

    def test_write_json_preserves_empty_items(self):
        result = {
            "company": "Samsung",
            "start_date": "2026-01-01",
            "end_date": "2026-04-25",
            "generated_at": "2026-04-25T00:00:00+00:00",
            "sources": ["naver"],
            "items": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_json(result, Path(tmpdir) / "news.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["items"], [])
        self.assertEqual(loaded["company"], "Samsung")

    def test_parse_naver_legacy_news_html(self):
        items = parse_naver_news_html(NAVER_LEGACY_HTML)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "naver")
        self.assertEqual(items[0]["title"], "Samsung update")
        self.assertEqual(items[0]["publisher"], "Example Press")
        self.assertEqual(items[0]["published_at"], "2026-04-24")
        self.assertEqual(items[0]["summary"], "Legacy summary.")

    def test_parse_naver_sds_news_html(self):
        items = parse_naver_news_html(NAVER_SDS_HTML)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "naver")
        self.assertEqual(items[0]["title"], "Samsung SDS title")
        self.assertEqual(items[0]["publisher"], "Example Daily")
        self.assertEqual(items[0]["published_at"], "2025-12-31")
        self.assertEqual(items[0]["summary"], "Samsung SDS summary text.")

    def test_parse_google_news_rss(self):
        items = parse_google_news_rss(GOOGLE_RSS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "google")
        self.assertEqual(items[0]["title"], "Samsung news")
        self.assertEqual(items[0]["publisher"], "Example Press")
        self.assertTrue(items[0]["published_at"].startswith("2026-04-24T01:02:03"))

    def test_google_before_date_is_exclusive_next_day(self):
        params = build_google_rss_params("Samsung", date(2026, 1, 1), date(2026, 4, 25))
        self.assertIn("after:2026-01-01", params["q"])
        self.assertIn("before:2026-04-26", params["q"])

    def test_crawl_functions_accept_injected_fetchers(self):
        naver = crawl_naver_news("Samsung", date(2026, 1, 1), date(2026, 4, 25), 5, fetch=lambda *_args, **_kwargs: NAVER_SDS_HTML)
        google = crawl_google_news("Samsung", date(2026, 1, 1), date(2026, 4, 25), 5, fetch=lambda *_args, **_kwargs: GOOGLE_RSS)
        self.assertEqual(len(naver), 1)
        self.assertEqual(len(google), 1)

    def test_deduplicate_items_prefers_link(self):
        items = [
            {"link": "https://example.com/a", "title": "A", "publisher": "P"},
            {"link": "https://example.com/a", "title": "Different", "publisher": "Q"},
            {"link": "", "title": "Same", "publisher": "Press"},
            {"link": "", "title": " Same ", "publisher": "Press"},
        ]
        self.assertEqual(len(deduplicate_items(items)), 2)


if __name__ == "__main__":
    unittest.main()
