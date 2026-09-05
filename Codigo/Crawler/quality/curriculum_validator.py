"""Validación transversal de completitud de planes de estudio."""

import re
from collections import defaultdict

from core.config import (
    ESPECIALES_GRADO_ECTS,
    GRADO_STANDARD_ECTS,
    MASTER_MIN_ECTS,
    MEDICINA_ECTS,
)


def is_doctorate_program(d_level: str, d_title: str) -> bool:
    """Identifica programas de Doctorado por lenguaje académico explícito."""
    level = (d_level or "").lower()
    title = (d_title or "").lower()
    markers = (
        "doctorado", "doctorat", "doutoramento", "doktoregoa", "phd",
        "doctorate", "programa de doctorado",
    )
    return any(marker in level or marker in title for marker in markers)


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
    is_master = bool(re.search(r"\bm.?ster(?:es|s)?\b", level)) or bool(
        re.search(r"\bm.?ster(?:es|s)?\b", title)
    ) or any(
        marker in level or marker in title
        for marker in ("posgrado", "postgrado", "postgrau", "posgrao", "masterra")
    )
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


_OPTIONAL_CODES = frozenset({"OP", "OPT", "OPTATIVA", "OPTATIVAS"})
_NON_CURRICULAR_CODES = frozenset({"PE", "PRACTICAS", "PRACTICA", "TFG", "TFM", "TESIS"})


def summarize_curriculum_elements(elementos: list) -> dict:
    """Resume créditos fijos y créditos ofertados como alternativas.

    El listado publicado por una universidad suele incluir todas las optativas
    posibles, aunque el alumno solo tenga que superar una parte de ellas. La
    suma plana de filas es, por tanto, una cota superior y no una duración del
    título. Este resumen conserva ambas magnitudes para que la capa de calidad
    pueda decidir de forma conservadora.
    """
    fixed = 0.0
    optional = 0.0
    counted = 0
    optional_count = 0
    for element in elementos if isinstance(elementos, list) else []:
        if not isinstance(element, dict):
            continue
        credits = _parse_credit_number(
            element.get("creditos_ects")
            or element.get("creditos")
            or element.get("ects")
        )
        if credits is None or not 0 < credits <= 60:
            continue
        counted += 1
        character = str(element.get("caracter") or element.get("tipo") or "").strip().upper()
        if character in _OPTIONAL_CODES or character.startswith("OP"):
            optional += credits
            optional_count += 1
        elif character not in _NON_CURRICULAR_CODES:
            fixed += credits
        else:
            fixed += credits
    return {
        "total_listado": round(fixed + optional, 2),
        "total_fijo": round(fixed, 2),
        "total_optativo_ofertado": round(optional, 2),
        "total_elementos_con_ects": counted,
        "total_elementos_optativos": optional_count,
        "hay_optativas_alternativas": optional_count > 0,
    }


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


def infer_summary_curriculum_total_ects(
    resumen_creditos: dict,
    required_ects: float,
) -> float | None:
    """Infiere el total desde una distribución académica completa.

    Algunas resoluciones no publican una clave ``Total``: sólo enumeran
    formación básica, obligatorias, optativas, prácticas y trabajo final. Se
    acepta la suma únicamente cuando contiene varias categorías académicas,
    todos los valores son plausibles y coincide prácticamente con la carga
    reglamentaria; así no se confunden contadores, páginas o porcentajes con
    créditos.
    """
    if not isinstance(resumen_creditos, dict) or required_ects <= 0:
        return None
    category_markers = (
        "formaci", "obligat", "optat", "pract", "práct", "trabajo", "treball",
        "tesis", "modul", "módul", "materia", "complement", "investig",
        "básica", "basica", "externas", "externs",
    )
    values = []
    for label, raw_value in resumen_creditos.items():
        label_text = str(label or "").casefold()
        if not any(marker in label_text for marker in category_markers):
            continue
        value = _parse_credit_number(raw_value)
        if value is not None and 0 < value <= 360:
            values.append(value)
    if len(values) < 2:
        return None
    total = round(sum(values), 2)
    tolerance = max(3.0, float(required_ects) * 0.05)
    return total if abs(total - float(required_ects)) <= tolerance else None


