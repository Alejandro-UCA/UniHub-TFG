import os
import re
import time
import random
import threading
import requests
import urllib3
from urllib.parse import urlparse, urlsplit, urlunsplit
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import (
    REQUEST_DELAY,
    MAX_RETRIES,
    HTTP_TIMEOUT,
    USER_AGENT,
    DOMAIN_MAPPINGS,
    CIRCUIT_BREAKER_FAILURES_THRESHOLD,
    CIRCUIT_BREAKER_PAUSE_SECONDS,
    CIRCUIT_BREAKER_MAX_PAUSES,
    JITTER_MIN_SECONDS,
    JITTER_MAX_SECONDS,
    HTTP_429_DEFAULT_RETRY_AFTER,
    DOWNLOAD_CHUNK_SIZE,
    HTTP_POOL_CONNECTIONS,
    HTTP_POOL_MAXSIZE
)

import logging
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.getLogger("urllib3").setLevel(logging.ERROR)

def normalize_url(url: str, domain_mappings: dict = None) -> str:
    """Normalizes legacy domains, cleans malformed protocol prefixes, and upgrades HTTP to HTTPS for secure official portals."""
    if not url:
        return ""
    url = url.strip().strip("'\"` ")
    while any(url.startswith(prefix) for prefix in ["http://https://", "https://http://", "http://http://", "https://https://"]):
        if url.startswith("http://https://"):
            url = "https://" + url[15:]
        elif url.startswith("https://http://"):
            url = "http://" + url[15:]
        elif url.startswith("http://http://"):
            url = "http://" + url[14:]
        elif url.startswith("https://https://"):
            url = "https://" + url[16:]

    if not url.startswith("http://") and not url.startswith("https://"):
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://www.boe.es" + url
        else:
            url = "https://" + url

    try:
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        
        if domain_mappings is None:
            domain_mappings = DOMAIN_MAPPINGS

        # Safe hostname-level mapping (prevents substring corruption like www -> wwwww)
        if netloc in domain_mappings:
            netloc = domain_mappings[netloc]
        elif re.match(r"^(?:w{1,8}|vwww|pww|'www)\.boe\.es$", netloc):
            netloc = "www.boe.es"
        elif re.match(r"^(?:w{1,8})\.bocm\.es$", netloc):
            netloc = "bocm.madrid.org"
        elif re.match(r"^(?:w{1,8})\.boa\.aragon\.es$", netloc):
            netloc = "boa.aragon.es"
        elif re.match(r"^(?:w{1,8})\.dogv\.gva\.es$", netloc):
            netloc = "dogv.gva.es"
        elif re.match(r"^(?:w{1,8})\.bocyl\.jcyl\.es$", netloc):
            netloc = "bocyl.jcyl.es"

        scheme = parts.scheme.lower()
        # Auto-upgrade to HTTPS for regional official bulletins that reject unencrypted HTTP
        for secure_domain in ["dogc.gencat.cat", "boe.es", "educacion.gob.es", "bocm.madrid.org", "bocyl.jcyl.es", "dogv.gva.es", "boa.aragon.es", "doe.juntaex.es"]:
            if secure_domain in netloc:
                scheme = "https"
                break

        url = urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass

    return url

class SkipUniversityException(Exception):
    """Raised when consecutive connection failures exceed threshold cycles of pauses for a university."""
    pass

