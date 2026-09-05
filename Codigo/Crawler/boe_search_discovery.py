"""Descubrimiento genérico de resoluciones curriculares en el BOE.

La ficha RUCT es la fuente preferente de referencias BOE, pero no siempre
conserva el enlace histórico de una titulación vigente. Este módulo usa
únicamente el buscador oficial del BOE como respaldo. No decide por sí mismo
que un documento sea válido: devuelve PDFs candidatos para que la Parte 1 los
someta al parser, a la identidad de la titulación y a la compuerta de calidad.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
import unicodedata
from datetime import datetime
from collections.abc import Callable
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from config import (
    BOE_SEARCH_DISCOVERY_ENABLED,
    BOE_SEARCH_DISCOVERY_MAX_DOCUMENTS,
    BOE_SEARCH_DISCOVERY_MAX_QUERIES,
    BOE_SEARCH_DISCOVERY_MAX_RESULTS,
    BOE_SEARCH_DISCOVERY_DELAY,
    BOE_SUMMARY_DISCOVERY_ENABLED,
    BOE_SUMMARY_DISCOVERY_MAX_DATES,
    BOE_SUMMARY_DISCOVERY_MAX_ITEMS,
    BOE_SUMMARY_DISCOVERY_DELAY,
)
from downloader import normalize_url

logger = logging.getLogger(__name__)


def needs_boe_curriculum_search(candidates, existing_record) -> bool:
    """Una referencia administrativa no cierra la búsqueda de un currículo.

    La primera visita conserva su preferencia por las referencias RUCT. En
    una revalidación sólo se omite la búsqueda si el plan ya supera calidad.
    """
    if not candidates:
        return True
    if not isinstance(existing_record, dict) or not existing_record:
        return False
    from data_quality import assess_plan_quality
    return not assess_plan_quality(existing_record, existing_record.get('origen_fuente')).get('publicable')

BOE_SEARCH_URL = "https://www.boe.es/buscar/redirector.php"
BOE_SUMMARY_API_URL = "https://www.boe.es/datosabiertos/api/boe/sumario/{}"
_BOE_REFERENCE_RE = re.compile(r"\bBOE-A-\d{4}-\d+\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_GENERIC_TITLE_WORDS = {
    "master", "máster", "masteres", "másteres", "grado", "grados",
    "doctorado", "doctorados", "universitario", "universitaria",
    "graduado", "graduada", "graduados", "graduadas", "bachelor",
    "licenciado", "licenciada", "diplomado", "diplomada",
    "universitarios", "universitarias", "título", "titulo", "titulos",
    "títulos", "estudios", "estudio", "plan", "planes", "de", "del",
    "la", "las", "el", "los", "en", "y", "por", "para", "con",
    "universidad", "universitat", "university", "universidade",
}
_PLAN_MARKERS = (
    "plan de estudios", "plan estudios", "plan de estudio",
    "publica el plan", "publicación del plan", "publicacion del plan",
    "plan actualizado", "modificación del plan", "modificacion del plan",
)
_BOE_HOSTS = {"boe.es", "www.boe.es"}


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _tokens(value: object, *, remove_generic: bool = False) -> list[str]:
    words = re.findall(r"[a-z0-9áéíóúüñàèìòùç]{3,}", _fold(value))
    if remove_generic:
        words = [word for word in words if word not in _GENERIC_TITLE_WORDS]
    return list(dict.fromkeys(words))


def _core_title(degree_title: str) -> str:
    value = " ".join(str(degree_title or "").split())
    value = re.split(r"\s+por\s+(?:la|el|las|los)?\s*", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = value.split(";", 1)[0].strip(" ,")
    return value[:180].strip()


def build_boe_search_queries(
    university_name: str,
    degree_title: str,
    academic_level: str = "",
    limit: int | None = None,
) -> list[str]:
    """Genera consultas de texto libre sin depender de una institución concreta.

    El BOE busca por coincidencia de palabras en el título. Se omiten palabras
    administrativas para resistir diferencias entre ``Máster``/``Másteres`` y
    las variantes lingüísticas de ``Universidad``. La institución se usa luego
    como evidencia de identidad, no como única consulta.
    """
    del academic_level
    # Las variantes de género y las traducciones RUCT no son palabras que
    # deban aparecer simultáneamente en el título de la resolución BOE.
    core = re.split(r"\s+/\s+", _core_title(degree_title), maxsplit=1)[0]
    title_tokens = _tokens(core, remove_generic=True)
    if not title_tokens:
        return []
    organisation_tokens = _tokens(university_name, remove_generic=True)
    organisation_term = next(
        (token for token in organisation_tokens if len(token) >= 5),
        "",
    )
    # Dos longitudes permiten recuperar títulos que cambiaron ligeramente
    # entre la publicación y el catálogo actual, manteniendo un presupuesto
    # fijo de peticiones.
    query_terms = [
        " ".join(title_tokens[:12] + ([organisation_term] if organisation_term else [])),
        " ".join(title_tokens[:8]),
    ]
    max_queries = BOE_SEARCH_DISCOVERY_MAX_QUERIES if limit is None else limit
    return list(dict.fromkeys(query_terms))[: max(0, int(max_queries))]


def _parse_date(value: object) -> datetime | None:
    match = _DATE_RE.search(str(value or ""))
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _normalise_summary_date(value: object) -> str | None:
    """Devuelve una fecha de sumario en formato AAAAMMDD si es válida."""
    text = str(value or "").strip()
    if not text:
        return None
    compact = re.fullmatch(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", text)
    if compact:
        year, month, day = (int(part) for part in compact.groups())
    else:
        parsed = _parse_date(text)
        if not parsed:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
            except (TypeError, ValueError):
                return None
        year, month, day = parsed.year, parsed.month, parsed.day
    try:
        return datetime(year, month, day).strftime("%Y%m%d")
    except ValueError:
        return None


def _iter_summary_items(value: object):
    """Recorre el JSON oficial sin acoplarse a la profundidad del sumario."""
    if isinstance(value, dict):
        if value.get("titulo") is not None and value.get("url_pdf") is not None:
            yield value
        for child in value.values():
            yield from _iter_summary_items(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_summary_items(child)


def _summary_pdf_url(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("texto") or value.get("url") or value.get("href")
    return _absolute_boe_url(str(value or ""), "https://www.boe.es/")


def parse_boe_summary_json(raw_json: str, limit: int | None = None) -> list[dict]:
    """Extrae documentos del sumario JSON oficial, sin validarlos curricularmente."""
    if not raw_json:
        return []
    try:
        payload = json.loads(str(raw_json))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    status = payload.get("status") if isinstance(payload, dict) else None
    if isinstance(status, dict) and str(status.get("code") or "") not in {"", "200"}:
        return []
    records = []
    seen = set()
    max_items = None if limit is None else max(0, int(limit))
    for item in _iter_summary_items(payload):
        reference = str(item.get("identificador") or "").upper().strip()
        if not _BOE_REFERENCE_RE.fullmatch(reference):
            reference_match = _BOE_REFERENCE_RE.search(
                " ".join((reference, str(item.get("url_pdf") or ""), str(item.get("titulo") or "")))
            )
            reference = reference_match.group(0).upper() if reference_match else ""
        pdf_url = _summary_pdf_url(item.get("url_pdf"))
        if not reference or not pdf_url or reference in seen:
            continue
        seen.add(reference)
        records.append({
            "reference": reference,
            "document_url": pdf_url,
            "title": str(item.get("titulo") or "").strip(),
            "publication": str(item.get("titulo") or "").strip(),
            "date": None,
            "boe_date": None,
        })
        if max_items is not None and len(records) >= max_items:
            break
    return records


def _absolute_boe_url(href: str, base_url: str = "https://www.boe.es/") -> str:
    candidate = normalize_url(urljoin(base_url, html.unescape(str(href or "").strip())))
    host = (urlparse(candidate).hostname or "").casefold().rstrip(".")
    return candidate if host in _BOE_HOSTS else ""


def _record_from_result_node(node) -> dict | None:
    anchors = node.find_all("a", href=True)
    doc_anchor = next(
        (
            anchor for anchor in anchors
            if _BOE_REFERENCE_RE.search(str(anchor.get("href") or ""))
            or _BOE_REFERENCE_RE.search(anchor.get("title", ""))
            or "doc.php?id=BOE-A-" in str(anchor.get("href") or "")
        ),
        None,
    )
    if doc_anchor is None:
        return None
    doc_url = _absolute_boe_url(doc_anchor.get("href", ""), "https://www.boe.es/buscar/")
    reference_match = _BOE_REFERENCE_RE.search(
        " ".join((doc_url, doc_anchor.get("title", ""), node.get_text(" ", strip=True)))
    )
    if not doc_url or not reference_match:
        return None
    paragraphs = node.find_all("p")
    publication = next(
        (item.get_text(" ", strip=True) for item in paragraphs if "linea-pub" in (item.get("class") or [])),
        "",
    )
    title_parts = [
        item.get_text(" ", strip=True)
        for item in paragraphs
        if "linea-dem" not in (item.get("class") or [])
        and "linea-pub" not in (item.get("class") or [])
        and item.get_text(" ", strip=True)
    ]
    title = title_parts[-1] if title_parts else node.get_text(" ", strip=True)
    date_obj = _parse_date(publication)
    return {
        "reference": reference_match.group(0).upper(),
        "document_url": doc_url,
        "title": title,
        "publication": publication,
        "date": date_obj,
        "boe_date": date_obj.strftime("%Y-%m-%d") if date_obj else None,
    }


def parse_boe_search_results(raw_html: str, limit: int | None = None) -> list[dict]:
    """Extrae documentos tipo resolución de una página de resultados BOE."""
    if not raw_html:
        return []
    soup = BeautifulSoup(str(raw_html), "html.parser")
    nodes = soup.select("li.resultado-busqueda")
    records = []
    seen = set()
    for node in nodes:
        record = _record_from_result_node(node)
        if not record or record["reference"] in seen:
            continue
        seen.add(record["reference"])
        records.append(record)
        if limit is not None and len(records) >= max(0, int(limit)):
            return records
    return records


def rebuild_persisted_boe_candidates(
    urls: object,
    fallback_date: object = None,
    limit: int | None = None,
) -> list[dict]:
    """Reconstruye candidatos a partir de URLs oficiales ya persistidas.

    Algunas ejecuciones históricas conservaron ``all_boe_urls`` aunque la
    ficha RUCT actual ya no expusiera esas referencias. Esas URLs son
    evidencia de descubrimiento, no una validación curricular: cada
    candidato debe volver a pasar por descarga, parser, identidad y calidad.
    La función solo normaliza URLs HTTP(S) que parecen documentos PDF y
    aplica un límite explícito para mantener acotado el coste de revalidación.
    """
    if not isinstance(urls, (list, tuple, set)):
        return []
    max_items = None if limit is None else max(0, int(limit))
    fallback = None
    if fallback_date:
        try:
            fallback = datetime.fromisoformat(str(fallback_date).replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            fallback = None
    records = []
    seen = set()
    for raw_url in urls:
        candidate = normalize_url(str(raw_url or "").strip())
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").casefold().rstrip(".")
        path = (parsed.path or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if not (path.endswith(".pdf") or "/boe/" in path or host in _BOE_HOSTS):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        date_obj = None
        url_date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", parsed.path or "")
        if url_date_match:
            year, month, day = (int(part) for part in url_date_match.groups())
            try:
                date_obj = datetime(year, month, day)
            except ValueError:
                date_obj = None
        date_obj = date_obj or fallback
        records.append({
            "url": candidate,
            "text": "evidencia BOE persistida",
            "date": date_obj,
            "boe_date": date_obj.strftime("%Y-%m-%d") if date_obj else None,
            "priority": 80 if host in _BOE_HOSTS else 60,
            "doc_type": "persisted_boe_candidate",
            "discovery": "persisted_ruct_evidence",
        })
    records.sort(
        key=lambda item: (
            int(item.get("priority", 0)),
            item.get("date") or datetime(1970, 1, 1),
        ),
        reverse=True,
    )
    return records if max_items is None else records[:max_items]


def _document_pdf_and_title(raw_html: str, document_url: str) -> tuple[str, str]:
    soup = BeautifulSoup(str(raw_html or ""), "html.parser")
    pdf_url = ""
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        label = anchor.get_text(" ", strip=True).casefold()
        if href.casefold().endswith(".pdf") or label == "pdf":
            pdf_url = _absolute_boe_url(href, document_url)
            if pdf_url:
                break
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if not title:
        title = soup.get_text(" ", strip=True)[:500]
    return pdf_url, title


def _candidate_score(record: dict, document_title: str, university_name: str, degree_title: str) -> int | None:
    context = _fold(" ".join(str(record.get(key, "")) for key in ("title", "publication")) + " " + document_title)
    level_patterns = (
        r"\b(?:grado|graduado|graduada|grau|bachelor)\b",
        r"\b(?:master|maestria)\b",
        r"\b(?:doctorado|doctorat|doctor)\b",
        r"\b(?:licenciatura|licenciado|licenciada|diplomatura|diplomado|diplomada)\b",
    )
    target_levels = {i for i, pattern in enumerate(level_patterns) if re.search(pattern, _fold(degree_title))}
    source_levels = {i for i, pattern in enumerate(level_patterns) if re.search(pattern, context)}
    if target_levels and source_levels and target_levels.isdisjoint(source_levels):
        return None
    variants = [set(_tokens(part, remove_generic=True)) for part in
                re.split(r"\s+/\s+", _core_title(degree_title))]
    title_tokens = max(variants, key=lambda tokens: sum(token in context for token in tokens) / max(1, len(tokens)))
    org_tokens = set(_tokens(university_name, remove_generic=True))
    title_hits = len({token for token in title_tokens if len(token) >= 4 and token in context})
    org_hits = len({token for token in org_tokens if len(token) >= 4 and token in context})
    meaningful_title_tokens = {token for token in title_tokens if len(token) >= 4}
    # Una palabra común como «investigación» no basta para adjudicar a una
    # titulación la resolución de otro programa de la misma institución.
    if not meaningful_title_tokens or title_hits / len(meaningful_title_tokens) < 0.7 or org_hits < 1:
        return None
    if not any(marker in context for marker in _PLAN_MARKERS):
        return None
    return title_hits * 25 + org_hits * 20 + (15 if "plan" in context else 0)


def discover_boe_candidates_from_summary(
    university_name: str,
    degree_title: str,
    academic_level: str,
    publication_dates: object,
    fetch_text: Callable[..., str],
    date_limit: int | None = None,
    item_limit: int | None = None,
    delay: float | None = None,
) -> dict:
    """Descubre resoluciones desde sumarios BOE fechados y legibles por máquina.

    La fecha es una señal de descubrimiento, no una prueba de identidad. Los
    candidatos se entregan al circuito normal, que vuelve a verificar robots,
    el documento, la identidad académica y la completitud curricular.
    """
    result = {
        "enabled": bool(BOE_SUMMARY_DISCOVERY_ENABLED),
        "dates": [],
        "summaries_inspected": 0,
        "records": [],
        "errors": [],
    }
    if not BOE_SUMMARY_DISCOVERY_ENABLED:
        return result
    values = publication_dates if isinstance(publication_dates, (list, tuple, set)) else [publication_dates]
    dates = list(dict.fromkeys(
        item for item in (_normalise_summary_date(value) for value in values) if item
    ))
    max_dates = BOE_SUMMARY_DISCOVERY_MAX_DATES if date_limit is None else date_limit
    max_items = BOE_SUMMARY_DISCOVERY_MAX_ITEMS if item_limit is None else item_limit
    dates = dates[: max(0, int(max_dates))]
    result["dates"] = dates
    by_reference = {}
    accepted_limit = max(0, int(max_items))
    if accepted_limit == 0:
        return result
    for index, date in enumerate(dates):
        if index:
            pause = BOE_SUMMARY_DISCOVERY_DELAY if delay is None else delay
            if pause > 0:
                time.sleep(pause)
        url = BOE_SUMMARY_API_URL.format(date)
        try:
            try:
                raw_json = fetch_text(url, request_headers={"Accept": "application/json"})
            except TypeError:
                # Compatibilidad con adaptadores de prueba o integraciones
                # antiguas que solo aceptan la URL.
                raw_json = fetch_text(url)
            result["summaries_inspected"] += 1
            # Se recorren todos los items del sumario y el límite se aplica
            # después de evaluar identidad y señales de plan. Los primeros
            # items del diario no tienen por qué pertenecer a universidades.
            for record in parse_boe_summary_json(raw_json):
                record["boe_date"] = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                if record["reference"] in by_reference:
                    continue
                score = _candidate_score(
                    record,
                    record.get("title", ""),
                    university_name,
                    degree_title,
                )
                if score is None:
                    continue
                record["_score"] = score
                by_reference[record["reference"]] = record
        except Exception as exc:
            result["errors"].append(type(exc).__name__)
            logger.debug("No se pudo consultar el sumario BOE %s: %s", date, exc)

    ranked_records = sorted(
        by_reference.values(),
        key=lambda item: int(item.get("_score", 0)),
        reverse=True,
    )[:accepted_limit]
    for record in ranked_records:
        score = int(record.get("_score", 0))
        result["records"].append({
            "url": record["document_url"],
            "text": record.get("title", ""),
            "date": None,
            "boe_date": record.get("boe_date"),
            "priority": 95,
            "doc_type": "boe_summary_plan",
            "score": score,
            "discovery": "boe_official_summary_api",
            "boe_reference": record.get("reference"),
        })
    result["records"].sort(key=lambda item: -int(item.get("score", 0)))
    return result


def discover_boe_candidates(
    university_name: str,
    degree_title: str,
    academic_level: str,
    fetch_text: Callable[[str], str],
    query_limit: int | None = None,
    result_limit: int | None = None,
    document_limit: int | None = None,
    delay: float | None = None,
) -> dict:
    """Busca y valida candidatos BOE sin escribir datos ni saltarse robots."""
    result = {
        "enabled": bool(BOE_SEARCH_DISCOVERY_ENABLED),
        "queries": [],
        "records": [],
        "documents_inspected": 0,
        "errors": [],
    }
    if not BOE_SEARCH_DISCOVERY_ENABLED:
        return result
    queries = build_boe_search_queries(university_name, degree_title, academic_level, query_limit)
    result["queries"] = queries
    max_results = BOE_SEARCH_DISCOVERY_MAX_RESULTS if result_limit is None else result_limit
    max_documents = BOE_SEARCH_DISCOVERY_MAX_DOCUMENTS if document_limit is None else document_limit
    by_reference = {}
    for index, query in enumerate(queries):
        if index:
            pause = BOE_SEARCH_DISCOVERY_DELAY if delay is None else delay
            if pause > 0:
                time.sleep(pause)
        search_url = BOE_SEARCH_URL + "?" + "accion=Buscar&bd=boe&texto=" + quote_plus(query)
        try:
            raw_html = fetch_text(search_url)
            # Los resultados de otros niveles o instituciones no deben
            # agotar el presupuesto antes de llegar al plan buscado.
            eligible = [record for record in parse_boe_search_results(raw_html)
                        if _candidate_score(record, '', university_name, degree_title) is not None]
            for record in eligible[:max(0, int(max_results))]:
                by_reference.setdefault(record["reference"], record)
        except Exception as exc:
            result["errors"].append(type(exc).__name__)
            logger.debug("No se pudo consultar el buscador oficial del BOE: %s", exc)
    records = list(by_reference.values())[: max(0, int(max_documents))]
    for record in records:
        try:
            document_html = fetch_text(record["document_url"])
            result["documents_inspected"] += 1
            pdf_url, document_title = _document_pdf_and_title(document_html, record["document_url"])
            score = _candidate_score(record, document_title, university_name, degree_title)
            if not pdf_url or score is None:
                continue
            result["records"].append({
                "url": pdf_url,
                "text": document_title,
                "date": record.get("date"),
                "boe_date": record.get("boe_date"),
                "priority": 90,
                "doc_type": "boe_search_plan",
                "score": score,
                "discovery": "boe_official_search",
                "boe_reference": record.get("reference"),
            })
        except Exception as exc:
            result["errors"].append(type(exc).__name__)
            logger.debug("No se pudo inspeccionar un documento BOE candidato: %s", exc)
    result["records"].sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            -(item.get("date") or datetime(1970, 1, 1)).timestamp(),
        )
    )
    return result
