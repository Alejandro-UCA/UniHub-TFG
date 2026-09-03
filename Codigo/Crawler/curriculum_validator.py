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
    is_master = any(marker in level or marker in title for marker in ("máster", "master", "màster", "masterra", "431"))
    if is_master:
        if any(marker in title for marker in ("doble", "simultaneidad", "pceo", "double")):
            return 120.0
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

    if "medicina" in title:
        return float(MEDICINA_ECTS)
    if any(marker in title for marker in ("veterinaria", "farmacia", "odontología", "odontologia", "arquitectura")):
        return float(ESPECIALES_GRADO_ECTS)
    if any(marker in title for marker in ("doble", "simultaneidad", "pceo", "double")):
        return float(ESPECIALES_GRADO_ECTS)

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


def get_declared_curriculum_total_ects(resumen_creditos: dict) -> float | None:
    """Devuelve el total oficial declarado en el BOE, si es verosímil."""
    if not isinstance(resumen_creditos, dict):
        return None
    raw_value = (
        resumen_creditos.get("Créditos Totales")
        or resumen_creditos.get("Creditos Totales")
        or resumen_creditos.get("Total")
        or resumen_creditos.get("total")
    )
    value = _parse_credit_number(raw_value)
    return value if value is not None and value >= 30 else None


def get_curriculum_completeness_status(degree_dict: dict) -> dict:
    """Devuelve un diagnóstico estable y apto para persistencia/API."""
    empty = {
        "is_complete": False,
        "total_ects_obtained": 0.0,
        "total_ects_listed": 0.0,
        "total_ects_declared": None,
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
        prog_doc = degree_dict.get("programa_doctoral") or (plan.get("programa_doctoral") if isinstance(plan, dict) else {})
        lineas = prog_doc.get("lineas_investigacion") if isinstance(prog_doc, dict) else []
        elements = plan.get("elementos_curriculares") if isinstance(plan, dict) else None
        total_elements = len(elements) if isinstance(elements, list) else 0
        total_lineas = len(lineas) if isinstance(lineas, list) else 0
        has_structure = (total_elements > 0) or (total_lineas > 0)
        return {
            "is_complete": has_structure,
            "total_ects_obtained": 0.0,
            "total_ects_listed": 0.0,
            "total_ects_declared": None,
            "required_ects": 0.0,
            "total_elementos": max(total_elements, total_lineas),
            "total_subjects": max(total_elements, total_lineas),
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
    listed_total = compute_curriculum_total_ects(elements)
    declared_total = get_declared_curriculum_total_ects(summary)
    # Las tablas BOE pueden listar todas las optativas posibles, cuya suma
    # supera el itinerario que debe cursar el estudiante. Para informar y
    # persistir la carga del plan, prevalece el total declarado por el BOE;
    # la suma de filas se conserva para decidir si hay detalle suficiente.
    obtained = declared_total if total_elements and declared_total is not None else listed_total

    min_subjects = 16 if required >= 180 else (6 if required >= 60 else 3)
    has_normative_summary_and_full_core = (
        declared_total is not None
        and declared_total >= required
        and listed_total >= 0.80 * required
        and total_elements >= min_subjects
    )

    if plan.get("es_alianza_europea") or plan.get("tipo_estructura") == "consorcio_europeo_erasmus_mundus":
        complete = bool(total_elements and (listed_total >= required or listed_total >= 0.80 * required))
        status = "consorcio_estructural" if complete else "consorcio_sin_detalle"
    elif total_elements == 0:
        complete = False
        status = "solo_resumen" if summary else "sin_asignaturas"
    elif listed_total >= required:
        complete = True
        status = "completo"
    elif has_normative_summary_and_full_core:
        complete = True
        status = "completo_normativo"
    else:
        complete = False
        status = "incompleto_parcial"

    return {
        "is_complete": complete,
        "total_ects_obtained": obtained,
        "total_ects_listed": listed_total,
        "total_ects_declared": declared_total,
        "required_ects": required,
        "total_elementos": total_elements,
        "total_subjects": total_elements,
        "status": status,
    }


def is_curriculum_complete(degree_dict: dict) -> bool:
    """Indica si el plan contiene toda la carga lectiva exigida."""
    return get_curriculum_completeness_status(degree_dict)["is_complete"]
