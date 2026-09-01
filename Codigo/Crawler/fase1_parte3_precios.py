import os
import json
import glob
import re
import logging
from config import (
    DATA_DIR,
    PLANES_DIR,
    UNIVERSIDADES_JSON,
    PRECIOS_CCAA_JSON,
    DOCTORATE_TUTELA_CREDITS,
    STANDARD_YEAR_ECTS_CREDITS,
    TARGET_UNIVERSITY_CODES,
)
from checkpoint import atomic_json_dump, load_json_safe
from phase_common import iter_plan_files
from cancellation import raise_if_shutdown_requested

PRICE_CATALOG_ACADEMIC_YEAR = os.getenv("CRAWLER_PRICE_CATALOG_ACADEMIC_YEAR", "2025-2026")
PRICE_CATALOG_VERIFIED = os.getenv("CRAWLER_PRICE_CATALOG_VERIFIED", "true").strip().lower() in {"1", "true", "yes", "si", "sí"}
logger = logging.getLogger(__name__)


def is_verified_academic_year(value: str) -> bool:
    """Solo permite publicar tarifas cuando se identifica el curso académico."""
    return bool(re.fullmatch(r"20\d{2}-20\d{2}", str(value or "").strip()))


def is_price_catalog_publishable(academic_year: str, verified: bool) -> bool:
    """Evita publicar estimaciones si no existe una revisión explícita del catálogo."""
    return is_verified_academic_year(academic_year) and bool(verified)

