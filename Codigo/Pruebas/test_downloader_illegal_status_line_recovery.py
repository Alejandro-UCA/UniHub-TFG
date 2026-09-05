"""Pruebas unitarias para recuperación ante 'illegal status line' y reintento con HTTP/2."""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Crawler")))

from core.downloader import RUCTDownloader, HTTP2ResponseWrapper


class TestDownloaderIllegalStatusLineRecovery(unittest.TestCase):
    """Verifica que Downloader detecte 'illegal status line' como transitorio y ejecute fallback."""

    def test_is_transient_network_error_recognizes_illegal_status_line(self):
        err1 = Exception("RemoteDisconnected: BadStatusLine(\"bytearray(b'cache-control: no-cache')\")")
        err2 = Exception("Illegal status line received from server")
        err3 = Exception("http.client.BadStatusLine: None")

        self.assertTrue(RUCTDownloader._is_transient_network_error(err1))
        self.assertTrue(RUCTDownloader._is_transient_network_error(err2))
        self.assertTrue(RUCTDownloader._is_transient_network_error(err3))

    def test_request_with_retry_falls_back_on_badstatusline(self):
        downloader = RUCTDownloader(delay=0.0, max_retries=2, respect_robots=False)

        # Mock de session.get que falla la primera vez con BadStatusLine
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://www.unirioja.es/estudios/grado"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.content = b"<html><title>Plan UniRioja</title></html>"
        mock_resp.text = "<html><title>Plan UniRioja</title></html>"

        with patch.object(downloader.session, "get") as mock_get:
            mock_get.side_effect = Exception("http.client.BadStatusLine: bytearray(b'cache-control: no-cache')")

            # Simulamos que httpx_client tiene éxito en el fallback
            mock_httpx = MagicMock()
            mock_httpx_resp = MagicMock()
            mock_httpx_resp.status_code = 200
            mock_httpx_resp.url = "https://www.unirioja.es/estudios/grado"
            mock_httpx_resp.headers = {"Content-Type": "text/html"}
            mock_httpx_resp.content = b"<html><title>Plan UniRioja</title></html>"
            mock_httpx_resp.text = "<html><title>Plan UniRioja</title></html>"
            mock_httpx.build_request.return_value = MagicMock()
            mock_httpx.send.return_value = mock_httpx_resp

            downloader.httpx_client = mock_httpx

            response = downloader._request_with_retry("https://www.unirioja.es/estudios/grado")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Plan UniRioja", response.text)


if __name__ == "__main__":
    unittest.main()
