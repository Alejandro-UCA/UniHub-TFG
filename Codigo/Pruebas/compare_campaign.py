"""Compara dos auditorías de campaña sin modificar ninguno de los corpus."""

from __future__ import annotations

import argparse
import json
import os


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _diff_maps(original: dict, pilot: dict) -> dict:
    keys = sorted(set(original) | set(pilot))
    return {key: pilot.get(key, 0) - original.get(key, 0) for key in keys if pilot.get(key, 0) != original.get(key, 0)}


def compare(original_report: dict, pilot_report: dict) -> dict:
    original_counts = original_report.get("counts", {})
    pilot_counts = pilot_report.get("counts", {})
    original_quality = original_report.get("quality", {})
    pilot_quality = pilot_report.get("quality", {})
    original_guides = original_report.get("guides", {})
    pilot_guides = pilot_report.get("guides", {})
    return {
        "generated_at": pilot_report.get("generated_at"),
        "original_root": original_report.get("root"),
        "pilot_root": pilot_report.get("root"),
        "catalog_entries_delta": pilot_report.get("catalog_entries", 0) - original_report.get("catalog_entries", 0),
        "counts_delta": _diff_maps(original_counts, pilot_counts),
        "quality_delta": _diff_maps(original_quality, pilot_quality),
        "guides_delta": _diff_maps(original_guides, pilot_guides),
        "pilot_mismatch_samples": pilot_report.get("mismatch_samples", []),
        "pilot_candidate_samples": pilot_report.get("candidate_samples", []),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("original_report")
    parser.add_argument("pilot_report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = compare(_load(args.original_report), _load(args.pilot_report))
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