# ==============================================================================
# Catálogo local de tarifas SIIU/decretos autonómicos configurado por el proyecto.
# La vigencia debe verificarse para cada curso académico antes de publicar importes.
# ==============================================================================
OFFICIAL_SIIU_PRICES_CATALOG = {
    "Andalucía": {
        "Grado": {"1": 12.62, "2": 25.24, "3": 54.40, "4": 75.60, "defecto": 12.62},
        "Máster Habilitante": {"1": 13.68, "2": 27.36, "3": 59.00, "4": 82.00, "defecto": 13.68},
        "Máster No Habilitante": {"1": 13.68, "2": 27.36, "3": 59.00, "4": 82.00, "defecto": 13.68},
        "Doctorado": {"1": 60.30, "defecto": 60.30},
        "tasas_admin": 59.10,
        "decreto_oficial": "Decreto de Precios Públicos de las Universidades Públicas de Andalucía"
    },
    "Aragón": {
        "Grado": {"1": 18.90, "2": 32.13, "3": 69.30, "4": 96.25, "defecto": 18.90},
        "Máster Habilitante": {"1": 22.40, "2": 38.08, "3": 82.15, "4": 114.10, "defecto": 22.40},
        "Máster No Habilitante": {"1": 34.50, "2": 58.65, "3": 126.50, "4": 175.70, "defecto": 34.50},
        "Doctorado": {"1": 185.00, "defecto": 185.00},
        "tasas_admin": 44.00,
        "decreto_oficial": "Decreto de Tarifas Universitarias de la Comunidad Autónoma de Aragón"
    },
    "Principado de Asturias": {
        "Grado": {"1": 16.15, "2": 27.45, "3": 59.20, "4": 82.20, "defecto": 16.15},
        "Máster Habilitante": {"1": 21.50, "2": 36.55, "3": 78.85, "4": 109.50, "defecto": 21.50},
        "Máster No Habilitante": {"1": 29.00, "2": 49.30, "3": 106.35, "4": 147.70, "defecto": 29.00},
        "Doctorado": {"1": 150.00, "defecto": 150.00},
        "tasas_admin": 42.00,
        "decreto_oficial": "Decreto de Precios Públicos del Principado de Asturias"
    },
    "Illes Balears": {
        "Grado": {"1": 16.40, "2": 27.88, "3": 60.15, "4": 83.50, "defecto": 16.40},
        "Máster Habilitante": {"1": 21.80, "2": 37.06, "3": 79.95, "4": 111.05, "defecto": 21.80},
        "Máster No Habilitante": {"1": 32.00, "2": 54.40, "3": 117.35, "4": 163.00, "defecto": 32.00},
        "Doctorado": {"1": 160.00, "defecto": 160.00},
        "tasas_admin": 45.00,
        "decreto_oficial": "Decret de Preus Públics de les Illes Balears"
    },
    "Canarias": {
        "Grado": {"1": 12.50, "2": 21.25, "3": 45.80, "4": 63.65, "defecto": 12.50},
        "Máster Habilitante": {"1": 14.20, "2": 24.14, "3": 52.05, "4": 72.30, "defecto": 14.20},
        "Máster No Habilitante": {"1": 18.50, "2": 31.45, "3": 67.85, "4": 94.20, "defecto": 18.50},
        "Doctorado": {"1": 120.00, "defecto": 120.00},
        "tasas_admin": 40.00,
        "decreto_oficial": "Decreto de Precios Públicos de la Comunidad Autónoma de Canarias"
    },
    "Cantabria": {
        "Grado": {"1": 14.80, "2": 25.16, "3": 54.28, "4": 75.38, "defecto": 14.80},
        "Máster Habilitante": {"1": 19.80, "2": 33.66, "3": 72.60, "4": 100.85, "defecto": 19.80},
        "Máster No Habilitante": {"1": 28.00, "2": 47.60, "3": 102.70, "4": 142.60, "defecto": 28.00},
        "Doctorado": {"1": 145.00, "defecto": 145.00},
        "tasas_admin": 43.00,
        "decreto_oficial": "Decreto de Precios Públicos del Gobierno de Cantabria"
    },
    "Castilla y León": {
        "Grado": {"1": 17.80, "2": 30.26, "3": 65.28, "4": 90.65, "defecto": 17.80},
        "Máster Habilitante": {"1": 23.50, "2": 39.95, "3": 86.20, "4": 119.70, "defecto": 23.50},
        "Máster No Habilitante": {"1": 35.00, "2": 59.50, "3": 128.35, "4": 178.25, "defecto": 35.00},
        "Doctorado": {"1": 200.00, "defecto": 200.00},
        "tasas_admin": 50.00,
        "decreto_oficial": "Decreto de Precios Públicos de la Junta de Castilla y León"
    },
    "Castilla-La Mancha": {
        "Grado": {"1": 15.50, "2": 26.35, "3": 56.85, "4": 78.95, "defecto": 15.50},
        "Máster Habilitante": {"1": 18.20, "2": 30.94, "3": 66.75, "4": 92.70, "defecto": 18.20},
        "Máster No Habilitante": {"1": 26.00, "2": 44.20, "3": 95.35, "4": 132.45, "defecto": 26.00},
        "Doctorado": {"1": 140.00, "defecto": 140.00},
        "tasas_admin": 45.00,
        "decreto_oficial": "Decreto de Precios Públicos de Castilla-La Mancha"
    },
    "Cataluña": {
        "Grado": {"1": 18.46, "2": 31.38, "3": 67.70, "4": 94.00, "defecto": 18.46},
        "Grado - Salud": {"1": 18.46, "2": 31.38, "3": 67.70, "4": 94.00, "defecto": 18.46},
        "Grado - Ciencias e Ingeniería": {"1": 18.46, "2": 31.38, "3": 67.70, "4": 94.00, "defecto": 18.46},
        "Grado - Ciencias Sociales y Humanidades": {"1": 17.69, "2": 30.07, "3": 64.86, "4": 90.08, "defecto": 17.69},
        "Máster Habilitante": {"1": 27.67, "2": 47.04, "3": 101.48, "4": 140.90, "defecto": 27.67},
        "Máster No Habilitante": {"1": 41.17, "2": 69.99, "3": 150.98, "4": 209.65, "defecto": 41.17},
        "Doctorado": {"1": 401.12, "defecto": 401.12},
        "tasas_admin": 69.80,
        "decreto_oficial": "Decret de Preus Públics de la Generalitat de Catalunya"
    },
    "Comunitat Valenciana": {
        "Grado": {"1": 15.10, "2": 25.67, "3": 55.37, "4": 76.90, "defecto": 15.10},
        "Grado - Salud": {"1": 17.34, "2": 29.48, "3": 63.58, "4": 88.30, "defecto": 17.34},
        "Grado - Ciencias e Ingeniería": {"1": 15.10, "2": 25.67, "3": 55.37, "4": 76.90, "defecto": 15.10},
        "Grado - Ciencias Sociales y Humanidades": {"1": 12.79, "2": 21.74, "3": 46.90, "4": 65.10, "defecto": 12.79},
        "Máster Habilitante": {"1": 20.20, "2": 34.34, "3": 74.07, "4": 102.88, "defecto": 20.20},
        "Máster No Habilitante": {"1": 35.34, "2": 60.08, "3": 129.60, "4": 180.00, "defecto": 35.34},
        "Doctorado": {"1": 180.00, "defecto": 180.00},
        "tasas_admin": 46.00,
        "decreto_oficial": "Decret de Taxes Universitàries de la Generalitat Valenciana"
    },
    "Extremadura": {
        "Grado": {"1": 14.10, "2": 23.97, "3": 51.71, "4": 71.82, "defecto": 14.10},
        "Máster Habilitante": {"1": 16.50, "2": 28.05, "3": 60.50, "4": 84.05, "defecto": 16.50},
        "Máster No Habilitante": {"1": 24.00, "2": 40.80, "3": 88.00, "4": 122.25, "defecto": 24.00},
        "Doctorado": {"1": 130.00, "defecto": 130.00},
        "tasas_admin": 41.00,
        "decreto_oficial": "Decreto de Precios Públicos de la Junta de Extremadura"
    },
    "Galicia": {
        "Grado": {"1": 11.89, "2": 20.21, "3": 43.60, "4": 60.56, "defecto": 11.89},
        "Grado - Salud": {"1": 13.93, "2": 23.68, "3": 51.08, "4": 70.94, "defecto": 13.93},
        "Grado - Ciencias e Ingeniería": {"1": 13.93, "2": 23.68, "3": 51.08, "4": 70.94, "defecto": 13.93},
        "Grado - Ciencias Sociales y Humanidades": {"1": 11.89, "2": 20.21, "3": 43.60, "4": 60.56, "defecto": 11.89},
        "Máster Habilitante": {"1": 13.50, "2": 22.95, "3": 49.50, "4": 68.75, "defecto": 13.50},
        "Máster No Habilitante": {"1": 18.20, "2": 30.94, "3": 66.75, "4": 92.70, "defecto": 18.20},
        "Doctorado": {"1": 110.00, "defecto": 110.00},
        "tasas_admin": 38.00,
        "decreto_oficial": "Decreto de Prezos Públicos da Xunta de Galicia"
    },
    "Comunidad de Madrid": {
        "Grado": {"1": 21.39, "2": 36.36, "3": 78.44, "4": 108.94, "defecto": 21.39},
        "Grado - Salud": {"1": 21.39, "2": 36.36, "3": 78.44, "4": 108.94, "defecto": 21.39},
        "Grado - Ciencias e Ingeniería": {"1": 21.39, "2": 36.36, "3": 78.44, "4": 108.94, "defecto": 21.39},
        "Grado - Ciencias Sociales y Humanidades": {"1": 21.39, "2": 36.36, "3": 78.44, "4": 108.94, "defecto": 21.39},
        "Máster Habilitante": {"1": 26.84, "2": 45.63, "3": 98.42, "4": 136.70, "defecto": 26.84},
        "Máster No Habilitante": {"1": 45.02, "2": 76.53, "3": 165.10, "4": 229.30, "defecto": 45.02},
        "Doctorado": {"1": 390.00, "defecto": 390.00},
        "tasas_admin": 65.00,
        "decreto_oficial": "Decreto del Consejo de Gobierno de la Comunidad de Madrid"
    },
    "Región de Murcia": {
        "Grado": {"1": 15.20, "2": 25.84, "3": 55.74, "4": 77.42, "defecto": 15.20},
        "Máster Habilitante": {"1": 19.50, "2": 33.15, "3": 71.50, "4": 99.32, "defecto": 19.50},
        "Máster No Habilitante": {"1": 29.00, "2": 49.30, "3": 106.35, "4": 147.70, "defecto": 29.00},
        "Doctorado": {"1": 160.00, "defecto": 160.00},
        "tasas_admin": 45.00,
        "decreto_oficial": "Decreto de Precios Públicos de la Región de Murcia"
    },
    "Comunidad Foral de Navarra": {
        "Grado": {"1": 17.50, "2": 29.75, "3": 64.17, "4": 89.13, "defecto": 17.50},
        "Máster Habilitante": {"1": 24.00, "2": 40.80, "3": 88.00, "4": 122.25, "defecto": 24.00},
        "Máster No Habilitante": {"1": 33.00, "2": 56.10, "3": 121.00, "4": 168.10, "defecto": 33.00},
        "Doctorado": {"1": 220.00, "defecto": 220.00},
        "tasas_admin": 48.00,
        "decreto_oficial": "Decreto Foral de Tarifas Universitarias de Navarra"
    },
    "País Vasco": {
        "Grado": {"1": 16.80, "2": 28.56, "3": 61.60, "4": 85.56, "defecto": 16.80},
        "Máster Habilitante": {"1": 22.00, "2": 37.40, "3": 80.67, "4": 112.05, "defecto": 22.00},
        "Máster No Habilitante": {"1": 31.00, "2": 52.70, "3": 113.67, "4": 157.90, "defecto": 31.00},
        "Doctorado": {"1": 210.00, "defecto": 210.00},
        "tasas_admin": 47.00,
        "decreto_oficial": "Decreto de Precios Públicos del Gobierno Vasco / Eusko Jaurlaritza"
    },
    "La Rioja": {
        "Grado": {"1": 16.20, "2": 27.54, "3": 59.40, "4": 82.51, "defecto": 16.20},
        "Máster Habilitante": {"1": 21.00, "2": 35.70, "3": 76.99, "4": 106.96, "defecto": 21.00},
        "Máster No Habilitante": {"1": 28.50, "2": 48.45, "3": 104.50, "4": 145.15, "defecto": 28.50},
        "Doctorado": {"1": 175.00, "defecto": 175.00},
        "tasas_admin": 44.00,
        "decreto_oficial": "Decreto de Precios Públicos del Gobierno de La Rioja"
    },
    "UNED": {
        "Grado": {"1": 14.50, "2": 24.65, "3": 53.17, "4": 73.85, "defecto": 14.50},
        "Máster Habilitante": {"1": 22.00, "2": 37.40, "3": 80.67, "4": 112.05, "defecto": 22.00},
        "Máster No Habilitante": {"1": 30.00, "2": 51.00, "3": 110.00, "4": 152.80, "defecto": 30.00},
        "Doctorado": {"1": 190.00, "defecto": 190.00},
        "tasas_admin": 40.00,
        "decreto_oficial": "Orden Ministerial de Precios Públicos de la UNED"
    }
}

