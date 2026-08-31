import unittest
import time
import threading
import sys
import os
import urllib.parse
from unittest.mock import MagicMock, patch

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('Codigo/Crawler'))

from downloader import RUCTDownloader, normalize_url, SkipUniversityException, HostCircuitOpenException
from univ_web_crawler import UniversityWebCrawler, score_academic_candidate_url, is_valid_curricular_table
from checkpoint import CheckpointManager, atomic_json_dump
from config import USER_AGENT, REQUEST_DELAY, JITTER_MIN_SECONDS, JITTER_MAX_SECONDS


class TestCrawlerPolitenessAndConcurrency(unittest.TestCase):
    """
    Auditoría técnica de:
    1. Normas éticas de cortesía de crawling (User-Agent, robots.txt RFC 9309, rate limiting, jitter, circuit breaker).
    2. Concurrencia segura y paralelismo multihilo/multiproceso.
    """

    def test_user_agent_identification(self):
        """Verifica que el User-Agent identifique formalmente el proyecto UniHub y enlace al repositorio."""
        self.assertIn("UniHubCrawler", USER_AGENT)
        self.assertIn("https://github.com/Alejandro-UCA/UniHub-TFG", USER_AGENT)

    def test_domain_lock_rate_limiting_concurrency(self):
        """Verifica que dos hilos simultáneos apuntando al mismo dominio respeten estrictamente el delay secuencial."""
        downloader = RUCTDownloader(delay=0.2)
        target_url = "https://www.uca.es/estudios/grados"
        
        timestamps = []
        def make_request():
            downloader._apply_delay(target_url)
            timestamps.append(time.time())

        t1 = threading.Thread(target=make_request)
        t2 = threading.Thread(target=make_request)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(timestamps), 2)
        diff = abs(timestamps[1] - timestamps[0])
        # El retraso entre dos peticiones al mismo dominio debe ser >= delay (0.2s) + jitter mínimo (0.10s) = 0.30s
        self.assertGreaterEqual(diff, 0.25)

    def test_circuit_breaker_resilience(self):
        """Verifica que tras fallos repetidos el Circuit Breaker actúe correctamente."""
        downloader = RUCTDownloader(delay=0.01)
        downloader.current_univ_code = "TEST_UNIV"
        
        # Simular 9 fallos (por debajo del umbral de 10)
        for _ in range(9):
            paused = downloader._handle_connection_failure("Connection reset by peer")
            self.assertFalse(paused)
            
        self.assertEqual(downloader.consecutive_failures, 9)

    def test_host_circuit_breaker_isolated_and_recoverable(self):
        url = "https://isolated-host.example/guide"
        RUCTDownloader._GLOBAL_DOMAIN_FAILURES.pop("isolated-host.example", None)
        RUCTDownloader._GLOBAL_DOMAIN_OPEN_UNTIL.pop("isolated-host.example", None)
        try:
            for _ in range(3):
                RUCTDownloader._record_domain_failure(url)
            with self.assertRaises(HostCircuitOpenException):
                RUCTDownloader._check_domain_circuit(url)
            RUCTDownloader._record_domain_success(url)
            RUCTDownloader._check_domain_circuit(url)
        finally:
            RUCTDownloader._GLOBAL_DOMAIN_FAILURES.pop("isolated-host.example", None)
            RUCTDownloader._GLOBAL_DOMAIN_OPEN_UNTIL.pop("isolated-host.example", None)

    def test_open_host_circuit_is_not_retried_by_http_loop(self):
        downloader = RUCTDownloader(delay=0.01, max_retries=3, respect_robots=False)
        try:
            with patch.object(downloader, "_apply_delay"), \
                 patch.object(
                     downloader,
                     "_check_domain_circuit",
                     side_effect=HostCircuitOpenException("circuit breaker abierto"),
                 ) as check_circuit:
                with self.assertRaises(HostCircuitOpenException):
                    downloader._request_with_retry("https://isolated-host.example/guide")
            self.assertEqual(check_circuit.call_count, 1)
        finally:
            downloader.close()

    def test_connection_failures_are_scoped_to_the_failing_host(self):
        downloader = RUCTDownloader(delay=0.01)
        host_a = "https://host-a.example/guide"
        host_b = "https://host-b.example/guide"
        with patch("downloader.CIRCUIT_BREAKER_FAILURES_THRESHOLD", 2):
            self.assertFalse(downloader._handle_connection_failure("Connection reset by peer", host_a))
            self.assertFalse(downloader._handle_connection_failure("Connection reset by peer", host_a))
            self.assertFalse(downloader._handle_connection_failure("Connection reset by peer", host_b))

        self.assertEqual(downloader._connection_pause_counts_by_domain.get("host-a.example"), 1)
        self.assertNotIn("host-b.example", downloader._connection_pause_counts_by_domain)
        self.assertNotEqual(downloader._connection_failures_by_domain.get("host-b.example"), 0)
        downloader.close()

    def test_robots_txt_cache_thread_safety(self):
        """Verifica que el acceso a la caché de robots.txt sea thread-safe con cerrojo sincronizado."""
        crawler = UniversityWebCrawler()
        self.assertTrue(hasattr(crawler, "_robots_lock"))
        self.assertIsInstance(crawler._robots_lock, type(threading.Lock()))

    def test_atomic_json_dump_concurrency(self):
        """Verifica que la escritura atómica de JSON cree y reemplace ficheros sin colisiones ni corrupción."""
        test_file = "Codigo/Crawler/Datos/test_atomic.json"
        data1 = {"thread": 1, "status": "ok"}
        data2 = {"thread": 2, "status": "ok"}

        t1 = threading.Thread(target=atomic_json_dump, args=(data1, test_file))
        t2 = threading.Thread(target=atomic_json_dump, args=(data2, test_file))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertTrue(os.path.exists(test_file))
        import json
        with open(test_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertIn("thread", saved)
        os.remove(test_file)


if __name__ == "__main__":
    unittest.main()
