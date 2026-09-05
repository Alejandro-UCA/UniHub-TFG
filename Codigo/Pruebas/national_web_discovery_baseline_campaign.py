"""Campaña nacional acotada para medir cobertura real de descubrimiento web."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_campaign import audit_root
from pipelines.parte2_web_crawler import run_phase1_part2


def _counts(report: dict) -> dict:
    counts = report.get("counts") or {}
    return {
        key: int(counts.get(key) or 0)
        for key in (
            "files",
            "plan_null",
            "publicable",
            "recomputed_publicable",
            "candidate_plan",
            "web_missing",
            "quality_inconsistency",
        )
    }


def run(
    root: str,
    output: str,
    workers: int = 4,
    limit_universities: int | None = None,
    target_universities: list[str] | None = None,
) -> dict:
    root_path = Path(root).resolve()
    before = _counts(audit_root(str(root_path)))
    crawler_result = run_phase1_part2(
        limit_universities=limit_universities,
        limit_degrees=1,
        max_workers=max(1, int(workers)),
        force=False,
        target_universities=target_universities,
    )
    after = _counts(audit_root(str(root_path)))
    report = {
        "campaign": "national_web_discovery_baseline",
        "scope": "one_pending_degree_per_institution",
        "institution_limit": limit_universities,
        "target_scope": "explicit_generic_selection" if target_universities else "catalog_order",
        "before": before,
        "after": after,
        "crawler": crawler_result,
        "recovered": after["publicable"] - before["publicable"],
        "plan_null_reduction": before["plan_null"] - after["plan_null"],
        "new_web_evidence": before["web_missing"] - after["web_missing"],
        "quality_inconsistency_delta": after["quality_inconsistency"] - before["quality_inconsistency"],
        "no_verified_regression": after["publicable"] >= before["publicable"],
        "no_quality_inconsistency": after["quality_inconsistency"] == 0,
    }
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-universities", type=int)
    parser.add_argument(
        "--target-universities",
        help="Lista opcional de identificadores del catálogo, separada por comas, para una cohorte reproducible.",
    )
    args = parser.parse_args(argv)
    targets = [value.strip() for value in (args.target_universities or "").split(",") if value.strip()]
    run(args.root, args.output, args.workers, args.limit_universities, targets or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