class RUCTDownloader:
    """
    Handles robust HTTP requests with rate limiting, per-domain jitter, Retry-After parsing,
    browser headers, automatic HTTP->HTTPS fallback, and a circuit breaker for connection resilience.
    """
    DOMAIN_MAPPINGS = DOMAIN_MAPPINGS
    _GLOBAL_DOMAIN_LOCKS = {}
    _GLOBAL_DOMAIN_LOCKS_GUARD = threading.Lock()
    _GLOBAL_DOMAIN_LAST_REQUEST_TIMES = {}

    @classmethod
    def _get_domain_lock(cls, domain: str) -> threading.Lock:
        """Returns a synchronized thread lock for a specific hostname/domain."""
        with cls._GLOBAL_DOMAIN_LOCKS_GUARD:
            if domain not in cls._GLOBAL_DOMAIN_LOCKS:
                cls._GLOBAL_DOMAIN_LOCKS[domain] = threading.Lock()
            return cls._GLOBAL_DOMAIN_LOCKS[domain]

    def __init__(self, delay=REQUEST_DELAY, max_retries=MAX_RETRIES, timeout=HTTP_TIMEOUT, metrics_tracker=None):
        self.delay = delay
        self.timeout = timeout
        self.metrics_tracker = metrics_tracker
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        })
        
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy, 
            pool_connections=HTTP_POOL_CONNECTIONS, 
            pool_maxsize=HTTP_POOL_MAXSIZE
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
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
        """Normalizes legacy domains and cleans malformed protocol prefixes."""
        return normalize_url(url, self.DOMAIN_MAPPINGS)

    def _apply_delay(self, url: str = ""):
        """Enforces per-domain rate limiting delay with random jitter and cross-thread domain synchronization."""
        domain = urlparse(url).netloc.lower() if url else "default"
        domain_lock = self._get_domain_lock(domain)
        domain_lock.acquire()
        try:
            last_time = self._GLOBAL_DOMAIN_LAST_REQUEST_TIMES.get(domain, 0)
            elapsed = time.time() - last_time
            effective_delay = self.delay + random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
            if elapsed < effective_delay:
                time.sleep(effective_delay - elapsed)
            self._GLOBAL_DOMAIN_LAST_REQUEST_TIMES[domain] = time.time()
        finally:
            domain_lock.release()

    def _handle_connection_success(self):
        """Resets failure counter on successful request."""
        self.consecutive_failures = 0

    def _handle_connection_failure(self, error_details: str) -> bool:
        """
        Increments failure counter for genuine network/server overloads.
        Handles 5-minute pause and 15-minute skip thresholds.
        """
        if "404" in str(error_details):
            print(f" [ADVERTENCIA] Recurso no encontrado (HTTP 404): {error_details}")
            return False

        self.consecutive_failures += 1
        print(f" [ADVERTENCIA] Fallo de conexión #{self.consecutive_failures}/{CIRCUIT_BREAKER_FAILURES_THRESHOLD}: {error_details}")
        
        if self.consecutive_failures >= CIRCUIT_BREAKER_FAILURES_THRESHOLD:
            self.pause_count_univ += 1
            if self.pause_count_univ < CIRCUIT_BREAKER_MAX_PAUSES:
                pause_min = int(CIRCUIT_BREAKER_PAUSE_SECONDS / 60)
                print(f"\n⚠️ [RESILIENCIA] {CIRCUIT_BREAKER_FAILURES_THRESHOLD} fallos de conexión seguidos detectados. Pausando {pause_min} minutos para reanudar (Pausa #{self.pause_count_univ}/{CIRCUIT_BREAKER_MAX_PAUSES})...")
                time.sleep(CIRCUIT_BREAKER_PAUSE_SECONDS)
                self.consecutive_failures = 0
                return True
            else:
                total_min = int((CIRCUIT_BREAKER_PAUSE_SECONDS * CIRCUIT_BREAKER_MAX_PAUSES) / 60)
                print(f"\n [CORTOCIRCUITO] {CIRCUIT_BREAKER_MAX_PAUSES} pausas alcanzadas ({total_min} min acumulados en la universidad [{self.current_univ_code}]). Saltando a la siguiente universidad...")
                self.consecutive_failures = 0
                raise SkipUniversityException(f"Problemas de conexion continuados en la universidad [{self.current_univ_code}]")
        return False

    def _prepare_ruct_session(self, url: str):
        """
        Garantiza que la sesión HTTP con el servidor RUCT del Ministerio esté inicializada
        y con la consulta de resultados activa antes de solicitar la descarga del archivo Excel (export=1).
        Esto previene que el servidor devuelva la página HTML del formulario (Expected BOF record; found <!DOC).
        """
        try:
            if "listauniversidades" in url and "export=1" in url:
                self.session.get("https://www.educacion.gob.es/ruct/listauniversidades.action?actual=universidades", timeout=self.timeout)
                self.session.get("https://www.educacion.gob.es/ruct/listauniversidades?actual=universidades&cccaa=&tipo_univ=&codigoUniversidad=&consulta=1", timeout=self.timeout)
            elif "listaestudiosuniversidad" in url and "export=1" in url:
                m = re.search(r"codigoUniversidad=([^&]+)", url)
                if m:
                    u_code = m.group(1)
                    self.session.get(f"https://www.educacion.gob.es/ruct/listaestudiosuniversidad?actual=universidades&codigoUniversidad={u_code}", timeout=self.timeout)
        except Exception:
            pass

    def _request_with_retry(self, url: str, stream: bool = False) -> requests.Response:
        """
        Executes an HTTP GET request with connection resilience, Retry-After header parsing,
        automatic HTTP->HTTPS fallback, and Circuit Breaker error management.
        """
        url = self._normalize_url(url)
        if "export=1" in url and ("listauniversidades" in url or "listaestudiosuniversidad" in url):
            self._prepare_ruct_session(url)

        max_retries = MAX_RETRIES
        attempt = 0
        urls_to_try = [url]
        if url.startswith("http://"):
            urls_to_try.append("https://" + url[7:])

        while attempt < max_retries:
            attempt += 1
            self._apply_delay(url)
            t0 = time.perf_counter()
            last_error = None
            for target_url in urls_to_try:
                try:
                    verify_ssl = True
                    response = self.session.get(target_url, stream=stream, timeout=self.timeout, verify=verify_ssl)
                    if response.status_code == 429:
                        retry_after_val = response.headers.get("Retry-After")
                        retry_secs = int(retry_after_val) if (retry_after_val and retry_after_val.isdigit()) else HTTP_429_DEFAULT_RETRY_AFTER
                        print(f" [AVISO CORTESIA RED] HTTP 429 detectado en '{target_url}'. Pausando {retry_secs}s...")
                        time.sleep(retry_secs)
                        continue
                    response.raise_for_status()
                    elapsed = time.perf_counter() - t0
                    if self.metrics_tracker:
                        self.metrics_tracker.record_io_time(elapsed)
                    self._handle_connection_success()
                    return response
                except SkipUniversityException:
                    raise
                except Exception as e:
                    last_error = e
                    print(f"     [Proceso Red] -> Falló conexión a '{target_url}': {e}")
                    continue
            should_retry = self._handle_connection_failure(str(last_error))
            if not should_retry:
                raise last_error
            print(f" 🔄 [RESILIENCIA] Reintentando petición tras pausa para '{url}'...")
        raise last_error

    def fetch_content(self, url: str) -> bytes:
        """Fetches raw content from a URL with connection resilience, Retry-After header parsing, and HTTPS fallback."""
        response = self._request_with_retry(url, stream=False)
        return response.content

    def fetch_text(self, url: str, encoding="utf-8") -> str:
        """Fetches decoded string content from a URL."""
        content = self.fetch_content(url)
        return content.decode(encoding, errors="replace")

    def download_file(self, url: str, destination_path: str, is_pdf: bool = False):
        """Downloads a remote file directly to disk with connection resilience and HTTPS fallback."""
        try:
            with self._request_with_retry(url, stream=True) as response:
                first_chunk = True
                with open(destination_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            if is_pdf and first_chunk:
                                first_chunk = False
                                content_type = response.headers.get("Content-Type", "").lower()
                                if not (b"%PDF-" in chunk[:1024] or "application/pdf" in content_type):
                                    raise ValueError("Respuesta HTTP no es un PDF válido")
                            elif first_chunk and destination_path.lower().endswith(".xls"):
                                first_chunk = False
                                # Si RUCT devuelve una página HTML de error/sesión en lugar de binario Excel
                                if chunk.strip().startswith(b"<!DOC") or chunk.strip().startswith(b"<html") or chunk.strip().startswith(b"<!doc"):
                                    print(f" ⚠️ [AVISO] Respuesta RUCT retornó HTML en lugar de binario XLS para '{url}'. Reinicializando sesión...")
                                    self._prepare_ruct_session(url)
                            f.write(chunk)
        except Exception:
            if os.path.exists(destination_path):
                try:
                    os.remove(destination_path)
                except Exception:
                    pass
            raise

    def close(self):
        """Closes the underlying requests session and releases open socket pool resources."""
        try:
            self.session.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
