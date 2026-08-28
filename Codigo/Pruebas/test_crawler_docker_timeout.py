import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestCrawlerDockerTimeout(unittest.TestCase):
    def test_etl_timeout_is_propagated_to_startup_and_cron_runs(self):
        compose_path = os.path.join(ROOT, "Docker", "docker-compose.yml")
        entrypoint_path = os.path.join(ROOT, "Docker", "crawler", "entrypoint.sh")
        with open(compose_path, encoding="utf-8") as handle:
            compose = handle.read()
        with open(entrypoint_path, encoding="utf-8") as handle:
            entrypoint = handle.read()

        self.assertIn("CRAWLER_API_SYNC_TIMEOUT: ${CRAWLER_API_SYNC_TIMEOUT:-600}", compose)
        self.assertIn('"CRAWLER_API_SYNC_TIMEOUT=${CRAWLER_API_SYNC_TIMEOUT:-600}"', entrypoint)


if __name__ == "__main__":
    unittest.main()
