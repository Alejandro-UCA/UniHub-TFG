import os
import re
import ipaddress
import time
import random
import threading
import hashlib
import requests
import urllib3
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import urlparse, urlsplit, urlunsplit, urljoin
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
    HOST_CIRCUIT_FAILURES_THRESHOLD,
    HOST_CIRCUIT_PAUSE_SECONDS,
    JITTER_MIN_SECONDS,
    JITTER_MAX_SECONDS,
    HTTP_429_DEFAULT_RETRY_AFTER,
    HTTP_429_MAX_RETRY_AFTER,
    MAX_RESPONSE_SIZE_BYTES,
    MAX_TEXT_RESPONSE_SIZE_BYTES,
    RESPECT_ROBOTS,
    ADAPTIVE_BACKOFF_MULTIPLIER,
    ADAPTIVE_BACKOFF_MAX_DELAY,
    DOWNLOAD_CHUNK_SIZE,
    HTTP_POOL_CONNECTIONS,
    HTTP_POOL_MAXSIZE,
    HTTP_CACHE_DIR,
    HTTP_CACHE_TTL_SECONDS,
    HTTP_RUN_MEMO_MAX_BYTES,
    ENABLE_HTTP2,
    HTTP2_MAX_CONNECTIONS,
    HTTP2_MAX_KEEPALIVE_CONNECTIONS,
    WEB_CONNECTIVITY_TIMEOUT,
    HTTP_RESPONSE_MAX_DURATION_SECONDS,
    WEB_DEGREE_TIMEOUT_SECONDS,
    ROBOTS_POLICY_MAX_TIMEOUT,
)
from robots_policy import RobotsPolicy
try:
    from crawl_ledger import CrawlLedger
except Exception:
    CrawlLedger = None

try:
    import httpx
    try:
        import h2
        HTTP2_AVAILABLE = True
    except ImportError:
        HTTP2_AVAILABLE = False
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    HTTPX_AVAILABLE = False
    HTTP2_AVAILABLE = False

import logging
logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.getLogger("urllib3").setLevel(logging.ERROR)

_RE_BOE_DOMAINS = re.compile(r"^(?:w{1,8}|vwww|pww|'www)\.boe\.es$")
_RE_BOCM_DOMAINS = re.compile(r"^(?:w{1,8})\.bocm\.es$")
_RE_BOA_DOMAINS = re.compile(r"^(?:w{1,8})\.boa\.aragon\.es$")
_RE_DOGV_DOMAINS = re.compile(r"^(?:w{1,8})\.dogv\.gva\.es$")
_RE_BOCYL_DOMAINS = re.compile(r"^(?:w{1,8})\.bocyl\.jcyl\.es$")
_SECURE_DOMAINS_TUPLE = ("dogc.gencat.cat", "boe.es", "educacion.gob.es", "bocm.madrid.org", "bocyl.jcyl.es", "dogv.gva.es", "boa.aragon.es", "doe.juntaex.es")

def normalize_url(url: str, domain_mappings: dict = None, base_url: str = None) -> str:
    """Normalizes legacy domains, cleans malformed protocol prefixes, and upgrades HTTP to HTTPS for secure official portals."""
    if not isinstance(url, str) or not url.strip():
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
        elif base_url:
            url = urljoin(base_url, url)
        elif url.startswith("/"):
            # Una ruta relativa no identifica un recurso por sí sola. Antes
            # se asociaba implícitamente a BOE, creando fuentes ficticias en
            # candidatos de universidades y guías docentes.
            return ""
        else:
            # No convertir esquemas especiales (mailto:, javascript:, ...)
            # en hosts HTTPS aparentemente válidos.
            scheme_match = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", url)
            if scheme_match:
                return ""
            url = "https://" + url

    try:
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if parts.scheme.lower() not in {"http", "https"} or not netloc:
            return ""
        
        if domain_mappings is None:
            domain_mappings = DOMAIN_MAPPINGS

        # Safe hostname-level mapping (prevents substring corruption like www -> wwwww)

        if netloc in domain_mappings:
            netloc = domain_mappings[netloc]
        elif _RE_BOE_DOMAINS.match(netloc):
            netloc = "www.boe.es"
        elif _RE_BOCM_DOMAINS.match(netloc):
            netloc = "bocm.madrid.org"
        elif _RE_BOA_DOMAINS.match(netloc):
            netloc = "boa.aragon.es"
        elif _RE_DOGV_DOMAINS.match(netloc):
            netloc = "dogv.gva.es"
        elif _RE_BOCYL_DOMAINS.match(netloc):
            netloc = "bocyl.jcyl.es"

        scheme = parts.scheme.lower()
        # Auto-upgrade to HTTPS for regional official bulletins that reject unencrypted HTTP
        for secure_domain in _SECURE_DOMAINS_TUPLE:
            if secure_domain in netloc:
                scheme = "https"
                break

        normalised = urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))
        return normalised if is_valid_http_url(normalised) else ""
    except Exception:
        return url


def is_valid_http_url(url: str) -> bool:
    """Comprueba que ``url`` sea una dirección HTTP(S) apta para solicitar.

    No intenta decidir si el recurso existe: solo evita enviar texto libre,
    hosts imposibles o URLs con caracteres de control al cliente HTTP.
    """
    if not isinstance(url, str) or not url.strip() or any(ord(char) < 32 for char in url):
        return False
    try:
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            return False
        hostname = parts.hostname
        if not hostname or any(char.isspace() for char in hostname):
            return False
        if len(hostname) > 253:
            return False
        # Acceder a .port valida puertos no numéricos y fuera de rango.
        if parts.port is not None and not 0 < parts.port <= 65535:
            return False
        ascii_host = hostname.encode("idna").decode("ascii")
        if len(ascii_host) > 253 or any(not label or len(label) > 63 for label in ascii_host.split(".")):
            return False
        return True
    except (UnicodeError, ValueError, TypeError):
        return False

