#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fachada de Compatibilidad hacia Atrás para el Punto de Entrada del Crawler.
Delega en el nuevo orquestador global 'main_fase_1.py' y los controladores de parte especializados.
"""

from main_fase_1 import (
    main,
    run_all_phase1,
    run_crawler,
    run_phase1,
)
from fase1_parte1_ruct_boe import (
    pdf_parser_consumer,
    run_phase1_part1
)

if __name__ == "__main__":
    main()
