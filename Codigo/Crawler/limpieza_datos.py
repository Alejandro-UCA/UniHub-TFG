#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script de administración CLI para la limpieza de datos volátiles de la Fase 1.

Permite purgar de forma idempotente las cachés y artefactos volátiles
garantizando la preservación incondicional de las 3 semillas maestras:
- universidades.json
- titulaciones_universidad.json
- precios_ccaa.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permitir ejecución directa
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.console_encoding import configure_console_encoding
from utils.data_cleanup import (
    get_crawler_data_inventory,
    clean_crawler_runtime_data,
    backup_seed_files,
)

configure_console_encoding()


def _format_bytes(bytes_count: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:3.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="UniHub - Herramienta de Limpieza Segura de Datos de Fase 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Inspeccionar inventario sin tocar nada:
  python limpieza_datos.py --inventory

  # Simulación de limpieza (dry-run):
  python limpieza_datos.py --dry-run

  # Ejecutar limpieza real con respaldo automático de semillas:
  python limpieza_datos.py --force

  # Respaldar únicamente las semillas maestras:
  python limpieza_datos.py --backup-only
        """,
    )
    parser.add_argument(
        "--inventory", "--status",
        action="store_true",
        help="Mostrar el inventario de semillas y artefactos volátiles sin realizar acciones.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular la limpieza listando los ficheros y directorios que se eliminarían.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ejecutar la purga real de artefactos volátiles.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Omitir la copia de seguridad preventiva de las semillas maestras.",
    )
    parser.add_argument(
        "--backup-only",
        action="store_true",
        help="Realizar únicamente una copia de seguridad de las semillas maestras.",
    )

    args = parser.parse_args(argv)

    print("\n" + "=" * 76)
    print("      UNIHUB · GESTIÓN Y LIMPIEZA DE DATOS DE LA FASE 1")
    print("=" * 76)

    if args.backup_only:
        print("\n [RESPALDO] Creando copia de seguridad de semillas maestras...")
        backups = backup_seed_files()
        for b in backups:
            print(f"  ✓ {b['seed']}: {b['size_bytes']} bytes -> {b['dst']}")
        print(f"\n -> {len(backups)} semillas respaldadas con éxito.\n")
        return 0

    if args.inventory or (not args.force and not args.dry_run):
        inv = get_crawler_data_inventory()
        print("\n [1] SEMILLAS MAESTRAS (INMUTABLES - NUNCA SE BORRAN):")
        for name, info in inv["seeds"].items():
            print(f"  • {name:32} : {_format_bytes(info['size_bytes']):>10} (SHA: {info['sha256'][:12]}...)")
        print(f"  Total Semillas: {_format_bytes(inv['total_seed_bytes'])}")

        print("\n [2] ARTEFACTOS VOLÁTILES PURGABLES:")
        print(f"  • Directorios de trabajo : {len(inv['disposable_dirs'])} carpetas")
        for d in inv["disposable_dirs"]:
            print(f"    - {d['name']:30} : {_format_bytes(d['size_bytes']):>10}")
        print(f"  • Ficheros y bases SQLite : {len(inv['disposable_files'])} archivos")
        for f in inv["disposable_files"]:
            print(f"    - {f['name']:30} : {_format_bytes(f['size_bytes']):>10}")
        print(f"  • Temporales de PDFs      : {inv['temp_pdfs']['count']} archivos ({_format_bytes(inv['temp_pdfs']['size_bytes'])})")
        print(f"  Total Volátil Liberable   : {_format_bytes(inv['total_disposable_bytes'])}")

        if not args.dry_run and not args.force:
            print("\n [AVISO] Ejecute con '--dry-run' para simular o con '--force' para proceder a la limpieza.\n")
            return 0

    is_dry_run = args.dry_run and not args.force
    mode_label = "SIMULACIÓN (DRY-RUN)" if is_dry_run else "EJECUCIÓN REAL"
    print(f"\n >>> Iniciando limpieza segura de datos en modo: {mode_label}...")

    report = clean_crawler_runtime_data(
        dry_run=is_dry_run,
        backup_seed=not args.no_backup,
    )

    print("\n [ESTADO DE SEMILLAS]")
    for s in report["seed_files_preserved"]:
        status_sym = "✓ INTACTO" if s["status"] == "intact" else "⚠ NO ENCONTRADO"
        print(f"  {status_sym} - {s['name']} ({_format_bytes(s['size_bytes'])})")

    if report["backups_created"]:
        print("\n [RESPALDOS PREVENTIVOS]")
        for b in report["backups_created"]:
            print(f"  ✓ Copia creada: {b['seed']} -> {b['dst']}")

    print("\n [RESUMEN DE LA OPERACIÓN]")
    print(f"  • Ficheros eliminados      : {report['files_deleted_count']}")
    print(f"  • Directorios purgados     : {report['dirs_deleted_count']}")
    print(f"  • Espacio total liberado   : {_format_bytes(report['bytes_freed'])}")
    if report["cleared_orphan_lock"]:
        print("  • Cerrojo ETL huérfano     : Limpiado")
    if report["recreated_directories"]:
        print(f"  • Directorios recreados    : {len(report['recreated_directories'])} listos para arranque en frío")

    print("\n -> Limpieza finalizada correctamente.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
