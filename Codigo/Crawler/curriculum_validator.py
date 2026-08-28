"""Validación transversal de completitud de planes de estudio."""

import re

from config import (
    ESPECIALES_GRADO_ECTS,
    GRADO_STANDARD_ECTS,
    MASTER_MIN_ECTS,
    MEDICINA_ECTS,
)


def is_doctorate_program(d_level: str, d_title: str) -> bool:
    """Identifica programas de Doctorado, incluida su codificación RUCT."""
    level = (d_level or "").lower()
    title = (d_title or "").lower()
    markers = (
        "doctorado", "doctorat", "doutoramento", "doktoregoa", "phd",
        "doctorate", "programa de doctorado",
    )
    return any(marker in level or marker in title for marker in markers) or "560" in level or "900" in level


def _parse_credit_number(raw_value) -> float | None:
    if raw_value is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", str(raw_value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def get_required_degree_credits(
    d_level: str,
    d_title: str,
    resumen_creditos: dict = None,
) -> float:
    """Calcula los ECTS reglamentarios de una titulación española."""
    level = (d_level or "").lower()
    title = (d_title or "").lower()

    if is_doctorate_program(d_level, d_title):
        return 0.0

    if isinstance(resumen_creditos, dict):
        declared_total = (
            resumen_creditos.get("Créditos Totales")
            or resumen_creditos.get("Creditos Totales")
            or resumen_creditos.get("Total")
            or resumen_creditos.get("total")
        )
        parsed_total = _parse_credit_number(declared_total)
        if parsed_total is not None and parsed_total >= 30:
            # Un resumen de modificación BOE puede contener solo 30–60 ECTS;
            # nunca debe reducir el total reglamentario de un grado.
            is_degree = any(marker in level or marker in title for marker in ("grado", "bachelor", "licenciatura", "diplomatura", "240", "231"))
            if not (is_degree and parsed_total < 180):
                return parsed_total
    if "medicina" in title:
        return float(MEDICINA_ECTS)
    if any(marker in title for marker in ("veterinaria", "farmacia", "odontología", "odontologia", "arquitectura")):
        return float(ESPECIALES_GRADO_ECTS)
    if any(marker in title for marker in ("doble", "simultaneidad", "pceo", "double")):
        return float(ESPECIALES_GRADO_ECTS)

    is_master = any(marker in level or marker in title for marker in ("máster", "master", "màster", "masterra", "431"))
    if is_master:
        if any(marker in title for marker in (
            "ingeniería industrial", "ingenieria industrial",
            "ingeniería de caminos", "ingenieria de caminos",
            "ingeniería de telecomunicación", "ingenieria de telecomunicacion",
            "ingeniería de telecomunicaciones", "ingeniería aeronáutica",
            "ingenieria aeronautica", "ingeniería agronómica",
            "ingenieria agronomica", "ingeniería naval", "ingenieria naval",
            "ingeniería de montes", "ingenieria de montes",
        )):
            return 120.0
        if any(marker in title for marker in (
            "abogacía", "abogacia", "abogacía y procura", "abogacia y procura",
            "psicología general sanitaria", "psicologia general sanitaria",
        )):
            return 90.0
        return float(MASTER_MIN_ECTS)

    return float(GRADO_STANDARD_ECTS)


def compute_curriculum_total_ects(elementos: list) -> float:
    """Suma únicamente valores ECTS numéricos y académicamente plausibles."""
    if not isinstance(elementos, list):
        return 0.0
    total = 0.0
    for element in elementos:
        if not isinstance(element, dict):
            continue
        raw_value = element.get("creditos_ects")
        if raw_value is None:
            raw_value = element.get("creditos")
        if raw_value is None:
            raw_value = element.get("ects")
        credits = _parse_credit_number(raw_value)
        if credits is not None and 0 < credits <= 60:
            total += credits
    return round(total, 2)


def get_curriculum_completeness_status(degree_dict: dict) -> dict:
    """Devuelve un diagnóstico estable y apto para persistencia/API."""
    empty = {
        "is_complete": False,
        "total_ects_obtained": 0.0,
        "required_ects": float(GRADO_STANDARD_ECTS),
        "total_elementos": 0,
        "total_subjects": 0,
        "status": "sin_datos",
    }
    if not isinstance(degree_dict, dict) or not degree_dict:
        return empty

    level = degree_dict.get("nivel_academico", "")
    title = degree_dict.get("titulo", "")
    plan = degree_dict.get("plan_estudios")
    if plan is None and "elementos_curriculares" in degree_dict:
        plan = degree_dict

    if is_doctorate_program(level, title):
        elements = plan.get("elementos_curriculares") if isinstance(plan, dict) else None
        total_elements = len(elements) if isinstance(elements, list) else 0
        # Un diccionario vacío o una plantilla normativa no demuestra que el
        # programa tenga un plan verificable. El Doctorado no se valida por un
        # total ECTS fijo, pero sí necesita elementos académicos observables.
        has_structure = total_elements > 0
        return {
            "is_complete": has_structure,
            "total_ects_obtained": 0.0,
            "required_ects": 0.0,
            "total_elementos": total_elements,
            "total_subjects": total_elements,
            "status": "doctorado_estructural" if has_structure else "doctorado_sin_detalle",
        }

    required = get_required_degree_credits(level, title)
    if not isinstance(plan, dict) or not plan:
        return {
            **empty,
            "required_ects": required,
            "status": "sin_plan",
        }

    elements = plan.get("elementos_curriculares") or []
    total_elements = len(elements)
    summary = plan.get("resumen_creditos") or {}
    required = get_required_degree_credits(level, title or plan.get("nombre_plan", ""), summary)
    obtained = compute_curriculum_total_ects(elements)

    if plan.get("es_alianza_europea") or plan.get("tipo_estructura") == "consorcio_europeo_erasmus_mundus":
        complete = bool(total_elements and obtained >= required)
        status = "consorcio_estructural" if complete else "consorcio_sin_detalle"
    elif total_elements == 0:
        complete = False
        status = "solo_resumen" if summary else "sin_asignaturas"
    elif obtained >= required:
        complete = True
        status = "completo"
    else:
        complete = False
        status = "incompleto_parcial"

    return {
        "is_complete": complete,
        "total_ects_obtained": obtained,
        "required_ects": required,
        "total_elementos": total_elements,
        "total_subjects": total_elements,
        "status": status,
    }


def is_curriculum_complete(degree_dict: dict) -> bool:
    """Indica si el plan contiene toda la carga lectiva exigida."""
    return get_curriculum_completeness_status(degree_dict)["is_complete"]