_ITINERARY_PREFIX_RE = re.compile(
    r"\b(?:menci[oó]n|menci[oò]|especialidad|especialitat|especialidade|itinerario|itinerari|ibilbidea|rama)\s*(?:en|de|:)?\s*([A-Za-zÀ-ÿ0-9\s]{3,60})",
    re.I,
)

_ITINERARY_BRACKET_RE = re.compile(
    r"[(\[]\s*(?:menci[oó]n|menci[oò]|esp\.?|especialidad|itinerario)\s*(?:en|de|:)?\s*([A-Za-zÀ-ÿ0-9\s]{3,60})[)\]]",
    re.I,
)


def detect_curriculum_itineraries(elements: list, required_ects: float = 240.0) -> dict:
    """Detecta y segrega materias de especialidad o menciones alternativas."""
    empty_result = {
        "tiene_itinerarios": False,
        "itinerarios_validos": False,
        "troncal_comun": [],
        "ects_troncal_comun": 0.0,
        "itinerarios": {},
        "ects_por_itinerario": {},
        "total_ects_por_itinerario": {},
    }
    if not isinstance(elements, list) or not elements:
        return empty_result

    troncal_comun = []
    itinerarios = defaultdict(list)

    for item in elements:
        if not isinstance(item, dict):
            continue

        itin_name = (
            str(item.get("itinerario") or "").strip()
            or str(item.get("mencion") or "").strip()
            or str(item.get("especialidad") or "").strip()
        )

        if not itin_name:
            for field in ("modulo", "materia"):
                val = str(item.get(field) or "").strip()
                m_brack = _ITINERARY_BRACKET_RE.search(val)
                if m_brack:
                    itin_name = m_brack.group(1).strip()
                    break
                m_pref = _ITINERARY_PREFIX_RE.search(val)
                if m_pref:
                    itin_name = m_pref.group(1).strip()
                    break

        if not itin_name:
            nom = str(item.get("nombre_elemento") or "").strip()
            m_brack = _ITINERARY_BRACKET_RE.search(nom)
            if m_brack:
                itin_name = m_brack.group(1).strip()
            else:
                m_pref = _ITINERARY_PREFIX_RE.search(nom)
                if m_pref:
                    itin_name = m_pref.group(1).strip()

        if itin_name:
            itin_name = re.sub(r"[\)\],;:\-]+$", "", itin_name).strip()
            itin_name = " ".join(itin_name.split()).title()

        caracter = str(item.get("caracter") or "").strip().upper()
        if not itin_name or caracter in {"FB", "OB", "TFG", "TFM"}:
            troncal_comun.append(item)
        else:
            itinerarios[itin_name].append(item)

    if not itinerarios:
        return empty_result

    ects_troncal = compute_curriculum_total_ects(troncal_comun)
    ects_por_itinerario = {}
    total_ects_por_itinerario = {}

    for name, items in itinerarios.items():
        itin_credits = compute_curriculum_total_ects(items)
        ects_por_itinerario[name] = itin_credits
        total_ects_por_itinerario[name] = round(ects_troncal + itin_credits, 2)

    tolerance = max(4.0, float(required_ects) * 0.03) if required_ects > 0 else 0.0

    itinerarios_validos = (
        len(itinerarios) >= 2
        and required_ects > 0
        and all(
            abs(total - float(required_ects)) <= tolerance
            for total in total_ects_por_itinerario.values()
        )
    )

    return {
        "tiene_itinerarios": bool(len(itinerarios) >= 1),
        "itinerarios_validos": itinerarios_validos,
        "troncal_comun": troncal_comun,
        "ects_troncal_comun": round(ects_troncal, 2),
        "itinerarios": dict(itinerarios),
        "ects_por_itinerario": ects_por_itinerario,
        "total_ects_por_itinerario": total_ects_por_itinerario,
    }


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
        has_official_source = bool(
            degree_dict.get("boe_url")
            or degree_dict.get("web")
            or (isinstance(plan, dict) and (plan.get("boe_url") or plan.get("web")))
        )
        is_complete = has_structure or has_official_source
        return {
            "is_complete": is_complete,
            "total_ects_obtained": 0.0,
            "total_ects_listed": 0.0,
            "total_ects_declared": None,
            "required_ects": 0.0,
            "total_elementos": max(total_elements, total_lineas),
            "total_subjects": max(total_elements, total_lineas),
            "status": "doctorado_estructural" if has_structure else ("doctorado_oficial" if has_official_source else "doctorado_sin_detalle"),
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
    summary_totals = summarize_curriculum_elements(elements)
    listed_total = summary_totals["total_listado"]
    element_text = " ".join(
        str(element.get(field) or "")
        for element in elements
        if isinstance(element, dict)
        for field in ("nombre_elemento", "materia", "modulo")
    ).casefold()
    legacy_plan_table_detected = any(
        marker in element_text
        for marker in (
            "plan de estudios de la licenciatura",
            "plan de estudios de la diplomatura",
            "previous plan of studies",
            "ancien plan d'études",
        )
    )
    declared_total = get_declared_curriculum_total_ects(summary)
    if declared_total is None:
        declared_total = infer_summary_curriculum_total_ects(summary, required)
    # Las tablas BOE pueden listar todas las optativas posibles, cuya suma
    # supera el itinerario que debe cursar el estudiante. Para informar y
    # persistir la carga del plan, prevalece el total declarado por el BOE;
    # la suma de filas se conserva para decidir si hay detalle suficiente.
    obtained = declared_total if total_elements and declared_total is not None else listed_total

    min_subjects = 16 if required >= 180 else (6 if required >= 60 else 3)
    # La suma de filas puede superar ampliamente la carga del título cuando
    # una resolución enumera una oferta completa de optativas alternativas.
    # Un total oficial, un núcleo fijo razonable y suficientes filas son
    # evidencia de esa estructura; no debe confundirse con una ficha ajena.
    optional_offer_excess_expected = (
        required > 0
        and declared_total is not None
        and declared_total >= required
        and summary_totals["hay_optativas_alternativas"]
        and summary_totals["total_fijo"] >= max(0.40 * required, required - 60.0)
        and total_elements >= min_subjects
    )
    # Una ficha ajena puede contener muchas asignaturas plausibles y superar
    # el umbral mínimo, aunque su carga total sea incompatible con el nivel
    # objetivo. Se conserva la cuarentena salvo que la propia tabla demuestre
    # el patrón normativo de optativas ofertadas descrito arriba.
    implausible_excess = (
        required > 0
        and listed_total > max(float(required) * 3.0, float(required) + 120.0)
        and not optional_offer_excess_expected
    )
    # Un total normativo no sustituye al detalle curricular. Algunas
    # publicaciones oficiales contienen un resumen completo y solo parte de
    # las filas (por ejemplo, una modificación o una tabla paginada). Ese
    # caso puede aceptarse de forma conservadora cuando el detalle cubre una
    # parte sustancial de la carga, pero no cuando el resumen es lo único que
    # hace que el plan parezca completo. El margen de 60 ECTS permite las
    # estructuras habituales con trabajo final/prácticas o módulos no
    # desglosados, manteniendo un suelo relativo del 80 %.
    minimum_listed_detail = max(0.80 * required, required - 60.0)
    # En másteres oficiales es habitual que el bloque fijo incluya 30–42
    # ECTS y que la carga restante se complete mediante optativas ofertadas.
    # Cuando esas filas llevan carácter explícito, exigir el 80 % del total
    # fijo descarta estructuras legítimas de 60 ECTS. Se relaja sólo el suelo
    # de esta inferencia (no la identidad, la fuente ni la cobertura mínima de
    # asignaturas), y sólo para el nivel académico de máster.
    level_title = f"{level} {title}".casefold()
    is_master_level = bool(
        re.search(r"\bm[aá]ster(?:es|s)?\b", level_title)
        or any(marker in level_title for marker in ("posgrado", "postgrado", "postgrau", "posgrao", "masterra"))
    )
    optional_inference_fixed_floor = minimum_listed_detail
    if is_master_level:
        optional_inference_fixed_floor = max(0.60 * required, required - 60.0)
    elif (
        required >= 120
        and summary_totals["total_elementos_optativos"] >= 3
        and summary_totals["total_optativo_ofertado"] >= max(18.0, 0.10 * required)
        and listed_total >= 1.20 * required
    ):
        # Algunas fichas oficiales separan la oferta optativa en una sección
        # propia, pero no publican una columna de carácter ni un resumen de
        # créditos. En ese patrón la suma de filas puede superar ampliamente
        # la carga exigida aunque el núcleo fijo sea inferior al 80 %: la
        # oferta enumerada es una bolsa de elección, no una carga simultánea.
        # El suelo del 65 %, la oferta mínima y el exceso total evitan aceptar
        # una tabla parcial con unas pocas optativas accidentales.
        optional_inference_fixed_floor = 0.65 * required
    has_normative_summary_and_full_core = (
        declared_total is not None
        and declared_total >= required
        and summary_totals["total_fijo"] >= minimum_listed_detail
        and total_elements >= min_subjects
    )

    # Cuando la fuente no ofrece una fila de total, todavía puede demostrar
    # una estructura completa: el núcleo fijo cubre la carga sustancial y la
    # oferta optativa contiene al menos la diferencia necesaria hasta el total
    # reglamentario. En ese caso las optativas son alternativas ofertadas, no
    # créditos adicionales que deban cursarse todos. La regla es global y
    # conserva el rechazo de tablas donde sólo aparecen optativas o falta
    # detalle suficiente.
    inferred_optional_completion = (
        summary_totals["hay_optativas_alternativas"]
        and declared_total is None
        and total_elements >= min_subjects
        and summary_totals["total_fijo"] >= optional_inference_fixed_floor
        and summary_totals["total_optativo_ofertado"] >= max(
            0.0,
            required - summary_totals["total_fijo"],
        )
    )

    # En una oferta optativa sin total declarado, ``listed_total`` representa
    # todos los créditos ofertados, no los que debe cursar simultáneamente un
    # estudiante. La inferencia sólo se activa cuando el núcleo fijo y la
    # oferta cubren la carga reglamentaria; por tanto, el total efectivo que
    # se publica debe ser la carga exigida y la oferta completa debe conservarse
    # en ``total_ects_listed``.
    if inferred_optional_completion and required > 0:
        obtained = float(required)

    # Sin total declarado no se puede saber qué subconjunto de optativas debe
    # cursarse. Publicar el sumatorio bruto produciría falsos planes completos.
    unresolved_alternatives = (
        summary_totals["hay_optativas_alternativas"]
        and declared_total is None
        and not inferred_optional_completion
    )

    # Un valor explícito inferior a la carga reglamentaria es una
    # contradicción, no una evidencia de que la suma de filas sea correcta.
    # Este caso aparece al capturar un subtotal de una ficha docente o una
    # sección del plan y mezclar después filas de competencias o información
    # auxiliar. La suma bruta no debe convertir esa fuente en un plan completo.
    declared_total_conflict = (
        declared_total is not None
        and required > 0
        and declared_total < required
        and not summary_totals["hay_optativas_alternativas"]
        and listed_total >= required
    )

    itinerary_data = detect_curriculum_itineraries(elements, required)
    if itinerary_data.get("tiene_itinerarios") and itinerary_data.get("itinerarios_validos"):
        unresolved_alternatives = False
        implausible_excess = False
        if required > 0:
            obtained = float(required)

    if plan.get("es_alianza_europea") or plan.get("tipo_estructura") == "consorcio_europeo_erasmus_mundus":
        complete = bool(total_elements and (listed_total >= required or listed_total >= 0.80 * required))
        status = "consorcio_estructural" if complete else "consorcio_sin_detalle"
    elif total_elements == 0:
        complete = False
        status = "solo_resumen" if summary else "sin_asignaturas"
    elif itinerary_data.get("itinerarios_validos"):
        complete = True
        status = "completo_con_menciones"
    elif unresolved_alternatives:
        complete = False
        status = "optatividad_no_resuelta"
    elif inferred_optional_completion:
        complete = True
        status = "completo_optatividad_inferida"
    elif listed_total >= required and not summary_totals["hay_optativas_alternativas"]:
        complete = True
        status = "completo"
    elif (
        declared_total is not None
        and declared_total >= required
        and listed_total >= required
        and total_elements > 0
    ):
        # Cuando la fuente declara el total oficial y la tabla incluye al
        # menos esa carga, las filas optativas pueden ser alternativas
        # ofertadas y no créditos adicionales que deba cursar cada alumno.
        # No exigir que ``total_fijo`` alcance el total evita degradar planes
        # legítimos con optatividad explícita, pero el requisito de que la
        # tabla sume la carga completa impide aceptar un mero resumen
        # normativo con unas pocas filas inconexas.
        complete = True
        status = "completo_normativo"
    elif has_normative_summary_and_full_core:
        complete = True
        status = "completo_normativo"
    else:
        complete = False
        status = "incompleto_parcial"

    if legacy_plan_table_detected:
        complete = False
        status = "tabla_plan_historico"
    elif implausible_excess:
        complete = False
        status = "inconsistencia_exceso_ects"
    elif declared_total_conflict:
        complete = False
        status = "inconsistencia_total_declarado"

    return {
        "is_complete": complete,
        "total_ects_obtained": obtained,
        "total_ects_listed": listed_total,
        "total_ects_declared": declared_total,
        "required_ects": required,
        "total_elementos": total_elements,
        "total_subjects": total_elements,
        "total_ects_fijos": summary_totals["total_fijo"],
        "total_ects_optativos_ofertados": summary_totals["total_optativo_ofertado"],
        "optatividad_no_resuelta": unresolved_alternatives,
        "optatividad_inferida_resuelta": inferred_optional_completion,
        "segmentacion_menciones": itinerary_data if itinerary_data.get("tiene_itinerarios") else None,
        "status": status,
    }


def is_curriculum_complete(degree_dict: dict) -> bool:
    """Indica si el plan contiene toda la carga lectiva exigida."""
    return get_curriculum_completeness_status(degree_dict)["is_complete"]


def infer_missing_courses_in_curriculum(elementos: list, total_duracion_anos: int = 4) -> list:
    """Infiere cursos secuenciales por acumulación de créditos ECTS si faltan en materias.
    
    Aplica los principios del RD 822/2021:
    - 60 ECTS por curso académico estándar.
    - FB (Formación Básica) se concentra en los primeros cursos (1º o 2º).
    - TFG / TFM se ancla en el último curso según la duración del título.
    """
    if not isinstance(elementos, list) or not elementos:
        return elementos

    with_curso = [item for item in elementos if isinstance(item, dict) and str(item.get("curso") or "").strip()]
    if len(with_curso) >= max(3, int(len(elementos) * 0.75)):
        return elementos

    cumulative_ects = 0.0
    for item in elementos:
        if not isinstance(item, dict):
            continue
        existing_curso = str(item.get("curso") or "").strip()
        caracter = str(item.get("caracter") or item.get("tipo") or "").strip().upper()
        nombre = str(item.get("nombre_elemento") or "").strip().lower()

        raw_credits = item.get("creditos_ects") or item.get("creditos") or item.get("ects")
        try:
            credits = float(str(raw_credits).replace(",", ".")) if raw_credits is not None else 6.0
            if credits <= 0 or credits > 60:
                credits = 6.0
        except (ValueError, TypeError):
            credits = 6.0

        if existing_curso:
            m_curso = re.search(r"(\d+)", existing_curso)
            if m_curso:
                c_num = int(m_curso.group(1))
                cumulative_ects = max(cumulative_ects, (c_num - 1) * 60.0 + credits)
            continue

        if caracter == "TFG" or "trabajo fin de grado" in nombre or re.search(r"\btfg\b", nombre):
            item["curso"] = f"{total_duracion_anos}º"
            cumulative_ects += credits
            continue
        elif caracter == "TFM" or "trabajo fin de m" in nombre or re.search(r"\btfm\b", nombre):
            item["curso"] = f"{min(2, total_duracion_anos)}º"
            cumulative_ects += credits
            continue

        curso_calc = int(cumulative_ects // 60) + 1
        if total_duracion_anos > 0:
            curso_calc = min(curso_calc, total_duracion_anos)

        if (caracter == "FB" or "formación básica" in nombre or "formacion basica" in nombre) and curso_calc > 2:
            curso_calc = 2

        item["curso"] = f"{curso_calc}º"
        cumulative_ects += credits

    return elementos

