import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import REQUEST_DELAY, MAX_RETRIES, HTTP_TIMEOUT, USER_AGENT

class RUCTDownloader:
    """
    Handles robust HTTP requests with rate limiting, retries, browser headers,
    and optional I/O performance timing.
    """
    def __init__(self, delay=REQUEST_DELAY, max_retries=MAX_RETRIES, timeout=HTTP_TIMEOUT, metrics_tracker=None):
        self.delay = delay
        self.timeout = timeout
        self.metrics_tracker = metrics_tracker
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        })
        
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        self.last_request_time = 0

    def _apply_delay(self):
        """Enforces rate limiting delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_time = time.time()

    def fetch_content(self, url: str) -> bytes:
        """Fetches raw content from a URL while recording I/O time."""
        self._apply_delay()
        t0 = time.perf_counter()
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        elapsed = time.perf_counter() - t0
        if self.metrics_tracker:
            self.metrics_tracker.record_io_time(elapsed)
        return response.content

    def fetch_text(self, url: str, encoding="utf-8") -> str:
        """Fetches decoded string content from a URL."""
        content = self.fetch_content(url)
        return content.decode(encoding, errors="replace")

    def download_file(self, url: str, destination_path: str):
        """Downloads a remote file directly to disk while recording I/O time."""
        self._apply_delay()
        t0 = time.perf_counter()
        with self.session.get(url, stream=True, timeout=self.timeout) as response:
            response.raise_for_status()
            with open(destination_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        elapsed = time.perf_counter() - t0
        if self.metrics_tracker:
            self.metrics_tracker.record_io_time(elapsed)
