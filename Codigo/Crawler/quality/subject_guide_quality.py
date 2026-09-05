"""Evaluación determinista de cobertura de campos de una guía docente."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from config import SUBJECT_GUIDE_QUALITY_WEIGHTS


def _non_empty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _ects_present(guide: dict) -> bool:
    credits = guide.get("creditos") or {}
    if isinstance(credits, dict):
        return _non_empty(credits.get("total_ects")) or _non_empty(credits.get("ects"))
    return _non_empty(credits) or _non_empty(guide.get("creditos_ects"))


def _norm_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


def _name_matches(expected: str, actual: str) -> bool:
    expected_tokens = set(re.findall(r"[a-z0-9]{4,}", _norm_text(expected)))
    actual_tokens = set(re.findall(r"[a-z0-9]{4,}", _norm_text(actual)))
    if not expected_tokens or not actual_tokens:
        return False
    overlap = len(expected_tokens & actual_tokens) / max(1, len(expected_tokens))
    return overlap >= 0.60 or _norm_text(expected) in _norm_text(actual)


_EVAL_MINIMUM_THRESHOLD_RE = re.compile(
    r"\b(?:m[ií]nim[oa]s?|al\s+menos|nota\s+m[ií]nima|requisito\s+m[ií]nimo|m[ií]nim)\b",
    re.I,
)

_EVAL_PERCENT_RE = re.compile(
    r"(?P<val>\d{1,3}(?:[.,]\d{1,2})?)\s*(?:%|(?:por\s*ciento|percent)\b)",
    re.I,
)

_EVAL_POINTS_RE = re.compile(
    r"(?P<val>\d{1,2}(?:[.,]\d{1,2})?)\s*(?:puntos?|pts)?\s*(?:sobre|de|/)\s*10\b",
    re.I,
)

_CATEGORY_ORDER = (
    ("examen_final", (
        "examen final", "prueba final", "examen teorico", "prueba teorica",
        "examen escrito", "prova final", "prova teorica", "examen escrit",
        "final exam", "written exam", "teoria", "examen", "prueba objetiva",
        "evaluacion final", "avaluacio final",
    )),
    ("practicas_laboratorio", (
        "practicas de laboratorio", "practicas", "prácticas", "laboratorio",
        "pratiques", "pràctiques", "talleres", "laboratory", "practicum",
        "laboratori", "practica", "pràctica",
    )),
    ("trabajos_proyectos", (
        "trabajos", "trabajo", "proyectos", "proyecto", "entregas", "entrega",
        "actividades", "actividad", "casos", "caso", "treballs", "treball",
        "projectes", "projecte", "memorias", "memoria", "assignments", "projects",
    )),
    ("evaluacion_continua", (
        "evaluacion continua", "evaluación continua", "avaluacio continuada",
        "avaluació continuada", "continua", "seguimiento", "participacion",
        "participación", "asistencia", "continuous evaluation", "continuous assessment",
        "interactivas",
    )),
)


def parse_evaluation_breakdown(text: str) -> dict:
    """Extrae las ponderaciones porcentuales de la sección de evaluación de una guía docente."""
    result = {
        "examen_final": 0.0,
        "evaluacion_continua": 0.0,
        "practicas_laboratorio": 0.0,
        "trabajos_proyectos": 0.0,
        "otros": 0.0,
        "suma_porcentual": 0.0,
        "desglose_valido": False,
        "detalles": [],
    }
    raw = str(text or "").strip()
    if not raw:
        return result

    raw = re.sub(r"\([^)]*(?:m[ií]nim|al\s+menos|asistencia)[^)]*\)", "", raw, flags=re.I)

    segments = re.split(r"[\r\n;•\-]+|(?<=[.!?])\s+", raw)
    expanded_segments = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if "," in seg and seg.count("%") > 1:
            for sub in seg.split(","):
                if sub.strip():
                    expanded_segments.append(sub.strip())
        else:
            expanded_segments.append(seg)

    for segment in expanded_segments:
        if _EVAL_MINIMUM_THRESHOLD_RE.search(segment):
            continue

        pct = None
        m_pct = _EVAL_PERCENT_RE.search(segment)
        if m_pct:
            try:
                pct = float(m_pct.group("val").replace(",", "."))
            except ValueError:
                pct = None
        else:
            m_pts = _EVAL_POINTS_RE.search(segment)
            if m_pts:
                try:
                    pct = float(m_pts.group("val").replace(",", ".")) * 10.0
                except ValueError:
                    pct = None

        if pct is None or pct <= 0 or pct > 100:
            continue

        norm_seg = _norm_text(segment)
        matched_cat = "otros"
        for cat_name, kw_list in _CATEGORY_ORDER:
            if any(_norm_text(kw) in norm_seg for kw in kw_list):
                matched_cat = cat_name
                break

        result[matched_cat] = round(result[matched_cat] + pct, 2)
        result["detalles"].append({
            "concepto": segment.strip(),
            "porcentaje": pct,
            "categoria": matched_cat,
        })

    total_sum = round(sum(
        result[cat] for cat in ("examen_final", "evaluacion_continua", "practicas_laboratorio", "trabajos_proyectos", "otros")
    ), 2)
    result["suma_porcentual"] = total_sum
    if 98.0 <= total_sum <= 102.0:
        result["desglose_valido"] = True
    else:
        result["desglose_valido"] = False

    return result


def assess_subject_guide_quality(guide: dict, expected_name: str = "", expected_code: str = "", source_url: str = "") -> dict:
    """Calcula una cobertura explicable; no es una probabilidad estadística."""
    guide = guide if isinstance(guide, dict) else {}
    fields = {
        "nombre_asignatura": _non_empty(guide.get("nombre_asignatura")),
        "codigo_asignatura": _non_empty(guide.get("codigo_asignatura")),
        "creditos_ects": _ects_present(guide),
        "temario": _non_empty(guide.get("temario")),
        "sistema_evaluacion": _non_empty(guide.get("sistema_evaluacion")),
        "competencias": _non_empty(guide.get("competencias")),
        "resultados_aprendizaje": _non_empty(guide.get("resultados_aprendizaje")),
        "profesorado": _non_empty(guide.get("profesorado")),
        "departamento": _non_empty(guide.get("departamento")),
    }
    weights = dict(SUBJECT_GUIDE_QUALITY_WEIGHTS)
    score = round(sum(weights[name] for name, present in fields.items() if present) * 100 / sum(weights.values()), 2)
    missing = [name for name, present in fields.items() if not present]
    actual_name = str(guide.get("nombre_asignatura") or "")
    actual_code = str(guide.get("codigo_asignatura") or "").strip()
    name_match = not expected_name or _name_matches(expected_name, actual_name)
    code_match = not expected_code or (bool(actual_code) and actual_code == str(expected_code).strip())
    identity_ok = bool(name_match and code_match)
    identity_issues = []
    if expected_name and not actual_name:
        identity_issues.append("nombre_extraido_vacio")
    elif expected_name and not name_match:
        identity_issues.append("nombre_asignatura_no_coincide")
    if expected_code and not actual_code:
        identity_issues.append("codigo_extraido_vacio")
    elif expected_code and not code_match:
        identity_issues.append("codigo_asignatura_no_coincide")
    if score >= 80:
        level = "alta"
    elif score >= 50:
        level = "media"
    else:
        level = "baja"
    res = {
        "tipo": "cobertura_de_campos",
        "puntuacion": score,
        "nivel": level,
        "campos": {name: {"presente": present, "peso": weights[name]} for name, present in fields.items()},
        "campos_faltantes": missing,
        "identidad_esperada": {"nombre": str(expected_name or ""), "codigo": str(expected_code or "")},
        "identidad": {
            "nombre_coincide": name_match,
            "codigo_coincide": code_match,
            "verificada": identity_ok,
            "incidencias": identity_issues,
        },
        # Una guía con identidad doblemente verificada y los tres campos
        # nucleares (nombre, código y temario) alcanza 54/100 con los pesos
        # por defecto. Mantener el umbral en 50 evita perder evidencia válida
        # por un redondeo de pesos, sin relajar la comprobación de identidad.
        "publicable": bool(identity_ok and score >= 50),
        "fuente_url": str(source_url or guide.get("url_guia_docente") or ""),
        "evaluado_en": datetime.now(timezone.utc).isoformat(),
    }
    sistema_eval = str(guide.get("sistema_evaluacion") or "").strip()
    if sistema_eval:
        res["evaluacion_desglose"] = parse_evaluation_breakdown(sistema_eval)
    return res


def annotate_subject_guide_quality(guide: dict, expected_name: str = "", expected_code: str = "", source_url: str = "") -> dict:
    """Añade la evaluación sin sobrescribir ningún dato extraído."""
    if not isinstance(guide, dict):
        return guide
    guide["calidad_extraccion"] = assess_subject_guide_quality(
        guide, expected_name=expected_name, expected_code=expected_code, source_url=source_url
    )
    return guide
