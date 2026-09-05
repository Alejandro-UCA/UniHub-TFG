"""Evaluación empírica reproducible del parser contra el BOE oficial.

Cada caso contrasta dos representaciones independientes de la misma resolución:
el PDF que consume el crawler y la tabla HTML estructurada publicada por el BOE.
Los índices de tabla se han revisado para apuntar al plan principal y excluir
tablas de temporalidad o itinerarios alternativos.

Este módulo no se ejecuta durante la suite normal porque descarga cinco PDFs.
Ejecutar explícitamente ``python Codigo/Pruebas/boe_empirical_evaluation.py``
respeta robots.txt y el límite de peticiones centralizado en ``RUCTDownloader``.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

from parsers.boe_pdf import parse_boe_pdf
from quality.curriculum_validator import get_curriculum_completeness_status
from core.downloader import RUCTDownloader
from utils.sanitizers import curriculum_element_key, is_spurious_or_administrative_subject, sanitize_subject_name


EMPIRICAL_BOE_CASES = (
    {
        "id": "BOE-A-2022-12382",
        "pdf_url": "https://www.boe.es/boe/dias/2022/07/25/pdfs/BOE-A-2022-12382.pdf",
        "title": "Máster Universitario en Economía",
        "university": "Universidad de La Rioja",
        "level": "Máster Universitario",
        "reference_table_index": 1,
        "expected_ects": 90.0,
    },
    {
        "id": "BOE-A-2024-1769",
        "pdf_url": "https://www.boe.es/boe/dias/2024/01/30/pdfs/BOE-A-2024-1769.pdf",
        "title": "Máster Universitario en Dirección de Proyectos",
        "university": "Universidad de La Rioja",
        "level": "Máster Universitario",
        "reference_table_index": 1,
        "expected_ects": 60.0,
    },
    {
        "id": "BOE-A-2023-6963",
        "pdf_url": "https://www.boe.es/boe/dias/2023/03/16/pdfs/BOE-A-2023-6963.pdf",
        "title": "Grado en Relaciones Internacionales",
        "university": "Universidad de Valladolid",
        "level": "Grado",
        "reference_table_index": 1,
        "expected_ects": 240.0,
    },
    {
        "id": "BOE-A-2023-11558",
        "pdf_url": "https://www.boe.es/boe/dias/2023/05/15/pdfs/BOE-A-2023-11558.pdf",
        "title": "Graduado o Graduada en Ingeniería Multimedia",
        "university": "Universidad de Alicante",
        "level": "Grado",
        "reference_table_index": 1,
        "expected_ects": 240.0,
    },
    {
        "id": "BOE-A-2025-21807",
        "pdf_url": "https://www.boe.es/boe/dias/2025/10/29/pdfs/BOE-A-2025-21807.pdf",
        "title": "Graduado o Graduada en Ingeniería Biomédica",
        "university": "",
        "level": "Grado",
        "reference_table_index": 1,
        "expected_ects": 240.0,
    },
)

_CREDIT_VALUE = re.compile(r"^\d+(?:[.,]\d+)?$")
_CHARACTER_VALUE = re.compile(r"^(?:FB|FBA|B|BA|OB|OBL|OP|OPT|PE|PEX|PAE|TFG|TFM|TFG/TFM|BÁSICA|OBLIGATORIA|OPTATIVA)$", re.IGNORECASE)


def official_text_url(case: dict) -> str:
    return f"https://www.boe.es/diario_boe/txt.php?id={case['id']}"


def _extract_reference_name(cells: Iterable[str]) -> str:
    """Obtiene la última celda semántica antes de la columna de créditos.

    La vista HTML del BOE omite celdas vacías por ``rowspan``. Por ello la
    posición física de «Asignatura» cambia entre filas; la celda inmediatamente
    anterior a los créditos, descartando el carácter, permanece estable.
    """
    normalized_cells = [sanitize_subject_name(cell) for cell in cells]
    credit_index = next(
        (index for index, value in enumerate(normalized_cells) if _CREDIT_VALUE.fullmatch(value)),
        None,
    )
    if credit_index is None:
        return ""
    for value in reversed(normalized_cells[:credit_index]):
        if not value or _CHARACTER_VALUE.fullmatch(value):
            continue
        return value
    return ""


def extract_reference_subjects(official_html: str, table_index: int) -> dict[str, str]:
    """Extrae las asignaturas de la tabla principal del texto oficial BOE."""
    tables = BeautifulSoup(official_html or "", "html.parser").find_all("table")
    if table_index < 0 or table_index >= len(tables):
        raise ValueError(f"No existe la tabla BOE de referencia con índice {table_index}.")

    subjects: dict[str, str] = {}
    rows = tables[table_index].find_all("tr")
    for row in rows[1:]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        name = _extract_reference_name(cells)
        if not name or is_spurious_or_administrative_subject(name):
            continue
        key = curriculum_element_key(name)
        if key:
            subjects.setdefault(key, name)
    return subjects


def evaluate_case(case: dict, pdf_content: bytes, official_html: str) -> dict:
    """Mide precisión, cobertura y ECTS frente a la fuente oficial."""
    parsed = parse_boe_pdf(pdf_content, case["title"], case.get("university", ""))
    reference_subjects = extract_reference_subjects(official_html, case["reference_table_index"])
    extracted_subjects = {
        curriculum_element_key(item.get("nombre_elemento", "")): item.get("nombre_elemento", "")
        for item in parsed.get("elementos_curriculares", [])
        if isinstance(item, dict) and curriculum_element_key(item.get("nombre_elemento", ""))
    }
    reference_keys = set(reference_subjects)
    extracted_keys = set(extracted_subjects)
    true_positives = reference_keys & extracted_keys
    false_positives = extracted_keys - reference_keys
    false_negatives = reference_keys - extracted_keys
    precision = len(true_positives) / len(extracted_keys) if extracted_keys else 0.0
    recall = len(true_positives) / len(reference_keys) if reference_keys else 0.0
    completeness = get_curriculum_completeness_status({
        "titulo": case["title"],
        "nivel_academico": case["level"],
        "plan_estudios": parsed,
    })
    declared_ects = completeness["total_ects_obtained"]
    ects_match = declared_ects == float(case["expected_ects"])
    return {
        "id": case["id"],
        "reference_subjects": len(reference_keys),
        "extracted_subjects": len(extracted_keys),
        "true_positives": len(true_positives),
        "false_positives": sorted(extracted_subjects[key] for key in false_positives),
        "false_negatives": sorted(reference_subjects[key] for key in false_negatives),
        "precision": precision,
        "recall": recall,
        "declared_ects": declared_ects,
        "expected_ects": float(case["expected_ects"]),
        "ects_match": ects_match,
        "passed": precision == 1.0 and recall == 1.0 and ects_match,
    }


def run_empirical_evaluation(cases=EMPIRICAL_BOE_CASES) -> dict:
    """Ejecuta los casos de control de forma secuencial y respetuosa."""
    results = []
    with RUCTDownloader(delay=1.0, max_retries=2, timeout=20, phase="empirical_boe_evaluation") as downloader:
        for case in cases:
            pdf_content = downloader.fetch_content(case["pdf_url"], max_size_bytes=8 * 1024 * 1024)
            official_html = downloader.fetch_text(official_text_url(case), max_size_bytes=4 * 1024 * 1024)
            results.append(evaluate_case(case, pdf_content, official_html))

    total_true_positives = sum(item["true_positives"] for item in results)
    total_extracted = sum(item["extracted_subjects"] for item in results)
    total_reference = sum(item["reference_subjects"] for item in results)
    return {
        "cases": results,
        "precision": total_true_positives / total_extracted if total_extracted else 0.0,
        "recall": total_true_positives / total_reference if total_reference else 0.0,
        "all_ects_match": all(item["ects_match"] for item in results),
        "passed": bool(results) and all(item["passed"] for item in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa el parser PDF contra las tablas oficiales del BOE.")
    parser.parse_args()
    report = run_empirical_evaluation()
    for result in report["cases"]:
        print(
            f"{result['id']}: referencia={result['reference_subjects']} extraídas={result['extracted_subjects']} "
            f"precisión={result['precision']:.1%} cobertura={result['recall']:.1%} "
            f"ECTS={result['declared_ects']:.0f}/{result['expected_ects']:.0f} "
            f"{'OK' if result['passed'] else 'FALLO'}"
        )
        if result["false_positives"]:
            print(f"  Espurias: {result['false_positives']}")
        if result["false_negatives"]:
            print(f"  Omitidas: {result['false_negatives']}")
    print(f"Global: precisión={report['precision']:.1%}; cobertura={report['recall']:.1%}; ECTS exactos={report['all_ects_match']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
