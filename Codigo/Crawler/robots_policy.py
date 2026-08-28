"""Política centralizada y conservadora para robots.txt (RFC 9309)."""
from __future__ import annotations

import threading
import time
import logging
import urllib.parse
import urllib.robotparser

import requests

from config import (
    ROBOTS_CHECK_TIMEOUT,
    ROBOTS_CACHE_TTL_SECONDS,
    ROBOTS_CONFIRMED_NO_FILE_HOSTS,
    ROBOTS_FAIL_CLOSED,
    USER_AGENT,
    REQUEST_DELAY,
)

logger = logging.getLogger("robots_policy")


class RobotsPolicy:
    """Carga robots una vez por origen y evalúa cada ruta individualmente.

    Los errores se consideran denegación cuando ``ROBOTS_FAIL_CLOSED`` está
    activo. Esto evita que un timeout o un 5xx se convierta accidentalmente en
    permiso de rastreo.
    """

    _lock = threading.RLock()
    _cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}
    _fetch_locks: dict[str, threading.Lock] = {}
    _last_fetch: dict[str, float] = {}
    # Motivo de la última evaluación por origen. Se mantiene separado de la
    # decisión booleana para poder distinguir ``robots.txt inexistente`` de
    # ``robots.txt no verificable`` en los diagnósticos del crawler.
    _last_outcome: dict[str, str] = {}
    _MAX_CACHE_SIZE = 512

    @classmethod
    def _evict_if_needed(cls):
        if len(cls._cache) > cls._MAX_CACHE_SIZE:
            if cls._last_fetch:
                oldest_origin = min(cls._last_fetch.keys(), key=lambda k: cls._last_fetch[k])
                cls._cache.pop(oldest_origin, None)
                cls._fetch_locks.pop(oldest_origin, None)
                cls._last_fetch.pop(oldest_origin, None)
                cls._last_outcome.pop(oldest_origin, None)

    def __init__(self, user_agent: str = USER_AGENT, timeout: float = ROBOTS_CHECK_TIMEOUT):
        self.user_agent = user_agent
        self.timeout = timeout

    @staticmethod
    def _origin(url: str) -> tuple[str, str] | None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        origin = f"{parsed.scheme}://{parsed.netloc.lower()}"
        return origin, f"{origin}/robots.txt"

    def _load(self, origin: str, robots_url: str) -> urllib.robotparser.RobotFileParser | None:
        now = time.time()
        with self._lock:
            cached = self._cache.get(origin)
            if cached and now - cached[0] < ROBOTS_CACHE_TTL_SECONDS:
                with self._lock:
                    self._last_outcome[origin] = "cacheado"
                return cached[1]
            fetch_lock = self._fetch_locks.setdefault(origin, threading.Lock())

        with fetch_lock:
            with self._lock:
                cached = self._cache.get(origin)
                if cached and now - cached[0] < ROBOTS_CACHE_TTL_SECONDS:
                    with self._lock:
                        self._last_outcome[origin] = "cacheado"
                    return cached[1]
            with self._lock:
                elapsed = time.time() - self._last_fetch.get(origin, 0.0)
            if elapsed < REQUEST_DELAY:
                time.sleep(REQUEST_DELAY - elapsed)
            with self._lock:
                self._last_fetch[origin] = time.time()
            current_url = robots_url
            redirect_count = 0
            redirect_codes = {301, 302, 303, 307, 308}
            response = None
            max_network_retries = 2

            for attempt in range(max_network_retries + 1):
                try:
                    while True:
                        response = requests.get(
                            current_url,
                            headers={
                                "User-Agent": self.user_agent,
                                "Accept": "text/plain",
                                "Connection": "close",
                                "Accept-Encoding": "identity",
                            },
                            timeout=self.timeout,
                            allow_redirects=False,
                        )
                        if response.status_code not in redirect_codes:
                            break
                        location = response.headers.get("Location")
                        response.close()
                        if not location or redirect_count >= 5:
                            with self._lock:
                                self._last_outcome[origin] = "robots_redireccion_excesiva_o_invalida"
                            return None
                        redirected_url = urllib.parse.urljoin(current_url, location)
                        if not self._is_safe_robots_redirect(redirected_url, origin):
                            with self._lock:
                                self._last_outcome[origin] = "robots_redireccion_fuera_del_origen"
                            return None
                        current_url = redirected_url
                        redirect_count += 1
                    break
                except requests.RequestException as exc:
                    if attempt < max_network_retries:
                        time.sleep(0.3 * (attempt + 1))
                        continue
                    if current_url.startswith("http://"):
                        https_url = "https://" + current_url[7:]
                        try:
                            response = requests.get(
                                https_url,
                                headers={
                                    "User-Agent": self.user_agent,
                                    "Accept": "text/plain",
                                    "Connection": "close",
                                    "Accept-Encoding": "identity",
                                },
                                timeout=self.timeout,
                                allow_redirects=True,
                            )
                        except requests.RequestException as error:
                            logger.debug("No se pudo consultar robots.txt para %s: %s", robots_url, error, exc_info=True)
                            with self._lock:
                                self._last_outcome[origin] = f"error_red_{type(exc).__name__}: {exc}"
                            return None
                    else:
                        with self._lock:
                            self._last_outcome[origin] = f"error_red_{type(exc).__name__}: {exc}"
                        return None

            try:
                if response is None:
                    return None
                if response.status_code != 200:
                    if response.status_code in {404, 410}:
                        parser = urllib.robotparser.RobotFileParser()
                        parser.parse([])
                        with self._lock:
                            self._cache[origin] = (time.time(), parser)
                            self._evict_if_needed()
                            suffix = f"_tras_{redirect_count}_redirecciones" if redirect_count else ""
                            self._last_outcome[origin] = f"robots_inexistente_http_{response.status_code}{suffix}"
                        return parser
                    if response.status_code in {401, 403}:
                        parser = urllib.robotparser.RobotFileParser()
                        parser.parse(["User-agent: *", "Disallow: /"])
                        with self._lock:
                            self._cache[origin] = (time.time(), parser)
                            self._evict_if_needed()
                            suffix = f"_tras_{redirect_count}_redirecciones" if redirect_count else ""
                            self._last_outcome[origin] = f"robots_acceso_restringido_http_{response.status_code}{suffix}"
                        return parser
                    with self._lock:
                        suffix = f"_tras_{redirect_count}_redirecciones" if redirect_count else ""
                        self._last_outcome[origin] = f"robots_http_{response.status_code}{suffix}"
                    return None
                if len(response.content) > 1024 * 1024:
                    with self._lock:
                        self._last_outcome[origin] = "robots_excesivo"
                    return None
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                with self._lock:
                    self._cache[origin] = (time.time(), parser)
                    self._evict_if_needed()
                    suffix = f"_tras_{redirect_count}_redirecciones" if redirect_count else ""
                    self._last_outcome[origin] = f"robots_ok_http_200{suffix}"
                return parser
            finally:
                if response is not None:
                    response.close()

    @staticmethod
    def _is_safe_robots_redirect(target_url: str, origin: str) -> bool:
        """Los robots sólo pueden redirigir dentro de su mismo host institucional."""
        target = urllib.parse.urlparse(target_url)
        expected = urllib.parse.urlparse(origin)
        return (
            target.scheme in {"http", "https"}
            and bool(target.hostname)
            and target.hostname.lower() == expected.hostname.lower()
        )

    def check(self, url: str) -> tuple[bool, float | None]:
        resolved = self._origin(url)
        if resolved is None:
            return False, None
        origin, robots_url = resolved
        parser = self._load(origin, robots_url)
        if parser is None:
            host = urllib.parse.urlparse(origin).netloc.lower()
            with self._lock:
                outcome = self._last_outcome.get(origin, "")
            # Excepción explícita y estrictamente acotada para un origen cuya
            # ausencia de robots.txt ha sido confirmada por el responsable del
            # proyecto. Solo cubre un cierre/error de red; un HTTP 401/403/5xx
            # o reglas válidas continúan bloqueando el rastreo.
            if host in ROBOTS_CONFIRMED_NO_FILE_HOSTS and outcome.startswith("error_red_"):
                parser = urllib.robotparser.RobotFileParser()
                parser.parse([])
                with self._lock:
                    self._cache[origin] = (time.time(), parser)
                    self._evict_if_needed()
                    self._last_outcome[origin] = "robots_confirmado_ausente_por_configuracion_tras_error_red"
            else:
                return (False if ROBOTS_FAIL_CLOSED else True), None
        allowed = parser.can_fetch(self.user_agent, url)
        with self._lock:
            previous = self._last_outcome.get(origin, "robots_verificado")
            if (
                previous.startswith("robots_inexistente_http_404")
                or previous.startswith("robots_inexistente_http_410")
                or previous.startswith("robots_confirmado_ausente_por_configuracion")
            ):
                self._last_outcome[origin] = f"{previous}_permitido"
            else:
                self._last_outcome[origin] = "permitido_por_reglas" if allowed else "denegado_por_reglas"
        delay = parser.crawl_delay(self.user_agent)
        if delay is None:
            delay = parser.crawl_delay("*")
        try:
            delay_value = float(delay) if delay is not None else None
        except (TypeError, ValueError):
            delay_value = None
        return allowed, delay_value

    def explain(self, url: str) -> str:
        """Devuelve el motivo técnico de la última decisión para ``url``."""
        resolved = self._origin(url)
        if resolved is None:
            return "URL_origen_invalida"
        origin, _ = resolved
        with self._lock:
            return self._last_outcome.get(origin, "sin_verificar")

    @classmethod
    def clear_cache(cls):
        with cls._lock:
            cls._cache.clear()
            cls._fetch_locks.clear()
            cls._last_fetch.clear()
            cls._last_outcome.clear()
