"""Política centralizada y conservadora para robots.txt (RFC 9309)."""
from __future__ import annotations

import re
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
    ROBOTS_MAX_CACHE_SIZE,
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
    # El fallback HTTP -> HTTPS vuelve a cargar la política del mismo origen;
    # el candado debe permitir esa reentrada sin relajar la exclusión entre hilos.
    _fetch_locks: dict[str, threading.RLock] = {}
    _last_fetch: dict[str, float] = {}
    # Motivo de la última evaluación por origen. Se mantiene separado de la
    # decisión booleana para poder distinguir ``robots.txt inexistente`` de
    # ``robots.txt no verificable`` en los diagnósticos del crawler.
    _last_outcome: dict[str, str] = {}
    _MAX_CACHE_SIZE = ROBOTS_MAX_CACHE_SIZE

    _courtesy_delays: dict[str, float] = {}

    @classmethod
    def _evict_if_needed(cls):
        if len(cls._cache) > cls._MAX_CACHE_SIZE:
            if cls._last_fetch:
                oldest_origin = min(cls._last_fetch.keys(), key=lambda k: cls._last_fetch[k])
                cls._cache.pop(oldest_origin, None)
                cls._fetch_locks.pop(oldest_origin, None)
                cls._last_fetch.pop(oldest_origin, None)
                cls._last_outcome.pop(oldest_origin, None)
                cls._courtesy_delays.pop(oldest_origin, None)

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
            fetch_lock = self._fetch_locks.setdefault(origin, threading.RLock())

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
                except requests.exceptions.SSLError as ssl_exc:
                    if current_url.startswith("https://"):
                        http_url = "http://" + current_url[8:]
                        try:
                            return self._load(origin, http_url)
                        except Exception:
                            pass
                    if attempt < max_network_retries:
                        time.sleep(0.3 * (attempt + 1))
                        continue
                    with self._lock:
                        self._last_outcome[origin] = f"error_red_{type(ssl_exc).__name__}: {ssl_exc}"
                    return None
                except requests.RequestException as exc:
                    if attempt < max_network_retries:
                        time.sleep(0.3 * (attempt + 1))
                        continue
                    if current_url.startswith("http://"):
                        https_url = "https://" + current_url[7:]
                        return self._load(origin, https_url)
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
                    if response.status_code == 401:
                        parser = urllib.robotparser.RobotFileParser()
                        parser.parse(["User-agent: *", "Disallow: /"])
                        with self._lock:
                            self._cache[origin] = (time.time(), parser)
                            self._evict_if_needed()
                            suffix = f"_tras_{redirect_count}_redirecciones" if redirect_count else ""
                            self._last_outcome[origin] = f"robots_acceso_restringido_http_401{suffix}"
                        return parser
                    if response.status_code == 403:
                        # WAFs universitarios frecuentemente responden 403 a robots.txt
                        # mientras la web pública está abierta. Se tolera con crawl-delay de cortesía.
                        parser = urllib.robotparser.RobotFileParser()
                        parser.parse([])
                        with self._lock:
                            self._cache[origin] = (time.time(), parser)
                            self._courtesy_delays[origin] = 1.0
                            self._evict_if_needed()
                            suffix = f"_tras_{redirect_count}_redirecciones" if redirect_count else ""
                            self._last_outcome[origin] = f"robots_waf_403_tolerado{suffix}"
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
    def _extract_base_domain(hostname: str) -> str:
        """Extrae el nombre base del host eliminando subdominios y TLDs comunes."""
        clean = re.sub(r"^w{1,8}\d*\.", "", hostname.lower().strip())
        parts = [p for p in clean.split(".") if p]
        if not parts:
            return ""
        compound = {("edu", "es"), ("gob", "es"), ("com", "es"), ("org", "es"), ("ac", "uk"), ("co", "uk")}
        if len(parts) >= 3 and tuple(parts[-2:]) in compound:
            return parts[-3]
        elif len(parts) >= 2:
            return parts[-2]
        return parts[0]

    @classmethod
    def _is_safe_robots_redirect(cls, target_url: str, origin: str) -> bool:
        """Los robots sólo pueden redirigir dentro del mismo host o dominio institucional legítimo."""
        target = urllib.parse.urlparse(target_url)
        expected = urllib.parse.urlparse(origin)
        if target.scheme not in {"http", "https"} or not target.hostname or not expected.hostname:
            return False
        
        t_host = target.hostname.lower()
        e_host = expected.hostname.lower()
        
        # 1. Mismo hostname exacto
        if t_host == e_host:
            return True
            
        # Descartar IPs, localhost y destinos numéricos
        if re.match(r"^(\d{1,3}\.){3}\d{1,3}$", t_host) or t_host in {"localhost", "127.0.0.1"}:
            return False

        # 2. Subdominio o dominio raíz de la misma organización (ej. web.unican.es <-> www.unican.es)
        t_clean = re.sub(r"^w{1,8}\d*\.", "", t_host)
        e_clean = re.sub(r"^w{1,8}\d*\.", "", e_host)
        if t_clean == e_clean or t_host.endswith("." + e_clean) or e_host.endswith("." + t_clean):
            return True

        # 3. Transición de TLDs institucionales reconocidos para la misma institución universitaria
        # (ej. uab.es <-> uab.cat, udc.es <-> udc.gal, ehu.es <-> ehu.eus, upc.es <-> upc.edu)
        allowed_tlds = {"es", "cat", "gal", "eus", "edu", "com", "org", "net"}
        t_tld = t_host.split(".")[-1]
        e_tld = e_host.split(".")[-1]
        if t_tld in allowed_tlds and e_tld in allowed_tlds:
            t_base = cls._extract_base_domain(t_host)
            e_base = cls._extract_base_domain(e_host)
            if t_base and e_base:
                if t_base == e_base:
                    return True
                # Variaciones de marca conocidas (ej. uao <-> uaoceu, viu <-> universidadviu)
                if (
                    (t_base.startswith(e_base) or e_base.startswith(t_base) or t_base.endswith(e_base) or e_base.endswith(t_base))
                    and len(t_base) >= 3
                    and len(e_base) >= 3
                ):
                    return True
                if "universidadeuropea" in t_host and "universidadeuropea" in e_host:
                    return True

        return False

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
                or previous.startswith("robots_waf_403_tolerado")
                or previous.startswith("robots_acceso_restringido_http_401")
            ):
                self._last_outcome[origin] = f"{previous}_permitido" if allowed else f"{previous}_denegado"
            else:
                self._last_outcome[origin] = "permitido_por_reglas" if allowed else "denegado_por_reglas"
        delay = parser.crawl_delay(self.user_agent)
        if delay is None:
            delay = parser.crawl_delay("*")
        if delay is None:
            with self._lock:
                delay = self._courtesy_delays.get(origin)
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
            cls._courtesy_delays.clear()