# ==============================================================================
# Catálogo de honorarios oficiales de referencia para Universidades Privadas (SIIU / Memorias)
# ==============================================================================
OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG = {
    # 031: Universidad de Navarra (UNAV)
    "031": {
        "nombre": "Universidad de Navarra",
        "Grado - Salud": {"precio_credito_ects": 275.00, "precio_estimado_anual": 16500.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 200.00, "precio_estimado_anual": 12000.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado": {"precio_credito_ects": 200.00, "precio_estimado_anual": 12000.00},
        "Máster Habilitante": {"precio_credito_ects": 230.00, "precio_estimado_anual": 13800.00},
        "Máster No Habilitante": {"precio_credito_ects": 250.00, "precio_estimado_anual": 15000.00},
        "Máster": {"precio_credito_ects": 240.00, "precio_estimado_anual": 14400.00},
        "Doctorado": {"precio_credito_ects": 600.00, "precio_estimado_anual": 600.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad de Navarra"
    },
    # 034: Universidad Pontificia Comillas (ICADE / ICAI)
    "034": {
        "nombre": "Universidad Pontificia Comillas",
        "Grado - Salud": {"precio_credito_ects": 210.00, "precio_estimado_anual": 12600.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 220.00, "precio_estimado_anual": 13200.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 215.00, "precio_estimado_anual": 12900.00},
        "Grado": {"precio_credito_ects": 215.00, "precio_estimado_anual": 12900.00},
        "Máster Habilitante": {"precio_credito_ects": 240.00, "precio_estimado_anual": 14400.00},
        "Máster No Habilitante": {"precio_credito_ects": 260.00, "precio_estimado_anual": 15600.00},
        "Máster": {"precio_credito_ects": 250.00, "precio_estimado_anual": 15000.00},
        "Doctorado": {"precio_credito_ects": 550.00, "precio_estimado_anual": 550.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Pontificia Comillas"
    },
    # 030: Universidad de Deusto
    "030": {
        "nombre": "Universidad de Deusto",
        "Grado - Salud": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 150.00, "precio_estimado_anual": 9000.00},
        "Grado": {"precio_credito_ects": 155.00, "precio_estimado_anual": 9300.00},
        "Máster": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad de Deusto"
    },
    # 076 / 058: Universidad Internacional de La Rioja (UNIR)
    "076": {
        "nombre": "Universidad Internacional de La Rioja (UNIR)",
        "Grado - Salud": {"precio_credito_ects": 85.00, "precio_estimado_anual": 5100.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 75.00, "precio_estimado_anual": 4500.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 68.00, "precio_estimado_anual": 4080.00},
        "Grado": {"precio_credito_ects": 72.00, "precio_estimado_anual": 4320.00},
        "Máster": {"precio_credito_ects": 88.00, "precio_estimado_anual": 5280.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - UNIR"
    },
    # 054: Universitat Oberta de Catalunya (UOC)
    "054": {
        "nombre": "Universitat Oberta de Catalunya (UOC)",
        "Grado": {"precio_credito_ects": 32.50, "precio_estimado_anual": 1950.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 35.00, "precio_estimado_anual": 2100.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 30.00, "precio_estimado_anual": 1800.00},
        "Máster": {"precio_credito_ects": 52.00, "precio_estimado_anual": 3120.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - UOC"
    },
    # 047 / 106: Universidad Alfonso X El Sabio (UAX)
    "047": {
        "nombre": "Universidad Alfonso X El Sabio",
        "Grado - Salud": {"precio_credito_ects": 230.00, "precio_estimado_anual": 13800.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Máster": {"precio_credito_ects": 210.00, "precio_estimado_anual": 12600.00},
        "Doctorado": {"precio_credito_ects": 500.00, "precio_estimado_anual": 500.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Alfonso X El Sabio"
    },
    # 052: Universidad Antonio de Nebrija
    "052": {
        "nombre": "Universidad Antonio de Nebrija",
        "Grado - Salud": {"precio_credito_ects": 195.00, "precio_estimado_anual": 11700.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 170.00, "precio_estimado_anual": 10200.00},
        "Grado": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Máster": {"precio_credito_ects": 215.00, "precio_estimado_anual": 12900.00},
        "Doctorado": {"precio_credito_ects": 480.00, "precio_estimado_anual": 480.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Nebrija"
    },
    # 056: Universidad San Pablo-CEU
    "056": {
        "nombre": "Universidad San Pablo-CEU",
        "Grado - Salud": {"precio_credito_ects": 220.00, "precio_estimado_anual": 13200.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 185.00, "precio_estimado_anual": 11100.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado": {"precio_credito_ects": 185.00, "precio_estimado_anual": 11100.00},
        "Máster": {"precio_credito_ects": 220.00, "precio_estimado_anual": 13200.00},
        "Doctorado": {"precio_credito_ects": 500.00, "precio_estimado_anual": 500.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad San Pablo-CEU"
    },
    # 067: Universidad Cardenal Herrera-CEU
    "067": {
        "nombre": "Universidad Cardenal Herrera-CEU",
        "Grado - Salud": {"precio_credito_ects": 210.00, "precio_estimado_anual": 12600.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 170.00, "precio_estimado_anual": 10200.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado": {"precio_credito_ects": 170.00, "precio_estimado_anual": 10200.00},
        "Máster": {"precio_credito_ects": 200.00, "precio_estimado_anual": 12000.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Cardenal Herrera-CEU"
    },
    # 065: Universidad Camilo José Cela
    "065": {
        "nombre": "Universidad Camilo José Cela",
        "Grado - Salud": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 165.00, "precio_estimado_anual": 9900.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 155.00, "precio_estimado_anual": 9300.00},
        "Grado": {"precio_credito_ects": 165.00, "precio_estimado_anual": 9900.00},
        "Máster": {"precio_credito_ects": 195.00, "precio_estimado_anual": 11700.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Camilo José Cela"
    },
    # 066: Universidad Católica San Antonio (UCAM)
    "066": {
        "nombre": "Universidad Católica San Antonio (UCAM)",
        "Grado - Salud": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 130.00, "precio_estimado_anual": 7800.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 115.00, "precio_estimado_anual": 6900.00},
        "Grado": {"precio_credito_ects": 125.00, "precio_estimado_anual": 7500.00},
        "Máster": {"precio_credito_ects": 145.00, "precio_estimado_anual": 8700.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - UCAM"
    },
    # 072: Universidad Católica de Valencia San Vicente Mártir (UCV)
    "072": {
        "nombre": "Universidad Católica de Valencia (UCV)",
        "Grado - Salud": {"precio_credito_ects": 170.00, "precio_estimado_anual": 10200.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 135.00, "precio_estimado_anual": 8100.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 120.00, "precio_estimado_anual": 7200.00},
        "Grado": {"precio_credito_ects": 130.00, "precio_estimado_anual": 7800.00},
        "Máster": {"precio_credito_ects": 150.00, "precio_estimado_anual": 9000.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - UCV"
    },
    # 077: Universidad Loyola Andalucía
    "077": {
        "nombre": "Universidad Loyola Andalucía",
        "Grado - Salud": {"precio_credito_ects": 185.00, "precio_estimado_anual": 11100.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 170.00, "precio_estimado_anual": 10200.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado": {"precio_credito_ects": 165.00, "precio_estimado_anual": 9900.00},
        "Máster": {"precio_credito_ects": 205.00, "precio_estimado_anual": 12300.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Loyola Andalucía"
    },
    # 078: Universidad Internacional de Valencia (VIU)
    "078": {
        "nombre": "Universidad Internacional de Valencia (VIU)",
        "Grado - Salud": {"precio_credito_ects": 80.00, "precio_estimado_anual": 4800.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 75.00, "precio_estimado_anual": 4500.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 68.00, "precio_estimado_anual": 4080.00},
        "Grado": {"precio_credito_ects": 70.00, "precio_estimado_anual": 4200.00},
        "Máster": {"precio_credito_ects": 85.00, "precio_estimado_anual": 5100.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - VIU"
    },
    # 079: Universidad Isabel I
    "079": {
        "nombre": "Universidad Isabel I",
        "Grado - Salud": {"precio_credito_ects": 78.00, "precio_estimado_anual": 4680.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 72.00, "precio_estimado_anual": 4320.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 65.00, "precio_estimado_anual": 3900.00},
        "Grado": {"precio_credito_ects": 68.00, "precio_estimado_anual": 4080.00},
        "Máster": {"precio_credito_ects": 82.00, "precio_estimado_anual": 4920.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Isabel I"
    },
    # 074: UDIMA (Universidad a Distancia de Madrid)
    "074": {
        "nombre": "Universidad a Distancia de Madrid (UDIMA)",
        "Grado - Salud": {"precio_credito_ects": 88.00, "precio_estimado_anual": 5280.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 82.00, "precio_estimado_anual": 4920.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 77.00, "precio_estimado_anual": 4620.00},
        "Grado": {"precio_credito_ects": 80.00, "precio_estimado_anual": 4800.00},
        "Máster": {"precio_credito_ects": 95.00, "precio_estimado_anual": 5700.00},
        "Doctorado": {"precio_credito_ects": 420.00, "precio_estimado_anual": 420.00},
        "fuente": "Tarifario Oficial Institución Privada - UDIMA"
    },
    # 057 / 109: IE Universidad
    "057": {
        "nombre": "IE Universidad",
        "Grado": {"precio_credito_ects": 420.00, "precio_estimado_anual": 25200.00},
        "Máster": {"precio_credito_ects": 550.00, "precio_estimado_anual": 33000.00},
        "Doctorado": {"precio_credito_ects": 800.00, "precio_estimado_anual": 800.00},
        "fuente": "Tarifario Oficial Institución Privada - IE Universidad"
    },
    # 089: CUNEF Universidad
    "089": {
        "nombre": "CUNEF Universidad",
        "Grado": {"precio_credito_ects": 240.00, "precio_estimado_anual": 14400.00},
        "Máster": {"precio_credito_ects": 320.00, "precio_estimado_anual": 19200.00},
        "Doctorado": {"precio_credito_ects": 600.00, "precio_estimado_anual": 600.00},
        "fuente": "Tarifario Oficial Institución Privada - CUNEF"
    },
    # 087: ESIC Universidad
    "087": {
        "nombre": "ESIC Universidad",
        "Grado": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Máster": {"precio_credito_ects": 260.00, "precio_estimado_anual": 15600.00},
        "Doctorado": {"precio_credito_ects": 500.00, "precio_estimado_anual": 500.00},
        "fuente": "Tarifario Oficial Institución Privada - ESIC"
    },
    # 061: Universidad Europea de Madrid
    "061": {
        "nombre": "Universidad Europea de Madrid",
        "Grado - Salud": {"precio_credito_ects": 245.00, "precio_estimado_anual": 14700.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Máster": {"precio_credito_ects": 230.00, "precio_estimado_anual": 13800.00},
        "Doctorado": {"precio_credito_ects": 500.00, "precio_estimado_anual": 500.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Europea"
    }
}

from functools import lru_cache

@lru_cache(maxsize=256)
def normalize_ccaa_name(name: str) -> str:
    """
    Normaliza de forma robusta las variantes autonómicas del RUCT y Ministerios
    hacia las claves canónicas del catálogo oficial.
    """
    if not name:
        return ""
    
    n = name.strip().lower()
    if "andaluc" in n:
        return "Andalucía"
    elif "arag" in n:
        return "Aragón"
    elif "astur" in n:
        return "Principado de Asturias"
    elif "balear" in n or "illes" in n:
        return "Illes Balears"
    elif "canar" in n:
        return "Canarias"
    elif "cantabr" in n:
        return "Cantabria"
    elif "castilla y le" in n or "castilla-le" in n or "león" in n or "leon" in n:
        return "Castilla y León"
    elif "castilla" in n and ("mancha" in n or "la mancha" in n):
        return "Castilla-La Mancha"
    elif "catalu" in n or "catalun" in n:
        return "Cataluña"
    elif "valenc" in n:
        return "Comunitat Valenciana"
    elif "extrem" in n:
        return "Extremadura"
    elif "galic" in n:
        return "Galicia"
    elif "madrid" in n:
        return "Comunidad de Madrid"
    elif "murci" in n:
        return "Región de Murcia"
    elif "navarr" in n:
        return "Comunidad Foral de Navarra"
    elif "vasco" in n or "euskad" in n:
        return "País Vasco"
    elif "rioja" in n:
        return "La Rioja"
    elif "uned" in n or "nacional" in n or "no aplicable" in n:
        return "UNED"
    
    return name


@lru_cache(maxsize=256)
def is_public_university(tipo_univ: str) -> bool:
    """Determina si una universidad es de titularidad pública."""
    if not tipo_univ:
        return False
    t = str(tipo_univ).strip().lower()
    # Algunos catálogos históricos se guardaron con el carácter de reemplazo
    # Unicode (p. ej. ``P�blica``). Se normaliza sólo este caso conocido para
    # no perder el cálculo oficial de precios de universidades públicas.
    t = t.replace("�", "u")
    return "pública" in t or "publica" in t or "public" in t


def apply_price_info_to_degree(degree_dict: dict, price_info: dict, tipo_univ: str) -> bool:
    """Aplica de forma consistente los precios ECTS y retorna True si hubo modificaciones reales."""
    changed = False
    for k in ["precio_credito_ects", "precio_credito_2", "precio_credito_3", "precio_credito_4", "precio_estimado_anual", "fuente_precio"]:
        new_v = price_info.get(k)
        if new_v is None and degree_dict.get(k) not in (None, "", "null"):
            # Una CCAA desconocida o un fallo temporal no debe borrar el último dato válido.
            continue
        if degree_dict.get(k) != new_v:
            degree_dict[k] = new_v
            changed = True
    return changed


def load_precios_ccaa() -> dict:
    """Carga el catálogo local de precios por CCAA combinando el archivo persistido con el catálogo base oficial."""
    catalog = load_json_safe(PRECIOS_CCAA_JSON, default={})
    merged = dict(OFFICIAL_SIIU_PRICES_CATALOG)
    if isinstance(catalog, dict) and catalog:
        for ccaa_key, ccaa_val in catalog.items():
            if ccaa_key in merged and isinstance(ccaa_val, dict) and isinstance(merged[ccaa_key], dict):
                merged_ccaa = dict(merged[ccaa_key])
                merged_ccaa.update(ccaa_val)
                merged[ccaa_key] = merged_ccaa
            else:
                merged[ccaa_key] = ccaa_val
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        atomic_json_dump(merged, PRECIOS_CCAA_JSON)
    except OSError as error:
        logger.warning("No se pudo persistir el catálogo local de precios: %s", error)
    return merged


def load_universidades_map() -> dict:
    univ_map = {}
    data = load_json_safe(UNIVERSIDADES_JSON, default=[])
    if not isinstance(data, list):
        logger.warning("El catálogo de universidades no tiene formato de lista; no se cargarán precios por CCAA.")
        return univ_map
    for u in data:
        if not isinstance(u, dict):
            continue
        code = u.get("codigo")
        if code:
            code_str = str(code).strip()
            univ_map[code_str] = u
            univ_map[code_str.zfill(3)] = u
    return univ_map


def classify_degree_experimental_tier(titulo: str) -> str:
    """Clasifica el grado en una de las tres categorías de experimentalidad oficial:
    - Grado - Salud: Nivel 1 (Medicina, Enfermería, Veterinaria, Odontología, Farmacia...)
    - Grado - Ciencias e Ingeniería: Nivel 2 (Ingenierías, Arquitectura, Física, Química, Biología, Informática...)
    - Grado - Ciencias Sociales y Humanidades: Nivel 3 (Derecho, ADE, Historia, Filología, Educación...)
    """
    t = (titulo or "").lower()
    if any(k in t for k in [
        "medicina", "enfermería", "enfermeria", "infermeria", "odontología", "odontologia",
        "veterinaria", "farmacia", "fisioterapia", "podología", "podologia",
        "biomedicina", "ciencias biomédicas", "ciències biomèdiques", "nutrición", "nutricio"
    ]):
        return "Grado - Salud"
    if any(k in t for k in [
        "ingeniería", "ingenieria", "enginyeria", "enxeñaría", "ingeniaritza", "engineering",
        "informática", "informatica", "informàtica", "software", "computadores", "datos", "data",
        "química", "quimica", "física", "fisica", "biología", "biologia", "biotecnología", "biotecnologia",
        "matemáticas", "matematicas", "matemàtiques", "geología", "geologia", "arquitectura", "biomédica",
        "telecomunicación", "telecomunicació", "telecomunicaciones", "aeroespacial", "naval", "mecánica", "mecanica", "eléctrica", "electrica", "industrial"
    ]):
        return "Grado - Ciencias e Ingeniería"
    return "Grado - Ciencias Sociales y Humanidades"


def compute_degree_price(
    ccaa: str,
    tipo_univ: str,
    nivel_academico: str,
    titulo: str,
    precios_catalogo: dict = None,
    univ_codigo: str = None,
    univ_nombre: str = None,
) -> dict:
    """Calcula una estimación a partir del catálogo local configurado por CCAA (públicas) o tarifarios institucionales (privadas).

    El año académico y la vigencia deben verificarse fuera de este módulo.
    """
    if not is_public_university(tipo_univ):
        # 1. Búsqueda en catálogo de universidades privadas por código o nombre
        u_code_norm = str(univ_codigo or "").zfill(3)
        priv_entry = OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG.get(u_code_norm)
        if not priv_entry and univ_nombre:
            u_nom_low = univ_nombre.lower()
            for code, data in OFFICIAL_PRIVATE_UNIVERSITIES_PRICES_CATALOG.items():
                if data.get("nombre", "").lower() in u_nom_low or u_nom_low in data.get("nombre", "").lower():
                    priv_entry = data
                    break

        if priv_entry:
            nivel_lower = (nivel_academico or "").lower()
            titulo_lower = (titulo or "").lower()

            if "doctorado" in nivel_lower or "560" in nivel_lower or "900" in nivel_lower or "doctor" in titulo_lower:
                tarifa = priv_entry.get("Doctorado")
            elif "máster" in nivel_lower or "master" in nivel_lower or "431" in nivel_lower:
                tarifa = priv_entry.get("Máster Habilitante") if any(h in titulo_lower for h in ["profesorado", "abogacía", "ingeniería"]) else (priv_entry.get("Máster No Habilitante") or priv_entry.get("Máster"))
            else:
                exp_tier = classify_degree_experimental_tier(titulo)
                tarifa = priv_entry.get(exp_tier) or priv_entry.get("Grado")

            if isinstance(tarifa, dict):
                p_ects = tarifa.get("precio_credito_ects")
                p_anual = tarifa.get("precio_estimado_anual") or (round(p_ects * 60, 2) if p_ects else None)
                fuente = priv_entry.get("fuente") or f"Tarifario Oficial Institución Privada - {priv_entry.get('nombre', 'Universidad Privada')}"
                return {
                    "precio_credito_ects": p_ects,
                    "precio_credito_2": p_ects,
                    "precio_credito_3": p_ects,
                    "precio_credito_4": p_ects,
                    "precio_estimado_anual": p_anual,
                    "fuente_precio": fuente
                }

        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Universidad Privada ({univ_nombre or 'Tarifas fijadas por la institución'} - Consultar con la institución)"
        }
        
    if precios_catalogo is None:
        precios_catalogo = load_precios_ccaa()

    canonical_ccaa = normalize_ccaa_name(ccaa)
    ccaa_data = precios_catalogo.get(canonical_ccaa)
    
    if not ccaa_data and canonical_ccaa:
        # Búsqueda difusa por nombre de CCAA
        for k, v in precios_catalogo.items():
            if k.lower() in canonical_ccaa.lower() or canonical_ccaa.lower() in k.lower():
                ccaa_data = v
                canonical_ccaa = k
                break
                
    if not ccaa_data:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"CCAA desconocida o no registrada ({ccaa or 'Sin CCAA'})"
        }

    nivel_lower = (nivel_academico or "").lower()
    titulo_lower = (titulo or "").lower()
    
    # Determinar categoría académica oficial
    if "doctorado" in nivel_lower or "560" in nivel_lower or "900" in nivel_lower or "doctor" in titulo_lower:
        cat = "Doctorado"
        cat_prices = ccaa_data.get(cat)
    elif "máster" in nivel_lower or "master" in nivel_lower or "431" in nivel_lower:
        # Másteres que habilitan para el ejercicio de profesiones reguladas en España (soporte multilingüe ES, CA, GL, EU)
        habilitantes = [
            "abogacía", "abogacia", "advocacia", "advocacia i procura", "procura",
            "profesorado", "profesor", "secundaria", "formació del professorat", "formacion del profesorado", "formacion do profesorado", "irakasleen prestakuntza",
            "ingeniería de caminos", "enginyeria de camins", "enxeñaría de camiños",
            "ingeniería industrial", "enginyeria industrial", "enxeñaría industrial", "industria ingeniaritza",
            "ingeniería de telecomunicación", "enginyeria de telecomunicació", "enxeñaría de telecomunicación", "telekomunikazio ingeniaritza",
            "ingeniería aeronáutica", "enginyeria aeronàutica", "enxeñaría aeronáutica", "aeronautika ingeniaritza",
            "ingeniería agronómica", "enginyeria agronòmica", "enxeñaría agronómica", "nekazaritza ingeniaritza",
            "ingeniería naval", "enginyeria naval", "enxeñaría naval",
            "ingeniería de montes", "enginyeria de forests", "enxeñaría de montes",
            "ingeniería de minas", "enginyeria de mines", "enxeñaría de minas",
            "arquitectura", "arkitektura",
            "psicología general sanitaria", "psicologia general sanitaria", "psicologia general sanitària", "osasun psikologia orokorra",
            "náutica y transporte marítimo", "nautica y transporte maritimo", "nàutica i transport marítim", "gestión y planificación portuaria", "marina mercante",
            "ingeniería química", "enginyeria química", "enxeñaría química", "ingenieria quimica"
        ]
        if any(h in titulo_lower for h in habilitantes):
            cat = "Máster Habilitante"
        else:
            cat = "Máster No Habilitante"
        cat_prices = ccaa_data.get(cat)
    else:
        cat = "Grado"
        exp_tier = classify_degree_experimental_tier(titulo)
        cat_prices = ccaa_data.get(exp_tier) or ccaa_data.get(cat)
        
    if not cat_prices:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Categoría {cat} no registrada en decreto de {canonical_ccaa}"
        }

    if isinstance(cat_prices, dict):
        precio_ects = cat_prices.get("1") or cat_prices.get("defecto")
        precio_2 = cat_prices.get("2")
        precio_3 = cat_prices.get("3")
        precio_4 = cat_prices.get("4")
    else:
        precio_ects = cat_prices
        precio_2 = None
        precio_3 = None
        precio_4 = None

    if precio_ects is None:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Precio no disponible en decreto de {canonical_ccaa}"
        }

    try:
        precio_ects = float(precio_ects)
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_ects malformado en catálogo: {precio_ects}")
        precio_ects = None

    if precio_ects is None or precio_ects <= 0:
        return {
            "precio_credito_ects": None,
            "precio_credito_2": None,
            "precio_credito_3": None,
            "precio_credito_4": None,
            "precio_estimado_anual": None,
            "fuente_precio": f"Precio por ECTS inválido en el catálogo de {canonical_ccaa}",
        }

    try:
        precio_2 = float(precio_2) if precio_2 is not None else None
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_2 malformado en catálogo: {precio_2}")
        precio_2 = None

    try:
        precio_3 = float(precio_3) if precio_3 is not None else None
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_3 malformado en catálogo: {precio_3}")
        precio_3 = None

    try:
        precio_4 = float(precio_4) if precio_4 is not None else None
    except (ValueError, TypeError):
        logger.warning(f"Dato de precio_4 malformado en catálogo: {precio_4}")
        precio_4 = None
        
    try:
        tasas_admin = float(ccaa_data.get("tasas_admin", 0.0))
    except (ValueError, TypeError):
        logger.warning("Tasa administrativa malformada en el catálogo de %s", canonical_ccaa)
        tasas_admin = 0.0
    decreto_fuente = ccaa_data.get("decreto_oficial", f"Decreto de Precios Públicos de {canonical_ccaa}")
    
    # Para Doctorado la matrícula anual es la tutela académica (~100-400€)
    if cat == "Doctorado":
        precio_anual = round(precio_ects + tasas_admin, 2)
    else:
        precio_anual = round(STANDARD_YEAR_ECTS_CREDITS * precio_ects + tasas_admin, 2)
        
    return {
        "precio_credito_ects": round(precio_ects, 2),
        "precio_credito_2": round(precio_2, 2) if precio_2 is not None else None,
        "precio_credito_3": round(precio_3, 2) if precio_3 is not None else None,
        "precio_credito_4": round(precio_4, 2) if precio_4 is not None else None,
        "precio_estimado_anual": round(precio_anual, 2),
        "fuente_precio": (
            f"Catálogo local SIIU ({PRICE_CATALOG_ACADEMIC_YEAR}) / {decreto_fuente}; "
            "verificar vigencia"
        )
    }


def run_phase1_part3(
    limit_universities: int = None,
    limit_degrees: int = None,
    force: bool = False,
    max_workers: int = None,
    metrics_tracker=None,
    progress_emitter=None,
    degree_title_filter: str | None = None,
    target_universities: list[str] | set[str] | None = None,
) -> dict:
    """
    Fase 1 - Parte 3: Asigna tarifas catalogadas y estima las matrículas
    anuales de las titulaciones de universidades públicas.
    """
    print("\n======================================================================")
    print("      FASE 1 - PARTE 3: CÁLCULO DE PRECIOS ECTS DE MATRÍCULA PÚBLICA")
    print("======================================================================")

    if not is_price_catalog_publishable(PRICE_CATALOG_ACADEMIC_YEAR, PRICE_CATALOG_VERIFIED):
        print(" [AVISO PARTE 3] Catálogo de precios sin curso y verificación explícita; no se publican importes.")
        return {
            "status": "skipped",
            "reason": "unverified_price_catalog",
            "academic_year": PRICE_CATALOG_ACADEMIC_YEAR,
            "verified": PRICE_CATALOG_VERIFIED,
        }
    
    precios_catalogo = load_precios_ccaa()
    univ_map = load_universidades_map()
    json_files = iter_plan_files(PLANES_DIR)

    selected_files = []
    selected_universities = []
    degrees_per_university = {}
    effective_targets = {str(c).zfill(3) for c in (target_universities or TARGET_UNIVERSITY_CODES or [])}
    for filepath in json_files:
        degree = load_json_safe(filepath, default={}) or {}
        if degree_title_filter:
            from phase_common import matches_degree_title
            if not matches_degree_title(degree.get("titulo"), degree_title_filter):
                continue
        u_code = str(degree.get("universidad_codigo") or os.path.basename(os.path.dirname(filepath))).strip().zfill(3)
        if effective_targets and u_code not in effective_targets:
            continue
        if u_code not in degrees_per_university:
            if limit_universities is not None and len(selected_universities) >= max(0, limit_universities):
                continue
            selected_universities.append(u_code)
            degrees_per_university[u_code] = 0
        if limit_degrees is not None and degrees_per_university[u_code] >= max(0, limit_degrees):
            continue
        degrees_per_university[u_code] += 1
        selected_files.append(filepath)
    
    updated_count = 0
    public_count = 0
    prices_cache = {}
    processing_errors = 0
    
    for position, filepath in enumerate(selected_files, start=1):
        raise_if_shutdown_requested()
        try:
            degree = load_json_safe(filepath, default={}) or {}
            d_code = degree.get("codigo_estudio") or os.path.splitext(os.path.basename(filepath))[0]
                
            u_code = str(degree.get("universidad_codigo") or os.path.basename(os.path.dirname(filepath))).strip().zfill(3)
            univ = univ_map.get(u_code, {})
            
            ccaa = univ.get("comunidad_autonoma") or degree.get("comunidad_autonoma") or ""
            tipo_univ = univ.get("tipo") or degree.get("tipo") or ""
            nivel = degree.get("nivel_academico", "")
            titulo = degree.get("titulo", "")
            
            univ_nombre = univ.get("nombre") or degree.get("universidad_nombre") or ""
            price_info = compute_degree_price(
                ccaa,
                tipo_univ,
                nivel,
                titulo,
                precios_catalogo=precios_catalogo,
                univ_codigo=u_code,
                univ_nombre=univ_nombre,
            )
            prices_cache[d_code] = (price_info, tipo_univ)
            
            changed = apply_price_info_to_degree(degree, price_info, tipo_univ)
            if changed:
                atomic_json_dump(degree, filepath)
                updated_count += 1
            
            if price_info.get("precio_credito_ects") is not None:
                public_count += 1
            if progress_emitter is not None:
                progress_emitter.update_degree(
                    position,
                    len(selected_files),
                    str(d_code),
                    degree.get("titulo", ""),
                    "Precio actualizado" if changed else "Sin cambios",
                )
        except Exception as e:
            processing_errors += 1
            print(f" [AVISO] Error al procesar precio de '{filepath}': {e}")

    # También actualizar titulaciones_universidad.json
    tit_json_path = os.path.join(DATA_DIR, "titulaciones_universidad.json")
    catalog_update_failed = False
    if os.path.exists(tit_json_path):
        try:
            tit_data = load_json_safe(tit_json_path)
                
            if isinstance(tit_data, dict):
                items_to_iter = tit_data.items()
            elif isinstance(tit_data, list):
                items_to_iter = [(u.get("codigo", ""), u) for u in tit_data if isinstance(u, dict)]
            else:
                items_to_iter = []
                
            for u_code, u_info in items_to_iter:
                if not isinstance(u_info, dict):
                    continue
                univ = univ_map.get(u_code, {})
                ccaa = univ.get("comunidad_autonoma") or ""
                tipo_univ = univ.get("tipo") or ""
                univ_nombre = univ.get("nombre") or ""
                
                for t in u_info.get("titulaciones_vigentes", []):
                    t_code = t.get("codigo_estudio") or t.get("codigo")
                    if t_code in prices_cache:
                        price_info, t_tipo = prices_cache[t_code]
                    elif limit_universities is not None or limit_degrees is not None:
                        continue
                    else:
                        price_info = compute_degree_price(
                            ccaa,
                            tipo_univ,
                            t.get("nivel_academico", ""),
                            t.get("titulo", ""),
                            precios_catalogo=precios_catalogo,
                            univ_codigo=u_code,
                            univ_nombre=univ_nombre,
                        )
                        t_tipo = tipo_univ
                        
                    apply_price_info_to_degree(t, price_info, t_tipo)
                    
            atomic_json_dump(tit_data, tit_json_path)
            print(" -> 'titulaciones_universidad.json' actualizado con precios ECTS.")
        except Exception as e:
            catalog_update_failed = True
            print(f" [AVISO] Error al actualizar titulaciones_universidad.json: {e}")
            
    print(f" -> Titulaciones en planes_estudio actualizadas: {updated_count}")
    print(f" -> Titulaciones Públicas con Tarifa Oficial SIIU: {public_count}")
    print("======================================================================\n")

    return {
        "status": "partial" if processing_errors or catalog_update_failed else "completed",
        "plans_inspected": len(selected_files),
        "plans_updated": updated_count,
        "public_degrees_priced": public_count,
        "errors": processing_errors + int(catalog_update_failed),
    }


if __name__ == "__main__":
    run_phase1_part3()
