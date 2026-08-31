import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DependencyContractTests(unittest.TestCase):
    def test_http_client_dependency_is_consistent_across_runtime_requirements(self):
        crawler = (ROOT / "Crawler" / "requirements.txt").read_text(encoding="utf-8")
        api = (ROOT / "API" / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("httpx[http2]>=0.28.1,<0.29", crawler)
        self.assertIn("httpx2>=2.0.0", api)
        active_crawler_requirements = "\n".join(
            line for line in crawler.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ).lower()
        self.assertNotIn("httpx2", active_crawler_requirements)


if __name__ == "__main__":
    unittest.main()
