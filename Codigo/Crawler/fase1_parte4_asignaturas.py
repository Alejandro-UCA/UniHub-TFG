import os
import sys
import re
import io
import json
import time
import sqlite3
import hashlib
import logging
import threading
import unicodedata
import contextlib
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from bs4 import BeautifulSoup
import pypdf

from config import (
    PLANES_DIR,
    UNIVERSIDADES_JSON,
    USER_AGENT,
    REQUEST_DELAY,
    WEB_CRAWLER_WORKERS,
    SQLITE_CONNECT_TIMEOUT,
    SUBJECT_GUIDE_CACHE_DB,
    SUBJECT_GUIDE_CACHE_TTL_SECONDS,
    NEGATIVE_CACHE_TTL_SECONDS,
    SUBJECT_GUIDE_CACHE_LIMIT,
    MAX_RESPONSE_SIZE_BYTES,
    DOWNLOAD_CHUNK_SIZE,
    MAX_SUBJECT_GUIDE_URL_CANDIDATES,
    MAX_SUBJECT_GUIDE_NO_CODE_CANDIDATES,
    FULL_REVALIDATION,
    TARGET_UNIVERSITY_CODES,
    SUBJECT_GUIDE_DISCOVERY_MAX_URLS,
    SUBJECT_GUIDE_DISCOVERY_CACHE_TTL_SECONDS,
    SUBJECT_GUIDE_PDF_MAX_BYTES,
    SUBJECT_GUIDE_PDF_MAX_PAGES,
    SUBJECT_GUIDE_PDF_MAX_TEXT_CHARS,
    SUBJECT_GUIDE_PDF_PARSE_TIMEOUT_SECONDS,
    SUBJECT_GUIDE_PDF_OCR_ENABLED,
    SUBJECT_GUIDE_PDF_OCR_MAX_PAGES,
    SUBJECT_GUIDE_PDF_OCR_DPI,
    SUBJECT_GUIDE_PDF_OCR_MIN_TEXT_CHARS,
)
from downloader import (
    RUCTDownloader,
    HostCircuitOpenException,
    SkipUniversityException,
    normalize_url,
    is_valid_http_url,
    is_same_or_subdomain,
)
from checkpoint import atomic_json_dump, load_json_safe
from data_quality import apply_plan_quality
from parsers import sanitize_subject_name, classify_subject_caracter, detect_academic_language
from univ_web_crawler import is_spurious_or_administrative_subject
from phase_common import iter_plan_files
from cancellation import CrawlerCancelled, raise_if_shutdown_requested, is_shutdown_requested
from crawl_ledger import CrawlLedger
from sqlite_recovery import is_sqlite_corruption, quarantine_corrupt_sqlite
from subject_guide_discovery import (
    build_subject_guide_discovery_index,
    derive_subject_guide_urls_from_routes,
    rank_discovered_guide_urls,
)
from subject_guide_quality import annotate_subject_guide_quality

logger = logging.getLogger(__name__)

CACHE_GUIAS_DB = SUBJECT_GUIDE_CACHE_DB
_RESUMABLE_GUIDE_STATES = frozenset({"verificada", "no_encontrada", "respaldo_ultima_fuente"})


