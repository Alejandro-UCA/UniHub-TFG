"""Evaluación reproducible campo a campo de parsers de guías docentes.

El corpus es local y versionable: no realiza peticiones de red y permite
comparar cambios del parser con casos de formatos heterogéneos y universidades nuevas.
Cada caso declara los campos que debe recuperar; los campos no declarados no
se interpretan como un fallo de cobertura.
"""

from __future__ import annotations

import argparse
import json
import os
from numbers import Number

from fase1_parte4_asignaturas import parse_subject_guide


def _get_path(payload: dict, path: str):
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _normalise(value) -> str:
    return " ".join(str(value or "").casefold().split())


def _matches(actual, expected) -> bool:
    if isinstance(expected, str):
        return _normalise(expected) in _normalise(actual)
    if isinstance(expected, Number) and isinstance(actual, Number):
        return abs(float(actual) - float(expected)) < 0.01
    if isinstance(expected, list) and isinstance(actual, list):
        actual_text = {_normalise(json.dumps(item, ensure_ascii=False, sort_keys=True)) for item in actual}
        return all(_normalise(json.dumps(item, ensure_ascii=False, sort_keys=True)) in actual_text for item in expected)
    return actual == expected


def _evaluate_expectations(parsed: dict, expectations: dict) -> tuple[dict, int, int]:
    fields = {}
    matched = 0
    total = 0
    for key, expected in (expectations or {}).items():
        if key.endswith("_min"):
            path = key[:-4]
            actual = _get_path(parsed, path)
            actual_count = len(actual) if isinstance(actual, (list, tuple, dict, str)) else 0
            ok = actual_count >= int(expected)
            fields[key] = {"ok": ok, "expected": expected, "actual": actual_count}
        else:
            actual = _get_path(parsed, key)
            ok = _matches(actual, expected)
            fields[key] = {"ok": ok, "expected": expected, "actual": actual}
        total += 1
        matched += int(ok)
    return fields, matched, total


def evaluate_case(case: dict, corpus_dir: str) -> dict:
    if not isinstance(case, dict):
        return {"name": "<invalid>", "status": "failed", "error": "case must be an object"}
    name = str(case.get("name") or case.get("content") or "<unnamed>")
    relative_path = str(case.get("content") or "").strip()
    if not relative_path:
        return {"name": name, "status": "failed", "error": "missing content"}
    root = os.path.abspath(corpus_dir)
    content_path = os.path.abspath(os.path.join(root, relative_path))
    try:
        if os.path.commonpath((root, content_path)) != root:
            raise ValueError("content path escapes corpus directory")
        with open(content_path, "rb") as handle:
            content = handle.read()
        parsed = parse_subject_guide(
            str(case.get("url") or content_path),
            content,
            str(case.get("content_type") or ""),
        )
        fields, matched, total = _evaluate_expectations(parsed, case.get("expect"))
        return {
            "name": name,
            "status": "passed" if matched == total else "failed",
            "score": round(matched / total, 4) if total else 1.0,
            "fields": fields,
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return {"name": name, "status": "failed", "error": str(error)}


def evaluate_corpus(corpus_path: str) -> dict:
    """Evalúa un corpus JSON y devuelve un informe serializable."""
    corpus_path = os.path.abspath(corpus_path)
    with open(corpus_path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    cases = document.get("cases", []) if isinstance(document, dict) else document
    if not isinstance(cases, list):
        raise ValueError("corpus must be a list or an object with 'cases'")
    results = [evaluate_case(case, os.path.dirname(corpus_path)) for case in cases]
    passed = sum(result.get("status") == "passed" for result in results)
    scores = [result["score"] for result in results if isinstance(result.get("score"), Number)]
    return {
        "corpus": corpus_path,
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "average_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa un corpus local de guías docentes.")
    parser.add_argument("corpus", help="Ruta al fichero JSON del corpus")
    parser.add_argument("--output", help="Ruta opcional del informe JSON")
    args = parser.parse_args()
    report = evaluate_corpus(args.corpus)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
