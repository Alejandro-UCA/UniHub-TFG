"""Descubrimiento acotado de guías docentes en portales nuevos.

Este módulo no conoce universidades concretas. Construye un pequeño índice por
universidad a partir de robots.txt y sitemaps oficiales y devuelve las URLs
que mejor encajan con una asignatura. La descarga posterior y la validación de
identidad siguen perteneciendo al pipeline de Parte 4.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup

from core.config import (
    MAX_RESPONSE_SIZE_BYTES,
    SUBJECT_GUIDE_DISCOVERY_MAX_FILES,
    SUBJECT_GUIDE_DISCOVERY_MAX_ROOTS,
    SUBJECT_GUIDE_DISCOVERY_MAX_URLS,
    SUBJECT_GUIDE_DISCOVERY_CACHE_DIR,
    SUBJECT_GUIDE_DISCOVERY_CACHE_TTL_SECONDS,
    SUBJECT_GUIDE_DISCOVERY_ENABLE_SPA,
)
from core.checkpoint import atomic_json_dump
from core.downloader import is_same_or_subdomain, normalize_url

logger = logging.getLogger(__name__)

_XML_LOC_TAG = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
_GUIDE_MARKERS = (
    "guia", "guía", "docente", "docentes", "asignatura", "asignaturas",
    "assignatura", "assignatures", "irakasgai", "irakasgaiak", "asineira",
    "syllabus", "subject", "course", "ficha", "fitxa", "teaching", "gida",
)
_ACADEMIC_MARKERS = (
    "grado", "grados", "master", "masters", "estudio", "estudios", "estudis", "estudos", "ikasketak",
    "degree", "degrees", "course", "courses", "asignatura", "asignaturas", "assignatura", "irakasgaia",
    "guias", "guias-docentes", "guia-docente", "pla-docent", "guia-docent", "guies-docents", "docencia",
    "curriculum", "curriculo", "plan-estudios", "programa-academico", "programas-academicos",
)
_NEGATIVE_PATH_MARKERS = {
    "noticia", "noticias", "news", "actualidad", "evento", "eventos", "agenda",
    "blog", "personal", "staff", "investigacion", "investigación", "research",
    "convocatoria", "convocatorias", "prensa", "contacto", "login", "legal",
    "transparencia", "empleo", "job", "jobs", "oposiciones", "proyecto",
}
_STRONG_GUIDE_MARKERS = {
    "guia", "guías", "guias", "docente", "docentes", "asignatura", "asignaturas",
    "assignatura", "assignatures", "syllabus", "ficha", "fitxa", "subject", "teaching",
    "curriculum", "curriculo", "plan-estudios", "pla-docent", "guia-docent", "guies-docents",
    "guies", "irakasgai", "irakasgaiak", "gida", "teaching-guide", "course-syllabus",
}
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "para", "con", "del", "las", "los", "una", "uno", "por", "the",
    "and", "from", "of", "de", "en", "grado", "master", "universidad",
}


def _origin(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


_DISCOVERY_CACHE_VERSION = 1


def _discovery_cache_path(base_url: str) -> str:
    canonical = _origin(normalize_url(base_url)) or str(base_url or "").strip().lower()
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return os.path.join(SUBJECT_GUIDE_DISCOVERY_CACHE_DIR, f"{digest}.json")


def _load_discovery_cache(base_url: str, max_roots: int, max_files: int, max_urls: int) -> dict | None:
    if SUBJECT_GUIDE_DISCOVERY_CACHE_TTL_SECONDS <= 0:
        return None
    path = _discovery_cache_path(base_url)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("version") != _DISCOVERY_CACHE_VERSION:
            return None
        if payload.get("limits") != {
            "max_roots": int(max_roots),
            "max_files": int(max_files),
            "max_urls": int(max_urls),
        }:
            return None
        fetched_at = datetime.fromisoformat(str(payload.get("fetched_at", "")).replace("Z", "+00:00"))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age < 0 or age > SUBJECT_GUIDE_DISCOVERY_CACHE_TTL_SECONDS:
            return None
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("records", []), list):
            return None
        result = dict(result)
        result["cache_hit"] = True
        result["cache_age_seconds"] = round(max(0.0, age), 2)
        return result
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        logger.debug("No se pudo leer caché de descubrimiento %s: %s", path, error)
        return None


def _store_discovery_cache(base_url: str, result: dict, max_roots: int, max_files: int, max_urls: int) -> None:
    if SUBJECT_GUIDE_DISCOVERY_CACHE_TTL_SECONDS <= 0:
        return
    if not result.get("files_read") or not isinstance(result.get("records", []), list):
        # No se cachean fallos de conectividad sin ningún fichero leído: el
        # siguiente run debe poder recuperarse de una caída temporal.
        return
    payload = {
        "version": _DISCOVERY_CACHE_VERSION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "limits": {
            "max_roots": int(max_roots),
            "max_files": int(max_files),
            "max_urls": int(max_urls),
        },
        "result": {key: value for key, value in result.items() if key not in {"cache_hit", "cache_age_seconds"}},
    }
    try:
        atomic_json_dump(payload, _discovery_cache_path(base_url))
    except OSError as error:
        logger.debug("No se pudo persistir caché de descubrimiento %s: %s", base_url, error)


def _normalise_host(value: str) -> str:
    raw = str(value or "").strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    return (urlparse(raw).hostname or "").lower().removeprefix("www.")


def _is_safe_xml(raw: bytes) -> bool:
    # ET no procesa recursos externos, pero rechazar declaraciones DTD evita
    # que un XML malicioso llegue a la capa de parsing de todos modos.
    prefix = raw[:4096].upper()
    return b"<!DOCTYPE" not in prefix and b"<!ENTITY" not in prefix


def parse_sitemap_locations(raw: bytes, source_url: str = "", max_locations: int = SUBJECT_GUIDE_DISCOVERY_MAX_URLS) -> dict:
    """Parsea un sitemap o sitemap-index y devuelve sus ``loc`` normalizados."""
    if not raw or len(raw) > MAX_RESPONSE_SIZE_BYTES or not _is_safe_xml(raw):
        return {"kind": "invalid", "locations": []}
    data = raw
    if str(source_url).lower().endswith(".gz") or raw.startswith(b"\x1f\x8b"):
        try:
            data = gzip.decompress(raw)
        except (OSError, EOFError):
            return {"kind": "invalid", "locations": []}
    if len(data) > MAX_RESPONSE_SIZE_BYTES or not _is_safe_xml(data):
        return {"kind": "invalid", "locations": []}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {"kind": "invalid", "locations": []}

    tag = root.tag.rsplit("}", 1)[-1].lower()
    kind = "index" if tag == "sitemapindex" else "urlset" if tag == "urlset" else "unknown"
    locations = []
    records = []
    seen = set()
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() != "url":
            continue
        loc_node = next(
            (child for child in node if child.tag.rsplit("}", 1)[-1].lower() == "loc"),
            None,
        )
        value = normalize_url((loc_node.text or "").strip(), base_url=source_url) if loc_node is not None else ""
        lastmod_node = next(
            (child for child in node if child.tag.rsplit("}", 1)[-1].lower() == "lastmod"),
            None,
        )
        if value and value not in seen and len(locations) < max(1, int(max_locations)):
            seen.add(value)
            locations.append(value)
            records.append(_url_evidence(value, source_url=source_url, lastmod=(lastmod_node.text or "") if lastmod_node is not None else ""))
    if not locations:
        # Algunos sitemaps no usan la estructura estándar <url><loc>, por
        # ejemplo ciertos índices o exportaciones CMS. Conservamos el parser
        # tolerante anterior y generamos evidencias mínimas.
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1].lower() != "loc":
                continue
            value = normalize_url((node.text or "").strip(), base_url=source_url)
            if value and value not in seen and len(locations) < max(1, int(max_locations)):
                seen.add(value)
                locations.append(value)
                records.append(_url_evidence(value, source_url=source_url))
    return {"kind": kind, "locations": locations, "records": records}


def _is_candidate_sitemap_location(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".xml", ".xml.gz", ".xml?", ".gz")) or "sitemap" in path


def _normalise_evidence_text(value: str) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").lower().split())


def _subject_tokens(value: str) -> list[str]:
    """Tokeniza nombres en castellano y otros idiomas sin perder la primera letra acentuada."""
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return [token for token in _TOKEN_RE.findall(normalized.lower()) if token not in _STOPWORDS]


def _path_segments(url: str) -> list[str]:
    parsed = urlparse(str(url or ""))
    path = parsed.path.lower()
    return [segment for segment in re.split(r"[/\\]+", path) if segment]


def _url_evidence(
    url: str,
    *,
    source_url: str = "",
    anchor_text: str = "",
    title: str = "",
    heading: str = "",
    lastmod: str = "",
) -> dict:
    """Construye evidencias explicables para ordenar una URL descubierta."""
    normalised_url = normalize_url(str(url or ""))
    segments = _path_segments(normalised_url)
    path_text = " ".join(segments)
    evidence_text = " ".join(
        part for part in (
            path_text,
            _normalise_evidence_text(anchor_text),
            _normalise_evidence_text(title),
            _normalise_evidence_text(heading),
        ) if part
    )
    negative_segments = sorted(set(segments) & _NEGATIVE_PATH_MARKERS)
    strong_markers = sorted(
        marker for marker in _STRONG_GUIDE_MARKERS
        if marker in segments or marker in evidence_text
    )
    return {
        "url": normalised_url,
        "source_url": normalize_url(source_url) if source_url else "",
        "anchor_text": str(anchor_text or "").strip(),
        "title": str(title or "").strip(),
        "heading": str(heading or "").strip(),
        "lastmod": str(lastmod or "").strip(),
        "path_segments": segments,
        "negative_markers": negative_segments,
        "strong_guide_markers": strong_markers,
    }


def _url_is_academic_or_guide(url: str, *, anchor_text: str = "", title: str = "", heading: str = "") -> bool:
    """Filtra URLs por segmentos y contexto, evitando páginas institucionales generales."""
    evidence = _url_evidence(
        url,
        anchor_text=anchor_text,
        title=title,
        heading=heading,
    )
    parsed = urlparse(evidence["url"])
    path = parsed.path.lower()
    segments = set(evidence["path_segments"])
    has_pdf = path.endswith(".pdf")
    has_guide_signal = bool(evidence["strong_guide_markers"] or has_pdf)
    has_academic_signal = bool(segments & set(_ACADEMIC_MARKERS))
    has_negative_signal = bool(evidence["negative_markers"])
    if has_negative_signal and not has_guide_signal:
        return False
    return has_guide_signal or has_academic_signal


def extract_academic_link_records(html: bytes, source_url: str, allowed_hosts: list[str], limit: int = 500) -> list[dict]:
    """Extrae enlaces académicos con contexto visible, sin seguir dominios externos."""
    if not html or len(html) > MAX_RESPONSE_SIZE_BYTES:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []
    result = []
    seen = set()
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for anchor in soup.find_all("a", href=True):
        target = normalize_url(anchor.get("href", ""), base_url=source_url)
        if not target or target in seen:
            continue
        if not any(is_same_or_subdomain(target, f"https://{host}") for host in allowed_hosts):
            continue
        anchor_text = anchor.get_text(" ", strip=True)
        heading = ""
        parent = anchor.parent
        if parent is not None:
            heading_node = parent.find_previous(["h1", "h2", "h3"])
            heading = heading_node.get_text(" ", strip=True) if heading_node else ""
        if not _url_is_academic_or_guide(target, anchor_text=anchor_text, title=page_title, heading=heading):
            continue
        seen.add(target)
        result.append(_url_evidence(
            target,
            source_url=source_url,
            anchor_text=anchor_text,
            title=page_title,
            heading=heading,
        ))
        if len(result) >= max(1, int(limit)):
            break
    return result


def extract_academic_links(html: bytes, source_url: str, allowed_hosts: list[str], limit: int = 500) -> list[str]:
    """Compatibilidad: devuelve solo las URLs de los registros de evidencia."""
    return [record["url"] for record in extract_academic_link_records(html, source_url, allowed_hosts, limit)]


def _candidate_hosts(base_url: str) -> list[str]:
    """
    Devuelve el host principal y los subdominios institucionales estándar
    de docencia y guías que pertenezcan estrictamente al mismo dominio.
    """
    host = _normalise_host(base_url)
    if not host:
        return []
    hosts = [host]
    clean_domain = re.sub(r"^www\d*\.", "", host)
    subdomains = (
        "guias", "guies", "guiasdocentes", "asignaturas", "assignatures",
        "docencia", "sia", "secretaria", "centros", "centres", "facultades",
        "facultats", "escuelas", "escoles", "posgrado", "postgrado",
        "titulaciones", "estudios", "esingenieria", "etsi", "eps", "ciencias"
    )
    for sub in subdomains:
        cand = f"{sub}.{clean_domain}"
        if cand != host and is_same_or_subdomain(f"https://{cand}", f"https://{clean_domain}"):
            hosts.append(cand)
    return list(dict.fromkeys(hosts))


def _iter_discovery_records(urls_or_records) -> list[dict]:
    """Normaliza la entrada histórica de URLs y la nueva entrada enriquecida."""
    records = []
    for item in urls_or_records or ():
        if isinstance(item, dict):
            record = dict(item)
            record["url"] = normalize_url(str(record.get("url") or ""))
        else:
            record = _url_evidence(str(item or ""))
        if record.get("url"):
            records.append(record)
    return records


def rank_discovered_guide_urls(urls: list[str] | set[str] | list[dict], subject_name: str = "", subject_code: str = "", limit: int = 12) -> list[str]:
    """Ordena URLs por evidencias combinadas de ruta, enlace y contenido."""
    code = str(subject_code or "").strip().lower()
    tokens = _subject_tokens(subject_name)
    slug = "-".join(tokens)
    scored = []
    seen = set()
    for record in _iter_discovery_records(urls):
        url = record["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        low = url.lower()
        context = " ".join(
            _normalise_evidence_text(record.get(field, ""))
            for field in ("anchor_text", "title", "heading")
        )
        path_segments = set(record.get("path_segments") or _path_segments(url))
        if not _url_is_academic_or_guide(
            url,
            anchor_text=record.get("anchor_text", ""),
            title=record.get("title", ""),
            heading=record.get("heading", ""),
        ):
            continue
        score = 0
        code_match = bool(code and re.search(rf"(?<![a-z0-9]){re.escape(code)}(?![a-z0-9])", low))
        if code_match:
            score += 120
        matched_path_tokens = sum(1 for token in tokens if token in low)
        matched_context_tokens = sum(1 for token in tokens if token in context)
        score += matched_path_tokens * 20
        score += matched_context_tokens * 12
        if tokens and matched_path_tokens == len(tokens):
            score += 35
        elif tokens and len(tokens) == 1 and (matched_path_tokens == 1 or matched_context_tokens == 1):
            score += 25
        if slug and slug in low:
            score += 70
        if any(marker in path_segments for marker in _STRONG_GUIDE_MARKERS):
            score += 24
        elif any(marker in path_segments for marker in _ACADEMIC_MARKERS):
            score += 8
        if any(marker in context for marker in _GUIDE_MARKERS):
            score += 12
        if low.endswith(".pdf"):
            score += 8
        if record.get("lastmod"):
            score += 1
        # Una URL sin código necesita al menos una palabra clave fuerte o evidencia semántica
        if not code:
            strong_path_marker = bool(path_segments & _STRONG_GUIDE_MARKERS) or low.endswith(".pdf") or any(marker in context for marker in _GUIDE_MARKERS)
            if not strong_path_marker:
                continue
        minimum = 25 if code else (35 if len(tokens) >= 2 else 20)
        if score >= minimum:
            scored.append((score, len(url), url))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [url for _, _, url in scored[: max(0, int(limit))]]


def derive_subject_guide_urls_from_routes(
    records: list[dict] | list[str] | None,
    subject_name: str = "",
    subject_code: str = "",
    limit: int = 12,
) -> list[dict]:
    """Deriva rutas de ficha a partir de evidencias académicas existentes.

    Muchos portales no publican la URL de una guía en sitemap: publican una
    URL de catálogo, plan o grado y construyen la ficha mediante una ruta
    hermana. Este derivador aprende únicamente la familia de ruta observada
    en la propia institución. No contiene dominios, códigos RUCT ni nombres
    de universidades y devuelve evidencias explicables para la auditoría.
    """
    tokens = _subject_tokens(subject_name)
    slug = "-".join(tokens)
    code = str(subject_code or "").strip()
    if code and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,31}", code, re.IGNORECASE):
        code = ""
    if not slug and not code:
        return []

    derived = []
    seen = set()
    max_items = max(0, int(limit))
    for record in _iter_discovery_records(records):
        source = record.get("url", "")
        if not source or not _url_is_academic_or_guide(
            source,
            anchor_text=record.get("anchor_text", ""),
            title=record.get("title", ""),
            heading=record.get("heading", ""),
        ):
            continue
        parsed = urlparse(source)
        segments = [segment for segment in parsed.path.split("/") if segment]
        if not parsed.scheme or not parsed.netloc or not segments:
            continue

        # Solo se reemplaza el último segmento de una ruta que ya ha sido
        # observada como académica. Así no se inventan subdominios ni raíces
        # ajenas al portal real.
        parent_segments = segments[:-1]
        if not parent_segments:
            continue
        parent_path = "/" + "/".join(parent_segments).rstrip("/") + "/"
        leaf = segments[-1].lower()
        leaf_stem = re.sub(r"\.(?:html?|aspx?|php|pdf)$", "", leaf)
        leaf_has_route_signal = (
            any(marker in segments for marker in _ACADEMIC_MARKERS)
            or any(marker in segments for marker in _STRONG_GUIDE_MARKERS)
            or any(marker in marker_text for marker_text in (
                source.lower(),
                _normalise_evidence_text(record.get("anchor_text", "")),
                _normalise_evidence_text(record.get("title", "")),
                _normalise_evidence_text(record.get("heading", "")),
            ) for marker in _GUIDE_MARKERS)
        )
        if not leaf_has_route_signal:
            continue

        replacements = []
        if slug:
            replacements.append((slug, "subject_slug"))
        if code:
            replacements.append((code, "subject_code"))
        if slug and code:
            replacements.append((f"{slug}-{code}", "subject_slug_code"))

        for replacement, derivation in replacements:
            for suffix in ("", "guia-docente"):
                path_parts = parent_path.rstrip("/").split("/")
                path_parts.append(replacement)
                if suffix:
                    path_parts.append(suffix)
                candidate_path = "/".join(path_parts) + "/"
                candidate = urlunparse((parsed.scheme, parsed.netloc, candidate_path, "", "", ""))
                candidate = normalize_url(candidate)
                if not candidate or candidate in seen or candidate == source:
                    continue
                seen.add(candidate)
                derived.append({
                    "url": candidate,
                    "source_url": source,
                    "anchor_text": record.get("anchor_text", ""),
                    "title": record.get("title", ""),
                    "heading": record.get("heading", ""),
                    "path_segments": _path_segments(candidate),
                    "source_kind": "derived_route",
                    "derivation": derivation,
                    "route_leaf": leaf_stem,
                })
                if len(derived) >= max_items:
                    return derived
    return derived


def build_subject_guide_discovery_index(
    downloader,
    base_url: str,
    max_roots: int = SUBJECT_GUIDE_DISCOVERY_MAX_ROOTS,
    max_files: int = SUBJECT_GUIDE_DISCOVERY_MAX_FILES,
    max_urls: int = SUBJECT_GUIDE_DISCOVERY_MAX_URLS,
) -> dict:
    """Construye un índice de URLs académicas manteniendo límites estrictos."""
    cached_result = _load_discovery_cache(base_url, max_roots, max_files, max_urls)
    if cached_result is not None:
        return cached_result
    hosts = _candidate_hosts(base_url)
    if not hosts:
        return {"urls": [], "records": [], "sitemaps": [], "files_read": 0, "blocked": 0, "truncated": False, "cache_hit": False, "spa_attempts": 0, "spa_fallbacks": 0}

    sitemap_queue = []
    seen_sitemaps = set()
    for host in hosts:
        origin = f"https://{host}"
        sitemap_queue.extend([
            f"{origin}/sitemap.xml",
            f"{origin}/sitemap_index.xml",
            f"{origin}/sitemap.xml.gz",
            f"{origin}/sitemap_index.xml.gz",
            f"{origin}/sitemap-estudios.xml",
            f"{origin}/sitemap-grados.xml",
        ])
        sitemap_queue.insert(0, f"{origin}/robots.txt")
    sitemap_queue = list(dict.fromkeys(sitemap_queue))[: max(1, int(max_roots)) * 8]

    candidate_records = []
    seen_candidates = set()
    sitemap_sources = []
    files_read = 0
    blocked = 0
    truncated = False
    spa_attempts = 0
    spa_fallbacks = 0
    index_queue = list(sitemap_queue)
    while index_queue and files_read < max(1, int(max_files)):
        source_url = index_queue.pop(0)
        if source_url in seen_sitemaps:
            continue
        seen_sitemaps.add(source_url)
        parsed = urlparse(source_url)
        if not parsed.hostname or not any(
            is_same_or_subdomain(f"https://{parsed.hostname}", f"https://{host}") for host in hosts
        ):
            continue
        try:
            allowed, _ = downloader.robots_policy.check(source_url)
            if not allowed:
                blocked += 1
                continue
            raw = downloader.fetch_content(source_url, max_size_bytes=MAX_RESPONSE_SIZE_BYTES)
        except Exception as exc:
            logger.debug("No se pudo leer sitemap %s: %s", source_url, exc)
            continue
        files_read += 1
        if source_url.lower().endswith("/robots.txt"):
            text = raw.decode("utf-8", errors="replace")
            declared = [line.split(":", 1)[1].strip() for line in text.splitlines() if line.lower().startswith("sitemap:") and ":" in line]
            for declared_url in declared:
                clean = normalize_url(declared_url, base_url=source_url)
                if clean and clean not in seen_sitemaps and _origin(clean):
                    index_queue.insert(0, clean)
            continue
        parsed_sitemap = parse_sitemap_locations(raw, source_url, max_locations=max_urls)
        if not parsed_sitemap["locations"]:
            continue
        sitemap_sources.append(source_url)
        if parsed_sitemap["kind"] == "index":
            for child in parsed_sitemap["locations"]:
                if _is_candidate_sitemap_location(child) and child not in seen_sitemaps:
                    index_queue.append(child)
        else:
            for record in parsed_sitemap.get("records", []):
                location = record["url"]
                if not any(is_same_or_subdomain(location, f"https://{host}") for host in hosts):
                    continue
                if _url_is_academic_or_guide(location) and location not in seen_candidates:
                    seen_candidates.add(location)
                    candidate_records.append(record)
                if len(candidate_records) >= max_urls:
                    truncated = True
                    break
        if len(candidate_records) >= max_urls:
            break

    # Algunos CMS universitarios no publican sitemap útil, pero sí tienen un
    # hub HTML de estudios/asignaturas. Se inspeccionan pocos hubs estables y
    # solo un nivel de enlaces; nunca se convierte esta capa en un spider.
    if files_read < max(1, int(max_files)) and len(candidate_records) < max_urls:
        hub_paths = (
            "/estudios", "/grados", "/estudios-oficiales", "/docencia",
            "/guias-docentes", "/guias", "/asignaturas", "/academic",
        )
        hub_queue = [f"https://{host}{path}" for host in hosts for path in hub_paths]
        for hub_url in hub_queue:
            if files_read >= max(1, int(max_files)) or len(candidate_records) >= max_urls:
                truncated = True
                break
            try:
                allowed, _ = downloader.robots_policy.check(hub_url)
                if not allowed:
                    blocked += 1
                    continue
                raw = downloader.fetch_content(
                    hub_url,
                    max_size_bytes=min(MAX_RESPONSE_SIZE_BYTES, 2 * 1024 * 1024),
                )
            except Exception as exc:
                logger.debug("No se pudo inspeccionar hub académico %s: %s", hub_url, exc)
                continue
            files_read += 1
            hub_records = extract_academic_link_records(raw, hub_url, hosts, limit=max_urls)
            # Algunos hubs son un shell de React/Vue/Angular: el HTML inicial
            # no contiene enlaces, aunque la página renderizada sí los tenga.
            # Se intenta una sola renderización acotada por hub vacío; el
            # crawler SPA aplica sus propios límites, robots y caché.
            if not hub_records and SUBJECT_GUIDE_DISCOVERY_ENABLE_SPA:
                spa_attempts += 1
                try:
                    from parsers.spa_engine import SPALayoutCrawler
                    rendered = SPALayoutCrawler.get_shared_instance().render_spa_page(hub_url)
                    rendered_html = str(rendered or "")
                    if rendered_html and len(rendered_html.encode("utf-8")) <= MAX_RESPONSE_SIZE_BYTES:
                        hub_records = extract_academic_link_records(
                            rendered_html.encode("utf-8"), hub_url, hosts, limit=max_urls
                        )
                        if hub_records:
                            spa_fallbacks += 1
                except Exception as exc:
                    logger.debug("No se pudo renderizar hub SPA %s: %s", hub_url, exc)
            for record in hub_records:
                target = record["url"]
                if target not in seen_candidates:
                    seen_candidates.add(target)
                    candidate_records.append(record)
                if len(candidate_records) >= max_urls:
                    truncated = True
                    break
    result = {
        "urls": [record["url"] for record in candidate_records[: max(1, int(max_urls))]],
        "records": candidate_records[: max(1, int(max_urls))],
        "sitemaps": sitemap_sources,
        "files_read": files_read,
        "blocked": blocked,
        "truncated": truncated or bool(index_queue),
        "cache_hit": False,
        "spa_attempts": spa_attempts,
        "spa_fallbacks": spa_fallbacks,
    }
    _store_discovery_cache(base_url, result, max_roots, max_files, max_urls)
    return result


def learn_guide_url_template(known_pairs: list[tuple[str, str]]) -> str | None:
    """
    Aprende algorítmicamente la plantilla canónica de URLs de guías docentes
    a partir de pares observados (código_asignatura, url_guia).
    Requiere al menos 2 pares consistentes para evitar sobreajuste.
    """
    if not known_pairs or len(known_pairs) < 2:
        return None

    templates_count: dict[str, int] = {}

    for code, url in known_pairs:
        c_str = str(code or "").strip()
        u_str = str(url or "").strip()
        if not c_str or not u_str or len(c_str) < 2:
            continue

        escaped_code = re.escape(c_str)
        # 1. Parámetro de consulta (ej. ?cod=101 o &id=101)
        m_param = re.search(rf"([?&][a-zA-Z0-9_]+={escaped_code})(?:[&/#]|$)", u_str)
        if m_param:
            matched_segment = m_param.group(1)
            replaced_segment = matched_segment.replace(f"={c_str}", "={code}")
            candidate_tpl = u_str.replace(matched_segment, replaced_segment)
            templates_count[candidate_tpl] = templates_count.get(candidate_tpl, 0) + 1
            continue

        # 2. Segmento en la ruta URL (ej. /guias/101.pdf o /asig/101/)
        m_path = re.search(rf"(/){escaped_code}(\.[a-zA-Z0-9]+|/|$)", u_str)
        if m_path:
            candidate_tpl = u_str[:m_path.start()] + m_path.group(1) + "{code}" + m_path.group(2) + u_str[m_path.end():]
            templates_count[candidate_tpl] = templates_count.get(candidate_tpl, 0) + 1
            continue

    if not templates_count:
        return None

    best_tpl, count = max(templates_count.items(), key=lambda item: item[1])
    return best_tpl if count >= 2 else None


def project_missing_guide_urls(template: str, subjects: list[dict]) -> list[dict]:
    """
    Proyecta URLs de guías docentes para asignaturas que tienen código pero carecen de enlace.
    Retorna la lista de asignaturas enriquecidas.
    """
    if not template or "{code}" not in template or not subjects:
        return subjects

    enriched = []
    for s in subjects:
        item = dict(s)
        if not item.get("url_guia_docente"):
            code = str(item.get("codigo_asignatura") or "").strip()
            if code and re.match(r"^[A-Za-z0-9._-]{2,32}$", code):
                item["url_guia_docente"] = template.replace("{code}", code)
                item["_guia_proyectada"] = True
        enriched.append(item)
    return enriched

