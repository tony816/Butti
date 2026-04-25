import json
import tempfile
import unittest
from pathlib import Path

from crawl_catch_recruits import (
    CatchRecruitError,
    build_recruit_params,
    crawl_catch_recruits,
    deduplicate_recruits,
    get_recruit_rows,
    get_total_count,
    is_within_date_range,
    normalize_recruit,
    parse_date,
    title_contains_keyword,
    write_json,
)


class CatchRecruitCrawlerTests(unittest.TestCase):
    def test_build_recruit_params_uses_keyword_and_active_recruits(self):
        params = build_recruit_params("Strategy", page=2, page_size=10, sort=1)
        self.assertEqual(params["Keyword"], "Strategy")
        self.assertEqual(params["curpage"], "2")
        self.assertEqual(params["pageSize"], "10")
        self.assertEqual(params["onRecruitYN"], "Y")

    def test_get_recruit_rows_accepts_known_payload_shapes(self):
        self.assertEqual(get_recruit_rows({"recruitData": [{"RecruitID": "1"}]}), [{"RecruitID": "1"}])
        self.assertEqual(get_recruit_rows({"data": {"recruitList": [{"RecruitID": "2"}]}}), [{"RecruitID": "2"}])

    def test_get_total_count_accepts_known_payload_shapes(self):
        self.assertEqual(get_total_count({"intTotalRecordCount": "12"}), 12)
        self.assertEqual(get_total_count({"data": {"totalCount": 7}}), 7)

    def test_normalize_recruit_builds_detail_link(self):
        item = normalize_recruit(
            {
                "RecruitID": "12345",
                "CompName": "Example",
                "RecruitTitle": "Backend Engineer",
                "ApplyEndDate": "2026-05-01",
            }
        )
        self.assertEqual(item["company"], "Example")
        self.assertEqual(item["title"], "Backend Engineer")
        self.assertEqual(item["deadline"], "2026-05-01")
        self.assertEqual(item["link"], "https://www.catch.co.kr/NCS/RecruitInfoDetails/12345")
        self.assertEqual(item["raw"]["RecruitID"], "12345")

    def test_crawl_catch_recruits_accepts_injected_fetcher(self):
        def fetch(_url, params=None):
            self.assertEqual(params["Keyword"], "Engineer")
            return {
                "intTotalRecordCount": 1,
                "recruitData": [
                    {
                        "RecruitID": "12345",
                        "CompName": "Example",
                        "RecruitTitle": "Backend Engineer",
                    }
                ],
            }

        result = crawl_catch_recruits("Engineer", max_results=5, fetch=fetch)
        self.assertEqual(result["keyword"], "Engineer")
        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["items"]), 1)

    def test_crawl_catch_recruits_filters_by_title_keyword(self):
        def fetch(_url, params=None):
            self.assertEqual(params["Keyword"], "Strategy")
            return {
                "intTotalRecordCount": 2,
                "recruitData": [
                    {"RecruitID": "1", "CompName": "A", "RecruitTitle": "Global Strategy Manager"},
                    {"RecruitID": "2", "CompName": "B", "RecruitTitle": "Finance Manager"},
                ],
            }

        result = crawl_catch_recruits("Strategy", max_results=5, fetch=fetch)
        self.assertEqual([item["recruit_id"] for item in result["items"]], ["1"])
        self.assertTrue(title_contains_keyword({"title": "Global Strategy Manager"}, "strategy"))
        self.assertFalse(title_contains_keyword({"title": "Finance Manager"}, "strategy"))

    def test_crawl_catch_recruits_filters_by_open_date(self):
        def fetch(_url, params=None):
            return {
                "intTotalRecordCount": 2,
                "recruitData": [
                    {
                        "RecruitID": "1",
                        "CompName": "A",
                        "RecruitTitle": "In range",
                        "ApplyStartDatetime": "2026-04-25T00:00:00.000Z",
                    },
                    {
                        "RecruitID": "2",
                        "CompName": "B",
                        "RecruitTitle": "Too old",
                        "ApplyStartDatetime": "2026-04-20T00:00:00.000Z",
                    },
                ],
            }

        result = crawl_catch_recruits("", max_results=5, start_date="2026-04-25", end_date="2026-04-25", fetch=fetch)
        self.assertEqual(result["start_date"], "2026-04-25")
        self.assertEqual(result["end_date"], "2026-04-25")
        self.assertEqual([item["recruit_id"] for item in result["items"]], ["1"])

    def test_date_helpers_reject_bad_ranges(self):
        self.assertEqual(parse_date("2026-04-25").isoformat(), "2026-04-25")
        self.assertTrue(
            is_within_date_range(
                {"start_date": "2026-04-25T00:00:00.000Z"},
                parse_date("2026-04-25"),
                parse_date("2026-04-25"),
            )
        )
        with self.assertRaises(CatchRecruitError):
            crawl_catch_recruits("A", start_date="2026-04-26", end_date="2026-04-25")

    def test_crawl_catch_recruits_rejects_bad_limits(self):
        with self.assertRaises(CatchRecruitError):
            crawl_catch_recruits("Engineer", max_results=0)

    def test_deduplicate_recruits_prefers_recruit_id(self):
        items = [
            {"recruit_id": "1", "link": "a", "company": "A", "title": "A"},
            {"recruit_id": "1", "link": "b", "company": "B", "title": "B"},
            {"recruit_id": "", "link": "", "company": "C", "title": "Same"},
            {"recruit_id": "", "link": "", "company": "C", "title": "Same"},
        ]
        self.assertEqual(len(deduplicate_recruits(items)), 2)

    def test_write_json_preserves_text(self):
        result = {"keyword": "Engineer", "items": [{"company": "Example"}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_json(result, Path(tmpdir) / "catch.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["items"][0]["company"], "Example")


if __name__ == "__main__":
    unittest.main()
