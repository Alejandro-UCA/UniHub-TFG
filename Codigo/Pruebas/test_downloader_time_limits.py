import unittest
from unittest.mock import MagicMock, patch

import requests

from core.downloader import DegreeTimeoutException, HTTP2ResponseWrapper, HostCircuitOpenException, RUCTDownloader


class _FakeHTTPXResponse:
    status_code = 200
    headers = {}
    url = "https://example.test/slow"
    encoding = "utf-8"
    http_version = "HTTP/2"

    def iter_bytes(self, chunk_size=8192):
        yield b"first"
        yield b"second"

    def close(self):
        pass


class DownloaderTimeLimitTests(unittest.TestCase):
    def test_degree_budget_is_explicit_and_raises_before_next_request(self):
        downloader = RUCTDownloader(respect_robots=False, enable_http2=False)
        try:
            downloader.set_degree_context("2500001")
            with patch("downloader.WEB_DEGREE_TIMEOUT_SECONDS", 10.0), \
                    patch("downloader.time.monotonic", return_value=20.0):
                downloader._degree_started_at = 0.0
                self.assertTrue(downloader.degree_budget_exceeded())
                with self.assertRaises(DegreeTimeoutException):
                    downloader._request_with_retry("https://example.test/plan")
        finally:
            downloader.close()

    def test_http2_stream_has_an_accumulated_duration_cap(self):
        response = _FakeHTTPXResponse()
        with patch("downloader.time.monotonic", side_effect=[100.0, 100.0, 161.0]):
            wrapped = HTTP2ResponseWrapper(response, response.url, max_duration=60.0)
            with self.assertRaises(requests.Timeout):
                list(wrapped.iter_content())

    def test_courtesy_delay_cannot_outlive_degree_budget(self):
        downloader = RUCTDownloader(respect_robots=False, enable_http2=False)
        try:
            downloader.set_degree_context("degree-budget-test")
            downloader._degree_started_at = 0.0
            with patch("downloader.WEB_DEGREE_TIMEOUT_SECONDS", 10.0), \
                    patch("downloader.time.monotonic", return_value=9.5), \
                    patch("downloader.time.sleep") as sleep:
                with self.assertRaises(DegreeTimeoutException):
                    downloader._sleep_with_degree_budget(30.0)
            sleep.assert_called_once_with(0.5)
        finally:
            downloader.close()

    def test_variant_failure_closes_the_original_ledger_attempt(self):
        ledger = MagicMock()
        downloader = RUCTDownloader(
            delay=0,
            max_retries=1,
            respect_robots=False,
            enable_http2=False,
            ledger=ledger,
        )
        response = requests.Response()
        response.status_code = 404
        response.url = "https://example.test/plan"
        response.headers = {}
        response._content = b"not found"
        try:
            with patch.object(downloader.session, "get", return_value=response):
                with self.assertRaises(requests.HTTPError):
                    downloader._request_with_retry("https://example.test/plan")
            ledger.record_response.assert_called_once()
            self.assertEqual(ledger.record_response.call_args.args[0], "https://example.test/plan")
            self.assertEqual(ledger.record_response.call_args.kwargs["status"], "failed")
        finally:
            downloader.close()

    def test_tls_host_failures_are_classified_for_global_circuit_breaker(self):
        error = requests.exceptions.SSLError(
            "SSLCertVerificationError: certificate verify failed: hostname mismatch"
        )
        self.assertTrue(RUCTDownloader._is_transient_network_error(error))
        host_url = "https://tls-circuit-test.example/guide"
        domain = "tls-circuit-test.example"
        try:
            with patch("downloader.HOST_CIRCUIT_FAILURES_THRESHOLD", 1), \
                    patch("downloader.HOST_CIRCUIT_PAUSE_SECONDS", 60):
                RUCTDownloader._record_domain_failure(host_url)
                with self.assertRaises(HostCircuitOpenException):
                    RUCTDownloader._check_domain_circuit(host_url)
        finally:
            RUCTDownloader._GLOBAL_DOMAIN_OPEN_UNTIL.pop(domain, None)
            RUCTDownloader._GLOBAL_DOMAIN_FAILURES.pop(domain, None)

    def test_permanent_http_statuses_are_not_retried(self):
        self.assertTrue(RUCTDownloader._is_permanent_http_error(requests.HTTPError("410 Gone")))
        self.assertTrue(RUCTDownloader._is_permanent_http_error(requests.HTTPError("404 Not Found")))
        self.assertFalse(RUCTDownloader._is_permanent_http_error(requests.HTTPError("408 Request Timeout")))
        self.assertFalse(RUCTDownloader._is_permanent_http_error(requests.HTTPError("429 Too Many Requests")))


if __name__ == "__main__":
    unittest.main()