def is_same_or_subdomain(target_url: str, base_url: str) -> bool:
    """
    Verifica si target_url pertenece al mismo dominio institucional, subdominio hermano
    (ej. quimicas.ub.edu vs web.ub.edu), variación www/no-www, o equivalente autonómico (.gal, .cat, .eus, .es, .edu).
    """
    try:
        t_netloc = urlsplit(target_url).netloc.lower().split(":")[0]
        b_netloc = urlsplit(base_url).netloc.lower().split(":")[0]
        if not t_netloc or not b_netloc:
            return False

        t_netloc = DOMAIN_MAPPINGS.get(t_netloc, t_netloc)
        b_netloc = DOMAIN_MAPPINGS.get(b_netloc, b_netloc)

        if t_netloc == b_netloc:
            return True

        t_clean = re.sub(r"^w{1,8}\d*\.", "", t_netloc)
        b_clean = re.sub(r"^w{1,8}\d*\.", "", b_netloc)

        if t_clean == b_clean:
            return True

        if t_clean.endswith("." + b_clean) or b_clean.endswith("." + t_clean):
            return True

        if _institutional_root(t_clean) == _institutional_root(b_clean):
            return True

        return False
    except Exception:
        return False


def _institutional_root(hostname: str) -> str:
    """Obtiene una raíz conservadora sin aceptar cambios de TLD como equivalentes."""
    parts = [part for part in hostname.lower().split(".") if part]
    if len(parts) < 2:
        return hostname.lower()
    # Sufijos compuestos frecuentes en dominios institucionales españoles y
    # británicos. Para el resto se conserva el último dominio + TLD.
    compound_suffixes = {("edu", "es"), ("gob", "es"), ("com", "es"), ("org", "es"), ("ac", "uk")}
    root_size = 3 if tuple(parts[-2:]) in compound_suffixes and len(parts) >= 3 else 2
    return ".".join(parts[-root_size:])

class SkipUniversityException(Exception):
    """Exception raised when a university server continues to fail and must be skipped."""
    pass


class RobotsDeniedException(PermissionError):
    """Indica que una petición fue omitida por la política de robots.txt.

    Se conserva como ``PermissionError`` para no romper consumidores existentes,
    pero permite distinguir una denegación explícita de robots de un fallo al
    verificar el archivo.
    """

    def __init__(self, url: str, reason: str = "", context: str = ""):
        self.url = str(url or "")
        self.reason = str(reason or "desconocido")
        self.context = str(context or "")
        self.explicit_rule_denial = self.reason == "denegado_por_reglas"
        if self.explicit_rule_denial:
            message = f"robots.txt deniega el rastreo de '{self.url}'"
        else:
            message = f"No se pudo verificar el permiso de robots.txt para '{self.url}'"
        if self.context:
            message += f" para {self.context}"
        message += f" (motivo: {self.reason})"
        super().__init__(message)


class DegreeTimeoutException(TimeoutError):
    """Presupuesto acumulado agotado al procesar una titulación."""


class HostCircuitOpenException(requests.RequestException):
    """El origen remoto está temporalmente aislado por fallos transitorios."""

