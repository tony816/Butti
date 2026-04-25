import json
import tempfile
import unittest
from pathlib import Path

from butti_interests import add_interests, interest_key, load_interests, merge_interests, write_interests


class ButtiInterestsTests(unittest.TestCase):
    def test_interest_key_prefers_stable_fields(self):
        self.assertEqual(interest_key({"recruit_id": "ABC", "link": "x"}), "abc")
        self.assertEqual(interest_key({"recruit_id": "", "link": "HTTPS://EXAMPLE"}), "https://example")

    def test_merge_interests_deduplicates(self):
        existing = [{"recruit_id": "1", "title": "A"}]
        incoming = [{"recruit_id": "1", "title": "A updated"}, {"recruit_id": "2", "title": "B"}]
        items, added = merge_interests(existing, incoming)
        self.assertEqual(added, 1)
        self.assertEqual([item["recruit_id"] for item in items], ["1", "2"])

    def test_add_interests_creates_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "interests.json"
            result = add_interests(path, [{"recruit_id": "1", "company": "A", "title": "T"}])
            self.assertEqual(result["added"], 1)
            loaded = load_interests(path)
        self.assertEqual(loaded["count"], 1)
        self.assertEqual(loaded["items"][0]["company"], "A")

    def test_write_interests_preserves_korean(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_interests([{"title": "전략"}], Path(tmpdir) / "interests.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["items"][0]["title"], "전략")


if __name__ == "__main__":
    unittest.main()