class RunNegativeURLRegistry:
    """Negativos exactos compartidos por todos los workers de un run.

    La caché persistente se puede ignorar durante una revalidación total. Este
    registro, en cambio, solo vive en la ejecución actual y evita que dos
    trabajadores soliciten la misma URL después de un 404, un bloqueo de
    robots o un error equivalente. Las claves se normalizan y se les elimina
    el fragmento, que nunca se envía al servidor.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._urls: set[str] = set()
        self._soft404_route_fingerprints: dict[tuple[str, str], set[str]] = {}
        self._blocked_soft404_routes: set[str] = set()
        self._circuit_hosts: set[str] = set()
        self._host_observations: dict[str, dict[str, int]] = {}

    @staticmethod
    def _soft404_route(url: str) -> str:
        normalized = RunNegativeURLRegistry._key(url)
        if not normalized:
            return ""
        parsed = urlparse(normalized)
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) <= 1:
            route_path = "/"
        else:
            # Se elimina solo el último segmento, que en los portales suele
            # ser el identificador o slug de la asignatura. Se conserva el
            # resto para no bloquear de forma global un host heterogéneo.
            route_path = "/" + "/".join(segments[:-1])
        return f"{parsed.scheme}://{parsed.netloc.lower()}{route_path}"

    @staticmethod
    def _key(url: str) -> str:
        normalized = normalize_url(str(url or "").strip())
        if not normalized:
            return ""
        # No eliminamos parámetros: en portales académicos suelen identificar
        # la asignatura o el curso. Solo el fragmento es siempre local.
        return normalized.split("#", 1)[0].rstrip("/") or normalized

    def add(self, url: str) -> bool:
        key = self._key(url)
        if not key:
            return False
        with self._lock:
            already_present = key in self._urls
            self._urls.add(key)
            return not already_present

    def contains(self, url: str) -> bool:
        key = self._key(url)
        if not key:
            return False
        with self._lock:
            return key in self._urls

    def mark_soft404(self, url: str, fingerprint: str, threshold: int = 3) -> bool:
        """Aprende un patrón solo tras respuestas soft-404 repetidas.

        Se exigen tres URLs distintas del mismo patrón y la misma huella de
        contenido. Una sola portada genérica nunca basta para cerrar la ruta.
        Devuelve si el patrón acaba de quedar bloqueado.
        """
        route = self._soft404_route(url)
        fingerprint = str(fingerprint or "").strip()
        if not route or not fingerprint:
            return False
        with self._lock:
            fingerprints = self._soft404_route_fingerprints.setdefault((route, fingerprint), set())
            fingerprints.add(self._key(url))
            if len(fingerprints) >= max(2, int(threshold)):
                was_blocked = route in self._blocked_soft404_routes
                self._blocked_soft404_routes.add(route)
                return not was_blocked
        return False

    def contains_soft404_route(self, url: str) -> bool:
        route = self._soft404_route(url)
        if not route:
            return False
        with self._lock:
            return route in self._blocked_soft404_routes

    @staticmethod
    def _host(url: str) -> str:
        return (urlparse(normalize_url(str(url or ""))).netloc or "").lower()

    def mark_circuit_host(self, url: str) -> None:
        host = self._host(url)
        if host:
            with self._lock:
                self._circuit_hosts.add(host)

    def contains_circuit_host(self, url: str) -> bool:
        host = self._host(url)
        if not host:
            return False
        with self._lock:
            return host in self._circuit_hosts

    def observe_host_result(self, url: str, *, negative: bool = False, positive: bool = False) -> None:
        """Acumula evidencia efímera para el presupuesto adaptativo del host."""
        host = self._host(url)
        if not host:
            return
        with self._lock:
            observation = self._host_observations.setdefault(
                host, {"samples": 0, "negatives": 0, "positives": 0}
            )
            observation["samples"] += 1
            if negative:
                observation["negatives"] += 1
            if positive:
                observation["positives"] += 1

    def contains_unproductive_host(
        self,
        url: str,
        *,
        minimum_samples: int = 16,
        minimum_negative_ratio: float = 0.95,
    ) -> bool:
        """Indica si seguir generando peticiones al host ya no es rentable."""
        host = self._host(url)
        if not host:
            return False
        with self._lock:
            observation = self._host_observations.get(host)
            if not observation or observation["positives"]:
                return False
            samples = observation["samples"]
            return (
                samples >= max(1, int(minimum_samples))
                and observation["negatives"] / samples >= float(minimum_negative_ratio)
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._urls)


def _guide_state_is_recent(timestamp: str) -> bool:
    """Determina si un estado persistido puede reutilizarse al reanudar."""
    if SUBJECT_GUIDE_CACHE_TTL_SECONDS <= 0 or not timestamp:
        return False
    try:
        checked_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if checked_at.tzinfo is not None:
            checked_at = checked_at.astimezone().replace(tzinfo=None)
        age = (datetime.now() - checked_at).total_seconds()
        return 0 <= age <= SUBJECT_GUIDE_CACHE_TTL_SECONDS
    except (TypeError, ValueError, OverflowError):
        return False


def _can_resume_guide_element(element: dict, revalidate_sources: bool) -> bool:
    """Evita repetir trabajo reciente, salvo en revalidación explícita."""
    if revalidate_sources or os.getenv("CRAWLER_RESUME", "1").strip().lower() in {"0", "false", "no"}:
        return False
    state = str(element.get("estado_guia_docente") or "").strip().lower()
    return state in _RESUMABLE_GUIDE_STATES and _guide_state_is_recent(
        element.get("fecha_ultima_comprobacion_guia")
    )


def _load_university_domain_map() -> dict[str, str]:
    """Carga los dominios desde el catálogo RUCT persistido.

    No se mantiene una tabla paralela de códigos RUCT: ese catálogo cambia y
    una asociación antigua puede enviar las heurísticas de guías al dominio de
    otra universidad. Si el catálogo no está disponible, se devuelve un mapa
    vacío y el crawler exige una web explícita en vez de inventar un dominio.
    """
    catalog_path = Path(UNIVERSIDADES_JSON)
    try:
        with catalog_path.open("r", encoding="utf-8") as handle:
            universities = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {}

    result = {}
    for university in universities if isinstance(universities, list) else []:
        if not isinstance(university, dict):
            continue
        code = str(university.get("codigo") or "").strip().zfill(3)
        raw_web = str(university.get("web") or "").strip()
        if not code or not raw_web:
            continue
        parseable_web = raw_web if "://" in raw_web else f"https://{raw_web}"
        hostname = (urlparse(parseable_web).hostname or "").lower().removeprefix("www.")
        if hostname:
            result[code] = hostname
    return result


UNIVERSITY_DOMAIN_BY_CODE = _load_university_domain_map()


class SubjectGuideCache:
    """
    Caché de alto rendimiento L1 (RAM) + L2 (SQLite WAL) para guías docentes.
    Permite búsqueda dual tanto por URL exacta como por clave compuesta canónica (universidad_codigo + codigo_asignatura).
    """
    _local = threading.local()
    _schema_initialized_paths: set = set()

    MAX_L1_ENTRIES = SUBJECT_GUIDE_CACHE_LIMIT

    def __init__(self, db_path: str = CACHE_GUIAS_DB):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._l1_url_cache = {}
        self._l1_comp_cache = {}
        self._l1_url_times = {}
        self._l1_comp_times = {}
        self._negative_urls = set()
        self._negative_url_times = {}
        self._persistent_cache_disabled = False
        self._persistent_cache_error = None
        self.recovered_corrupt_path = None
        self._recovering_persistent_cache = False
        self._init_db()

    def _disable_persistent_cache(self, error: Exception):
        if not self._recovering_persistent_cache and is_sqlite_corruption(error):
            try:
                quarantine_path = quarantine_corrupt_sqlite(self.db_path)
            except OSError as recovery_error:
                quarantine_path = None
                logger.error(
                    "No se pudo poner en cuarentena la caché SQLite corrupta %s: %s",
                    self.db_path,
                    recovery_error,
                )
            if quarantine_path:
                self.recovered_corrupt_path = quarantine_path
                self._schema_initialized_paths.discard(self.db_path)
                self._recovering_persistent_cache = True
                self._persistent_cache_disabled = False
                self._persistent_cache_error = None
                self.close()
                self._recovering_persistent_cache = False
                logger.warning(
                    "Caché SQLite de guías corrupta apartada en %s; se reconstruirá automáticamente",
                    quarantine_path,
                )
                return
        if not self._persistent_cache_disabled:
            logger.warning(
                "Caché SQLite de guías no disponible en %s; se continúa solo con caché en memoria: %s",
                self.db_path,
                error,
            )
        self._persistent_cache_disabled = True
        self._persistent_cache_error = str(error)
        self.close()

    def _prune_l1_caches(self):
        """Poda las cachés en RAM cuando exceden MAX_L1_ENTRIES para evitar consumo excesivo de memoria."""
        if len(self._l1_url_cache) > self.MAX_L1_ENTRIES:
            keys_to_remove = list(self._l1_url_cache.keys())[:self.MAX_L1_ENTRIES // 2]
            for k in keys_to_remove:
                self._l1_url_cache.pop(k, None)
                self._l1_url_times.pop(k, None)
        if len(self._l1_comp_cache) > self.MAX_L1_ENTRIES:
            keys_to_remove = list(self._l1_comp_cache.keys())[:self.MAX_L1_ENTRIES // 2]
            for k in keys_to_remove:
                self._l1_comp_cache.pop(k, None)
                self._l1_comp_times.pop(k, None)
        if len(self._negative_urls) > self.MAX_L1_ENTRIES:
            retained = set(list(self._negative_urls)[self.MAX_L1_ENTRIES // 2:])
            self._negative_urls = retained
            self._negative_url_times = {
                url: timestamp for url, timestamp in self._negative_url_times.items()
                if url in retained
            }

    @staticmethod
    def _identity_key(u_code="", asig_code="", degree_code="", plan_code="", academic_year="", language=""):
        """Clave estable de guía, aislando planes/cursos/idiomas que comparten código."""
        plan_identity = str(plan_code or degree_code or "").strip()
        return ":".join([
            str(u_code or "").zfill(3),
            plan_identity,
            str(asig_code or "").strip(),
            str(academic_year or "").strip().lower(),
            str(language or "").strip().lower(),
        ])

    @staticmethod
    def _table_columns(conn):
        return {row[1] for row in conn.execute("PRAGMA table_info(guias_docentes)").fetchall()}

    @staticmethod
    def _is_fresh(extracted_at: str) -> bool:
        """Determina si una entrada persistida sigue siendo reutilizable."""
        if SUBJECT_GUIDE_CACHE_TTL_SECONDS <= 0:
            return True
        if not extracted_at:
            return False
        try:
            extracted = datetime.strptime(str(extracted_at)[:19], "%Y-%m-%d %H:%M:%S")
            age_seconds = (datetime.now() - extracted).total_seconds()
            return 0 <= age_seconds <= SUBJECT_GUIDE_CACHE_TTL_SECONDS
        except (TypeError, ValueError, OverflowError):
            return False

    def _get_conn(self):
        if self._persistent_cache_disabled:
            return None
        conns = getattr(self._local, "guide_conns", None)
        if conns is None:
            conns = {}
            self._local.guide_conns = conns
        if self.db_path not in conns:
            conn = None
            try:
                if self.db_path and self.db_path != ":memory:":
                    dir_path = os.path.dirname(os.path.abspath(self.db_path))
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)
                conn = sqlite3.connect(self.db_path, timeout=SQLITE_CONNECT_TIMEOUT)
                conn.execute("PRAGMA busy_timeout = 30000;")
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA temp_store=MEMORY;")
                conn.execute("PRAGMA mmap_size=268435456;")
                conn.execute("PRAGMA cache_size=-64000;")
                if self.db_path == ":memory:" or self.db_path not in type(self)._schema_initialized_paths:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS guias_docentes (
                            url_hash TEXT PRIMARY KEY,
                            url TEXT NOT NULL,
                            universidad_codigo TEXT,
                            codigo_asignatura TEXT,
                            nombre TEXT,
                            datos_json TEXT NOT NULL,
                            fecha_extraccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_guias_url ON guias_docentes(url);")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS guias_negativas (
                            url_hash TEXT PRIMARY KEY,
                            url TEXT NOT NULL,
                            razon TEXT NOT NULL,
                            fecha_marca TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_guias_negativas_url ON guias_negativas(url);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_guias_univ_asig ON guias_docentes(universidad_codigo, codigo_asignatura);")
                    columns = type(self)._table_columns(conn)
                    for column, definition in (
                        ("codigo_estudio", "TEXT NOT NULL DEFAULT ''"),
                        ("curso_academico", "TEXT NOT NULL DEFAULT ''"),
                        ("idioma", "TEXT NOT NULL DEFAULT ''"),
                    ):
                        if column not in columns:
                            conn.execute(f"ALTER TABLE guias_docentes ADD COLUMN {column} {definition}")
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_guias_identity "
                        "ON guias_docentes(universidad_codigo, codigo_estudio, codigo_asignatura, curso_academico, idioma)"
                    )
                    type(self)._schema_initialized_paths.add(self.db_path)
                conn.commit()
                conns[self.db_path] = conn
            except (OSError, sqlite3.Error) as error:
                if conn is not None:
                    conn.close()
                self._disable_persistent_cache(error)
                return None
        return conns[self.db_path]

    def _init_db(self):
        self._get_conn()

    def get(self, url: str = None, u_code: str = None, asig_code: str = None,
            degree_code: str = "", plan_code: str = "", academic_year: str = "",
            language: str = "") -> dict:
        if url and self.is_negative(url):
            return None
        with self._lock:
            if url:
                url_clean = url.strip()
                if url_clean in self._l1_url_cache and self._is_fresh(self._l1_url_times.get(url_clean)):
                    return self._l1_url_cache[url_clean]
                self._l1_url_cache.pop(url_clean, None)
                self._l1_url_times.pop(url_clean, None)

            if u_code and asig_code:
                comp_key = self._identity_key(u_code, asig_code, degree_code, plan_code, academic_year, language)
                if comp_key in self._l1_comp_cache and self._is_fresh(self._l1_comp_times.get(comp_key)):
                    return self._l1_comp_cache[comp_key]
                self._l1_comp_cache.pop(comp_key, None)
                self._l1_comp_times.pop(comp_key, None)

        try:
            conn = self._get_conn()
            if conn is None:
                return None
            cursor = conn.cursor()
            if url:
                url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
                cursor.execute("SELECT datos_json, fecha_extraccion FROM guias_docentes WHERE url_hash = ?", (url_hash,))
                row = cursor.fetchone()
                if row and self._is_fresh(row[1]):
                    data = json.loads(row[0])
                    with self._lock:
                        self._l1_url_cache[url.strip()] = data
                        self._l1_url_times[url.strip()] = row[1]
                        self._prune_l1_caches()
                    return data

            if u_code and asig_code:
                comp_key = self._identity_key(u_code, asig_code, degree_code, plan_code, academic_year, language)
                if degree_code or plan_code or academic_year or language:
                    cursor.execute(
                        "SELECT datos_json, fecha_extraccion FROM guias_docentes WHERE universidad_codigo = ? "
                        "AND codigo_estudio = ? AND codigo_asignatura = ? AND curso_academico = ? "
                        "AND idioma = ? ORDER BY fecha_extraccion DESC LIMIT 1",
                        (
                            str(u_code).zfill(3), str(plan_code or degree_code or "").strip(),
                            str(asig_code).strip(), str(academic_year or "").strip(),
                            str(language or "").strip().lower(),
                        )
                    )
                else:
                    # Compatibilidad con consumidores antiguos que aún no
                    # conocen la identidad ampliada.
                    cursor.execute(
                        "SELECT datos_json, fecha_extraccion FROM guias_docentes WHERE universidad_codigo = ? AND codigo_asignatura = ? ORDER BY fecha_extraccion DESC LIMIT 1",
                        (str(u_code).zfill(3), str(asig_code).strip())
                    )
                row = cursor.fetchone()
                if row and self._is_fresh(row[1]):
                    data = json.loads(row[0])
                    with self._lock:
                        self._l1_comp_cache[comp_key] = data
                        self._l1_comp_times[comp_key] = row[1]
                        self._prune_l1_caches()
                    return data
        except Exception as e:
            logger.warning(f"Error al leer caché de guía docente: {e}")
        return None

    @staticmethod
    def _is_negative_fresh(marked_at: str) -> bool:
        """Determina si una respuesta negativa aún puede evitar una petición."""
        if NEGATIVE_CACHE_TTL_SECONDS <= 0 or not marked_at:
            return False
        try:
            marked = datetime.strptime(str(marked_at)[:19], "%Y-%m-%d %H:%M:%S")
            age_seconds = (datetime.now() - marked).total_seconds()
            return 0 <= age_seconds <= NEGATIVE_CACHE_TTL_SECONDS
        except (TypeError, ValueError, OverflowError):
            return False

    def mark_negative(self, url: str, reason: str = "negative"):
        if url:
            url = str(url).strip()
            marked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._lock:
                self._negative_urls.add(url)
                self._negative_url_times[url] = marked_at
                self._prune_l1_caches()
            try:
                conn = self._get_conn()
                if conn is not None:
                    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
                    conn.execute(
                        "INSERT OR REPLACE INTO guias_negativas (url_hash, url, razon, fecha_marca) "
                        "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                        (url_hash, url, str(reason or "negative")[:200]),
                    )
                    conn.commit()
            except Exception as error:
                logger.debug("No se pudo persistir URL negativa %s: %s", url, error, exc_info=True)

    def is_negative(self, url: str) -> bool:
        """Devuelve si una URL tiene un resultado negativo reciente."""
        if not url or NEGATIVE_CACHE_TTL_SECONDS <= 0:
            return False
        url_clean = str(url).strip()
        with self._lock:
            if url_clean in self._negative_urls:
                marked_at = self._negative_url_times.get(url_clean)
                if self._is_negative_fresh(marked_at):
                    return True
                self._negative_urls.discard(url_clean)
                self._negative_url_times.pop(url_clean, None)
        try:
            conn = self._get_conn()
            if conn is None:
                return False
            url_hash = hashlib.sha256(url_clean.encode("utf-8")).hexdigest()
            row = conn.execute(
                "SELECT fecha_marca FROM guias_negativas WHERE url_hash = ?", (url_hash,)
            ).fetchone()
            if not row:
                return False
            if self._is_negative_fresh(row[0]):
                with self._lock:
                    self._negative_urls.add(url_clean)
                    self._negative_url_times[url_clean] = row[0]
                    self._prune_l1_caches()
                return True
            conn.execute("DELETE FROM guias_negativas WHERE url_hash = ?", (url_hash,))
            conn.commit()
        except Exception as error:
            logger.debug("No se pudo consultar URL negativa %s: %s", url_clean, error, exc_info=True)
        return False

    def set(self, url: str, data: dict, u_code: str = "", asig_code: str = "", nombre: str = "",
            degree_code: str = "", plan_code: str = "", academic_year: str = "", language: str = ""):
        if not data:
            return
        with self._lock:
            if url:
                url_clean = url.strip()
                self._l1_url_cache[url_clean] = data
                self._l1_url_times[url_clean] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._negative_urls.discard(url_clean)
                self._negative_url_times.pop(url_clean, None)
            if u_code and asig_code:
                comp_key = self._identity_key(u_code, asig_code, degree_code, plan_code, academic_year, language)
                self._l1_comp_cache[comp_key] = data
                self._l1_comp_times[comp_key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._prune_l1_caches()

        url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
        try:
            conn = self._get_conn()
            if conn is None:
                return
            if url:
                conn.execute(
                    "DELETE FROM guias_negativas WHERE url_hash = ?",
                    (hashlib.sha256(url.strip().encode("utf-8")).hexdigest(),),
                )
            conn.execute("""
                INSERT OR REPLACE INTO guias_docentes 
                (url_hash, url, universidad_codigo, codigo_asignatura, nombre, datos_json,
                 codigo_estudio, curso_academico, idioma, fecha_extraccion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                url_hash, url.strip(), str(u_code).zfill(3) if u_code else "",
                str(asig_code).strip() if asig_code else "", nombre, json.dumps(data, ensure_ascii=False),
                str(plan_code or degree_code or "").strip(), str(academic_year or "").strip(),
                str(language or "").strip().lower(),
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Error al escribir en caché SQLite de guías docentes: {e}")

    def close(self):
        """Closes thread-local SQLite connection handles."""
        conns = getattr(self._local, "guide_conns", None)
        if conns:
            for conn in list(conns.values()):
                try:
                    conn.close()
                except Exception as close_error:
                    logger.warning("No se pudo cerrar una conexión de caché de guías: %s", close_error, exc_info=True)
            conns.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# =============================================================================
# MOTOR UNIVERSAL DE RESOLUCIÓN CANÓNICA DE GUÍAS DOCENTES (FAST-PATH)
# =============================================================================

def generate_subject_slug(name: str) -> str:
    """Genera un slug limpio y normalizado (sin tildes, con guiones) para rutas URL."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = re.sub(r"[^\w\s-]", "", ascii_text).strip()
    return re.sub(r"[\s_]+", "-", clean)


def _academic_year_candidates(academic_year: str, count: int = 3) -> list[str]:
    """Devuelve el curso solicitado y cursos anteriores para usar como respaldo."""
    match = re.search(r"(20\d{2})", str(academic_year or ""))
    start_year = int(match.group(1)) if match else datetime.now().year - (1 if datetime.now().month < 9 else 0)
    return [f"{start_year - offset}-{str(start_year - offset + 1)[-2:]}" for offset in range(max(1, count))]


def _normalise_academic_year_token(value: str) -> str:
    """Normaliza ``2025-2026`` y ``2025-26`` al mismo identificador."""
    match = re.search(r"(20\d{2})[-_/](20)?(\d{2})", str(value or ""))
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(3)}"


_RE_NUMERIC_SUBJECT_CODE = re.compile(r"^\d{4,8}$")
_RE_ALPHANUMERIC_SUBJECT_CODE = re.compile(r"^[A-Z]{2,4}\d{2,6}$", re.IGNORECASE)


def is_plausible_subject_code(value: str) -> bool:
    """Evita consultar códigos administrativos como si fueran asignaturas."""
    code = str(value or "").strip()
    if _RE_NUMERIC_SUBJECT_CODE.fullmatch(code) or _RE_ALPHANUMERIC_SUBJECT_CODE.fullmatch(code):
        return True
    return False


def _is_likely_subject_guide_url(url: str, subject_code: str = "") -> bool:
    """Clasifica una URL explícita antes de convertirla en una petición de guía."""
    if not url:
        return False
    url_low = str(url).lower()
    if subject_code and is_plausible_subject_code(subject_code) and str(subject_code).lower() in url_low:
        return True
    return any(marker in url_low for marker in (
        "guia", "guía", "asignatura", "assignatura", "syllabus", "subject",
        "cvfichaasig", "codig asignatura", "codigoasignatura", "asig=",
    ))


def _normalise_subject_identity(value: str) -> list[str]:
    """Devuelve tokens comparables, eliminando prefijos editoriales comunes."""
    text = unicodedata.normalize("NFKD", str(value or "")).lower()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\b(?:guia|docente|asignatura|materia|subject|course|course name)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [token for token in text.split() if len(token) >= 3]


def _subject_guide_identity_matches(expected_name: str, expected_code: str, parsed_guide: dict, source_url: str = "") -> bool:
    """Evita asociar una página curricular válida a otra asignatura."""
    parsed_name = str(parsed_guide.get("nombre_asignatura") or "").strip()
    parsed_code = str(parsed_guide.get("codigo_asignatura") or "").strip()
    expected_code = str(expected_code or "").strip()

    if expected_code and parsed_code and expected_code.lower() == parsed_code.lower():
        return True
    if parsed_code and expected_code and is_plausible_subject_code(expected_code):
        return False
    if not parsed_name:
        return bool(expected_code and expected_code.lower() in str(source_url or "").lower())

    expected_tokens = _normalise_subject_identity(expected_name)
    parsed_tokens = _normalise_subject_identity(parsed_name)
    if not expected_tokens or not parsed_tokens:
        return False
    expected_key = " ".join(expected_tokens)
    parsed_key = " ".join(parsed_tokens)
    if expected_key == parsed_key:
        return True

    # Los portales pueden mostrar una variante bilingüe o añadir/quitar el
    # número de edición. Se tolera una relación de inclusión completa,
    # exigiendo que para términos únicos (len == 1) el título destino sea una variante corta (<= 3 tokens).
    expected_set = set(expected_tokens)
    parsed_set = set(parsed_tokens)
    shared = expected_set & parsed_set
    min_required = min(2, len(expected_set), len(parsed_set))
    if len(shared) < min_required:
        return False
    if min_required == 1 and len(expected_tokens) == 1:
        return expected_set.issubset(parsed_set) and len(parsed_tokens) <= 3
    return expected_set.issubset(parsed_set) or parsed_set.issubset(expected_set)


def resolve_candidate_subject_guide_urls(
    elem: dict, 
    u_code: str, 
    u_web: str = "", 
    d_code: str = "",
    academic_year: str = None,
    discovery_index: dict | None = None,
    negative_registry: RunNegativeURLRegistry | None = None,
    negative_urls: set[str] | None = None,
    pruning_stats: dict | None = None,
) -> list:
    """
    Generador universal de URLs candidatas para guías docentes del EEES.
    Combina URLs explícitas ya extraídas con patrones institucionales generalizados.
    """
    candidates = []
    seen = set()
    candidate_limit = max(1, MAX_SUBJECT_GUIDE_URL_CANDIDATES)
    pool_limit = max(candidate_limit, candidate_limit * 4)
    if not academic_year:
        academic_year = _academic_year_candidates(None, count=1)[0]
    year_candidates = _academic_year_candidates(academic_year)

    def _add_url(u: str):
        if not u:
            return
        norm = normalize_url(u)
        if (
            norm
            and norm not in seen
            and is_valid_http_url(norm)
            and len(candidates) < pool_limit
        ):
            seen.add(norm)
            candidates.append(norm)

    # 1. URL explícita ya detectada en el plan web o BOE. Si pertenece a un
    # curso antiguo se añade al final, para que no oculte una URL vigente.
    url_directa = elem.get("url_guia_docente")
    explicit_urls = [url_directa]
    if isinstance(elem.get("urls_guia_docente"), (list, tuple)):
        explicit_urls.extend(elem.get("urls_guia_docente"))
    current_year = year_candidates[0]
    for explicit_url in dict.fromkeys(str(item).strip() for item in explicit_urls if item):
        explicit_year = _normalise_academic_year_token(explicit_url)
        if (
            _is_likely_subject_guide_url(explicit_url, elem.get("codigo_asignatura") or elem.get("codigo"))
            and (not explicit_year or explicit_year == current_year)
        ):
            _add_url(explicit_url)

    explicit_candidates = list(candidates)
    discovered_items = (
        discovery_index.get("records") or discovery_index.get("urls", [])
        if discovery_index
        else []
    )

    asig_code = elem.get("codigo_asignatura") or elem.get("codigo")
    asig_nombre = elem.get("nombre_elemento", "")

    # Inferir código numérico de asignatura si está embebido en el nombre
    if not asig_code:
        m_code = re.match(r"^(\d{4,8})\s*[-–_:]\s*(.+)$", asig_nombre)
        if m_code:
            asig_code = m_code.group(1)
            asig_nombre = m_code.group(2).strip()

    if asig_code and not is_plausible_subject_code(asig_code):
        asig_code = ""

    slug = generate_subject_slug(asig_nombre)
    u_code_padded = str(u_code).zfill(3)

    # Si el sitemap/hub solo expone rutas de catálogo, aprende la familia de
    # ruta observada y deriva pocas rutas hermanas. Es una heurística basada
    # en evidencia, sin perfiles declarativos ni ramas por universidad.
    route_derived_items = derive_subject_guide_urls_from_routes(
        discovered_items,
        subject_name=asig_nombre,
        subject_code=asig_code,
        limit=max(1, candidate_limit * 2),
    ) if discovered_items else []
    enriched_discovered_items = list(discovered_items) + route_derived_items

    # 2. El catálogo de universidades es la fuente de verdad para el dominio.
    # El parámetro explícito tiene prioridad porque puede contener un portal
    # institucional legítimo que no sea el dominio raíz.
    parseable_web = str(u_web or "").strip()
    if parseable_web and "://" not in parseable_web:
        parseable_web = f"https://{parseable_web}"
    parsed_domain = (urlparse(parseable_web).hostname or "").lower() if parseable_web else ""
    if not parsed_domain:
        domain = UNIVERSITY_DOMAIN_BY_CODE.get(u_code_padded, "")
    else:
        domain = parsed_domain.removeprefix("www.")

    if domain:
        clean_domain = re.sub(r"^www\.", "", domain)
        # Algunos catálogos registran el dominio raíz, pero publican todo el
        # contenido académico bajo un host canónico (normalmente www). El
        # índice ya consultado es evidencia válida para aprender ese host sin
        # introducir perfiles declarativos por universidad.
        discovered_host_counts = {}
        for discovered_item in enriched_discovered_items:
            discovered_url = (
                discovered_item.get("url", "")
                if isinstance(discovered_item, dict)
                else discovered_item
            )
            discovered_host = (urlparse(str(discovered_url or "")).hostname or "").lower().rstrip(".")
            if not discovered_host:
                continue
            try:
                belongs_to_institution = is_same_or_subdomain(
                    f"https://{discovered_host}",
                    f"https://{clean_domain}",
                )
            except Exception:
                belongs_to_institution = False
            if belongs_to_institution:
                discovered_host_counts[discovered_host] = discovered_host_counts.get(discovered_host, 0) + 1
        learned_public_host = (
            max(discovered_host_counts, key=discovered_host_counts.get)
            if discovered_host_counts
            else clean_domain
        )
        # Códigos variantes (original y sin ceros a la izquierda)
        code_variants = [asig_code] if asig_code else []
        if asig_code and asig_code.startswith("0"):
            code_variants.append(asig_code.lstrip("0"))

        # 3.1. Algunos planes BOE solo conservan el nombre de la materia.
        # En ese caso no se deben generar cero URLs: se prueban rutas de ficha
        # por slug en los portales académicos oficiales conocidos. Son pocas,
        # deterministas y quedan sometidas al mismo filtro de contenido.
        if slug and not code_variants:
            candidate_limit = min(
                candidate_limit,
                max(1, MAX_SUBJECT_GUIDE_NO_CODE_CANDIDATES),
            )
            guide_domains = [learned_public_host]
            for guide_domain in dict.fromkeys(
                str(candidate).strip().lower()
                for candidate in guide_domains
                if candidate
            ):
                _add_url(f"https://{guide_domain}/es/estudios/asignatura/{slug}/")
                _add_url(f"https://{guide_domain}/estudios/asignatura/{slug}/")
                _add_url(f"https://{guide_domain}/{slug}/guia-docente")

        # 3. Patrones institucionales genéricos.
        #
        # No se mantienen ramas por código RUCT ni por nombre de universidad:
        # una universidad nueva debe poder pasar por esta misma ruta. Las
        # fuentes explícitas del plan y el índice descubierto tienen prioridad
        # y permiten resolver portales con rutas no predecibles.
        for c_code in code_variants:
            # 4. Patrones Institucionales Genéricos del SUE
            _add_url(f"https://secretaria.{clean_domain}/docencia/guia/{c_code}")
            _add_url(f"https://cv1.cpd.{clean_domain}/ConsPlanesEstudio/cvFichaAsigRedir.asp?asig={c_code}")
            for year in year_candidates:
                _add_url(f"https://asignaturas.{clean_domain}/{year}/{c_code}")
                _add_url(f"https://guias.{clean_domain}/{year}/{c_code}")
                _add_url(f"https://guiasdocentes.{clean_domain}/{year}/{c_code}")

            if slug:
                _add_url(f"https://{learned_public_host}/es/estudios/estudios-oficiales/grados/asignatura/{slug}-{c_code}/")
                _add_url(f"https://{learned_public_host}/estudios/asignatura/{slug}-{c_code}/")

            if d_code:
                _add_url(f"https://{learned_public_host}/descargas/guias/{c_code}.pdf")
                for year in year_candidates:
                    _add_url(f"https://{learned_public_host}/shared/es/estudios/estudios-oficiales/grados/.galleries/Programs-En/{c_code}_{d_code}_{year}_en.pdf")
                    _add_url(f"https://{learned_public_host}/shared/es/estudios/estudios-oficiales/grados/.galleries/Programs-Es/{c_code}_{d_code}_{year}_es.pdf")

    if (
        url_directa
        and _is_likely_subject_guide_url(url_directa, asig_code)
    ):
        _add_url(url_directa)

    discovered_candidates = set()
    route_derived_candidates = set()
    if enriched_discovered_items:
        discovered = rank_discovered_guide_urls(
            enriched_discovered_items,
            subject_name=asig_nombre,
            subject_code=asig_code,
            limit=candidate_limit,
        )
        direct_discovered_candidates = {
            item.get("url", "") if isinstance(item, dict) else str(item)
            for item in discovered_items
        }
        discovered_candidates = set(discovered) & direct_discovered_candidates
        route_derived_candidates = set(discovered) - discovered_candidates
        # Las URLs descubiertas se colocan antes de las heurísticas genéricas:
        # un sitemap real tiene más evidencia que un subdominio inventado. La
        # URL explícita conservada en el plan mantiene siempre la prioridad.
        candidates = list(dict.fromkeys(
            explicit_candidates + discovered + candidates
        ))

    def _candidate_score(url: str) -> tuple[int, int, str]:
        low = str(url or "").lower()
        path = urlparse(low).path
        score = 0
        if url in explicit_candidates:
            score += 1000
        if url in discovered_candidates:
            score += 500
        if url in route_derived_candidates:
            score += 300
        if asig_code and re.search(rf"(?<![a-z0-9]){re.escape(str(asig_code).lower())}(?![a-z0-9])", low):
            score += 250
        if slug and slug in low:
            score += 120
        if any(marker in low for marker in (
            "guia", "docente", "asignatura", "asignaturas", "guiasdocentes",
            "syllabus", "ficha", "teaching",
        )):
            score += 60
        if urlparse(low).netloc.startswith(("asignaturas.", "guias.", "guiasdocentes.")):
            score += 90
        if any(marker in low for marker in ("estudios", "study", "grado", "degree", "curriculum", "plan")):
            score += 20
        if path.endswith(".pdf"):
            score += 15
        if academic_year and str(academic_year).lower() in low:
            score += 10
        return score, len(low), low

    # El límite se aplica después de puntuar todo el conjunto, para que una
    # plantilla genérica no desplace una URL explícita o descubierta por sitemap.
    candidates = list(dict.fromkeys(candidate for candidate in candidates if is_valid_http_url(candidate)))
    before_negative_filter = len(candidates)
    negative_keys = {
        RunNegativeURLRegistry._key(url)
        for url in (negative_urls or set())
        if RunNegativeURLRegistry._key(url)
    }
    if negative_keys or negative_registry is not None:
        candidates = [
            candidate for candidate in candidates
            if RunNegativeURLRegistry._key(candidate) not in negative_keys
            and not (negative_registry and negative_registry.contains(candidate))
        ]

    candidates.sort(key=lambda item: (-_candidate_score(item)[0], _candidate_score(item)[1], _candidate_score(item)[2]))
    relevant_evidence_count = len(set(discovered or [])) if enriched_discovered_items else 0
    has_explicit_evidence = bool(explicit_candidates)
    has_route_evidence = bool(route_derived_candidates)
    # El tamaño total del índice ya no influye. Una asignatura solo recibe un
    # pequeño margen según sus evidencias relevantes, nunca miles de URLs del
    # catálogo compartido de otra asignatura.
    if has_explicit_evidence:
        adaptive_limit = min(candidate_limit, 2)
    elif relevant_evidence_count or has_route_evidence:
        adaptive_limit = min(candidate_limit, 3)
    else:
        adaptive_limit = min(candidate_limit, 3 if asig_code else 2)

    # Diversificación estructural: una única URL por familia de ruta hasta
    # agotar el presupuesto. Conserva host, directorios y claves de query,
    # pero abstrae identificadores/curso/código para no repetir plantillas
    # equivalentes con distinto formato.
    def _route_family(url: str) -> str:
        parsed = urlparse(url)
        family_segments = []
        for segment in parsed.path.strip("/").lower().split("/"):
            if not segment:
                continue
            value = segment
            if asig_code and str(asig_code).lower() in value:
                value = value.replace(str(asig_code).lower(), "{subject}")
            if slug and slug.lower() in value:
                value = value.replace(slug.lower(), "{subject}")
            value = re.sub(r"20\d{2}(?:[-_]20?\d{2})?", "{year}", value)
            value = re.sub(r"(?<![a-z])\d{3,}(?![a-z])", "{id}", value)
            family_segments.append(value)
        query_keys = ",".join(sorted({key.lower() for key in re.findall(r"(?:^|&)\s*([^=&\s]+)=", parsed.query)}))
        return f"{parsed.netloc.lower()}/{'/'.join(family_segments)}?{query_keys}"

    selected = []
    selected_families = set()
    for candidate in candidates:
        family = _route_family(candidate)
        if family in selected_families:
            continue
        selected_families.add(family)
        selected.append(candidate)
        if len(selected) >= adaptive_limit:
            break
    # Si todas las alternativas caen en la misma familia, no descartamos la
    # oportunidad de rescate por cumplir la cuota de diversidad.
    if len(selected) < adaptive_limit:
        selected.extend(candidate for candidate in candidates if candidate not in selected)
        selected = selected[:adaptive_limit]
    candidates = selected

    if pruning_stats is not None:
        pruning_stats["candidate_urls_before_filter"] = before_negative_filter
        pruning_stats["candidate_urls_after_filter"] = len(candidates)
        pruning_stats["candidate_urls_pruned"] = max(0, before_negative_filter - len(candidates))

    return candidates


# =============================================================================
# PARSERS ESPECIALIZADOS DE GUÍAS DOCENTES (HTML & PDF STREAM IN-RAM)
# =============================================================================

def parse_tabular_subject_guide(soup: BeautifulSoup, url: str) -> dict:
    """
    Extrae una guía docente HTML basada en tablas y etiquetas semánticas.
    """
    res = {
        "url_guia_docente": url,
        "fuente": "Portal oficial universitario (estructura tabular)",
        "codigo_asignatura": "",
        "nombre_asignatura": "",
        "curso_academico": "2025-26",
        "idioma": "Castellano",
        "departamento": "",
        "area_conocimiento": "",
        "creditos": {"teoria": None, "practicas": None, "total_ects": None},
        "horas_presenciales": {"teoria": None, "otras": None, "total": None},
        "temario": [],
        "sistema_evaluacion": [],
        "criterios_evaluacion": "",
        "profesorado": [],
        "actividades_docentes": [],
        "resultados_aprendizaje": []
    }

    # Encabezado: Código y Nombre
    title_elem = soup.find("h2")
    if title_elem:
        m_t = re.search(r"<\s*(\d+)\s*\|\s*([^>]+)>", title_elem.get_text())
        if m_t:
            res["codigo_asignatura"] = m_t.group(1).strip()
            res["nombre_asignatura"] = sanitize_subject_name(m_t.group(2).strip())

    # Bloque de metadatos generales
    info_div = soup.find("div", class_="info-asignatura")
    if info_div:
        text_info = info_div.get_text(separator=" ", strip=True)
        m_dept = re.search(r"Departamento:\s*([^|]+)\|?\s*([A-Za-zÁÉÍÓÚáéíóúñ\s]+)", text_info)
        if m_dept:
            res["departamento"] = m_dept.group(2).strip()
        m_area = re.search(r"Área:\s*([^|]+)\|?\s*([A-Za-zÁÉÍÓÚáéíóúñ\s]+)", text_info)
        if m_area:
            res["area_conocimiento"] = m_area.group(2).strip()
        m_idioma = re.search(r"Idioma:\s*([A-Za-zÁÉÍÓÚáéíóúñ]+)", text_info)
        if m_idioma:
            res["idioma"] = m_idioma.group(1).strip().capitalize()
        m_ct = re.search(r"Créd\.\s*Teoría:\s*([\d,]+)", text_info)
        if m_ct:
            try:
                res["creditos"]["teoria"] = float(m_ct.group(1).replace(",", "."))
            except ValueError:
                pass
        m_cp = re.search(r"Créd\.\s*Prácticas:\s*([\d,]+)", text_info)
        if m_cp:
            try:
                res["creditos"]["practicas"] = float(m_cp.group(1).replace(",", "."))
            except ValueError:
                pass
        m_ects = re.search(r"Créd\.\s*ECTS:\s*([\d,]+)", text_info)
        if m_ects:
            try:
                res["creditos"]["total_ects"] = float(m_ects.group(1).replace(",", "."))
            except ValueError:
                pass

    # Temario (Tabla id="temario")
    temario_table = soup.find("table", id="temario")
    if temario_table:
        for tr in temario_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                orden = tds[0].get_text(strip=True)
                td_text = tds[1].get_text(separator="\n", strip=True)
                lineas = [l.strip() for l in td_text.splitlines() if l.strip()]
                if lineas:
                    bloque_titulo = lineas[0]
                    subtemas = lineas[1:] if len(lineas) > 1 else []
                    if not is_spurious_or_administrative_subject(bloque_titulo):
                        res["temario"].append({
                            "orden": orden,
                            "titulo": bloque_titulo,
                            "contenidos": subtemas
                        })

    # Sistema de evaluación
    eval_table = soup.find("table", id=lambda x: x and "procedimientos_evaluacion" in x)
    if eval_table:
        for tr in eval_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4:
                tarea = tds[1].get_text(strip=True)
                tecnicas = tds[2].get_text(strip=True)
                ponderacion_str = tds[3].get_text(strip=True)
                try:
                    pond_val = float(ponderacion_str.replace(",", ".").replace("%", ""))
                except ValueError:
                    pond_val = 0.0
                res["sistema_evaluacion"].append({
                    "tarea": tarea,
                    "instrumentos": tecnicas,
                    "ponderacion_porcentaje": pond_val
                })

    # Criterios de evaluación e IA Generativa
    crit_input = soup.find("input", attrs={"name": "criterios_evaluacion"})
    if crit_input and crit_input.get("value"):
        raw_val = crit_input["value"]
        clean_crit = BeautifulSoup(raw_val, "html.parser").get_text(separator="\n", strip=True)
        res["criterios_evaluacion"] = clean_crit

    # Profesorado
    prof_table = soup.find("table", id="profesorado")
    if prof_table:
        for tr in prof_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4:
                apellidos = f"{tds[0].get_text(strip=True)} {tds[1].get_text(strip=True)}".strip()
                nombre = tds[2].get_text(strip=True)
                categoria = tds[3].get_text(strip=True)
                es_coord = bool(tr.find("i", class_="text-primary"))
                res["profesorado"].append({
                    "nombre_completo": f"{nombre} {apellidos}".strip(),
                    "categoria": categoria,
                    "coordinador": es_coord
                })

    return res


def parse_generic_eees_subject_guide(soup: BeautifulSoup, url: str) -> dict:
    """
    Parser semántico modular para guías docentes del EEES en HTML heterogéneo.
    """
    res = {
        "url_guia_docente": url,
        "fuente": "Portal Oficial Universidad",
        "codigo_asignatura": "",
        "nombre_asignatura": "",
        "idioma": "Castellano",
        "departamento": "",
        "creditos": {"teoria": None, "practicas": None, "total_ects": None},
        "requisitos_previos": [],
        "temario": [],
        "sistema_evaluacion": [],
        "criterios_evaluacion": "",
        "profesorado": [],
        "bibliografia": [],
        "competencias": [],
        "resultados_aprendizaje": [],
    }

    h1 = soup.find("h1")
    if h1:
        res["nombre_asignatura"] = sanitize_subject_name(h1.get_text(strip=True))
    if not res["nombre_asignatura"]:
        for selector in ("meta[property='og:title']", "meta[name='twitter:title']"):
            meta = soup.select_one(selector)
            if meta and meta.get("content"):
                res["nombre_asignatura"] = sanitize_subject_name(meta["content"])
                break
    if not res["nombre_asignatura"] and soup.title:
        res["nombre_asignatura"] = sanitize_subject_name(soup.title.get_text(" ", strip=True))

    # Muchas universidades publican los metadatos en tablas de dos columnas,
    # dl/dt/dd o tarjetas sin clases estables. Se extraen por la etiqueta
    # visible, nunca por la posición de la página.
    metadata_pairs = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) >= 2:
            metadata_pairs.append((cells[0].get_text(" ", strip=True), cells[1].get_text(" ", strip=True)))
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            metadata_pairs.append((dt.get_text(" ", strip=True), dd.get_text(" ", strip=True)))
    for label, value in metadata_pairs:
        label_lower = label.casefold()
        value = " ".join(value.split())
        if not value:
            continue
        if any(token in label_lower for token in ("código", "codigo", "code", "sigla", "abrev")):
            code_match = re.search(r"[A-Za-z]{0,4}\s*\d{4,8}", value)
            candidate = re.sub(r"\s+", "", code_match.group(0)) if code_match else value
            if not res["codigo_asignatura"] and is_plausible_subject_code(candidate):
                res["codigo_asignatura"] = candidate.upper()
        elif any(token in label_lower for token in ("ects", "crédito", "credito", "credits")):
            ects_match = re.search(r"\d+(?:[.,]\d+)?", value)
            if ects_match and res["creditos"]["total_ects"] is None:
                res["creditos"]["total_ects"] = float(ects_match.group(0).replace(",", "."))
        elif any(token in label_lower for token in ("idioma", "language", "llengua")):
            res["idioma"] = value
        elif any(token in label_lower for token in ("departamento", "department", "facultad", "school")):
            if not res["departamento"]:
                res["departamento"] = value

    SECTIONS_MAP = {
        "requisitos": ["requisitos", "prerrequisitos", "prerrequisits", "requisits previs", "recomanacions", "aurretiazko baldintzak", "requisitos previos", "prerequisites", "incompatibilidades", "incompatibilitats"],
        "temario": ["temario", "continguts", "contenidos", "programa", "syllabus", "bloques temáticos", "plà docent", "edukiak", "contidos", "course outline", "thematic units"],
        "evaluacion": ["evaluación", "evaluacion", "avaluació", "avaluacio", "evaluation", "sistema de evaluación", "criteris d'avaluació", "ebaluazioa", "cualificación", "assessment"],
        "profesorado": ["profesorado", "professorat", "equip docent", "equipo docente", "teaching staff", "coordinación", "professors", "profesores", "irakasleak", "docentes", "faculty"],
        "bibliografia": ["bibliografía", "bibliografia", "bibliography", "referencias", "recursos d'aprenentatge", "bibliografia basica", "reading list"],
        "competencias": ["competencias", "competències", "competencias básicas", "competencias específicas", "learning outcomes", "resultados de aprendizaje", "gaitasunak", "competencias xerais", "skills"]
    }

    headings = soup.find_all(["h2", "h3", "h4", "dt", "strong", "legend"])
    for h in headings:
        h_text = h.get_text(strip=True).lower()

        # 0. Requisitos previos e incompatibilidades
        if any(kw in h_text for kw in SECTIONS_MAP["requisitos"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "table", "p", "dd"])
            if next_node:
                for it in next_node.find_all(["li", "p", "tr"]):
                    req_txt = " ".join(it.get_text(" ", strip=True).split())
                    if req_txt and 4 <= len(req_txt) <= 300 and not is_spurious_or_administrative_subject(req_txt):
                        if req_txt not in res["requisitos_previos"]:
                            res["requisitos_previos"].append(req_txt)

        # 1. Temario
        elif any(kw in h_text for kw in SECTIONS_MAP["temario"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "table", "p", "dd"])
            if next_node:
                items = next_node.find_all(["li", "p", "tr"])
                for it in items:
                    txt = it.get_text(strip=True)
                    if txt and 4 <= len(txt) <= 250 and not is_spurious_or_administrative_subject(txt):
                        res["temario"].append({"titulo": txt, "contenidos": []})

        # 2. Evaluación
        elif any(kw in h_text for kw in SECTIONS_MAP["evaluacion"]):
            next_node = h.find_next_sibling(["div", "table", "p", "ul", "dd"])
            if next_node:
                criteria = next_node.get_text(separator="\n", strip=True)
                if len(criteria) > len(res["criterios_evaluacion"]):
                    res["criterios_evaluacion"] = criteria
                for row in next_node.find_all("tr"):
                    cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                    percent = None
                    for cell in cells:
                        percent = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*%", cell)
                        if percent:
                            break
                    if percent and cells:
                        task = cells[0]
                        if len(cells) > 1 and re.search(r"%", task):
                            task = cells[1]
                        entry = {"tarea": task, "instrumentos": " ".join(cells[1:]), "ponderacion_porcentaje": float(percent.group(1).replace(",", "."))}
                        if not any(existing == entry for existing in res["sistema_evaluacion"]):
                            res["sistema_evaluacion"].append(entry)
                # Extracción desde texto continuo con porcentajes (ej. "Examen: 60%, Prácticas: 40%")
                if not res["sistema_evaluacion"] and criteria:
                    for m_pond in re.finditer(r"([^.,;\n:()]+?)\s*:\s*(\d{1,3}(?:[.,]\d+)?)\s*%", criteria):
                        task_name = m_pond.group(1).strip()
                        if 3 <= len(task_name) <= 80:
                            entry = {
                                "tarea": task_name,
                                "instrumentos": task_name,
                                "ponderacion_porcentaje": float(m_pond.group(2).replace(",", "."))
                            }
                            if not any(existing == entry for existing in res["sistema_evaluacion"]):
                                res["sistema_evaluacion"].append(entry)

        # 3. Profesorado
        elif any(kw in h_text for kw in SECTIONS_MAP["profesorado"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "table", "p", "dd"])
            if next_node:
                for it in next_node.find_all(["li", "tr", "p"]):
                    p_txt = it.get_text(strip=True)
                    if p_txt and 4 <= len(p_txt) <= 80:
                        email = ""
                        mailto = it.find("a", href=re.compile(r"^mailto:", re.I))
                        if mailto and mailto.get("href"):
                            email = mailto["href"].replace("mailto:", "").strip()
                        if not email:
                            m_em = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", it.get_text())
                            if m_em:
                                email = m_em.group(0)
                        prof_item = {"nombre_completo": p_txt, "coordinador": False}
                        if email:
                            prof_item["email"] = email
                        res["profesorado"].append(prof_item)

        # 4. Bibliografía
        elif any(kw in h_text for kw in SECTIONS_MAP["bibliografia"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "p", "dd"])
            if next_node:
                for it in next_node.find_all(["li", "p"]):
                    b_txt = it.get_text(strip=True)
                    if b_txt and 6 <= len(b_txt) <= 300:
                        res["bibliografia"].append(b_txt)

        # Algunas plantillas mezclan competencias y resultados bajo un mismo
        # bloque; los resultados se conservan como entidades separadas.
        elif any(kw in h_text for kw in SECTIONS_MAP["competencias"]):
            next_node = h.find_next_sibling(["ul", "ol", "div", "table", "p", "dd"])
            if next_node:
                for it in next_node.find_all(["li", "tr", "p"]):
                    text = " ".join(it.get_text(" ", strip=True).split())
                    if not (6 <= len(text) <= 500):
                        continue
                    code_match = re.match(r"((?:CG|CE|CT|CB|RA)\s*\d+)\s*[-:–]?\s*(.*)$", text, re.IGNORECASE)
                    if code_match and code_match.group(1).upper().replace(" ", "").startswith("RA"):
                        res["resultados_aprendizaje"].append({
                            "codigo": code_match.group(1).upper().replace(" ", ""),
                            "descripcion": code_match.group(2).strip() or text,
                        })
                    else:
                        value = {"codigo": code_match.group(1).upper().replace(" ", "") if code_match else "", "descripcion": (code_match.group(2).strip() if code_match else text)}
                        if value not in res["competencias"]:
                            res["competencias"].append(value)

    return res


def parse_subject_guide_pdf_stream(pdf_bytes: bytes, url: str) -> dict:
    """
    Extrae temarios, evaluación y profesorado directamente desde el flujo binario de un PDF en RAM (0 I/O en disco).
    """
    res = {
        "url_guia_docente": url,
        "fuente": "Guía Docente Oficial PDF",
        "codigo_asignatura": "",
        "nombre_asignatura": "",
        "idioma": "Castellano",
        "departamento": "",
        "creditos": {"teoria": None, "practicas": None, "total_ects": None},
        "temario": [],
        "sistema_evaluacion": [],
        "criterios_evaluacion": "",
        "profesorado": [],
        "bibliografia": [],
        "competencias": [],
        "resultados_aprendizaje": [],
        "metodo_extraccion": "texto_nativo",
        "ocr_usado": False,
        "pdf_paginas_procesadas": 0,
        "pdf_paginas_totales": 0,
        "pdf_parseo_limitado": False,
    }

    if not isinstance(pdf_bytes, (bytes, bytearray)) or len(pdf_bytes) > max(1, SUBJECT_GUIDE_PDF_MAX_BYTES):
        res["pdf_parseo_limitado"] = True
        res["motivo_parseo_limitado"] = "max_bytes"
        res["pdf_parse_duracion_seg"] = 0.0
        return res

    parse_started = time.perf_counter()
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        try:
            total_pages = len(reader.pages)
        except Exception:
            total_pages = 0
        res["pdf_paginas_totales"] = total_pages
        max_pages = min(max(1, SUBJECT_GUIDE_PDF_MAX_PAGES), total_pages) if total_pages else 0
        pages_text = []
        total_chars = 0
        for page_number in range(max_pages):
            if time.perf_counter() - parse_started >= max(0.1, SUBJECT_GUIDE_PDF_PARSE_TIMEOUT_SECONDS):
                res["pdf_parseo_limitado"] = True
                res["motivo_parseo_limitado"] = "timeout"
                break
            try:
                page_text = reader.pages[page_number].extract_text() or ""
            except Exception as page_error:
                logger.debug("No se pudo extraer la página %s de %s: %s", page_number + 1, url, page_error)
                page_text = ""
            remaining = max(0, SUBJECT_GUIDE_PDF_MAX_TEXT_CHARS - total_chars)
            if len(page_text) > remaining:
                page_text = page_text[:remaining]
                res["pdf_parseo_limitado"] = True
                res["motivo_parseo_limitado"] = "max_text_chars"
            pages_text.append(page_text)
            total_chars += len(page_text)
            res["pdf_paginas_procesadas"] += 1
            if total_chars >= SUBJECT_GUIDE_PDF_MAX_TEXT_CHARS:
                break
        if max_pages < total_pages and not res["pdf_parseo_limitado"]:
            res["pdf_parseo_limitado"] = True
            res["motivo_parseo_limitado"] = "max_pages"
        full_text = "\n".join(pages_text)

        # OCR es una segunda oportunidad únicamente para PDFs escaneados o
        # con una capa de texto prácticamente vacía. La disponibilidad de
        # Tesseract/las librerías es opcional y nunca convierte un fallo de
        # OCR en un error de la ejecución.
        if (
            SUBJECT_GUIDE_PDF_OCR_ENABLED
            and len(full_text.strip()) < max(0, SUBJECT_GUIDE_PDF_OCR_MIN_TEXT_CHARS)
            and time.perf_counter() - parse_started < max(0.1, SUBJECT_GUIDE_PDF_PARSE_TIMEOUT_SECONDS)
        ):
            try:
                from ocr_parser import OCRPDFParser, OCR_AVAILABLE
                if OCR_AVAILABLE:
                    ocr_text = OCRPDFParser(
                        dpi=max(72, SUBJECT_GUIDE_PDF_OCR_DPI),
                        max_pages=max(1, SUBJECT_GUIDE_PDF_OCR_MAX_PAGES),
                    ).extract_text_via_ocr(bytes(pdf_bytes))
                    if ocr_text and len(ocr_text.strip()) >= max(10, SUBJECT_GUIDE_PDF_OCR_MIN_TEXT_CHARS):
                        full_text = ocr_text[:max(1, SUBJECT_GUIDE_PDF_MAX_TEXT_CHARS)]
                        res["metodo_extraccion"] = "ocr"
                        res["ocr_usado"] = True
            except Exception as ocr_error:
                logger.debug("OCR no disponible para %s: %s", url, ocr_error)
        lines = [l.strip() for l in full_text.splitlines() if l.strip()]

        is_structured_guide = _looks_like_structured_learning_guide(lines)
        is_signed_guide = _looks_like_signed_learning_guide(lines)
        if is_structured_guide:
            _enrich_structured_learning_guide_from_lines(res, lines)
        if is_signed_guide:
            _enrich_signed_learning_guide_from_lines(res, lines)

        # 1. Metadatos generales (Nombre, Código, ECTS, Departamento)
        for l in lines[:30]:
            m_name = re.search(r"(?:Course Name|Asignatura|Nombre):\s*([^\n|]+)", l, re.IGNORECASE)
            if m_name and not res["nombre_asignatura"]:
                res["nombre_asignatura"] = sanitize_subject_name(m_name.group(1).strip())

            m_code = re.search(r"(?:Code|Código):\s*(\d{4,8})", l, re.IGNORECASE)
            if m_code and not res["codigo_asignatura"]:
                res["codigo_asignatura"] = m_code.group(1).strip()

            m_ects = re.search(r"(?:ECTS|Créditos|Credits):\s*([\d,.]+)", l, re.IGNORECASE)
            if m_ects:
                try:
                    res["creditos"]["total_ects"] = float(m_ects.group(1).replace(",", "."))
                except ValueError:
                    pass

            m_dept = re.search(r"(?:Department|Departamento|Área):\s*([^\n|]+)", l, re.IGNORECASE)
            if m_dept and not res["departamento"]:
                res["departamento"] = m_dept.group(1).strip()

        # 2. Temario / Units / Blocks / Section-bounded Contents
        in_contents = False
        for l in ([] if is_signed_guide else lines):
            if re.search(r"^(?:3\.\s*)?(?:COURSE\s+)?(?:CONTENTS|CONTENIDOS|TEMARIO|PROGRAMA|SYLLABUS)", l, re.IGNORECASE):
                in_contents = True
                continue
            if in_contents and re.search(r"^(?:4\.\s*)?(?:TEACHING|METODOLOGÍA|ACTIVIDADES|5\.\s*ASSESSMENT|EVALUACIÓN)", l, re.IGNORECASE):
                in_contents = False

            m_unit = re.search(r"^(Unit\s+\d+|Tema\s+\d+|Bloque\s+[I|V|X\d]+|Módulo\s+\d+)[:.\-–\s]+(.+)$", l, re.IGNORECASE)
            if m_unit:
                u_label = m_unit.group(1).strip()
                u_title = m_unit.group(2).strip()
                if not is_spurious_or_administrative_subject(u_title):
                    res["temario"].append({
                        "orden": u_label,
                        "titulo": u_title,
                        "contenidos": []
                    })
            elif in_contents:
                clean_topic = re.sub(r"\b\d+\s*hours?\b.*$", "", l, flags=re.IGNORECASE).strip()
                clean_topic = re.sub(r"\b\d+\s*horas?\b.*$", "", clean_topic, flags=re.IGNORECASE).strip()
                if 4 <= len(clean_topic) <= 120 and not any(kw in clean_topic.lower() for kw in ["contents", "total number", "credits", "approved by", "school board"]):
                    if not is_spurious_or_administrative_subject(clean_topic):
                        if not any(t["titulo"] == clean_topic for t in res["temario"]):
                            res["temario"].append({
                                "orden": f"Bloque {len(res['temario']) + 1}",
                                "titulo": clean_topic,
                                "contenidos": []
                            })

        # 3. Evaluación
        eval_lines = []
        in_eval = False
        for l in ([] if is_signed_guide else lines):
            if re.search(r"(?:5\.\s*ASSESSMENT|EVALUACIÓN|EVALUATION|SISTEMA DE EVALUACIÓN)", l, re.IGNORECASE):
                in_eval = True
                continue
            if in_eval and re.search(r"(?:6\.\s*BIBLIOGRAPHY|BIBLIOGRAFÍA|7\.\s*DOCENCIA|PROFESORADO)", l, re.IGNORECASE):
                in_eval = False
                break
            if in_eval:
                eval_lines.append(l)
                # Detectar pruebas evaluables y porcentajes
                m_pond = re.search(r"([A-Za-zÁÉÍÓÚáéíóúñ\s,–\-]{4,50})\s*[:=–]\s*(\d{1,2}(?:[.,]\d+)?)\s*%", l)
                if m_pond:
                    tarea_nom = m_pond.group(1).strip()
                    pond_val = float(m_pond.group(2).replace(",", "."))
                    if not any(ev["tarea"] == tarea_nom for ev in res["sistema_evaluacion"]):
                        res["sistema_evaluacion"].append({
                            "tarea": tarea_nom,
                            "instrumentos": "",
                            "ponderacion_porcentaje": pond_val
                        })
                # Detectar instrumentos específicos (ej. PEI1, PEI2, PEF)
                elif re.search(r"\b(PEI\d*|PEF|Continuous assessment|Examen final|Evaluación continua)\b", l, re.IGNORECASE):
                    crit_nom = l.strip()
                    if 4 <= len(crit_nom) <= 80 and not any(ev["tarea"] == crit_nom for ev in res["sistema_evaluacion"]):
                        res["sistema_evaluacion"].append({
                            "tarea": crit_nom,
                            "instrumentos": "Criterio de evaluación oficial",
                            "ponderacion_porcentaje": 0.0
                        })

        if eval_lines and not res["criterios_evaluacion"]:
            res["criterios_evaluacion"] = "\n".join(eval_lines[:15])

        # 4. Profesorado / Lecturers
        for l in lines:
            m_prof = re.search(r"(?:Lecturers?|Profesorado|Teaching staff):\s*([^\n]+)", l, re.IGNORECASE)
            if m_prof:
                profs_raw = m_prof.group(1).split(",")
                for p in profs_raw:
                    p_clean = p.strip()
                    if 4 <= len(p_clean) <= 60 and not any(p_clean == x["nombre_completo"] for x in res["profesorado"]):
                        res["profesorado"].append({"nombre_completo": p_clean, "coordinador": False})

    except Exception as e:
        logger.warning(f"Error al procesar stream PDF de guía docente: {e}")

    res["pdf_parse_duracion_seg"] = round(max(0.0, time.perf_counter() - parse_started), 6)
    return res


def _looks_like_structured_learning_guide(lines: list[str]) -> bool:
    """Detecta una plantilla de guía estructurada por sus etiquetas visibles."""
    text = " ".join(str(line or "") for line in lines[:80]).lower()
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return "guia de aprendizaje" in text and "datos de la asignatura" in text


def _looks_like_signed_learning_guide(lines: list[str]) -> bool:
    """Detecta una plantilla firmada por sus secciones académicas."""
    text = " ".join(str(line or "") for line in lines[:180]).lower()
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return (
        "guias docentes" in text
        and "competencias asociadas a materia/asignatura" in text
        and "programa de contenidos" in text
    )


def _is_footer_or_repeated_header(line: str) -> bool:
    normalized = " ".join(str(line or "").split()).lower()
    return (
        not normalized
        or normalized in {"guias", "docentes", "curso:"}
        or re.match(r"^\d+\s*/\s*\d+$", normalized) is not None
        or normalized.startswith(("cif:", "firma", "firmado electronicamente", "este documento firmado", "codigo seguro", "05/", "pag."))
    )


def _enrich_signed_learning_guide_from_lines(result: dict, lines: list[str]) -> None:
    """Extrae campos semánticos de una plantilla PDF académica firmada."""
    clean_lines = [" ".join(str(line or "").split()) for line in lines if str(line or "").strip()]

    # Cabecera: el nombre puede ocupar varias líneas y el código aparece en
    # una línea independiente entre paréntesis.
    header_index = next(
        (i for i, line in enumerate(clean_lines) if "guía docente de la asignatura" in line.lower()),
        None,
    )
    if header_index is not None:
        name_parts = []
        for line in clean_lines[header_index + 1:header_index + 10]:
            code_match = re.fullmatch(r"\(([^)]+)\)", line)
            if code_match:
                code = code_match.group(1).strip()
                if re.fullmatch(r"[A-Za-z0-9/\-]{4,12}", code):
                    result["codigo_asignatura"] = code
                break
            if _is_footer_or_repeated_header(line) or line.lower().startswith("fecha de aprobación"):
                continue
            name_parts.append(line)
        if name_parts:
            result["nombre_asignatura"] = sanitize_subject_name(" ".join(name_parts))

    for line in clean_lines[:35]:
        ects_match = re.search(r"cr[eé]ditos\s*:?\s*([\d.,]+)", line, re.IGNORECASE)
        if ects_match:
            try:
                result["creditos"]["total_ects"] = float(ects_match.group(1).replace(",", "."))
            except ValueError:
                pass
        department_match = re.match(r"(Departamento de .+?):\s*$", line, re.IGNORECASE)
        if department_match and not result.get("departamento"):
            result["departamento"] = department_match.group(1).strip()

    def add_unique(target: str, value: dict) -> None:
        if value and value not in result[target]:
            result[target].append(value)

    # Competencias: el texto descriptivo se parte entre páginas. Se vuelve a
    # unir hasta encontrar otra competencia o el siguiente bloque principal.
    competence_start = next(
        (i for i, line in enumerate(clean_lines) if "competencias asociadas a materia/asignatura" in line.lower()),
        None,
    )
    result_start = next(
        (i for i, line in enumerate(clean_lines) if "resultados de aprendizaje" in line.lower()),
        len(clean_lines),
    )
    current = None
    if competence_start is not None:
        for line in clean_lines[competence_start + 1:result_start]:
            if _is_footer_or_repeated_header(line) or line.upper().startswith("COMPETENCIAS "):
                continue
            match = re.match(r"^((?:CG|CE|CT)\d+)\s*[-–:]\s*(.+)$", line, re.IGNORECASE)
            if match:
                if current:
                    add_unique("competencias", current)
                current = {"codigo": match.group(1).upper(), "descripcion": match.group(2).strip()}
            elif current and len(line) >= 3:
                current["descripcion"] += " " + line
        if current:
            add_unique("competencias", current)

    # Resultados: se agrupan las líneas partidas y se cierra cada resultado en
    # un punto final, evitando incorporar pies de página firmados.
    program_start = next(
        (i for i, line in enumerate(clean_lines) if "programa de contenidos" in line.lower()),
        len(clean_lines),
    )
    if result_start < program_start:
        pending = ""
        for line in clean_lines[result_start + 1:program_start]:
            if _is_footer_or_repeated_header(line) or line.lower() == "el estudiantado será capaz de:":
                continue
            pending = f"{pending} {line}".strip()
            if line.endswith((".", ".)", ":")):
                add_unique("resultados_aprendizaje", {"descripcion": pending})
                pending = ""
        if pending:
            add_unique("resultados_aprendizaje", {"descripcion": pending})

    # Programa de contenidos: se conservan solo los temas numerados y se
    # fusionan las continuaciones de línea de la extracción PDF.
    bibliography_start = next(
        (i for i, line in enumerate(clean_lines[program_start + 1:], program_start + 1) if line.upper().startswith("BIBLIOGRAF")),
        len(clean_lines),
    )
    current_topic = None
    for line in clean_lines[program_start + 1:bibliography_start]:
        if _is_footer_or_repeated_header(line) or line.upper() in {"TEÓRICO", "TEORICO", "PRÁCTICO", "PRACTICO"} or line.lower().startswith("bloque "):
            continue
        match = re.match(r"^(Tema\s+\d+)\.\s*(.+)$", line, re.IGNORECASE)
        if match:
            if current_topic:
                add_unique("temario", current_topic)
            current_topic = {"orden": match.group(1), "titulo": match.group(2).strip(), "contenidos": []}
        elif current_topic and len(line) >= 3 and not line.upper().startswith(("METODOLOG", "EVALUACIÓN", "EVALUACION")):
            current_topic["titulo"] += " " + line
    if current_topic:
        add_unique("temario", current_topic)

    # Algunas plantillas publican ponderaciones entre paréntesis.
    evaluation_start = next(
        (i for i, line in enumerate(clean_lines) if line.upper().startswith("EVALUACIÓN ") or line.upper().startswith("EVALUACION ")),
        None,
    )
    if evaluation_start is not None:
        info_start = next(
            (i for i, line in enumerate(clean_lines[evaluation_start + 1:], evaluation_start + 1) if line.upper().startswith("INFORMACIÓN ADICIONAL") or line.upper().startswith("INFORMACION ADICIONAL")),
            len(clean_lines),
        )
        criteria = []
        for line in clean_lines[evaluation_start + 1:info_start]:
            if _is_footer_or_repeated_header(line):
                continue
            criteria.append(line)
            match = re.search(r"(?:\d+(?:\.\d+)*\.\s*)?([^()]{4,100})\((\d{1,3}(?:[.,]\d+)?)\s*%", line)
            if match:
                add_unique("sistema_evaluacion", {
                    "tarea": match.group(1).strip(),
                    "instrumentos": "",
                    "ponderacion_porcentaje": float(match.group(2).replace(",", ".")),
                })
        if criteria:
            result["criterios_evaluacion"] = "\n".join(criteria[:30])


def _enrich_structured_learning_guide_from_lines(result: dict, lines: list[str]) -> None:
    """Extrae los campos semánticos estables de una guía PDF estructurada."""
    for line in lines[:90]:
        match = re.search(r"nombre\s+de\s+la\s+asignatura\s+(\d{4,8})\s*[-–:]\s*(.+)$", line, re.IGNORECASE)
        if match:
            result["codigo_asignatura"] = match.group(1)
            result["nombre_asignatura"] = sanitize_subject_name(match.group(2).strip())
            continue
        match = re.search(r"(?:no|n[ºo])\s+de\s+cr[eé]ditos\s+([\d,.]+)\s*ects", line, re.IGNORECASE)
        if match:
            result["creditos"]["total_ects"] = float(match.group(1).replace(",", "."))
            continue
        match = re.search(r"car[aá]cter\s+(.+)$", line, re.IGNORECASE)
        if match:
            result["caracter"] = match.group(1).strip()
            continue
        match = re.search(r"idioma\s+de\s+impartici[oó]n\s+(.+)$", line, re.IGNORECASE)
        if match:
            result["idioma"] = match.group(1).strip()

    def add_unique(target: str, value: dict) -> None:
        if value and value not in result[target]:
            result[target].append(value)

    # El PDF repite el índice. Tomamos sólo el bloque real 4.1/4.2, que va
    # seguido de "5. Cronograma", no la entrada equivalente del índice.
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^4\.\s+Descripci[oó]n de la asignatura y temario$", line, re.IGNORECASE):
            if any(re.match(r"^4\.1\.", candidate, re.IGNORECASE) for candidate in lines[index + 1:index + 5]):
                start = index
                break
    if start is not None:
        end = next(
            (index for index in range(start + 1, len(lines)) if re.match(r"^5\.\s+Cronograma", lines[index], re.IGNORECASE)),
            len(lines),
        )
        for line in lines[start:end]:
            match = re.match(r"^(\d{1,2})\.\s+(.+)$", line)
            if match and not line.startswith("4.") and len(match.group(2).strip()) >= 4:
                title = match.group(2).strip()
                if not is_spurious_or_administrative_subject(title):
                    add_unique("temario", {"orden": match.group(1), "titulo": title, "contenidos": []})

    for line in lines:
        match = re.match(r"^(RA\s*\d+)\s*[-–:]\s*(.+)$", line, re.IGNORECASE)
        if match:
            add_unique("resultados_aprendizaje", {"codigo": re.sub(r"\s+", "", match.group(1).upper()), "descripcion": match.group(2).strip()})
            continue
        match = re.match(r"^((?:CB|CE|CG|CT)\s*\d*)\s*[-–:]\s*(.+)$", line, re.IGNORECASE)
        if match:
            add_unique("competencias", {"codigo": re.sub(r"\s+", "", match.group(1).upper()), "descripcion": match.group(2).strip()})

    # Las tablas de evaluación extraídas por pypdf suelen separar la
    # descripción y el porcentaje en líneas distintas.
    eval_start = next((
        i for i, line in enumerate(lines)
        if re.match(r"^6\.\s+Actividades y criterios de evaluaci", line, re.IGNORECASE)
        and any(re.match(r"^6\.1\.", candidate, re.IGNORECASE) for candidate in lines[i + 1:i + 8])
    ), None)
    if eval_start is not None:
        pending = ""
        for line in lines[eval_start:]:
            if re.match(r"^7\.\s+Recursos did[aá]cticos", line, re.IGNORECASE):
                break
            match = re.match(r"^\d+\s+(.+)$", line)
            if match and not re.match(r"^6\.\d", line):
                pending = match.group(1).strip()
            percent = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*%", line)
            if pending and percent:
                entry = {
                    "tarea": pending,
                    "instrumentos": "",
                    "ponderacion_porcentaje": float(percent.group(1).replace(",", ".")),
                }
                add_unique("sistema_evaluacion", entry)
                pending = ""


def _html_guide_richness(data: dict) -> int:
    """Puntúa la información recuperada sin depender del dominio de origen."""
    if not isinstance(data, dict):
        return -1
    score = 0
    for field in ("nombre_asignatura", "codigo_asignatura", "idioma", "departamento", "criterios_evaluacion"):
        if str(data.get(field) or "").strip():
            score += 4
    credits = data.get("creditos") or {}
    if any(value is not None for value in credits.values() if isinstance(credits, dict)):
        score += 5
    for field in ("temario", "sistema_evaluacion", "profesorado", "bibliografia", "competencias", "resultados_aprendizaje"):
        value = data.get(field)
        if isinstance(value, (list, tuple)):
            score += min(len(value), 12)
    return score


_LANG_CODE_TO_NAME = {
    "es": "Castellano",
    "ca": "Català",
    "gl": "Galego",
    "eu": "Euskara",
    "en": "English",
}


def _normalize_evaluation_breakdown(guide: dict) -> dict:
    """Calcula porcentajes agregados normalizados de evaluación."""
    eval_list = guide.get("sistema_evaluacion") or []
    breakdown = {
        "teoria_porcentaje": 0.0,
        "practicas_porcentaje": 0.0,
        "examen_final_porcentaje": 0.0,
        "evaluacion_continua_porcentaje": 0.0,
        "otras_actividades_porcentaje": 0.0,
    }
    if not isinstance(eval_list, list):
        return breakdown
    for item in eval_list:
        if not isinstance(item, dict):
            continue
        pct = item.get("ponderacion_porcentaje")
        if pct is None:
            continue
        try:
            val = float(pct)
        except (ValueError, TypeError):
            continue
        text = f"{item.get('tarea', '')} {item.get('instrumentos', '')}".lower()
        if any(w in text for w in ("examen", "exame", "azterketa", "prueba final", "proba final", "exàmen", "final exam", "written exam", "test final", "avaluacio final", "evaluacion final", "azterketa idatzia")):
            breakdown["examen_final_porcentaje"] += val
        elif any(w in text for w in ("práctica", "practica", "pràctica", "laboratorio", "laborategi", "praktikak", "lab", "taller", "obradoiro", "laboratory", "practicum")):
            breakdown["practicas_porcentaje"] += val
        elif any(w in text for w in ("teoría", "teoria", "teórico", "teoriko", "theory", "continguts teorics")):
            breakdown["teoria_porcentaje"] += val
        elif any(w in text for w in ("continua", "contínua", "etengabe", "etengabeko", "avaliación continua", "avaluació continuada", "continuous", "seguimiento", "participación", "coursework")):
            breakdown["evaluacion_continua_porcentaje"] += val
        else:
            breakdown["otras_actividades_porcentaje"] += val
    for k in breakdown:
        breakdown[k] = round(breakdown[k], 2)
    return breakdown


def _infer_subject_guide_language(guide: dict, full_text: str = "") -> str:
    """Infiere el idioma de impartición si no está explícito en los metadatos."""
    current = str(guide.get("idioma") or "").strip()
    if current and current.lower() not in {"castellano", "español", "es", "spanish", ""}:
        return current
    sample_text = full_text or " ".join([
        str(guide.get("nombre_asignatura") or ""),
        " ".join(str(t.get("titulo", "")) for t in guide.get("temario", []) if isinstance(t, dict)),
        " ".join(str(c.get("descripcion", "")) for c in guide.get("competencias", []) if isinstance(c, dict)),
        str(guide.get("criterios_evaluacion") or ""),
    ])
    if len(sample_text.strip()) > 25:
        detected = detect_academic_language(sample_text)
        if detected and detected in _LANG_CODE_TO_NAME:
            return _LANG_CODE_TO_NAME[detected]
    return current or "Castellano"


def _enrich_parsed_guide(guide: dict, full_text: str = "") -> dict:
    """Añade normalización de evaluación y verificación lingüística."""
    if not isinstance(guide, dict):
        return guide
    if guide.get("sistema_evaluacion") and "desglose_evaluacion" not in guide:
        guide["desglose_evaluacion"] = _normalize_evaluation_breakdown(guide)
    guide["idioma"] = _infer_subject_guide_language(guide, full_text)
    return guide


def parse_subject_guide(url: str, content: bytes, content_type: str = "") -> dict:
    """Analiza HTML/PDF mediante estrategias seleccionadas por su contenido.

    El formato del portal no se infiere a partir del código RUCT, el nombre de
    la universidad ni el dominio. Para HTML se ejecutan las estrategias
    semántica y tabular y se conserva la que extrae más información útil.
    """
    is_pdf = url.lower().endswith(".pdf") or "application/pdf" in content_type.lower() or content.startswith(b"%PDF")
    if is_pdf:
        parsed = parse_subject_guide_pdf_stream(content, url)
        return _enrich_parsed_guide(parsed)
    
    # Si es HTML
    try:
        html_text = content.decode("utf-8", errors="replace")
    except Exception:
        html_text = str(content)

    soup = BeautifulSoup(html_text, "html.parser")
    parsed_candidates = []
    for parser in (parse_generic_eees_subject_guide, parse_tabular_subject_guide):
        try:
            parsed = parser(soup, url)
        except Exception as exc:
            logger.debug("Estrategia HTML descartada para %s: %s", url, exc)
            continue
        if isinstance(parsed, dict):
            parsed_candidates.append(parsed)
    if not parsed_candidates:
        parsed = parse_generic_eees_subject_guide(soup, url)
    else:
        parsed = max(parsed_candidates, key=_html_guide_richness)
    return _enrich_parsed_guide(parsed, full_text=html_text)


def _guide_has_content(parsed_guide: dict) -> bool:
    """Indica si una respuesta contiene estructura docente aprovechable."""
    return bool(
        len(parsed_guide.get("temario", [])) > 0
        or len(parsed_guide.get("sistema_evaluacion", [])) > 0
        or len(parsed_guide.get("profesorado", [])) > 0
        or len(parsed_guide.get("competencias", [])) > 0
        or len(parsed_guide.get("resultados_aprendizaje", [])) > 0
        or parsed_guide.get("resumen")
    )


_SOFT_404_MARKERS = (
    "404", "not found", "page not found", "página no encontrada",
    "pagina no encontrada", "recurso no encontrado", "página no existe",
    "pagina no existe", "contenido no encontrado", "recurso no disponible",
    "page doesn’t exist", "page doesn't exist",
)
_GENERIC_LANDING_TITLES = frozenset({
    "inicio", "home", "welcome", "bienvenido", "bienvenida", "portal",
    "universidad", "universidad de", "error", "acceso denegado",
})


def detect_soft_404_response(
    requested_url: str,
    response_url: str,
    body: bytes,
    content_type: str = "",
) -> tuple[bool, str, str]:
    """Detecta páginas 200 que son realmente un 404 o una portada genérica.

    La detección es deliberadamente estricta: exige un marcador inequívoco,
    una redirección a una portada/error o un título genérico junto con una
    ruta de aterrizaje. Devuelve ``(detectado, huella, motivo)``.
    """
    if not body or len(body) > MAX_RESPONSE_SIZE_BYTES or "pdf" in str(content_type or "").casefold():
        return False, "", ""
    try:
        soup = BeautifulSoup(body, "html.parser")
    except Exception:
        return False, "", ""
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    headings = " ".join(node.get_text(" ", strip=True) for node in soup.find_all(["h1", "h2"], limit=3))
    visible_text = " ".join(soup.stripped_strings)
    title_low = " ".join(title.casefold().split())
    heading_low = " ".join(headings.casefold().split())
    text_low = " ".join(visible_text.casefold().split())
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical_url = normalize_url(str(canonical.get("href") or ""), base_url=response_url) if canonical else ""
    requested = normalize_url(requested_url)
    response = normalize_url(response_url or requested_url)
    response_path = urlparse(response).path.strip("/").casefold()
    requested_path = urlparse(requested).path.strip("/").casefold()

    marker = next((item for item in _SOFT_404_MARKERS if item in title_low or item in heading_low), "")
    if not marker:
        marker = next((item for item in _SOFT_404_MARKERS if item in text_low[:5000]), "")
    redirected_to_landing = bool(
        response
        and requested
        and response != requested
        and len(response_path.split("/")) <= 1
        and len(requested_path.split("/")) >= 2
    )
    canonical_landing = bool(
        canonical_url
        and requested
        and canonical_url != requested
        and len(urlparse(canonical_url).path.strip("/").split("/")) <= 1
        and len(requested_path.split("/")) >= 2
    )
    generic_landing = bool(
        (title_low in _GENERIC_LANDING_TITLES or heading_low in _GENERIC_LANDING_TITLES)
        and (not requested_path or len(requested_path.split("/")) >= 2)
        and (redirected_to_landing or canonical_landing or len(text_low) < 1200)
    )
    if not (marker or redirected_to_landing or canonical_landing or generic_landing):
        return False, "", ""

    fingerprint_source = "|".join((
        title_low,
        heading_low[:300],
        canonical_url or response,
        re.sub(r"\s+", " ", visible_text.casefold())[:2000],
    ))
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8", errors="ignore")).hexdigest()
    reason = "marcador_404" if marker else "redireccion_portada" if redirected_to_landing else "canonical_portada" if canonical_landing else "portada_generica"
    return True, fingerprint, reason


_DOMAIN_METRIC_FIELDS = (
    "candidate_urls_generated", "candidate_urls_requested", "cache_hits",
    "negative_cache_hits", "robots_denied", "http_200", "http_404",
    "http_other", "request_errors", "soft404_detected", "soft404_route_skips",
    "circuit_host_skips", "unproductive_host_skips",
)
_UNIVERSITY_METRIC_FIELDS = (
    "guide_subjects_considered", "guide_subjects_not_found", "processed_guides",
    "cached_hits", "resumed_subjects", "negative_cache_hits",
    "guide_discovery_cache_hits",
    "guide_discovery_spa_attempts", "guide_discovery_spa_fallbacks",
    "guide_shared_discovery_urls",
    "guide_candidate_urls_generated", "guide_candidate_urls_requested",
    "guide_candidate_urls_pruned",
    "guide_http_200", "guide_http_404", "guide_http_other", "guide_request_errors",
    "guide_robots_denied", "guide_identity_rejected", "guide_spa_fallbacks",
    "guide_soft404_detected", "guide_soft404_route_skips", "guide_circuit_host_skips",
    "guide_unproductive_host_skips",
    "guide_pdf_parse_count", "guide_pdf_parse_time", "guide_ocr_used",
    "enriched_degrees", "promoted_candidates",
)


def _domain_metrics(stats: dict, url: str) -> dict:
    """Obtiene un contador por host sin introducir perfiles de universidades."""
    parsed = urlparse(str(url or ""))
    domain = (parsed.netloc or "<sin-dominio>").lower().split("@")[-1]
    bucket = stats.setdefault("by_domain", {}).setdefault(
        domain,
        {field: 0 for field in _DOMAIN_METRIC_FIELDS},
    )
    return bucket


def _merge_domain_metrics(target: dict, source: dict) -> None:
    """Suma métricas por dominio devueltas por trabajadores independientes."""
    for domain, values in (source or {}).items():
        bucket = target.setdefault(domain, {field: 0 for field in _DOMAIN_METRIC_FIELDS})
        for field in _DOMAIN_METRIC_FIELDS:
            bucket[field] += int(values.get(field, 0) or 0)


def _record_guide_request_failure(stats: dict, error: Exception, url: str = "") -> None:
    """Clasifica fallos HTTP que el downloader propaga como excepciones."""
    message = str(error or "")
    match = re.search(r"\bHTTP(?:/\d(?:\.\d)?)?\s+(\d{3})\b", message, re.IGNORECASE)
    if not match:
        match = re.search(r"\b([45]\d{2})\b", message)
    status_code = int(match.group(1)) if match else 0
    if status_code == 404:
        stats["guide_http_404"] += 1
        if url:
            _domain_metrics(stats, url)["http_404"] += 1
    elif status_code:
        stats["guide_http_other"] += 1
        if url:
            _domain_metrics(stats, url)["http_other"] += 1
    else:
        stats["guide_request_errors"] += 1
        if url:
            _domain_metrics(stats, url)["request_errors"] += 1


def _plan_selection_priority(data: dict) -> tuple:
    """Ordena planes para que las muestras limitadas sean representativas.

    El catálogo puede contener muchos registros de identidad sin plan BOE
    disponible. Si ``limit_degrees`` se usa sobre ese catálogo, escoger los
    primeros ficheros produce una muestra que no ejercita la Parte 4. La
    prioridad favorece, en este orden, planes verificados, planes con
    asignaturas, planes completos y un mayor número de elementos.
    """
    if not isinstance(data, dict):
        return (0, 0, 0, 0)
    plan = data.get("plan_estudios") or {}
    candidate_plan = data.get("candidato_plan_estudios") or {}
    if not isinstance(plan, dict) or not plan.get("elementos_curriculares"):
        plan = candidate_plan if isinstance(candidate_plan, dict) else plan
    elements = plan.get("elementos_curriculares") or [] if isinstance(plan, dict) else []
    element_count = sum(1 for item in elements if isinstance(item, dict) and str(item.get("nombre_elemento") or "").strip())
    source_state = str(data.get("estado_fuente") or data.get("estado_calidad") or "").lower()
    is_candidate = bool(data.get("candidato_plan_estudios")) and not data.get("plan_estudios")
    source_rank = 3 if source_state == "verificada" else 2 if is_candidate and element_count else 1 if element_count else 0
    complete = 1 if isinstance(plan, dict) and plan.get("plan_completo") else 0
    return (source_rank, 1 if element_count else 0, complete, min(element_count, 10000))


def _select_plan_items_for_limit(plan_items: list[dict], limit_degrees: int | None) -> tuple[list[dict], int]:
    """Selecciona planes por universidad y devuelve (seleccionados, omitidos)."""
    if limit_degrees is None:
        return list(plan_items), 0
    limit = max(0, int(limit_degrees))
    ranked = sorted(
        plan_items,
        key=lambda item: _plan_selection_priority(item.get("data") or {}),
        reverse=True,
    )
    selected = ranked[:limit]
    return selected, max(0, len(plan_items) - len(selected))


# =============================================================================
# PROCESAMIENTO SECUENCIAL POR UNIVERSIDAD (CORTESÍA ÉTICA)
# =============================================================================

def _process_single_university_guides(
    u_code: str,
    degree_items: list,
    cache: SubjectGuideCache,
    downloader: RUCTDownloader,
    force: bool = False,
    negative_registry: RunNegativeURLRegistry | None = None,
) -> dict:
    """
    Procesa de forma 100% secuencial y cortés todas las titulaciones de una única universidad.
    Garantiza que ningún dominio universitario reciba peticiones simultáneas.
    """
    stats = {
        "university_code": str(u_code).zfill(3),
        "enriched_degrees": 0,
        "processed_guides": 0,
        "cached_hits": 0,
        "candidate_degrees_inspected": 0,
        "candidate_guides_processed": 0,
        "promoted_candidates": 0,
        "guide_subjects_considered": 0,
        "guide_subjects_not_found": 0,
        "guide_identity_rejected": 0,
        "guide_discovery_files": 0,
        "guide_discovery_urls": 0,
        "guide_discovery_blocked": 0,
        "guide_discovery_cache_hits": 0,
        "guide_discovery_spa_attempts": 0,
        "guide_discovery_spa_fallbacks": 0,
        "guide_shared_discovery_urls": 0,
        "guide_spa_fallbacks": 0,
        "guide_candidate_urls_generated": 0,
        "guide_candidate_urls_requested": 0,
        "guide_candidate_urls_pruned": 0,
        "guide_http_200": 0,
        "guide_http_404": 0,
        "guide_http_other": 0,
        "guide_request_errors": 0,
        "guide_robots_denied": 0,
        "guide_soft404_detected": 0,
        "guide_soft404_route_skips": 0,
        "guide_circuit_host_skips": 0,
        "guide_unproductive_host_skips": 0,
        "guide_pdf_parse_count": 0,
        "guide_pdf_parse_time": 0.0,
        "guide_ocr_used": 0,
        "guide_quality_score_total": 0.0,
        "guide_quality_scored": 0,
        "resumed_subjects": 0,
        "negative_cache_hits": 0,
        "by_domain": {},
    }
    revalidate_sources = bool(FULL_REVALIDATION or force)
    process_candidates = os.getenv("CRAWLER_P4_PROCESS_CANDIDATES", "1").strip().lower() in {
        "1", "true", "yes", "si", "sí"
    }
    discovery_index = None
    discovery_attempted = False
    # La revalidación total debe volver a consultar fuentes antiguas, pero no
    # repetir una URL que ya ha demostrado ser permanentemente inexistente en
    # esta misma ejecución. La caché persistente sigue respetando su política
    # normal fuera de ``force``/``FULL_REVALIDATION``.
    run_negative_urls: set[str] = set()
    negative_registry = negative_registry or RunNegativeURLRegistry()

    for item in degree_items:
        raise_if_shutdown_requested()
        p_path = item["p_path"]
        data = item.get("data")
        if data is None:
            try:
                with open(p_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception as exc:
                logger.warning("No se pudo leer el plan %s: %s", p_path, exc)
                continue
        d_code = data.get("codigo_estudio", "")
        downloader.set_degree_context(d_code)
        u_web = data.get("web", "") or data.get("web_fuente_directa_url", "")
        plan = data.get("plan_estudios") or {}
        elementos = plan.get("elementos_curriculares") or []
        candidate_mode = False
        degree_modified = False

        # Los candidatos parciales permanecen en cuarentena, pero sus guías
        # pueden aportar evidencia útil para una posterior promoción. Nunca se
        # mezclan con ``plan_estudios`` durante este enriquecimiento.
        if not elementos and process_candidates:
            candidate_plan = data.get("candidato_plan_estudios") or {}
            candidate_elements = candidate_plan.get("elementos_curriculares") or []
            if candidate_elements:
                plan = candidate_plan
                elementos = candidate_elements
                candidate_mode = True
                stats["candidate_degrees_inspected"] += 1

        if not elementos:
            continue

        for elem in elementos:
            raise_if_shutdown_requested()
            stats["guide_subjects_considered"] += 1
            if _can_resume_guide_element(elem, revalidate_sources):
                stats["resumed_subjects"] += 1
                continue
            asig_code = elem.get("codigo_asignatura") or elem.get("codigo")
            asig_name = elem.get("nombre_elemento", "")
            degree_identity = str(
                data.get("codigo_estudio") or data.get("codigo_plan") or data.get("plan_id") or ""
            ).strip()
            academic_year_identity = str(
                data.get("curso_academico") or data.get("anio_academico") or data.get("academic_year") or ""
            ).strip()
            language_identity = str(elem.get("idioma") or data.get("idioma_plan") or "").strip()

            # 1. La caché es válida durante su TTL. Al caducar, la URL conocida
            # se vuelve a resolver para detectar cambios o desplazamientos del
            # contenido a otra URL; ``force`` permite una revalidación total.
            url_directa = elem.get("url_guia_docente")
            cached_data = cache.get(
                url=url_directa,
                u_code=u_code,
                asig_code=asig_code,
                degree_code=degree_identity,
                plan_code=degree_identity,
                academic_year=academic_year_identity,
                language=language_identity,
            )
            if cached_data and not _subject_guide_identity_matches(
                asig_name,
                asig_code,
                cached_data,
                source_url=url_directa or cached_data.get("url_guia_docente", ""),
            ):
                # Una entrada antigua o una URL reutilizada no puede saltarse
                # el mismo control de identidad aplicado a las respuestas de
                # red. Se invalida solo para esta asignatura y se continúa con
                # la resolución normal.
                cached_data = None
                stats["guide_identity_rejected"] += 1
            if cached_data and not revalidate_sources:
                elem["guia_docente"] = cached_data
                elem["estado_guia_docente"] = "verificada"
                elem["fecha_ultima_comprobacion_guia"] = datetime.now().isoformat()
                stats["cached_hits"] += 1
                degree_modified = True
                continue

            # 2. Resolución de URLs candidatas mediante el Fast-Path Universal
            if not discovery_attempted:
                discovery_attempted = True
                shared_records = []
                get_discovery = getattr(getattr(downloader, "ledger", None), "get_discovery_evidence", None)
                if callable(get_discovery):
                    shared_records = get_discovery(
                        str(u_code).zfill(3),
                        limit=SUBJECT_GUIDE_DISCOVERY_MAX_URLS,
                        max_age_seconds=SUBJECT_GUIDE_DISCOVERY_CACHE_TTL_SECONDS,
                    ) or []
                    stats["guide_shared_discovery_urls"] = len(shared_records)
                if u_web:
                    discovery_index = build_subject_guide_discovery_index(downloader, u_web)
                    stats["guide_discovery_cache_hits"] += int(bool(discovery_index.get("cache_hit")))
                    stats["guide_discovery_spa_attempts"] += int(discovery_index.get("spa_attempts", 0) or 0)
                    stats["guide_discovery_spa_fallbacks"] += int(discovery_index.get("spa_fallbacks", 0) or 0)
                    stats["guide_discovery_files"] += int(discovery_index.get("files_read", 0))
                    stats["guide_discovery_urls"] += len(
                        discovery_index.get("records") or discovery_index.get("urls", [])
                    )
                    stats["guide_discovery_blocked"] += int(discovery_index.get("blocked", 0))
                    local_records = discovery_index.get("records") or discovery_index.get("urls", [])
                    combined_records = []
                    seen_discovery_urls = set()
                    for record in list(shared_records) + list(local_records):
                        candidate_url = record.get("url") if isinstance(record, dict) else record
                        candidate_url = normalize_url(str(candidate_url or ""))
                        if candidate_url and candidate_url not in seen_discovery_urls:
                            seen_discovery_urls.add(candidate_url)
                            if isinstance(record, dict):
                                enriched_record = dict(record)
                                enriched_record["url"] = candidate_url
                            else:
                                enriched_record = {"url": candidate_url}
                            combined_records.append(enriched_record)
                    discovery_index = dict(discovery_index)
                    discovery_index["records"] = combined_records
                    discovery_index["urls"] = [record["url"] for record in combined_records]
                elif shared_records:
                    discovery_index = {
                        "records": shared_records,
                        "urls": [record.get("url", "") for record in shared_records],
                    }
            pruning_stats = {}
            candidate_urls = resolve_candidate_subject_guide_urls(
                elem=elem,
                u_code=u_code,
                u_web=u_web,
                d_code=d_code,
                discovery_index=discovery_index,
                negative_registry=negative_registry,
                negative_urls=run_negative_urls,
                pruning_stats=pruning_stats,
            )
            stats["guide_candidate_urls_generated"] += len(candidate_urls)
            stats["guide_candidate_urls_pruned"] += int(pruning_stats.get("candidate_urls_pruned", 0) or 0)
            for candidate_url in candidate_urls:
                _domain_metrics(stats, candidate_url)["candidate_urls_generated"] += 1

            # 3. Descarga y parsing híbrido en memoria (HTML / PDF stream)
            found_current_guide = False
            for c_url in candidate_urls:
                if (
                    negative_registry.contains(c_url)
                    or c_url in run_negative_urls
                    or (not revalidate_sources and cache.is_negative(c_url))
                ):
                    stats["negative_cache_hits"] += 1
                    _domain_metrics(stats, c_url)["negative_cache_hits"] += 1
                    continue
                if negative_registry.contains_soft404_route(c_url):
                    stats["negative_cache_hits"] += 1
                    stats["guide_soft404_route_skips"] += 1
                    _domain_metrics(stats, c_url)["negative_cache_hits"] += 1
                    _domain_metrics(stats, c_url)["soft404_route_skips"] += 1
                    continue
                if negative_registry.contains_circuit_host(c_url):
                    stats["guide_circuit_host_skips"] += 1
                    _domain_metrics(stats, c_url)["circuit_host_skips"] += 1
                    continue
                if negative_registry.contains_unproductive_host(c_url):
                    stats["guide_unproductive_host_skips"] += 1
                    _domain_metrics(stats, c_url)["unproductive_host_skips"] += 1
                    continue

                if not revalidate_sources:
                    cached_candidate = cache.get(
                        url=c_url,
                        u_code=u_code,
                        asig_code=asig_code,
                        degree_code=degree_identity,
                        plan_code=degree_identity,
                        academic_year=academic_year_identity,
                        language=language_identity,
                    )
                    if cached_candidate and _subject_guide_identity_matches(
                        asig_name,
                        asig_code,
                        cached_candidate,
                        source_url=c_url,
                    ) and _guide_has_content(cached_candidate):
                        elem["guia_docente"] = cached_candidate
                        elem["url_guia_docente"] = c_url
                        elem["estado_guia_docente"] = "verificada"
                        elem["fecha_ultima_comprobacion_guia"] = datetime.now().isoformat()
                        stats["cached_hits"] += 1
                        _domain_metrics(stats, c_url)["cache_hits"] += 1
                        negative_registry.observe_host_result(c_url, positive=True)
                        degree_modified = True
                        found_current_guide = True
                        break
                if getattr(downloader, "respect_robots", True):
                    allowed, _ = downloader.robots_policy.check(c_url)
                    if not allowed:
                        run_negative_urls.add(c_url)
                        negative_registry.add(c_url)
                        stats["guide_robots_denied"] += 1
                        _domain_metrics(stats, c_url)["robots_denied"] += 1
                        if not revalidate_sources:
                            cache.mark_negative(c_url)
                        logger.info("[robots.txt] Guía docente omitida: %s", c_url)
                        continue
                resp = None
                try:
                    stats["guide_candidate_urls_requested"] += 1
                    _domain_metrics(stats, c_url)["candidate_urls_requested"] += 1
                    resp = downloader._request_with_retry(c_url, stream=True, robots_prechecked=True)
                    status_code = int(getattr(resp, "status_code", 0) or 0)
                    if status_code == 200:
                        stats["guide_http_200"] += 1
                        _domain_metrics(stats, c_url)["http_200"] += 1
                        c_type = resp.headers.get("Content-Type", "")
                        chunks, total = [], 0
                        for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                            if chunk:
                                total += len(chunk)
                                if total > MAX_RESPONSE_SIZE_BYTES:
                                    raise ValueError("Guía docente demasiado grande")
                                chunks.append(chunk)
                        body = b"".join(chunks)
                        downloader.store_response_content(c_url, resp, body)
                        soft404, soft404_fingerprint, soft404_reason = detect_soft_404_response(
                            c_url,
                            str(getattr(resp, "url", "") or c_url),
                            body,
                            c_type,
                        )
                        if soft404:
                            stats["guide_soft404_detected"] += 1
                            _domain_metrics(stats, c_url)["soft404_detected"] += 1
                            run_negative_urls.add(c_url)
                            negative_registry.add(c_url)
                            negative_registry.observe_host_result(c_url, negative=True)
                            negative_registry.mark_soft404(c_url, soft404_fingerprint)
                            cache.mark_negative(c_url, reason=f"soft404:{soft404_reason}")
                            logger.info("[soft-404] Respuesta 200 descartada para %s (%s)", c_url, soft404_reason)
                            continue
                        parsed_guide = parse_subject_guide(c_url, body, c_type)
                        if c_url.lower().endswith(".pdf") or "application/pdf" in c_type.lower() or body.startswith(b"%PDF"):
                            stats["guide_pdf_parse_count"] += 1
                            stats["guide_pdf_parse_time"] += float(parsed_guide.get("pdf_parse_duracion_seg", 0.0) or 0.0)
                            stats["guide_ocr_used"] += int(bool(parsed_guide.get("ocr_usado")))
                        identity_ok = _subject_guide_identity_matches(
                            asig_name, asig_code, parsed_guide, source_url=c_url
                        )
                        has_content = _guide_has_content(parsed_guide)

                        # Las guías servidas por React/Vue/Angular pueden
                        # devolver un HTML shell sin nombre ni contenido. Se
                        # renderiza solo esa candidata, nunca el portal
                        # completo, y se vuelve a aplicar identidad después.
                        enable_spa_fallback = os.getenv("CRAWLER_P4_ENABLE_SPA_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}
                        if enable_spa_fallback and "application/pdf" not in c_type.lower() and (not identity_ok or not has_content):
                            try:
                                from spa_crawler import SPALayoutCrawler
                                spa_result = SPALayoutCrawler.get_shared_instance().render_spa_page(c_url)
                                if getattr(spa_result, "is_download", False) and getattr(spa_result, "content_bytes", b""):
                                    rendered_body = spa_result.content_bytes
                                    rendered_type = "application/pdf"
                                elif str(spa_result).strip():
                                    rendered_body = str(spa_result).encode("utf-8", errors="replace")
                                    rendered_type = "text/html"
                                else:
                                    rendered_body = b""
                                    rendered_type = ""
                                if rendered_body:
                                    rendered_guide = parse_subject_guide(c_url, rendered_body, rendered_type)
                                    if "application/pdf" in rendered_type.lower() or rendered_body.startswith(b"%PDF"):
                                        stats["guide_pdf_parse_count"] += 1
                                        stats["guide_pdf_parse_time"] += float(rendered_guide.get("pdf_parse_duracion_seg", 0.0) or 0.0)
                                        stats["guide_ocr_used"] += int(bool(rendered_guide.get("ocr_usado")))
                                    if _subject_guide_identity_matches(asig_name, asig_code, rendered_guide, source_url=c_url):
                                        parsed_guide = rendered_guide
                                        identity_ok = True
                                        has_content = _guide_has_content(parsed_guide)
                                        if has_content:
                                            stats["guide_spa_fallbacks"] += 1
                            except Exception as spa_error:
                                logger.debug("Fallback SPA de guía no disponible para %s: %s", c_url, spa_error)

                        if not identity_ok:
                            stats["guide_identity_rejected"] += 1
                            run_negative_urls.add(c_url)
                            negative_registry.add(c_url)
                            negative_registry.observe_host_result(c_url, negative=True)
                            cache.mark_negative(c_url)
                            logger.info(
                                "[identidad] Guía descartada para %s: la respuesta no corresponde a la asignatura",
                                asig_name or asig_code,
                            )
                            continue
                        if not has_content:
                            run_negative_urls.add(c_url)
                            negative_registry.add(c_url)
                            negative_registry.observe_host_result(c_url, negative=True)
                            cache.mark_negative(c_url)
                            continue

                        annotate_subject_guide_quality(
                            parsed_guide,
                            expected_name=asig_name,
                            expected_code=asig_code,
                            source_url=c_url,
                        )
                        quality_info = parsed_guide.get("calidad_extraccion") or {}
                        stats["guide_quality_score_total"] += float(quality_info.get("puntuacion") or 0.0)
                        stats["guide_quality_scored"] += 1

                        final_asig_code = parsed_guide.get("codigo_asignatura") or asig_code or ""
                        cache.set(
                            url=c_url,
                            data=parsed_guide,
                            u_code=u_code,
                            asig_code=final_asig_code,
                            nombre=asig_name,
                            degree_code=degree_identity,
                            plan_code=degree_identity,
                            academic_year=academic_year_identity,
                            language=language_identity,
                        )
                        negative_registry.observe_host_result(c_url, positive=True)
                        elem["guia_docente"] = parsed_guide
                        elem["url_guia_docente"] = c_url
                        elem["estado_guia_docente"] = "verificada"
                        elem["fecha_ultima_comprobacion_guia"] = datetime.now().isoformat()
                        stats["processed_guides"] += 1
                        if candidate_mode:
                            stats["candidate_guides_processed"] += 1
                        degree_modified = True
                        found_current_guide = True
                        break
                    elif status_code == 404:
                        run_negative_urls.add(c_url)
                        negative_registry.add(c_url)
                        negative_registry.observe_host_result(c_url, negative=True)
                        stats["guide_http_404"] += 1
                        _domain_metrics(stats, c_url)["http_404"] += 1
                        cache.mark_negative(c_url)
                    elif status_code == 403:
                        stats["guide_http_other"] += 1
                        _domain_metrics(stats, c_url)["http_other"] += 1
                        if not revalidate_sources:
                            cache.mark_negative(c_url)
                    elif status_code:
                        stats["guide_http_other"] += 1
                        _domain_metrics(stats, c_url)["http_other"] += 1
                except HostCircuitOpenException as circuit_error:
                    negative_registry.mark_circuit_host(c_url)
                    stats["guide_circuit_host_skips"] += 1
                    _domain_metrics(stats, c_url)["circuit_host_skips"] += 1
                    logger.info("[circuit-breaker] Host omitido hasta el final del run: %s", circuit_error)
                    continue
                except SkipUniversityException:
                    _record_guide_request_failure(stats, SkipUniversityException("circuit breaker"), c_url)
                    print(f" [AVISO CORTOCIRCUITO] Omitiendo guías de la universidad [{u_code}] por sobrecarga del servidor.")
                    break
                except Exception as e:
                    if re.search(r"\b404\b", str(e), re.IGNORECASE):
                        run_negative_urls.add(c_url)
                        negative_registry.add(c_url)
                        cache.mark_negative(c_url)
                    _record_guide_request_failure(stats, e, c_url)
                    logger.debug(f"Error al descargar guía '{c_url}': {e}")
                finally:
                    if resp is not None:
                        try:
                            resp.close()
                        except Exception as close_error:
                            logger.debug("No se pudo cerrar la respuesta HTTP de la guía: %s", close_error, exc_info=True)

            # Si ninguna fuente actual respondió o produjo contenido válido,
            # conservar la última guía fiable en vez de dejar un hueco.
            if not found_current_guide and cached_data:
                elem["guia_docente"] = cached_data
                elem["estado_guia_docente"] = "respaldo_ultima_fuente"
                elem["fecha_ultima_comprobacion_guia"] = datetime.now().isoformat()
                stats["cached_hits"] += 1
                degree_modified = True
            elif not found_current_guide:
                elem["estado_guia_docente"] = "no_encontrada"
                elem["fecha_ultima_comprobacion_guia"] = datetime.now().isoformat()
                stats["guide_subjects_not_found"] += 1
                degree_modified = True

        if candidate_mode and degree_modified:
            # La evidencia de las guías no publica por sí sola el candidato.
            # Solo se promociona si, tras el enriquecimiento, supera el mismo
            # control de identidad, fuente y completitud que el resto del
            # pipeline.
            source_type = data.get("origen_fuente") or "web_oficial_universidad"
            assessment = apply_plan_quality(data, plan, source_type)
            if assessment.get("publicable"):
                data["estado_fuente"] = "verificada"
                stats["promoted_candidates"] = stats.get("promoted_candidates", 0) + 1

        if degree_modified:
            atomic_json_dump(data, p_path)
            stats["enriched_degrees"] += 1

    return stats


def _process_university_guides_isolated(
    u_code,
    degree_items,
    cache,
    force=False,
    ledger=None,
    negative_registry=None,
):
    """Procesa una universidad con sesión y estado de circuit breaker propios."""
    if negative_registry is None:
        negative_registry = getattr(cache, "_run_negative_registry", None)
    downloader = RUCTDownloader(ledger=ledger, phase="fase1_parte4")
    downloader.reset_university_context(str(u_code))
    try:
        return _process_single_university_guides(
            u_code,
            degree_items,
            cache,
            downloader,
            force,
            negative_registry=negative_registry,
        )
    finally:
        try:
            from spa_crawler import SPALayoutCrawler
            SPALayoutCrawler.close_thread_instance()
        except Exception as close_error:
            logger.debug("No se pudo cerrar la instancia SPA de la universidad %s: %s", u_code, close_error)
        downloader.close()
        cache.close()


# =============================================================================
# EJECUTOR PRINCIPAL DE LA FASE 1 - PARTE 4
# =============================================================================

def run_phase1_part4(
    limit_universities: int = None,
    limit_degrees: int = None,
    force: bool = False,
    max_workers: int = None,
    metrics_tracker=None,
    progress_emitter=None,
    target_univ_code: str = None,
    limit_univ: int = None,
    workers: int = None,
    robots_denied_university_codes: set[str] | None = None,
) -> dict:
    """
    FASE 1 - PARTE 4: Extracción de temarios, evaluación y contenido de guías docentes.
    Agrupa los planes de estudio por universidad y los procesa en paralelo (hasta max_workers universidades a la vez),
    manteniendo estricta cortesía secuencial por dominio.
    """
    print("\n" + "=" * 70)
    print("      INICIANDO FASE 1 - PARTE 4: GUÍAS DOCENTES Y TEMARIOS EEES")
    print("======================================================================")

    if limit_universities is None:
        limit_universities = limit_univ
    if max_workers is None:
        max_workers = workers
    if max_workers is None:
        max_workers = WEB_CRAWLER_WORKERS
    max_workers = max(1, int(max_workers))

    cache = SubjectGuideCache()
    ledger = CrawlLedger()
    negative_registry = RunNegativeURLRegistry()
    # Se asocia a la caché compartida para mantener la firma histórica del
    # worker (útil para integraciones y pruebas) sin perder coordinación entre
    # universidades concurrentes.
    try:
        cache._run_negative_registry = negative_registry
    except Exception:
        pass
    try:
        if not os.path.exists(PLANES_DIR):
            print(f" -> [AVISO] Directorio de planes {PLANES_DIR} no existe en disco. Omitiendo enriquecimiento.")
            return {
                "status": "skipped",
                "reason": "missing_plans_directory",
                "total_planes_inspeccionados": 0,
                "asignaturas_enriquecidas": 0,
            }

        plan_files = iter_plan_files(PLANES_DIR)
        universities = load_json_safe(UNIVERSIDADES_JSON, default=[])
        universities_map = {str(u.get("codigo")): u for u in universities if isinstance(u, dict) and u.get("codigo")} if isinstance(universities, list) else {}

        total_degrees = len(plan_files)
        print(f" -> {total_degrees} planes de estudio a inspeccionar en disco.")

        # Agrupar titulaciones por universidad para procesamiento concurrente seguro
        univ_groups = {}
        seen_univs = set()
        total_enqueued = 0
        plans_with_curriculum_selected = 0
        plans_skipped_by_limit = 0
        eligible_by_university = {}

        for p_path in plan_files:
            try:
                with open(p_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            u_code = data.get("universidad_codigo", "000")
            if TARGET_UNIVERSITY_CODES and str(u_code).zfill(3) not in TARGET_UNIVERSITY_CODES:
                continue
            if not data.get("web"):
                university_meta = universities_map.get(str(u_code))
                if university_meta and university_meta.get("web"):
                    data["web"] = university_meta["web"]

            if target_univ_code and str(u_code).zfill(3) != str(target_univ_code).zfill(3):
                continue

            if limit_universities is not None and len(seen_univs) >= max(0, limit_universities) and u_code not in seen_univs:
                continue

            if u_code:
                seen_univs.add(u_code)

            eligible_by_university.setdefault(u_code, []).append({
                "p_path": p_path,
                # El worker debe recibir la metadata enriquecida en memoria:
                # los planes históricos normalmente no almacenan ``web`` y
                # volver a abrir solo la ruta perdería el dominio del RUCT.
                "data": data,
            })

        robots_denied_codes = {
            str(code).strip().zfill(3)
            for code in (robots_denied_university_codes or set())
            if str(code).strip()
        }
        robots_denied_universities_skipped = 0
        for u_code, items in eligible_by_university.items():
            if str(u_code).zfill(3) in robots_denied_codes:
                robots_denied_universities_skipped += 1
                continue
            selected_items, skipped_items = _select_plan_items_for_limit(items, limit_degrees)
            univ_groups[u_code] = selected_items
            plans_skipped_by_limit += skipped_items
            plans_with_curriculum_selected += sum(
                1 for item in selected_items
                if _plan_selection_priority(item.get("data") or {})[1] > 0
            )
            total_enqueued += len(selected_items)

        # En ejecuciones dirigidas a una sola universidad, el modo normal
        # conserva el procesamiento secuencial por dominio. Para pruebas
        # completas muy grandes puede habilitarse explícitamente el particionado
        # de sus planes; cada lote mantiene su propio downloader y comparte la
        # caché protegida, sin alterar la semántica del resultado.
        split_university = os.getenv("CRAWLER_P4_SPLIT_UNIVERSITY", "0").strip().lower() in {
            "1", "true", "yes", "si", "sí"
        }
        if split_university and max_workers > 1:
            split_groups = {}
            for u_code, items in univ_groups.items():
                chunk_size = max(1, (len(items) + max_workers - 1) // max_workers)
                for chunk_idx in range(0, len(items), chunk_size):
                    task_id = f"{u_code}__lote_{chunk_idx // chunk_size + 1}"
                    split_groups[task_id] = (u_code, items[chunk_idx:chunk_idx + chunk_size])
            univ_groups = split_groups

        print(f" -> {len(univ_groups)} grupos de universidad para procesamiento en paralelo con {max_workers} trabajadores.")

        processed_guides = 0
        cached_hits = 0
        enriched_degrees = 0
        candidate_degrees_inspected = 0
        candidate_guides_processed = 0
        promoted_candidates = 0
        guide_subjects_considered = 0
        guide_subjects_not_found = 0
        guide_identity_rejected = 0
        guide_discovery_files = 0
        guide_discovery_urls = 0
        guide_discovery_blocked = 0
        guide_discovery_cache_hits = 0
        guide_discovery_spa_attempts = 0
        guide_discovery_spa_fallbacks = 0
        guide_shared_discovery_urls = 0
        guide_spa_fallbacks = 0
        guide_candidate_urls_generated = 0
        guide_candidate_urls_requested = 0
        guide_candidate_urls_pruned = 0
        guide_http_200 = 0
        guide_http_404 = 0
        guide_http_other = 0
        guide_request_errors = 0
        guide_robots_denied = 0
        guide_soft404_detected = 0
        guide_soft404_route_skips = 0
        guide_circuit_host_skips = 0
        guide_unproductive_host_skips = 0
        guide_pdf_parse_count = 0
        guide_pdf_parse_time = 0.0
        guide_ocr_used = 0
        guide_quality_score_total = 0.0
        guide_quality_scored = 0
        resumed_subjects = 0
        negative_cache_hits = 0
        metrics_by_university = {}
        metrics_by_domain = {}
        university_errors = 0
        cancelled = False
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            group_iterator = iter(univ_groups.items())
            futures = {}

            def _submit_next_group() -> bool:
                try:
                    group_code, group_value = next(group_iterator)
                except StopIteration:
                    return False
                futures[executor.submit(
                    _process_university_guides_isolated,
                    group_value[0] if isinstance(group_value, tuple) else group_code,
                    group_value[1] if isinstance(group_value, tuple) else group_value,
                    cache,
                    force,
                    ledger,
                )] = group_code
                return True

            for _ in range(min(max_workers, len(univ_groups))):
                _submit_next_group()

            completed = 0
            while futures:
                done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    u_code = futures.pop(future)
                    completed += 1
                    if is_shutdown_requested():
                        cancelled = True
                    try:
                        res = future.result()
                        processed_guides += res.get("processed_guides", 0)
                        cached_hits += res.get("cached_hits", 0)
                        enriched_degrees += res.get("enriched_degrees", 0)
                        candidate_degrees_inspected += res.get("candidate_degrees_inspected", 0)
                        candidate_guides_processed += res.get("candidate_guides_processed", 0)
                        promoted_candidates += res.get("promoted_candidates", 0)
                        guide_subjects_considered += res.get("guide_subjects_considered", 0)
                        guide_subjects_not_found += res.get("guide_subjects_not_found", 0)
                        guide_identity_rejected += res.get("guide_identity_rejected", 0)
                        guide_discovery_files += res.get("guide_discovery_files", 0)
                        guide_discovery_urls += res.get("guide_discovery_urls", 0)
                        guide_discovery_blocked += res.get("guide_discovery_blocked", 0)
                        guide_discovery_cache_hits += res.get("guide_discovery_cache_hits", 0)
                        guide_discovery_spa_attempts += res.get("guide_discovery_spa_attempts", 0)
                        guide_discovery_spa_fallbacks += res.get("guide_discovery_spa_fallbacks", 0)
                        guide_shared_discovery_urls += res.get("guide_shared_discovery_urls", 0)
                        guide_spa_fallbacks += res.get("guide_spa_fallbacks", 0)
                        guide_candidate_urls_generated += res.get("guide_candidate_urls_generated", 0)
                        guide_candidate_urls_requested += res.get("guide_candidate_urls_requested", 0)
                        guide_candidate_urls_pruned += res.get("guide_candidate_urls_pruned", 0)
                        guide_http_200 += res.get("guide_http_200", 0)
                        guide_http_404 += res.get("guide_http_404", 0)
                        guide_http_other += res.get("guide_http_other", 0)
                        guide_request_errors += res.get("guide_request_errors", 0)
                        guide_robots_denied += res.get("guide_robots_denied", 0)
                        guide_soft404_detected += res.get("guide_soft404_detected", 0)
                        guide_soft404_route_skips += res.get("guide_soft404_route_skips", 0)
                        guide_circuit_host_skips += res.get("guide_circuit_host_skips", 0)
                        guide_unproductive_host_skips += res.get("guide_unproductive_host_skips", 0)
                        guide_pdf_parse_count += res.get("guide_pdf_parse_count", 0)
                        guide_pdf_parse_time += res.get("guide_pdf_parse_time", 0.0)
                        guide_ocr_used += res.get("guide_ocr_used", 0)
                        guide_quality_score_total += res.get("guide_quality_score_total", 0.0)
                        guide_quality_scored += res.get("guide_quality_scored", 0)
                        resumed_subjects += res.get("resumed_subjects", 0)
                        negative_cache_hits += res.get("negative_cache_hits", 0)
                        worker_code = str(res.get("university_code") or u_code).zfill(3)
                        university_metrics = metrics_by_university.setdefault(worker_code, {})
                        for metric_name in _UNIVERSITY_METRIC_FIELDS:
                            university_metrics[metric_name] = (
                                university_metrics.get(metric_name, 0) + res.get(metric_name, 0)
                            )
                        _merge_domain_metrics(metrics_by_domain, res.get("by_domain", {}))
                    except CrawlerCancelled:
                        cancelled = True
                        for pending in futures:
                            pending.cancel()
                        futures.clear()
                        break
                    except Exception as exc:
                        university_errors += 1
                        print(f" [ERROR PARTE 4] Excepción en universidad [{u_code}]: {exc}")
                    if progress_emitter is not None:
                        progress_emitter.update_university(
                            completed,
                            len(univ_groups),
                            str(u_code),
                            str(u_code),
                        )
                    if not cancelled and not is_shutdown_requested():
                        _submit_next_group()
                    if cancelled:
                        for pending in futures:
                            pending.cancel()
                        futures.clear()
                        break

        elapsed = round(time.time() - start_time, 2)
        if metrics_tracker is not None:
            record_pdf_parse_aggregate = getattr(metrics_tracker, "record_pdf_parse_aggregate", None)
            if callable(record_pdf_parse_aggregate):
                record_pdf_parse_aggregate(guide_pdf_parse_count, guide_pdf_parse_time)
        print("\n" + "=" * 70)
        print(f"      FASE 1 - PARTE 4 FINALIZADA {'PARCIALMENTE' if university_errors else 'CON ÉXITO'}")
        print("======================================================================")
        print(f" -> Titulaciones enriquecidas con temario: {enriched_degrees}")
        print(f" -> Guías docentes descargadas de la red:  {processed_guides}")
        print(f" -> Candidatos parciales auditados:          {candidate_degrees_inspected}")
        print(f" -> Guías encontradas en cuarentena:         {candidate_guides_processed}")
        print(f" -> Candidatos promovidos tras validación:   {promoted_candidates}")
        print(f" -> Asignaturas con guía evaluada:            {guide_subjects_considered}")
        print(f" -> Asignaturas sin guía localizada:          {guide_subjects_not_found}")
        print(f" -> Guías rechazadas por identidad:          {guide_identity_rejected}")
        print(f" -> Ficheros de sitemap consultados:         {guide_discovery_files}")
        print(f" -> URLs académicas indexadas para guías:    {guide_discovery_urls}")
        print(f" -> Accesos de descubrimiento bloqueados:     {guide_discovery_blocked}")
        print(f" -> Índices de descubrimiento reutilizados:    {guide_discovery_cache_hits}")
        print(f" -> Renderizados SPA de descubrimiento:         {guide_discovery_spa_attempts}/{guide_discovery_spa_fallbacks}")
        print(f" -> Evidencias reutilizadas desde Parte 2:       {guide_shared_discovery_urls}")
        print(f" -> Guías recuperadas mediante SPA/OCR web:   {guide_spa_fallbacks}")
        print(f" -> PDFs de guías parseados/tiempo:             {guide_pdf_parse_count}/{round(guide_pdf_parse_time, 2)}s (OCR: {guide_ocr_used})")
        print(f" -> URL candidatas generadas/solicitadas:      {guide_candidate_urls_generated}/{guide_candidate_urls_requested}")
        print(f" -> Candidatas descartadas por poda inteligente: {guide_candidate_urls_pruned}")
        print(f" -> Respuestas 200/404/otras:                 {guide_http_200}/{guide_http_404}/{guide_http_other}")
        print(f" -> Bloqueos robots/errores de petición:      {guide_robots_denied}/{guide_request_errors}")
        print(f" -> Soft-404 detectados/URLs omitidas por patrón: {guide_soft404_detected}/{guide_soft404_route_skips}")
        print(f" -> URLs omitidas por cortocircuito de host:       {guide_circuit_host_skips}")
        print(f" -> URLs omitidas por host improductivo:           {guide_unproductive_host_skips}")
        print(f" -> Universidades omitidas por robots de Parte 2: {robots_denied_universities_skipped}")
        print(f" -> Planes seleccionados con currículo útil:   {plans_with_curriculum_selected}")
        print(f" -> Planes omitidos por límite de muestra:     {plans_skipped_by_limit}")
        average_quality = round(guide_quality_score_total / guide_quality_scored, 2) if guide_quality_scored else 0.0
        print(f" -> Cobertura media de campos extraídos:      {average_quality}%")
        print(f" -> Aciertos en caché SQLite WAL (0ms):    {cached_hits}")
        print(f" -> Asignaturas reanudadas sin repetir red: {resumed_subjects}")
        print(f" -> Candidatas negativas omitidas desde caché: {negative_cache_hits}")
        print(f" -> Tiempo total de procesamiento:        {elapsed}s\n")

        return {
            "status": "cancelled" if cancelled or is_shutdown_requested() else ("partial" if university_errors else "completed"),
            "plans_inspected": total_enqueued,
            "universities_processed": len(univ_groups),
            "university_codes_processed": sorted(
                str(code).zfill(3) for code in univ_groups if code
            ),
            "robots_denied_universities_skipped": robots_denied_universities_skipped,
            "plans_with_curriculum_selected": plans_with_curriculum_selected,
            "plans_skipped_by_limit": plans_skipped_by_limit,
            "enriched_degrees": enriched_degrees,
            "processed_guides": processed_guides,
            "cached_hits": cached_hits,
            "candidate_degrees_inspected": candidate_degrees_inspected,
            "candidate_guides_processed": candidate_guides_processed,
            "promoted_candidates": promoted_candidates,
            "guide_subjects_considered": guide_subjects_considered,
            "guide_subjects_not_found": guide_subjects_not_found,
            "guide_identity_rejected": guide_identity_rejected,
            "guide_discovery_files": guide_discovery_files,
            "guide_discovery_urls": guide_discovery_urls,
            "guide_discovery_blocked": guide_discovery_blocked,
            "guide_discovery_cache_hits": guide_discovery_cache_hits,
            "guide_discovery_spa_attempts": guide_discovery_spa_attempts,
            "guide_discovery_spa_fallbacks": guide_discovery_spa_fallbacks,
            "guide_shared_discovery_urls": guide_shared_discovery_urls,
            "guide_spa_fallbacks": guide_spa_fallbacks,
            "guide_candidate_urls_generated": guide_candidate_urls_generated,
            "guide_candidate_urls_requested": guide_candidate_urls_requested,
            "guide_candidate_urls_pruned": guide_candidate_urls_pruned,
            "guide_http_200": guide_http_200,
            "guide_http_404": guide_http_404,
            "guide_http_other": guide_http_other,
            "guide_request_errors": guide_request_errors,
            "guide_robots_denied": guide_robots_denied,
            "guide_soft404_detected": guide_soft404_detected,
            "guide_soft404_route_skips": guide_soft404_route_skips,
            "guide_circuit_host_skips": guide_circuit_host_skips,
            "guide_unproductive_host_skips": guide_unproductive_host_skips,
            "guide_pdf_parse_count": guide_pdf_parse_count,
            "guide_pdf_parse_time": round(guide_pdf_parse_time, 6),
            "guide_ocr_used": guide_ocr_used,
            "guide_quality_score_total": round(guide_quality_score_total, 2),
            "guide_quality_scored": guide_quality_scored,
            "guide_quality_average": average_quality,
            "resumed_subjects": resumed_subjects,
            "negative_cache_hits": negative_cache_hits,
            "metrics_by_university": metrics_by_university,
            "metrics_by_domain": metrics_by_domain,
            "errors": university_errors,
            "cancelled": bool(cancelled or is_shutdown_requested()),
            "persistence": {
                "subject_guide_cache_sqlite": "degraded" if getattr(cache, "_persistent_cache_disabled", False) else "ok",
                "crawl_ledger_sqlite": "degraded" if getattr(ledger, "_disabled", False) else "ok",
            },
            "elapsed_s": elapsed
        }
    finally:
        try:
            cache.close()
        except Exception as close_error:
            logger.warning("No se pudo cerrar la caché SQLite de guías: %s", close_error, exc_info=True)
        try:
            reconcile_processing = getattr(ledger, "reconcile_processing", None)
            if callable(reconcile_processing):
                reconcile_processing(
                    phase_prefix="fase1_parte4",
                    reason="intento sin respuesta al cerrar la Parte 4",
                )
            ledger.close()
        except Exception as close_error:
            logger.warning("No se pudo cerrar el ledger de guías: %s", close_error, exc_info=True)
