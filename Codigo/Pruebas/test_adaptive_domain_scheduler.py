import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import requests


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))
from core.downloader import RUCTDownloader


class TestAdaptiveDomainScheduler(unittest.TestCase):
    def test_transient_failures_increase_domain_delay_and_success_recovers_it(self):
        url = "https://adaptive-domain.example/guide"
        domain = "adaptive-domain.example"
        RUCTDownloader._GLOBAL_DOMAIN_DELAYS.pop(domain, None)
        RUCTDownloader._GLOBAL_DOMAIN_FAILURES.pop(domain, None)
        RUCTDownloader._GLOBAL_DOMAIN_OPEN_UNTIL.pop(domain, None)
        try:
            with patch("downloader.HOST_CIRCUIT_FAILURES_THRESHOLD", 99), \
                 patch("downloader.REQUEST_DELAY", 0.25), \
                 patch("downloader.ADAPTIVE_BACKOFF_MULTIPLIER", 2.0), \
                 patch("downloader.ADAPTIVE_BACKOFF_MAX_DELAY", 2.0):
                RUCTDownloader._record_domain_failure(url)
                self.assertEqual(RUCTDownloader._GLOBAL_DOMAIN_DELAYS[domain], 0.5)
                RUCTDownloader._record_domain_success(url)
                self.assertNotIn(domain, RUCTDownloader._GLOBAL_DOMAIN_DELAYS)
        finally:
            RUCTDownloader._GLOBAL_DOMAIN_DELAYS.pop(domain, None)
            RUCTDownloader._GLOBAL_DOMAIN_FAILURES.pop(domain, None)
            RUCTDownloader._GLOBAL_DOMAIN_OPEN_UNTIL.pop(domain, None)

    def test_request_can_reuse_a_robots_decision_without_second_check(self):
        downloader = RUCTDownloader(
            delay=0,
            max_retries=1,
            respect_robots=True,
            enable_http2=False,
        )
        response = requests.Response()
        response.status_code = 200
        response.url = "https://robots-once.example/guide"
        response._content = b"ok"
        response._content_consumed = True
        response.raise_for_status = MagicMock()
        try:
            with patch.object(downloader.session, "get", return_value=response), \
                 patch.object(downloader.robots_policy, "check", return_value=(True, None)) as check:
                downloader._request_with_retry(response.url, robots_prechecked=True)
            check.assert_not_called()
        finally:
            downloader.close()


if __name__ == "__main__":
    unittest.main()
