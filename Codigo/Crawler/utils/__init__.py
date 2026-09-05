"""Subpaquete de utilidades generales para la plataforma de rastreo UniHub."""

from __future__ import annotations

from utils.credit_utils import (
    compute_curriculum_total_ects,
    parse_credit_number,
)
from utils.sqlite_recovery import (
    inspect_sqlite_database,
    is_sqlite_corruption,
    quarantine_and_recreate_sqlite,
    quarantine_corrupt_sqlite,
)
from utils.text_utils import (
    clean_ascii_slug,
    clean_spaces,
    detect_academic_language,
    normalize_ascii_text,
    normalize_joint_title,
    normalize_unicode_text,
    repair_mojibake_utf8,
    strip_combining_accents,
    unreverse_boustrophedon_text,
)

__all__ = [
    "clean_ascii_slug",
    "clean_spaces",
    "compute_curriculum_total_ects",
    "detect_academic_language",
    "inspect_sqlite_database",
    "is_sqlite_corruption",
    "normalize_ascii_text",
    "normalize_joint_title",
    "normalize_unicode_text",
    "parse_credit_number",
    "quarantine_and_recreate_sqlite",
    "quarantine_corrupt_sqlite",
    "repair_mojibake_utf8",
    "strip_combining_accents",
    "unreverse_boustrophedon_text",
]
