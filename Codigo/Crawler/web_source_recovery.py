"""Políticas seguras para recuperar fuentes académicas que cambian de portal.

Este módulo no decide si una página es curricular. Sólo resuelve dos problemas
previos que estaban mezclados en el crawler: distinguir una redirección
institucional legítima de una salida de dominio y ordenar páginas vigentes por
delante de rutas históricas. La validación curricular continúa en los parsers
y en la compuerta de calidad.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit


OFFICIAL_REDIRECT_TLDS = frozenset({
    "es", "cat", "gal", "eus", "edu", "com", "org",
    "pt", "it", "fr", "de", "nl", "be", "lu", "is", "uk",
})

_HISTORICAL_MARKERS = (
    "ext-plan", "extingu", "extincion", "extinción", "a extinguir",
    "plan antiguo", "plan anterior", "historico", "histórico", "historical",
    "archivo", "archived", "old-plan", "plan-amortizado", "amortizado",
)

_CURRENT_MARKERS = (
    "vigente", "activo", "actual", "curso 2026", "curso-2026",
    "2026-27", "2026/2027", "2025-26", "2025/2026", "2024-25", "2024/2025",
)

_HOST_PREFIXES = frozenset({
    "www", "web", "portal", "www2", "www3", "academico", "estudios",
    "grados", "graus", "graos", "campus", "online", "madrid", "barcelona",
    "valencia", "sevilla", "alicante", "bilbao", "coruna", "coruña",
})


def _normalise_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _registrable_label(host: str) -> str:
    labels = [part for part in str(host or "").casefold().split(".") if part]
    if len(labels) < 2:
        return labels[0] if labels else ""
    return labels[-2]


def _host_tokens(host: str) -> set[str]:
    label = _registrable_label(host)
    return {
        token for token in re.split(r"[^a-z0-9]+", _normalise_text(label))
        if len(token) >= 3 and token not in _HOST_PREFIXES
    }


def _host_suffix(host: str) -> str:
    labels = [part for part in str(host or "").casefold().split(".") if part]
    return labels[-1] if labels else ""


def is_trusted_institutional_redirect(
    source_url: str,
    destination_url: str,
    university_name: str = "",
) -> bool:
    """Acepta sólo redirecciones que conservan una marca institucional.

    La política permite migraciones como ``uab.es -> uab.cat`` o
    ``universidadeuropea.es -> universidadeuropea.com``. No permite un host
    cuyo dominio registrable sea distinto, aunque contenga el mismo texto en
    un subdominio, evitando convertir el seguimiento de redirecciones en una
    relajación de seguridad.
    """
    try:
        source = urlsplit(str(source_url or ""))
        destination = urlsplit(str(destination_url or ""))
        if source.scheme.casefold() not in {"http", "https"}:
            return False
        if destination.scheme.casefold() not in {"http", "https"}:
            return False
        source_host = (source.hostname or "").casefold().rstrip(".")
        destination_host = (destination.hostname or "").casefold().rstrip(".")
        if not source_host or not destination_host:
            return False
        if _host_suffix(destination_host) not in OFFICIAL_REDIRECT_TLDS:
            return False

        source_label = _registrable_label(source_host)
        destination_label = _registrable_label(destination_host)
        if source_label and source_label == destination_label:
            return True

        source_tokens = _host_tokens(source_host)
        destination_tokens = _host_tokens(destination_host)
        name_tokens = {
            token for token in re.split(r"[^a-z0-9]+", _normalise_text(university_name))
            if len(token) >= 4
        }
        # Sirve para portales con una marca abreviada en el dominio y nombre
        # completo en la página de origen/destino, sin permitir una mera
        # coincidencia de una palabra académica genérica.
        return bool(
            name_tokens
            and (source_tokens | destination_tokens) & name_tokens
            and source_tokens & destination_tokens
        )
    except (TypeError, ValueError):
        return False


def currentness_score(url: str, visible_text: str = "") -> int:
    """Devuelve una bonificación/penalización de vigencia para el ranking."""
    context = _normalise_text(f"{url or ''} {visible_text or ''}")
    score = 0
    if any(marker in context for marker in _HISTORICAL_MARKERS):
        score -= 180
    if any(marker in context for marker in _CURRENT_MARKERS):
        score += 45
    if re.search(r"(?:curso|curs|course)[-_ ]20(?:2[0-9]|3[0-9])", context):
        score += 20
    return score


def is_explicitly_historical(url: str, visible_text: str = "") -> bool:
    """Indica si la URL o su texto declaran que el plan no es el vigente."""
    context = _normalise_text(f"{url or ''} {visible_text or ''}")
    return any(marker in context for marker in _HISTORICAL_MARKERS)


def classify_source_failure(error: object = None, status_code: int | None = None) -> str:
    """Clasifica un fallo recuperable para dirigir el siguiente intento."""
    message = _normalise_text(error)
    if "robots" in message or "deneg" in message:
        return "robots_denegado"
    if "redirect" in message or "redireccion" in message:
        return "redireccion_institucional"
    if any(marker in message for marker in ("ssl", "tls", "eof", "hostname mismatch", "certificate")):
        return "tls_o_protocolo"
    if status_code in {401, 403} or "forbidden" in message:
        return "acceso_restringido"
    if status_code == 404 or "404" in message or "not found" in message:
        return "url_obsoleta_o_404"
    if any(marker in message for marker in ("pdf", "parse", "encoding", "html")):
        return "documento_no_parseable"
    if any(marker in message for marker in ("timeout", "connection", "stream", "protocol", "network")):
        return "fallo_transitorio_de_red"
    return "fuente_no_encontrada"
