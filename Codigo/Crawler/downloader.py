import time
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import REQUEST_DELAY, MAX_RETRIES, HTTP_TIMEOUT, USER_AGENT

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SkipUniversityException(Exception):
    """Raised when consecutive connection failures exceed 3 cycles of 5-minute pauses for a university."""
    pass

class RUCTDownloader:
    """
    Handles robust HTTP requests with rate limiting, retries, browser headers,
    automatic HTTP->HTTPS fallback, and a circuit breaker for connection resilience:
    - 10 consecutive failures -> 5-minute (300s) pause.
    - 3 consecutive 5-minute pauses -> raise SkipUniversityException and log error.
    """
    DOMAIN_MAPPINGS = {
        "portaldogc.gencat.cat": "dogc.gencat.cat",
        "www.boa.aragon.es": "boa.aragon.es"
    }

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
        
        # Connection resilience counters
        self.consecutive_failures = 0
        self.pause_count_univ = 0
        self.current_univ_code = ""

    def reset_university_context(self, univ_code: str):
        """Resets pause counters when starting a new university."""
        self.current_univ_code = univ_code
        self.consecutive_failures = 0
        self.pause_count_univ = 0

    def _normalize_url(self, url: str) -> str:
        """Normalizes legacy domains to modern active hostnames."""
        for old_domain, new_domain in self.DOMAIN_MAPPINGS.items():
            if old_domain in url:
                url = url.replace(old_domain, new_domain)
        return url

    def _apply_delay(self):
        """Enforces rate limiting delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_time = time.time()

    def _handle_connection_success(self):
        """Resets failure counter on successful request."""
        self.consecutive_failures = 0

    def _handle_connection_failure(self, error_details: str):
        """
        Increments failure counter. Handles 5-minute pause and 15-minute skip thresholds.
        """
        self.consecutive_failures += 1
        print(f" [ADVERTENCIA] Fallo de conexión #{self.consecutive_failures}/10: {error_details}")
        
        if self.consecutive_failures >= 10:
            self.pause_count_univ += 1
            if self.pause_count_univ < 3:
                print(f"\n⚠️ [RESILIENCIA] 10 fallos de conexión seguidos detectados. Pausando 5 minutos para reanudar (Pausa #{self.pause_count_univ}/3)...")
                time.sleep(300) # 5 minutes pause
                self.consecutive_failures = 0
            else:
                print(f"\n❌ [CORTOCIRCUITO] 3 pausas de 5 minutos alcanzadas (15 min acumulados en la universidad [{self.current_univ_code}]). Saltando a la siguiente universidad...")
                self.consecutive_failures = 0
                raise SkipUniversityException(f"Problemas de conexion continuados en la universidad [{self.current_univ_code}]")

    def fetch_content(self, url: str) -> bytes:
        """Fetches raw content from a URL with connection resilience and HTTPS fallback."""
        url = self._normalize_url(url)
        self._apply_delay()
        t0 = time.perf_counter()

        urls_to_try = [url]
        if url.startswith("http://"):
            urls_to_try.append("https://" + url[7:])

        last_error = None
        for attempt_idx, target_url in enumerate(urls_to_try, 1):
            try:
                verify_ssl = False if target_url.startswith("https://") else True
                response = self.session.get(target_url, timeout=self.timeout, verify=verify_ssl)
                response.raise_for_status()
                elapsed = time.perf_counter() - t0
                if self.metrics_tracker:
                    self.metrics_tracker.record_io_time(elapsed)
                self._handle_connection_success()
                return response.content
            except SkipUniversityException:
                raise
            except Exception as e:
                last_error = e
                if attempt_idx < len(urls_to_try):
                    print(f"     [Proceso Red] -> Falló conexión a '{target_url}'. Reintentando con HTTPS...")
                    continue

        self._handle_connection_failure(str(last_error))
        raise last_error

    def fetch_text(self, url: str, encoding="utf-8") -> str:
        """Fetches decoded string content from a URL."""
        content = self.fetch_content(url)
        return content.decode(encoding, errors="replace")

    def download_file(self, url: str, destination_path: str, is_pdf: bool = False):
        """Downloads a remote file directly to disk with connection resilience and HTTPS fallback."""
        url = self._normalize_url(url)
        self._apply_delay()
        t0 = time.perf_counter()

        urls_to_try = [url]
        if url.startswith("http://"):
            urls_to_try.append("https://" + url[7:])

        last_error = None
        for attempt_idx, target_url in enumerate(urls_to_try, 1):
            try:
                verify_ssl = False if target_url.startswith("https://") else True
                with self.session.get(target_url, stream=True, timeout=self.timeout, verify=verify_ssl) as response:
                    response.raise_for_status()
                    
                    first_chunk = True
                    with open(destination_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                if is_pdf and first_chunk:
                                    first_chunk = False
                                    content_type = response.headers.get("Content-Type", "").lower()
                                    if not (b"%PDF-" in chunk[:1024] or "application/pdf" in content_type):
                                        raise ValueError("Respuesta HTTP no es un PDF válido (posible HTML u otro tipo de contenido)")
                                f.write(chunk)
                elapsed = time.perf_counter() - t0
                if self.metrics_tracker:
                    self.metrics_tracker.record_io_time(elapsed)
                self._handle_connection_success()
                return
            except SkipUniversityException:
                raise
            except Exception as e:
                last_error = e
                if attempt_idx < len(urls_to_try):
                    print(f"     [Proceso Red] -> Falló conexión HTTP a '{target_url}'. Reintentando con HTTPS...")
                    continue

        self._handle_connection_failure(str(last_error))
        raise last_error
