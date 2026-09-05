"""Extractor semántico de mallas curriculares mediante microformatos y JSON-LD (schema.org).

Interpreta entidades normalizadas schema.org/Course, EducationalOccupationalProgram,
hasCourseInstance y CourseRun incrustadas en etiquetas <script type="application/ld+json">.
Garantiza máxima precisión semántica y cero ruido de maquetación HTML.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from bs4 import BeautifulSoup

from sanitizers import (
    classify_subject_caracter,
    curriculum_element_key,
    detect_academic_language,
    is_spurious_or_administrative_subject,
    normalize_cuatrimestre,
    normalize_curso,
    sanitize_subject_name,
)
from utils.credit_utils import parse_credit_number

logger = logging.getLogger(__name__)


def _extract_credits_from_node(node: dict) -> str:
    """Extrae el valor de créditos ECTS de nodos schema.org variados."""
    for key in ("numberOfCredits", "courseWorkload", "credits", "creditValue"):
        val = node.get(key)
        if val is None:
            continue
        if isinstance(val, (int, float)):
            parsed = parse_credit_number(val)
            if parsed:
                return str(int(parsed)) if parsed.is_integer() else str(parsed)
        elif isinstance(val, dict):
            sub_val = val.get("value") or val.get("numberOfCredits")
            if sub_val is not None:
                parsed = parse_credit_number(sub_val)
                if parsed:
                    return str(int(parsed)) if parsed.is_integer() else str(parsed)
        elif isinstance(val, str):
            parsed = parse_credit_number(val)
            if parsed:
                return str(int(parsed)) if parsed.is_integer() else str(parsed)
    return "6"


def _flatten_schema_entities(payload: object) -> list[dict]:
    """Aplana colecciones, listas y grafos (@graph) en una secuencia de dicts."""
    entities = []
    if isinstance(payload, dict):
        if "@graph" in payload and isinstance(payload["@graph"], list):
            for sub in payload["@graph"]:
                entities.extend(_flatten_schema_entities(sub))
        else:
            entities.append(payload)
            # Explorar cursos anidados (hasCourse, course, programPrerequisites)
            for sub_key in ("hasCourse", "course", "hasCourseInstance", "programCourses", "itemListElement"):
                sub_val = payload.get(sub_key)
                if isinstance(sub_val, list):
                    for elem in sub_val:
                        entities.extend(_flatten_schema_entities(elem))
                elif isinstance(sub_val, dict):
                    entities.extend(_flatten_schema_entities(sub_val))
    elif isinstance(payload, list):
        for item in payload:
            entities.extend(_flatten_schema_entities(item))
    return entities


def extract_schema_org_curriculum(soup: BeautifulSoup, base_url: str = "") -> list[dict]:
    """
    Localiza y parsea todos los bloques de metadatos JSON-LD schema.org en el documento.
    Retorna una lista de elementos curriculares normalizados para UniHub.
    """
    if not soup:
        return []

    scripts = soup.find_all("script", type=lambda t: t and "ld+json" in t.lower())
    if not scripts:
        return []

    collected_entities = []
    for s in scripts:
        raw_text = (s.string or s.get_text() or "").strip()
        if not raw_text:
            continue
        try:
            data = json.loads(raw_text)
            collected_entities.extend(_flatten_schema_entities(data))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    if not collected_entities:
        return []

    results = []
    seen_keys = set()

    for entity in collected_entities:
        if not isinstance(entity, dict):
            continue

        e_type = entity.get("@type", "")
        # Aceptar Course, CourseRun, o items de ListItem con item de tipo Course
        is_course = False
        if isinstance(e_type, str):
            is_course = any(k in e_type.lower() for k in ("course", "courseinstance", "courserun"))
        elif isinstance(e_type, list):
            is_course = any(any(k in str(t).lower() for k in ("course", "courseinstance", "courserun")) for t in e_type)

        raw_name = entity.get("name") or entity.get("courseName")
        if not raw_name:
            item_node = entity.get("item")
            if isinstance(item_node, dict):
                raw_name = item_node.get("name")
                if not is_course:
                    sub_type = str(item_node.get("@type", "")).lower()
                    is_course = "course" in sub_type
        
        if not is_course or not raw_name or not isinstance(raw_name, str):
            continue

        clean_name = sanitize_subject_name(raw_name)
        if len(clean_name) < 4 or is_spurious_or_administrative_subject(clean_name):
            continue

        norm_key = curriculum_element_key(clean_name)
        if norm_key in seen_keys:
            continue
        seen_keys.add(norm_key)

        # Código de asignatura
        code = ""
        for code_key in ("courseCode", "identifier", "courseIdentifier"):
            c_val = entity.get(code_key)
            if c_val and isinstance(c_val, (str, int)):
                c_str = str(c_val).strip()
                if re.match(r"^[A-Za-z0-9._-]{2,32}$", c_str):
                    code = c_str
                    break

        # Créditos ECTS
        creditos = _extract_credits_from_node(entity)

        # Carácter
        caracter = "OB"
        for car_key in ("courseType", "category", "educationalCredentialAwarded", "description"):
            car_text = entity.get(car_key)
            if isinstance(car_text, str) and car_text:
                classified = classify_subject_caracter(car_text, default="")
                if classified:
                    caracter = classified
                    break
        if caracter == "OB":
            caracter = classify_subject_caracter(clean_name, default="OB") or "OB"

        # Curso y cuatrimestre
        curso = "1"
        cuatri = "1C"
        for term_key in ("term", "courseSchedule", "academicTerm", "courseInstance"):
            t_val = entity.get(term_key)
            if isinstance(t_val, str):
                c_norm, _ = normalize_curso(t_val)
                if c_norm:
                    curso = c_norm
                q_norm = normalize_cuatrimestre(t_val)
                if q_norm:
                    cuatri = q_norm
            elif isinstance(t_val, dict):
                desc = str(t_val.get("description") or t_val.get("name") or "")
                c_norm, _ = normalize_curso(desc)
                if c_norm:
                    curso = c_norm
                q_norm = normalize_cuatrimestre(desc)
                if q_norm:
                    cuatri = q_norm

        # Enlace a guía docente
        url_guia = ""
        raw_url = entity.get("url") or entity.get("sameAs")
        if raw_url and isinstance(raw_url, str):
            raw_url_clean = raw_url.strip()
            if raw_url_clean.startswith("http"):
                url_guia = raw_url_clean
            elif base_url and not raw_url_clean.startswith("javascript:"):
                url_guia = urllib.parse.urljoin(base_url, raw_url_clean)

        # Idioma
        lang = entity.get("inLanguage")
        if not lang or not isinstance(lang, str):
            lang = detect_academic_language(clean_name)
        else:
            lang = lang[:2].lower()

        results.append({
            "modulo": "",
            "materia": "",
            "codigo_asignatura": code,
            "nombre_elemento": clean_name,
            "creditos_ects": creditos,
            "creditos": creditos,
            "caracter": caracter,
            "tipo": caracter,
            "curso": curso,
            "cuatrimestre": cuatri,
            "idioma": lang,
            "url_guia_docente": url_guia,
        })

    return results
