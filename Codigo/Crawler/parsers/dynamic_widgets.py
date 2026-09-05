"""Extractor de mallas curriculares servidas vía microservicios y widgets dinámicos HTML5."""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from bs4 import BeautifulSoup

from utils.sanitizers import (
    classify_subject_caracter,
    curriculum_element_key,
    detect_academic_language,
    is_spurious_or_administrative_subject,
    normalize_cuatrimestre,
    normalize_curso,
    sanitize_string_value,
    sanitize_subject_name,
)
from core.downloader import is_same_or_subdomain
from parsers.html_tables import extract_html_subjects

logger = logging.getLogger(__name__)

def extract_dynamic_widget_subjects(
    soup: BeautifulSoup,
    current_page_url: str,
    web_url: str,
    downloader,
) -> list:
    """
    Detecta y consulta microservicios y widgets HTML5 dinámicos (data-config, data-url, data-endpoint)
    que cargan mallas curriculares de forma desacoplada en portales universitarios.
    Garantiza estricta neutralidad agnóstica (sin lógica por universidad) y seguridad de dominio (anti-SSRF).
    """
    if not soup or not current_page_url or not downloader:
        return []

    academic_widget_keywords = (
        "plan", "estudio", "estudis", "asignatura", "assignatura",
        "curriculum", "malla", "docencia", "guia", "subject", "course",
        "grau", "grado", "master", "máster"
    )

    candidates = []
    # 1. Atributos data-config con JSON estructurado
    for el in soup.find_all(attrs={"data-config": True}):
        raw_cfg = el.get("data-config", "").strip()
        if not raw_cfg:
            continue
        try:
            cfg = json.loads(raw_cfg)
            if isinstance(cfg, dict):
                target_url = cfg.get("url") or cfg.get("endpoint") or cfg.get("api")
                if target_url:
                    candidates.append((el, str(target_url), cfg))
        except (json.JSONDecodeError, ValueError):
            pass

    # 2. Atributos directos data-url / data-endpoint / data-ajax-url / data-api-url / data-service-url
    for attr_name in ("data-url", "data-endpoint", "data-ajax-url", "data-api-url", "data-service-url"):
        for el in soup.find_all(attrs={attr_name: True}):
            target_url = el.get(attr_name, "").strip()
            if target_url and not any(c[1] == target_url for c in candidates):
                candidates.append((el, target_url, {}))

    if not candidates:
        return []

    for el, target_url, cfg in candidates:
        # Filtro semántico: descartar widgets no académicos (tiempo, cookies, menús, etc.)
        combined_meta = (
            target_url.lower()
            + " " + " ".join(str(k).lower() + " " + str(v).lower() for k, v in cfg.items())
            + " " + " ".join(el.get("class", []))
            + " " + (el.get("id") or "")
        )
        if not any(ak in combined_meta for ak in academic_widget_keywords):
            continue

        full_service_url = urllib.parse.urljoin(current_page_url, target_url)
        if not is_same_or_subdomain(full_service_url, web_url):
            continue

        # Incorporar parámetros de consulta si el data-config los provee
        query_params = {}
        for k, v in cfg.items():
            if k in ("url", "endpoint", "api", "txt_loading", "wsid", "servicioweb"):
                continue
            if isinstance(v, (str, int, float)) and str(v).strip():
                query_params[k] = str(v).strip()

        if query_params:
            parsed = urllib.parse.urlparse(full_service_url)
            existing_qs = urllib.parse.parse_qsl(parsed.query)
            merged_qs = existing_qs + list(query_params.items())
            full_service_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(merged_qs)))

        try:
            content = downloader.fetch_text(full_service_url)
            if not content:
                continue

            html_payload = ""
            trimmed = content.strip()
            if trimmed.startswith("{") and trimmed.endswith("}"):
                try:
                    data = json.loads(trimmed)
                    if isinstance(data, dict):
                        for key in ("html", "content", "data", "body", "rendered"):
                            if isinstance(data.get(key), str) and len(data[key]) > 20:
                                html_payload = data[key]
                                break
                except Exception:
                    pass
            if not html_payload:
                html_payload = content

            sub_soup = BeautifulSoup(html_payload, "html.parser")
            
            # Intento A: Tablas curriculares estándar
            extracted = extract_html_subjects(sub_soup, base_url=full_service_url)
            if len(extracted) >= 3:
                return extracted

            # Intento B: Tarjetas y filas estructuradas no tabulares (.asi, .asignatura, etc.)
            row_nodes = sub_soup.select(
                ".asi, .asig-item, .asignatura-item, .subject-card, .subject-row, "
                ".materia-item, .plan-estudios-item, .course-item, [data-subject], [data-asignatura]"
            )
            if not row_nodes:
                row_nodes = [
                    p for p in sub_soup.find_all(["div", "li", "tr"])
                    if p.find("a", href=True) and any(g in p.find("a", href=True)["href"].lower() for g in ["guia", "guiadocente", "asig=", "codasi=", "docencia"])
                ]

            block_results = []
            seen_names = set()
            for node in row_nodes:
                lines = [l.strip() for l in node.get_text(separator="\n").splitlines() if l.strip()]
                if not lines:
                    continue

                code = ""
                name = ""
                a_tag = node.find("a", href=True)
                guide_url = ""
                if a_tag:
                    guide_url = urllib.parse.urljoin(full_service_url, a_tag["href"])
                    a_text = a_tag.get_text(" ", strip=True)
                    m_a = re.match(r"^(\d{2,10})\s*[-–—:]\s*(.+)$", a_text)
                    if m_a:
                        code = m_a.group(1).strip()
                        name = m_a.group(2).strip()
                    elif len(a_text) >= 4 and not a_text.isdigit():
                        name = a_text

                if not name:
                    for l in lines:
                        m = re.match(r"^(\d{2,10})\s*[-–—:]\s*(.+)$", l)
                        if m:
                            code = m.group(1).strip()
                            name = m.group(2).strip()
                            break

                if not name:
                    for l in lines:
                        if len(l) >= 4 and not l.isdigit() and not any(k in l.lower() for k in ["básica", "basica", "obligatoria", "optativa", "curso", "semestre"]):
                            name = l
                            break

                name = sanitize_subject_name(name)
                if not name or len(name) < 3:
                    continue

                norm_key = curriculum_element_key(name)
                if norm_key in seen_names:
                    continue
                seen_names.add(norm_key)

                creditos = None
                for l in reversed(lines):
                    m_c = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:ects|cr[eé]ditos)?\b", l, re.I)
                    if m_c:
                        try:
                            c_f = float(m_c.group(1).replace(",", "."))
                            if 1.0 <= c_f <= 30.0:
                                creditos = str(int(c_f)) if c_f.is_integer() else str(c_f)
                                break
                        except ValueError:
                            pass

                caracter = classify_subject_caracter(" ".join(lines), default="OB")
                curso = ""
                for l in lines:
                    c_norm, _ = normalize_curso(l)
                    if c_norm:
                        curso = c_norm
                        break

                cuatri = ""
                for l in lines:
                    q_norm = normalize_cuatrimestre(l)
                    if q_norm:
                        cuatri = q_norm
                        break

                elem = {
                    "modulo": "",
                    "materia": "",
                    "codigo_asignatura": code,
                    "nombre_elemento": name,
                    "creditos_ects": creditos or "6",
                    "creditos": creditos or "6",
                    "caracter": caracter,
                    "tipo": caracter,
                    "curso": curso or "1º",
                    "cuatrimestre": cuatri or "1C",
                    "idioma": detect_academic_language(name),
                }
                if guide_url:
                    elem["url_guia_docente"] = guide_url
                block_results.append(elem)

            if len(block_results) >= 3:
                return block_results

        except Exception as widget_err:
            logger.debug("Excepción en resolución de widget dinámico '%s': %s", full_service_url, widget_err)
            continue

    return []

