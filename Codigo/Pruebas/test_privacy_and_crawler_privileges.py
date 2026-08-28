import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestPrivacyAndCrawlerPrivileges(unittest.TestCase):
    def test_analytics_do_not_persist_exact_searches_or_coordinates(self):
        with open(os.path.join(ROOT, "WWW", "src", "analytics", "usageTracker.js"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("unihub_web_usage_analytics_v2", source)
        self.assertIn("localStorage.removeItem('unihub_web_usage_analytics_v1')", source)
        self.assertNotIn("term: query.trim()", source)
        self.assertNotIn("{ coords }", source)

    def test_crawler_workload_runs_as_dedicated_user(self):
        with open(os.path.join(ROOT, "Docker", "crawler", "Dockerfile"), encoding="utf-8") as handle:
            dockerfile = handle.read()
        with open(os.path.join(ROOT, "Docker", "crawler", "entrypoint.sh"), encoding="utf-8") as handle:
            entrypoint = handle.read()
        self.assertIn("adduser --system --ingroup crawler crawler", dockerfile)
        self.assertIn("crontab -u \"$CRAWLER_USER\" -", entrypoint)
        self.assertIn("su -s /bin/sh \"$CRAWLER_USER\"", entrypoint)


if __name__ == "__main__":
    unittest.main()
