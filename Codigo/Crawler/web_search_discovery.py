"""Descubrimiento genérico de fuentes académicas mediante buscadores.

El buscador sólo aporta candidatos de navegación. Ningún resultado se
considera fuente curricular hasta que el crawler lo descarga y supera sus
controles normales de identidad, nivel académico y completitud.
"""

from __future__ import annotations

import base64
import html as html_module
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from config import (
    WEB_SEARCH_DISCOVERY_ENABLED,
    WEB_SEARCH_DISCOVERY_ENDPOINT,
    WEB_SEARCH_DISCOVERY_FALLBACK_ENDPOINTS,
    WEB_SEARCH_DISCOVERY_MAX_QUERIES,
    WEB_SEARCH_DISCOVERY_MAX_RESULTS,
    WEB_SEARCH_DISCOVERY_TIMEOUT,
    WEB_SEARCH_RETRY_DELAY,
)
from downloader import is_same_or_subdomain, normalize_url

logger = logging.getLogger(__name__)

_SEARCH_HOSTS = {
    "duckduckgo.com",
    "www.duckduckgo.com",
    "html.duckduckgo.com",
    "lite.duckduckgo.com",
    "bing.com",
    "www.bing.com",
    "google.com",
    "www.google.com",
}
_ACADEMIC_MARKERS = (
    "plan de estudios", "plan d'estudis", "pla d'estudis", "plan-estudios",
    "asignaturas", "assignatures", "materias", "curriculum", "curriculo",
    "estudios", "estudis", "titulacion", "titulació", "degree", "master",
    "máster", "grado", "grau", "doctorado", "doctorat", "programa",
    "study plan", "courses", "subjects", "syllabus",
)
_QUERY_STOPWORDS = {
    "para", "con", "del", "las", "los", "una", "uno", "por", "the", "and",
    "from", "of", "de", "en", "grado", "master", "máster", "universidad",
    "universitat", "universidade", "university", "official", "oficial",
}
_NON_INSTITUTIONAL_HOST_MARKERS = (
    "wikipedia.org", "wikimedia.org", "facebook.com", "instagram.com",
    "linkedin.com", "youtube.com", "twitter.com", "x.com",
)
_TOKEN_RE = re.compile(r"[a-z0-9áéíóúüñàèìòùç]{3,}", re.IGNORECASE)


def _ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()


def _tokens(value: str) -> list[str]:
    return [
        token for token in _TOKEN_RE.findall(_ascii_fold(value))
        if token not in _QUERY_STOPWORDS
    ]