class HTTP2ResponseWrapper:
    """Wrapper around httpx.Response providing full requests.Response API compatibility."""
    def __init__(self, httpx_resp, target_url: str, max_duration: float = HTTP_RESPONSE_MAX_DURATION_SECONDS):
        self._resp = httpx_resp
        self.status_code = int(httpx_resp.status_code)
        self.headers = httpx_resp.headers
        self.url = str(httpx_resp.url) or target_url
        self.encoding = httpx_resp.encoding
        self.http_version = getattr(httpx_resp, "http_version", "HTTP/2")
        self._unihub_cached = False
        self._started_at = time.monotonic()
        self._max_duration = max(0.0, float(max_duration))

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise requests.HTTPError(
                f"HTTP {self.status_code} para '{self.url}'",
                response=self
            )

    def iter_content(self, chunk_size=DOWNLOAD_CHUNK_SIZE):
        for chunk in self._resp.iter_bytes(chunk_size=chunk_size):
            if self._max_duration and time.monotonic() - self._started_at > self._max_duration:
                raise requests.Timeout(
                    f"Respuesta HTTP excede el límite acumulado de {self._max_duration:.1f}s"
                )
            yield chunk

    @property
    def content(self) -> bytes:
        return self._resp.content

    @property
    def text(self) -> str:
        return self._resp.text

    def close(self):
        try:
            self._resp.close()
        except Exception as error:
            logger.debug("No se pudo cerrar la respuesta HTTP/2: %s", error, exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class RUCTDownloader:
    """
    HTTP downloader with per-domain polite rate limiting (RFC 9309 compliance), 
    HTTP/2 multiplexing, Keep-Alive connection pooling, Retry-After header parsing, and Circuit Breaker resilience.
    """
    _GLOBAL_DOMAIN_LOCKS = {}
    _GLOBAL_DOMAIN_LAST_REQUEST_TIMES = {}
    _GLOBAL_DOMAIN_DELAYS = {}
    _GLOBAL_DOMAIN_FAILURES = {}
    _GLOBAL_DOMAIN_OPEN_UNTIL = {}
    _LOCK_CREATION_LOCK = threading.Lock()

    @classmethod
    def _get_domain_lock(cls, domain: str) -> threading.Lock:
        """Returns a synchronized thread lock for a specific hostname/domain."""
        with cls._LOCK_CREATION_LOCK:
            if domain not in cls._GLOBAL_DOMAIN_LOCKS:
                cls._GLOBAL_DOMAIN_LOCKS[domain] = threading.Lock()
            return cls._GLOBAL_DOMAIN_LOCKS[domain]

    def __init__(self, delay=REQUEST_DELAY, max_retries=MAX_RETRIES, timeout=HTTP_TIMEOUT, metrics_tracker=None, respect_robots=RESPECT_ROBOTS, ledger=None, phase="", enable_http2=ENABLE_HTTP2):
        self.delay = delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.metrics_tracker = metrics_tracker
        self.respect_robots = bool(respect_robots)
        self.robots_policy = RobotsPolicy(timeout=min(timeout, ROBOTS_POLICY_MAX_TIMEOUT))
        self.ledger = ledger
        self.phase = phase
        self.current_degree_code = ""
        self._degree_started_at = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        })
        
        # Desactivamos reintentos internos en urllib3 para que _request_with_retry gestione el control unificado
        adapter = HTTPAdapter(
            max_retries=0, 
            pool_connections=HTTP_POOL_CONNECTIONS, 
            pool_maxsize=HTTP_POOL_MAXSIZE
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.enable_http2 = bool(enable_http2 and HTTPX_AVAILABLE and HTTP2_AVAILABLE)
        self.httpx_client = None
        if self.enable_http2:
            try:
                self.httpx_client = httpx.Client(
                    http2=True,
                    timeout=httpx.Timeout(self.timeout, connect=WEB_CONNECTIVITY_TIMEOUT),
                    follow_redirects=True,
                    limits=httpx.Limits(
                        max_connections=HTTP2_MAX_CONNECTIONS,
                        max_keepalive_connections=HTTP2_MAX_KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=30.0
                    ),
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "same-origin",
                    }
                )
            except Exception as e:
                logger.debug(f"No se pudo inicializar httpx con HTTP/2: {e}. Usando fallback a requests HTTP/1.1.")
                self.httpx_client = None
        
        # Connection resilience counters
        self.consecutive_failures = 0
        self.pause_count_univ = 0
        # La resiliencia de conexiones debe estar asociada al host que falla.
        # Se conserva el contador histórico anterior solo para compatibilidad
        # con integraciones que llaman al método sin URL.
        self._connection_failures_by_domain = {}
        self._connection_pause_counts_by_domain = {}
        self.current_univ_code = ""
        self._run_response_memo = OrderedDict()
        self._run_response_memo_bytes = 0

    def reset_university_context(self, univ_code: str):
        self.current_univ_code = univ_code
        self.consecutive_failures = 0
        self.pause_count_univ = 0
        self._connection_failures_by_domain.clear()
        self._connection_pause_counts_by_domain.clear()

    def set_degree_context(self, degree_code: str):
        self.current_degree_code = str(degree_code or "")
        self._degree_started_at = time.monotonic() if self.current_degree_code else None

    def degree_budget_exceeded(self) -> bool:
        """Indica si la titulación actual agotó su presupuesto acumulado."""
        if not self.current_degree_code or self._degree_started_at is None:
            return False
        budget = max(0.0, float(WEB_DEGREE_TIMEOUT_SECONDS))
        return bool(budget and time.monotonic() - self._degree_started_at >= budget)

    DOMAIN_MAPPINGS = DOMAIN_MAPPINGS

    def _normalize_url(self, url: str) -> str:
        """Normalizes legacy domains and cleans malformed protocol prefixes."""
        return normalize_url(url, DOMAIN_MAPPINGS)

    @staticmethod
    def _request_url_variants(url: str) -> list[str]:
        """Devuelve variantes seguras del host para portales con alias www.

        Muchos portales institucionales publican el certificado TLS y el
        servicio real en ``www`` aunque el catálogo, un BOE o un enlace
        histórico conserve el dominio raíz. Se prueba primero ``www`` y se
        mantiene el host original como respaldo; no se inventan subdominios
        para direcciones locales, IPs ni hosts que ya son ``www``.
        """
        parsed = urlsplit(str(url or ""))
        host = (parsed.hostname or "").lower()
        try:
            is_ip = bool(ipaddress.ip_address(host))
        except ValueError:
            is_ip = False
        # Los TLD reservados para tests/documentación no representan aliases
        # DNS públicos; no se les añade ``www`` porque muchos mocks esperan
        # exactamente una sola petición.
        cctld_suffixes = (".com.es", ".edu.es", ".org.es", ".gob.es", ".nom.es", ".co.uk")
        is_subdomain = False
        if any(host.endswith(sfx) for sfx in cctld_suffixes):
            if host.count(".") >= 3:
                is_subdomain = True
        elif host.count(".") >= 2:
            is_subdomain = True

        if (
            not host
            or is_ip
            or host.startswith("www.")
            or is_subdomain
            or "." not in host
            or host.endswith((".test", ".invalid", ".localhost"))
        ):
            return [url] if url else []
        try:
            if parsed.port is not None:
                host_with_port = f"www.{host}:{parsed.port}"
            else:
                host_with_port = f"www.{host}"
        except ValueError:
            return [url] if url else []
        www_url = urlunsplit((parsed.scheme, host_with_port, parsed.path, parsed.query, parsed.fragment))
        return list(dict.fromkeys((www_url, url)))

    @staticmethod
    def _cache_path(url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return os.path.join(HTTP_CACHE_DIR, f"{digest}.body")

    def _load_cached_response(self, url: str):
        if self.ledger is None:
            return None
        meta = self.ledger.validators(url)
        path = meta.get("cache_path")
        if not path or not os.path.isfile(path):
            return None
        try:
            # La antigüedad no invalida el cuerpo: en una revalidación
            # condicional el servidor puede responder 304 incluso después del
            # TTL operativo. La poda por presupuesto controla el espacio;
            # descartar aquí obligaría a perder el dato anterior ante un 304.
            with open(path, "rb") as handle:
                body = handle.read()
            cached = requests.Response()
            cached.status_code = 200
            cached.url = url
            cached.headers["Content-Type"] = "application/octet-stream"
            cached._content = body
            cached._content_consumed = True
            cached.encoding = "utf-8"
            cached._unihub_cached = True
            self._remember_response_content(url, cached, body)
            return cached
        except OSError:
            return None

    def _remember_response_content(self, url: str, response, content: bytes) -> None:
        """Guarda cuerpos pequeños para evitar peticiones duplicadas durante el run."""
        if not url or not content or HTTP_RUN_MEMO_MAX_BYTES <= 0:
            return
        body = bytes(content)
        if len(body) > HTTP_RUN_MEMO_MAX_BYTES:
            return
        headers = dict(getattr(response, "headers", {}) or {})
        previous = self._run_response_memo.pop(url, None)
        if previous is not None:
            self._run_response_memo_bytes -= len(previous[0])
        self._run_response_memo[url] = (body, headers, getattr(response, "encoding", None))
        self._run_response_memo_bytes += len(body)
        while self._run_response_memo and self._run_response_memo_bytes > HTTP_RUN_MEMO_MAX_BYTES:
            _, (old_body, _, _) = self._run_response_memo.popitem(last=False)
            self._run_response_memo_bytes -= len(old_body)

    def _memoized_response(self, url: str):
        """Reconstruye una respuesta nueva para cada consumidor."""
        entry = self._run_response_memo.get(url)
        if entry is None:
            return None
        body, headers, encoding = entry
        self._run_response_memo.move_to_end(url)
        cached = requests.Response()
        cached.status_code = 200
        cached.url = url
        cached.headers.update(headers)
        cached._content = body
        cached._content_consumed = True
        cached.encoding = encoding or "utf-8"
        cached._unihub_cached = True
        return cached

    def store_response_content(self, url: str, response, content: bytes):
        """Guarda un cuerpo acotado y actualiza el ledger sin interrumpir el crawler."""
        self._remember_response_content(url, response, content)
        if not self.ledger or not content or len(content) > MAX_RESPONSE_SIZE_BYTES or getattr(response, "_unihub_cached", False) is True:
            return
        path = self._cache_path(url)
        temp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            os.makedirs(HTTP_CACHE_DIR, exist_ok=True)
            with open(temp, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            self.ledger.record_response(url, response=response, content=content, status="success", cache_path=path)
        except OSError:
            try:
                if os.path.exists(temp):
                    os.remove(temp)
            except OSError:
                pass

    @staticmethod
    def _http_cache_is_fresh(updated_at: str) -> bool:
        """Indica si procede una petición condicional para un cuerpo cacheado."""
        if HTTP_CACHE_TTL_SECONDS <= 0 or not updated_at:
            return False
        try:
            parsed = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - parsed).total_seconds()
            return 0 <= age <= HTTP_CACHE_TTL_SECONDS
        except (TypeError, ValueError, OverflowError):
            return False

    def _apply_delay(self, url: str = ""):
        """Enforces per-domain rate limiting delay with random jitter, adaptive backoff and cross-thread domain synchronization."""
        domain = urlparse(url).netloc.lower() if url else "default"
        domain_lock = self._get_domain_lock(domain)
        domain_lock.acquire()
        try:
            last_time = self._GLOBAL_DOMAIN_LAST_REQUEST_TIMES.get(domain, 0)
            elapsed = time.time() - last_time
            with self._LOCK_CREATION_LOCK:
                base_delay = self._GLOBAL_DOMAIN_DELAYS.get(domain, self.delay)
            effective_delay = base_delay + random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
            if elapsed < effective_delay:
                time.sleep(effective_delay - elapsed)
            self._GLOBAL_DOMAIN_LAST_REQUEST_TIMES[domain] = time.time()
        finally:
            domain_lock.release()

    def _handle_connection_success(self, url: str = ""):
        """Resets failure counter on successful request."""
        if url:
            domain = urlparse(url).netloc.lower() or "default"
            self._connection_failures_by_domain.pop(domain, None)
            return
        self.consecutive_failures = 0

    @classmethod
    def _check_domain_circuit(cls, url: str) -> None:
        domain = urlparse(url).netloc.lower() if url else "default"
        now = time.time()
        with cls._LOCK_CREATION_LOCK:
            open_until = cls._GLOBAL_DOMAIN_OPEN_UNTIL.get(domain, 0.0)
            if open_until > now:
                remaining = round(open_until - now, 1)
                raise HostCircuitOpenException(
                    f"circuit breaker abierto para '{domain}' ({remaining}s restantes)"
                )

    @classmethod
    def _record_domain_failure(cls, url: str) -> None:
        domain = urlparse(url).netloc.lower() if url else "default"
        with cls._LOCK_CREATION_LOCK:
            failures = cls._GLOBAL_DOMAIN_FAILURES.get(domain, 0) + 1
            cls._GLOBAL_DOMAIN_FAILURES[domain] = failures
            current_delay = cls._GLOBAL_DOMAIN_DELAYS.get(domain, REQUEST_DELAY)
            cls._GLOBAL_DOMAIN_DELAYS[domain] = min(
                max(current_delay, REQUEST_DELAY) * ADAPTIVE_BACKOFF_MULTIPLIER,
                ADAPTIVE_BACKOFF_MAX_DELAY,
            )
            if failures >= max(1, HOST_CIRCUIT_FAILURES_THRESHOLD):
                cls._GLOBAL_DOMAIN_OPEN_UNTIL[domain] = time.time() + max(1, HOST_CIRCUIT_PAUSE_SECONDS)
                cls._GLOBAL_DOMAIN_FAILURES[domain] = 0

    @classmethod
    def _record_domain_success(cls, url: str) -> None:
        domain = urlparse(url).netloc.lower() if url else "default"
        with cls._LOCK_CREATION_LOCK:
            cls._GLOBAL_DOMAIN_FAILURES.pop(domain, None)
            cls._GLOBAL_DOMAIN_OPEN_UNTIL.pop(domain, None)
            current_delay = cls._GLOBAL_DOMAIN_DELAYS.get(domain)
            if current_delay is not None:
                recovered_delay = max(REQUEST_DELAY, current_delay / max(1.0, ADAPTIVE_BACKOFF_MULTIPLIER))
                if recovered_delay <= REQUEST_DELAY:
                    cls._GLOBAL_DOMAIN_DELAYS.pop(domain, None)
                else:
                    cls._GLOBAL_DOMAIN_DELAYS[domain] = recovered_delay

    @staticmethod
    def _is_transient_network_error(error: Exception) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in (
            "server disconnected", "connection reset", "connection aborted",
            "connection refused", "timed out", "timeout", "temporarily unavailable",
            # Errores de TLS/DNS a nivel de host: no tiene sentido gastar el
            # presupuesto de cada URL si el origen completo está inutilizable.
            "sslcertverificationerror", "certificate verify failed",
            "hostname mismatch", "max retries exceeded",
        ))

    @staticmethod
    def _is_permanent_http_error(error: Exception) -> bool:
        """Indica respuestas 4xx o fallos permanentes de DNS/URL que no deben reintentarse."""
        text = str(error or "").lower()
        if any(m in text for m in ("getaddrinfo", "nameresolution", "invalidurl", "no such host", "failed to resolve", "name or service not known")):
            return True
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code is None:
            match = re.search(r"\b([45]\d{2})\b", text)
            status_code = int(match.group(1)) if match else 0
        return 400 <= int(status_code or 0) < 500 and int(status_code) not in {408, 429}

    def _handle_connection_failure(self, error_details: str, url: str = "") -> bool:
        """
        Registra fallos de red de forma aislada por host.

        La versión anterior acumulaba fallos de todos los hosts en un único
        contador de universidad y podía pausar o descartar una universidad
        completa por un dominio ajeno. El circuito de host ya aplica el
        enfriamiento real en ``_record_domain_failure``; este contador solo
        aporta observabilidad y nunca interrumpe otros dominios.

        Cuando se invoca sin URL se mantiene el comportamiento del contador
        legado para no romper integraciones externas antiguas; el flujo HTTP
        interno siempre proporciona la URL.
        """
        err_str = str(error_details)
        if any(marker in err_str for marker in ["404", "NameResolutionError", "getaddrinfo failed", "ConnectionRefusedError", "InvalidURL"]):
            logger.debug(f"[ADVERTENCIA] Enlace no disponible o no resuelto: {error_details}")
            return False

        if url:
            domain = urlparse(url).netloc.lower() or "default"
            failures = self._connection_failures_by_domain.get(domain, 0) + 1
            self._connection_failures_by_domain[domain] = failures
            logger.debug(
                "[ADVERTENCIA] Fallo de conexión en '%s' #%s/%s: %s",
                domain, failures, CIRCUIT_BREAKER_FAILURES_THRESHOLD, error_details,
            )
            if failures >= CIRCUIT_BREAKER_FAILURES_THRESHOLD:
                self._connection_pause_counts_by_domain[domain] = (
                    self._connection_pause_counts_by_domain.get(domain, 0) + 1
                )
                logger.debug(
                    "[RESILIENCIA] Se aísla temporalmente el host '%s'; "
                    "los demás dominios de la universidad continúan.", domain,
                )
                self._connection_failures_by_domain[domain] = 0
            return False

        self.consecutive_failures += 1
        logger.debug(f"[ADVERTENCIA] Fallo de conexión #{self.consecutive_failures}/{CIRCUIT_BREAKER_FAILURES_THRESHOLD}: {error_details}")
        
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
            if self.respect_robots:
                allowed, _ = self.robots_policy.check(url)
                if not allowed:
                    reason = self.robots_policy.explain(url)
                    raise RobotsDeniedException(url, reason, context="inicializar RUCT")
            self._apply_delay("https://www.educacion.gob.es")
            if self.httpx_client is not None:
                try:
                    if "listauniversidades" in url and "export=1" in url:
                        r1 = self.httpx_client.get("https://www.educacion.gob.es/ruct/listauniversidades.action?actual=universidades")
                        r1.close()
                        r2 = self.httpx_client.get("https://www.educacion.gob.es/ruct/listauniversidades?actual=universidades&cccaa=&tipo_univ=&codigoUniversidad=&consulta=1")
                        r2.close()
                    elif "listaestudiosuniversidad" in url and "export=1" in url:
                        m = re.search(r"codigoUniversidad=([^&]+)", url)
                        if m:
                            u_code = m.group(1)
                            r = self.httpx_client.get(f"https://www.educacion.gob.es/ruct/listaestudiosuniversidad?actual=universidades&codigoUniversidad={u_code}")
                            r.close()
                except Exception as error:
                    logger.debug("No se pudo preparar una sesión auxiliar RUCT: %s", error, exc_info=True)
            else:
                if "listauniversidades" in url and "export=1" in url:
                    r1 = self.session.get("https://www.educacion.gob.es/ruct/listauniversidades.action?actual=universidades", timeout=self.timeout)
                    r1.close()
                    r2 = self.session.get("https://www.educacion.gob.es/ruct/listauniversidades?actual=universidades&cccaa=&tipo_univ=&codigoUniversidad=&consulta=1", timeout=self.timeout)
                    r2.close()
                elif "listaestudiosuniversidad" in url and "export=1" in url:
                    m = re.search(r"codigoUniversidad=([^&]+)", url)
                    if m:
                        u_code = m.group(1)
                        r = self.session.get(f"https://www.educacion.gob.es/ruct/listaestudiosuniversidad?actual=universidades&codigoUniversidad={u_code}", timeout=self.timeout)
                        r.close()
        except Exception as e:
            print(f" [AVISO] Inicialización de sesión RUCT: {e}")

    def _request_with_retry(
        self,
        url: str,
        stream: bool = False,
        robots_prechecked: bool = False,
    ) -> requests.Response:
        """
        Executes an HTTP GET request with connection resilience, Retry-After header parsing,
        automatic HTTP->HTTPS fallback, exponential backoff and Circuit Breaker error management.
        """
        url = self._normalize_url(url)
        if not is_valid_http_url(url):
            raise requests.exceptions.InvalidURL(f"URL HTTP(S) no válida: {url!r}")
        if "export=1" in url and ("listauniversidades" in url or "listaestudiosuniversidad" in url):
            self._prepare_ruct_session(url)

        max_retries = max(1, int(self.max_retries))
        attempt = 0
        urls_to_try = []
        for candidate_url in self._request_url_variants(url):
            urls_to_try.append(candidate_url)
            if candidate_url.startswith("http://"):
                urls_to_try.append("https://" + candidate_url[7:])

        while attempt < max_retries:
            attempt += 1
            if self.degree_budget_exceeded():
                raise DegreeTimeoutException(
                    f"Titulación '{self.current_degree_code}' excede el presupuesto "
                    f"acumulado de {WEB_DEGREE_TIMEOUT_SECONDS:.1f}s"
                )
            self._apply_delay(url)
            if self.ledger is not None:
                try:
                    self.ledger.record_attempt(url, phase=self.phase, university_code=self.current_univ_code, degree_code=self.current_degree_code)
                except Exception as error:
                    logger.warning("No se pudo registrar el intento de descarga en el ledger: %s", error, exc_info=True)
            t0 = time.perf_counter()
            last_error = None
            had_429 = False
            for target_url in urls_to_try:
                response = None
                try:
                    self._check_domain_circuit(target_url)
                    memoized = self._memoized_response(target_url)
                    if memoized is not None:
                        if self.ledger is not None:
                            self.ledger.mark_cached(target_url)
                        if self.metrics_tracker is not None:
                            record_memo_hit = getattr(self.metrics_tracker, "record_request_memo_hit", None)
                            if callable(record_memo_hit):
                                record_memo_hit()
                            else:
                                # Compatibilidad con trackers externos antiguos.
                                self.metrics_tracker.record_cache_hit()
                        return memoized
                    request_headers = {}
                    if self.ledger is not None and not target_url.rstrip('/').lower().endswith('/robots.txt'):
                        try:
                            meta = self.ledger.validators(target_url)
                            if (
                                meta.get("cache_path")
                                and os.path.isfile(meta["cache_path"])
                                and self._http_cache_is_fresh(meta.get("cache_updated_at"))
                            ):
                                if meta.get("etag"):
                                    request_headers["If-None-Match"] = meta["etag"]
                                if meta.get("last_modified"):
                                    request_headers["If-Modified-Since"] = meta["last_modified"]
                        except Exception as error:
                            logger.debug("No se pudo leer metadata de caché para %s: %s", target_url, error, exc_info=True)
                    if (
                        self.respect_robots
                        and not robots_prechecked
                        and not target_url.rstrip('/').lower().endswith('/robots.txt')
                    ):
                        allowed, crawl_delay = self.robots_policy.check(target_url)
                        if self.ledger is not None:
                            try:
                                self.ledger.mark_robots(
                                    target_url,
                                    allowed,
                                    reason=self.robots_policy.explain(target_url) if not allowed else None,
                                )
                            except Exception as error:
                                logger.debug("No se pudo registrar la decisión de robots para %s: %s", target_url, error, exc_info=True)
                        if not allowed:
                            reason = self.robots_policy.explain(target_url)
                            raise RobotsDeniedException(target_url, reason)
                        if crawl_delay is not None:
                            with self._LOCK_CREATION_LOCK:
                                domain = urlparse(target_url).netloc.lower()
                                self._GLOBAL_DOMAIN_DELAYS[domain] = max(
                                    self._GLOBAL_DOMAIN_DELAYS.get(domain, self.delay),
                                    min(max(0.0, crawl_delay), 3600.0),
                                )
                    if self.httpx_client is not None:
                        req = self.httpx_client.build_request("GET", target_url, headers=request_headers or None)
                        httpx_resp = self.httpx_client.send(req, stream=stream)
                        response = HTTP2ResponseWrapper(
                            httpx_resp,
                            target_url,
                            max_duration=HTTP_RESPONSE_MAX_DURATION_SECONDS,
                        )
                    else:
                        verify_ssl = True
                        response = self.session.get(target_url, stream=stream, timeout=self.timeout, verify=verify_ssl, headers=request_headers or None)
                    final_url = response.url or target_url
                    if final_url and target_url and not is_same_or_subdomain(final_url, target_url):
                        response.close()
                        req_host = urlsplit(target_url).netloc.lower()
                        fin_host = urlsplit(final_url).netloc.lower()
                        raise PermissionError(f"redirect externo no permitido: {req_host} -> {fin_host}")
                    if response.status_code == 304:
                        cached_response = self._load_cached_response(target_url)
                        response.close()
                        if cached_response is None:
                            raise requests.HTTPError(f"HTTP 304 sin cuerpo cacheado para '{target_url}'")
                        response = cached_response
                        if self.ledger is not None:
                            try:
                                self.ledger.mark_cached(target_url)
                            except Exception as error:
                                logger.debug("No se pudo registrar una respuesta cacheada para %s: %s", target_url, error, exc_info=True)
                    # Protección contra descargas masivas no deseadas
                    if stream:
                        content_length = response.headers.get('Content-Length')
                        if content_length:
                            try:
                                size = int(content_length)
                            except (TypeError, ValueError):
                                size = None
                            if size is not None and size > MAX_RESPONSE_SIZE_BYTES:
                                response.close()
                                raise ValueError(f"Descarga demasiado grande: {size} bytes > {MAX_RESPONSE_SIZE_BYTES}")
                    if response.status_code == 429:
                        if stream:
                            try:
                                response.close()
                            except Exception as error:
                                logger.debug("No se pudo cerrar la respuesta HTTP 429: %s", error, exc_info=True)
                        domain = urlparse(target_url).netloc.lower() if target_url else "default"
                        with self._LOCK_CREATION_LOCK:
                            curr_delay = self._GLOBAL_DOMAIN_DELAYS.get(domain, self.delay)
                            new_delay = min(curr_delay * ADAPTIVE_BACKOFF_MULTIPLIER, ADAPTIVE_BACKOFF_MAX_DELAY)
                            self._GLOBAL_DOMAIN_DELAYS[domain] = new_delay
                        retry_after_val = response.headers.get("Retry-After")
                        retry_secs = int(retry_after_val) if (retry_after_val and retry_after_val.isdigit()) else HTTP_429_DEFAULT_RETRY_AFTER
                        retry_secs = min(max(0, retry_secs), max(0, HTTP_429_MAX_RETRY_AFTER))
                        logger.debug("[AVISO CORTESIA RED] HTTP 429 detectado en '%s'. Retardo adaptativo para '%s' ajustado a %.2fs. Pausando %ss...", target_url, domain, new_delay, retry_secs)
                        time.sleep(retry_secs)
                        last_error = requests.HTTPError(f"HTTP 429 Too Many Requests para '{target_url}'")
                        had_429 = True
                        break
                    response.raise_for_status()
                    if self.ledger is not None and getattr(response, "_unihub_cached", False) is not True:
                        try:
                            self.ledger.record_response(target_url, response=response, status="success")
                        except Exception as error:
                            logger.debug("No se pudo registrar una respuesta exitosa en el ledger: %s", error, exc_info=True)
                    self._record_domain_success(target_url)
                    elapsed = time.perf_counter() - t0
                    if self.metrics_tracker:
                        self.metrics_tracker.record_io_time(elapsed)
                    self._handle_connection_success(target_url)
                    return response
                except PermissionError:
                    if 'response' in locals() and response is not None:
                        try:
                            response.close()
                        except Exception as error:
                            logger.debug("No se pudo cerrar la respuesta tras redirección no permitida: %s", error, exc_info=True)
                    raise
                except SkipUniversityException:
                    if 'response' in locals() and response is not None:
                        try:
                            response.close()
                        except Exception as error:
                            logger.debug("No se pudo cerrar la respuesta tras circuito abierto: %s", error, exc_info=True)
                    raise
                except HostCircuitOpenException:
                    # El circuito ya ha decidido que el host está en
                    # enfriamiento. No convertir ese estado controlado en
                    # otro fallo, reintento o incremento de contadores.
                    if 'response' in locals() and response is not None:
                        try:
                            response.close()
                        except Exception as error:
                            logger.debug("No se pudo cerrar la respuesta tras circuito abierto: %s", error, exc_info=True)
                    raise
                except Exception as e:
                    if 'response' in locals() and response is not None:
                        try:
                            response.close()
                        except Exception as error:
                            logger.debug("No se pudo cerrar la respuesta tras error de red: %s", error, exc_info=True)
                    last_error = e
                    if self._is_transient_network_error(e):
                        self._record_domain_failure(target_url)
                    if self.ledger is not None:
                        try:
                            self.ledger.record_response(target_url, response=locals().get("response"), status="failed", error=str(e))
                        except Exception as ledger_error:
                            logger.warning("No se pudo registrar el fallo de descarga en el ledger: %s", ledger_error, exc_info=True)
                    logger.debug("[Proceso Red] -> Falló conexión a '%s': %s", target_url, e)
                    continue

            if last_error is None:
                last_error = requests.RequestException(f"Error de conexión no especificado para '{url}'")

            # Check if this error is an unresolvable URL / 404
            err_str = str(last_error)
            if self._is_permanent_http_error(last_error) or any(marker in err_str for marker in ["404", "NameResolutionError", "getaddrinfo failed", "ConnectionRefusedError", "InvalidURL"]):
                raise last_error

            # Handle connection failure for circuit breaker monitoring
            self._handle_connection_failure(str(last_error), target_url if target_url else url)

            if attempt < max_retries:
                if not had_429:
                    backoff_wait = (2 ** (attempt - 1)) * 0.5
                    time.sleep(backoff_wait)
                logger.debug("[RESILIENCIA] Reintentando petición (%s/%s) para '%s'...", attempt + 1, max_retries, url)

        if last_error is None:
            last_error = requests.RequestException(f"Error tras agotar {max_retries} intentos para '{url}'")
        raise last_error

    def fetch_content(self, url: str, max_size_bytes: int = MAX_RESPONSE_SIZE_BYTES) -> bytes:
        """Fetches raw content from a URL with connection resilience, Retry-After header parsing, and max size cap."""
        with self._request_with_retry(url, stream=True) as response:
            cl = response.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > max_size_bytes:
                raise ValueError(f"El tamaño del archivo ({cl} bytes) excede el límite permitido de {max_size_bytes} bytes")
            chunks = []
            total_bytes = 0
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    total_bytes += len(chunk)
                    if total_bytes > max_size_bytes:
                        raise ValueError(f"El flujo descargado supera el límite de seguridad de {max_size_bytes} bytes")
                    chunks.append(chunk)
            content = b"".join(chunks)
            self.store_response_content(self._normalize_url(url), response, content)
            return content

    def fetch_text(self, url: str, encoding="utf-8", max_size_bytes: int = MAX_TEXT_RESPONSE_SIZE_BYTES) -> str:
        """Fetches decoded string content from a URL with charset detection."""
        with self._request_with_retry(url, stream=True) as response:
            header_charset = None
            get_charset = getattr(response.headers, "get_content_charset", None)
            if callable(get_charset):
                try:
                    header_charset = get_charset()
                except Exception:
                    header_charset = None
            charset = response.encoding or header_charset or encoding
            cl = response.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > max_size_bytes:
                raise ValueError(f"El texto remoto supera el límite de seguridad de {max_size_bytes} bytes")
            chunks = []
            total = 0
            deadline = time.monotonic() + max(0.0, float(HTTP_RESPONSE_MAX_DURATION_SECONDS))
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if HTTP_RESPONSE_MAX_DURATION_SECONDS > 0 and time.monotonic() > deadline:
                    raise requests.Timeout(
                        f"Respuesta HTTP excede el límite acumulado de "
                        f"{HTTP_RESPONSE_MAX_DURATION_SECONDS:.1f}s"
                    )
                if chunk:
                    total += len(chunk)
                    if total > max_size_bytes:
                        raise ValueError(f"El texto remoto supera el límite de seguridad de {max_size_bytes} bytes")
                    chunks.append(chunk)
            content = b"".join(chunks)
            self.store_response_content(self._normalize_url(url), response, content)
            try:
                return content.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                return content.decode(encoding, errors="replace")

    def download_file(self, url: str, destination_path: str, is_pdf: bool = False, max_size_bytes: int = 50 * 1024 * 1024):
        """Downloads a remote file directly to disk with connection resilience, size limit defense, and HTTPS fallback."""
        try:
            with self._request_with_retry(url, stream=True) as response:
                cl = response.headers.get("Content-Length")
                if cl and cl.isdigit() and int(cl) > max_size_bytes:
                    raise ValueError(f"El tamaño del archivo ({cl} bytes) excede el límite permitido de {max_size_bytes} bytes")
                first_chunk = True
                total_bytes = 0
                cache_chunks = []
                cache_enabled = getattr(response, "_unihub_cached", False) is not True and max_size_bytes <= MAX_RESPONSE_SIZE_BYTES
                with open(destination_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            total_bytes += len(chunk)
                            if total_bytes > max_size_bytes:
                                raise ValueError(f"El archivo descargado supera el límite de seguridad de {max_size_bytes} bytes")
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
                                    raise ValueError("Respuesta RUCT retornó página HTML de sesión en lugar de binario XLS")
                            f.write(chunk)
                            if cache_enabled:
                                cache_chunks.append(chunk)
                if cache_enabled and cache_chunks:
                    self.store_response_content(self._normalize_url(url), response, b"".join(cache_chunks))
        except Exception:
            if os.path.exists(destination_path):
                try:
                    os.remove(destination_path)
                except OSError as cleanup_error:
                    logger.warning("No se pudo eliminar la descarga parcial %s: %s", destination_path, cleanup_error)
            raise

    def close(self):
        """Closes the underlying requests session and releases open socket pool resources."""
        try:
            self.session.close()
        except Exception as error:
            logger.debug("No se pudo cerrar la sesión requests: %s", error, exc_info=True)
        if self.httpx_client is not None:
            try:
                self.httpx_client.close()
            except Exception as error:
                logger.debug("No se pudo cerrar el cliente HTTP/2: %s", error, exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