def _search_degree_title(degree_title: str) -> str:
    """Reduce títulos administrativos a un núcleo útil para un buscador."""
    value = " ".join(str(degree_title or "").split())
    # Los catálogos suelen añadir "por la Universidad..." o una lista de
    # instituciones asociadas. Son metadatos de identidad, no términos que
    # deban formar parte de una consulta exacta.
    value = re.split(r"\s+por\s+(?:la|el|las|los)?\s*", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = value.split(";", 1)[0].strip(" ,")
    return value[:180].strip()


def _organisation_label(url: str) -> str:
    """Obtiene la etiqueta registrable de un host sin depender de un TLD concreto."""
    host = (urlparse(str(url or "")).hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = [part for part in host.split(".") if part]
    if len(parts) < 2:
        return host
    compound_suffixes = {
        ("com", "es"), ("edu", "es"), ("org", "es"), ("gob", "es"),
        ("co", "uk"), ("ac", "uk"),
    }
    suffix_size = 3 if len(parts) >= 3 and tuple(parts[-2:]) in compound_suffixes else 2
    return parts[-suffix_size]


def is_search_result_host_compatible(candidate_url: str, registered_url: str) -> bool:
    """Permite el mismo origen o un alias de organización conservador.

    El alias sólo resuelve cambios de subdominio/TLD de la misma etiqueta
    institucional. La validación semántica de la página sigue siendo obligatoria.
    """
    if not candidate_url or not registered_url:
        return False
    if is_same_or_subdomain(candidate_url, registered_url):
        return True
    candidate_label = _organisation_label(candidate_url)
    registered_label = _organisation_label(registered_url)
    return bool(candidate_label and registered_label and candidate_label == registered_label)


def _unwrap_result_url(raw_url: str, endpoint: str) -> str:
    raw = html_module.unescape(str(raw_url or "").strip())
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    for key in ("uddg", "url", "target", "u"):
        values = query.get(key)
        if values:
            decoded = unquote(values[0])
            if decoded.startswith("a1"):
                try:
                    encoded = decoded[2:]
                    encoded += "=" * (-len(encoded) % 4)
                    decoded = base64.urlsafe_b64decode(encoded).decode("utf-8", errors="ignore")
                except (ValueError, TypeError):
                    decoded = ""
            if decoded.startswith(("http://", "https://")):
                raw = decoded
                break
    normalized = normalize_url(raw)
    if not normalized:
        return ""
    host = (urlparse(normalized).hostname or "").lower()
    endpoint_host = (urlparse(endpoint).hostname or "").lower()
    if host in _SEARCH_HOSTS or host == endpoint_host:
        return ""
    return normalized


def _search_request_url(endpoint: str, query: str) -> str:
    """Añade la consulta sin romper endpoints que ya llevan parámetros."""
    separator = "&" if "?" in str(endpoint) else "?"
    return f"{endpoint}{separator}q={quote_plus(query)}"


def build_search_queries(university_name: str, degree_title: str, academic_level: str = "", limit: int | None = None) -> list[str]:
    """Construye consultas lingüísticas, sin códigos internos ni reglas locales."""
    university = " ".join(str(university_name or "").split())
    degree = _search_degree_title(degree_title)
    if not university or not degree:
        return []
    level = _ascii_fold(academic_level)
    level_terms = "master" if "master" in level else "grado" if "grado" in level else "doctorado" if "doctor" in level else "estudios"
    compact_degree = re.sub(
        r"^(?:graduad[oa](?:\s+o\s+graduada)?|máster(?:\s+universitario)?|master(?:\s+universitario)?|grado|doctor(?:ado)?)\s+(?:en|de)\s+",
        "",
        degree,
        flags=re.IGNORECASE,
    ).strip()
    compact_degree = compact_degree or degree
    queries = [
        f'{university} {degree} "plan de estudios"',
        f'{university} {level_terms} {compact_degree} "plan de estudios"',
    ]
    max_queries = WEB_SEARCH_DISCOVERY_MAX_QUERIES if limit is None else limit
    return list(dict.fromkeys(queries))[: max(0, int(max_queries))]


def build_institution_search_queries(university_name: str, limit: int = 1) -> list[str]:
    """Genera consultas de origen institucional, independientes de un proveedor."""
    name = " ".join(str(university_name or "").split())
    if not name:
        return []
    return [f'"{name}"'][: max(0, int(limit))]


def parse_search_results(raw_html: str, endpoint: str = WEB_SEARCH_DISCOVERY_ENDPOINT, limit: int | None = None) -> list[dict]:
    """Extrae resultados de Bing/DuckDuckGo HTML o RSS y enlaces directos."""
    if not raw_html:
        return []
    records = []
    seen = set()
    # Bing RSS es una alternativa estable cuando el HTML presenta un reto de
    # automatización; conservarlo aquí permite cambiar el endpoint por
    # configuración sin cambiar el pipeline.
    raw_text = str(raw_html)
    if re.search(r"<rss\b", raw_text, re.IGNORECASE):
        try:
            root = ET.fromstring(raw_text)
            for item in root.iter():
                if item.tag.rsplit("}", 1)[-1].lower() != "item":
                    continue
                fields = {
                    child.tag.rsplit("}", 1)[-1].lower(): (child.text or "").strip()
                    for child in list(item)
                }
                url = _unwrap_result_url(fields.get("link", ""), endpoint)
                if not url or url in seen:
                    continue
                seen.add(url)
                records.append({
                    "url": url,
                    "title": fields.get("title", ""),
                    "snippet": fields.get("description", ""),
                })
                if limit is not None and len(records) >= max(0, int(limit)):
                    return records
        except ET.ParseError:
            logger.debug("RSS de buscador inválido; se intenta como HTML")

    soup = BeautifulSoup(raw_text, "html.parser")

    anchors = soup.select("li.b_algo h2 a, a.result__a, a.result-link")
    if not anchors:
        anchors = soup.find_all("a", href=True)
    for anchor in anchors:
        url = _unwrap_result_url(anchor.get("href", ""), endpoint)
        if not url or url in seen:
            continue
        title = anchor.get_text(" ", strip=True)
        container = anchor.find_parent(class_=re.compile(r"result|b_algo", re.IGNORECASE))
        snippet_node = container.select_one("p") if container else None
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else (container.get_text(" ", strip=True) if container else "")
        seen.add(url)
        records.append({"url": url, "title": title, "snippet": snippet})
        if limit is not None and len(records) >= max(0, int(limit)):
            break
    return records


def is_search_provider_challenge(raw_html: str) -> bool:
    """Detecta una respuesta de desafío, distinta de una búsqueda sin resultados."""
    text = _ascii_fold(raw_html)
    return any(marker in text for marker in (
        "complete the following challenge",
        "select all squares",
        "unfortunately, bots use",
        "verify you are human",
    ))


def rank_search_results(
    records: list[dict],
    university_name: str,
    degree_title: str,
    registered_url: str,
    limit: int | None = None,
) -> list[dict]:
    """Filtra y ordena resultados antes de que el crawler descargue páginas."""
    degree_tokens = set(_tokens(degree_title))
    university_tokens = set(_tokens(university_name))
    ranked = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        url = normalize_url(record.get("url", ""))
        if not url or not is_search_result_host_compatible(url, registered_url):
            continue
        context = _ascii_fold(" ".join(str(record.get(key, "")) for key in ("title", "snippet", "url")))
        degree_hits = len({token for token in degree_tokens if len(token) >= 4 and token in context})
        university_hits = len({token for token in university_tokens if len(token) >= 4 and token in context})
        academic_hit = any(marker in context for marker in _ACADEMIC_MARKERS)
        # Un resultado debe evidenciar la titulación y contexto académico; el
        # nombre de la institución por sí solo no basta para abrir una página.
        if degree_hits < 1 or not academic_hit:
            continue
        score = degree_hits * 20 + university_hits * 8 + int(academic_hit) * 12
        if url.lower().endswith(".pdf"):
            score += 5
        ranked.append({**record, "url": url, "score": score})
    ranked.sort(key=lambda item: (-int(item.get("score", 0)), item.get("url", "")))
    max_results = WEB_SEARCH_DISCOVERY_MAX_RESULTS if limit is None else limit
    return ranked[: max(0, int(max_results))]


def rank_institutional_origins(records: list[dict], university_name: str, registered_url: str, limit: int = 5) -> list[dict]:
    """Selecciona posibles raíces oficiales para rescatar un dominio obsoleto."""
    university_tokens = {token for token in _tokens(university_name) if len(token) >= 4}
    ranked = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        url = normalize_url(record.get("url", ""))
        host = (urlparse(url).hostname or "").lower()
        if (
            not url
            or not is_search_result_host_compatible(url, registered_url)
            or any(marker in host for marker in _NON_INSTITUTIONAL_HOST_MARKERS)
        ):
            continue
        context = _ascii_fold(" ".join(str(record.get(key, "")) for key in ("title", "snippet", "url")))
        name_hits = len({token for token in university_tokens if token in context})
        if name_hits < 1:
            continue
        score = name_hits * 20
        if not urlparse(url).path.strip("/"):
            score += 12
        if any(marker in context for marker in ("universidad", "universitat", "university", "universidade")):
            score += 8
        ranked.append({**record, "url": url, "score": score})
    ranked.sort(key=lambda item: (-int(item.get("score", 0)), item.get("url", "")))
    return ranked[: max(0, int(limit))]


def discover_search_candidates(
    university_name: str,
    degree_title: str,
    academic_level: str,
    registered_url: str,
    fetch_text: Callable[[str], str],
    query_limit: int | None = None,
    result_limit: int | None = None,
    delay: float | None = None,
) -> dict:
    """Consulta el proveedor configurado y devuelve sólo candidatos trazables."""
    result = {"queries": [], "records": [], "errors": [], "enabled": bool(WEB_SEARCH_DISCOVERY_ENABLED)}
    if not WEB_SEARCH_DISCOVERY_ENABLED:
        return result
    queries = build_search_queries(university_name, degree_title, academic_level, query_limit)
    result["queries"] = queries
    endpoints = list(dict.fromkeys(
        [WEB_SEARCH_DISCOVERY_ENDPOINT]
        + list(WEB_SEARCH_DISCOVERY_FALLBACK_ENDPOINTS)
    ))
    for index, query in enumerate(queries):
        if index and (delay if delay is not None else WEB_SEARCH_RETRY_DELAY) > 0:
            time.sleep(delay if delay is not None else WEB_SEARCH_RETRY_DELAY)
        query_records = []
        for endpoint in endpoints:
            search_url = _search_request_url(endpoint, query)
            try:
                raw_html = fetch_text(search_url)
                if is_search_provider_challenge(raw_html):
                    result["errors"].append("provider_challenge")
                    continue
                query_records = parse_search_results(raw_html, endpoint, result_limit)
                result["records"].extend(query_records)
                # El primer proveedor puede responder correctamente sin
                # devolver candidatos compatibles; probar el fallback en ese
                # caso aumenta recall sin convertirlo en fuente de confianza.
                if query_records:
                    break
            except Exception as exc:
                result["errors"].append(type(exc).__name__)
                logger.debug("Fallo controlado en descubrimiento de búsqueda: %s", exc)
    unique = {}
    for record in result["records"]:
        unique.setdefault(record.get("url"), record)
    result["records"] = rank_search_results(list(unique.values()), university_name, degree_title, registered_url, result_limit)
    return result


def discover_institutional_origins(
    university_name: str,
    registered_url: str,
    fetch_text: Callable[[str], str],
    query_limit: int = 1,
    result_limit: int = 8,
    delay: float | None = None,
) -> dict:
    """Busca una raíz institucional alternativa sin aceptar contenido curricular."""
    result = {"queries": [], "records": [], "errors": [], "enabled": bool(WEB_SEARCH_DISCOVERY_ENABLED)}
    if not WEB_SEARCH_DISCOVERY_ENABLED:
        return result
    queries = build_institution_search_queries(university_name, query_limit)
    result["queries"] = queries
    endpoints = list(dict.fromkeys(
        [WEB_SEARCH_DISCOVERY_ENDPOINT]
        + list(WEB_SEARCH_DISCOVERY_FALLBACK_ENDPOINTS)
    ))
    for index, query in enumerate(queries):
        if index and (delay if delay is not None else WEB_SEARCH_RETRY_DELAY) > 0:
            time.sleep(delay if delay is not None else WEB_SEARCH_RETRY_DELAY)
        for endpoint in endpoints:
            try:
                raw_html = fetch_text(_search_request_url(endpoint, query))
                if is_search_provider_challenge(raw_html):
                    result["errors"].append("provider_challenge")
                    continue
                parsed = parse_search_results(raw_html, endpoint, result_limit)
                result["records"].extend(parsed)
                if parsed:
                    break
            except Exception as exc:
                result["errors"].append(type(exc).__name__)
                logger.debug("Fallo controlado en rescate de origen institucional: %s", exc)
    unique = {}
    for record in result["records"]:
        unique.setdefault(record.get("url"), record)
    result["records"] = rank_institutional_origins(list(unique.values()), university_name, registered_url, result_limit)
    return result
