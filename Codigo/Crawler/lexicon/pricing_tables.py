"""Tablas de precios oficiales autonómicos (SIIU) y honorarios de referencia en privadas."""

from __future__ import annotations

import re
from functools import lru_cache

PRICE_CATALOG_ACADEMIC_YEAR = "2025-2026"

def is_verified_academic_year(value: str) -> bool:
    """Solo permite publicar tarifas cuando se identifica el curso académico."""
    return bool(re.fullmatch(r"20\d{2}-20\d{2}", str(value or "").strip()))


def is_price_catalog_publishable(academic_year: str, verified: bool) -> bool:
    """Evita publicar estimaciones si no existe una revisión explícita del catálogo."""
    return is_verified_academic_year(academic_year) and bool(verified)

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
    },
    # 053: Universidad Europea de Madrid (código oficial RUCT)
    "053": {
        "nombre": "Universidad Europea de Madrid",
        "Grado - Salud": {"precio_credito_ects": 245.00, "precio_estimado_anual": 14700.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Máster": {"precio_credito_ects": 230.00, "precio_estimado_anual": 13800.00},
        "Doctorado": {"precio_credito_ects": 500.00, "precio_estimado_anual": 500.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Europea de Madrid"
    },
    # 041 / 055: Universitat Ramon Llull
    "041": {
        "nombre": "Universitat Ramon Llull",
        "Grado - Salud": {"precio_credito_ects": 215.00, "precio_estimado_anual": 12900.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 195.00, "precio_estimado_anual": 11700.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Grado": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Máster": {"precio_credito_ects": 235.00, "precio_estimado_anual": 14100.00},
        "Doctorado": {"precio_credito_ects": 550.00, "precio_estimado_anual": 550.00},
        "fuente": "Tarifario Oficial Institución Privada - Universitat Ramon Llull"
    },
    "055": {
        "nombre": "Universitat Ramon Llull",
        "Grado - Salud": {"precio_credito_ects": 215.00, "precio_estimado_anual": 12900.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 195.00, "precio_estimado_anual": 11700.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Grado": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Máster": {"precio_credito_ects": 235.00, "precio_estimado_anual": 14100.00},
        "Doctorado": {"precio_credito_ects": 550.00, "precio_estimado_anual": 550.00},
        "fuente": "Tarifario Oficial Institución Privada - Universitat Ramon Llull"
    },
    # 060: Universitat de Vic - Universitat Central de Catalunya (UVic-UCC)
    "060": {
        "nombre": "Universitat de Vic-Universitat Central de Catalunya",
        "Grado - Salud": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 145.00, "precio_estimado_anual": 8700.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 135.00, "precio_estimado_anual": 8100.00},
        "Grado": {"precio_credito_ects": 145.00, "precio_estimado_anual": 8700.00},
        "Máster": {"precio_credito_ects": 170.00, "precio_estimado_anual": 10200.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - UVic-UCC"
    },
    # 068 / 064: Universidad Francisco de Vitoria (UFV)
    "068": {
        "nombre": "Universidad Francisco de Vitoria",
        "Grado - Salud": {"precio_credito_ects": 235.00, "precio_estimado_anual": 14100.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado": {"precio_credito_ects": 185.00, "precio_estimado_anual": 11100.00},
        "Máster": {"precio_credito_ects": 225.00, "precio_estimado_anual": 13500.00},
        "Doctorado": {"precio_credito_ects": 520.00, "precio_estimado_anual": 520.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Francisco de Vitoria"
    },
    "064": {
        "nombre": "Universidad Francisco de Vitoria",
        "Grado - Salud": {"precio_credito_ects": 235.00, "precio_estimado_anual": 14100.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado": {"precio_credito_ects": 185.00, "precio_estimado_anual": 11100.00},
        "Máster": {"precio_credito_ects": 225.00, "precio_estimado_anual": 13500.00},
        "Doctorado": {"precio_credito_ects": 520.00, "precio_estimado_anual": 520.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Francisco de Vitoria"
    },
    # 032: Universidad Pontificia de Salamanca (UPSA)
    "032": {
        "nombre": "Universidad Pontificia de Salamanca",
        "Grado - Salud": {"precio_credito_ects": 140.00, "precio_estimado_anual": 8400.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 120.00, "precio_estimado_anual": 7200.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 105.00, "precio_estimado_anual": 6300.00},
        "Grado": {"precio_credito_ects": 115.00, "precio_estimado_anual": 6900.00},
        "Máster": {"precio_credito_ects": 135.00, "precio_estimado_anual": 8100.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Pontificia de Salamanca"
    },
    # 062: Universitat Internacional de Catalunya (UIC)
    "062": {
        "nombre": "Universitat Internacional de Catalunya",
        "Grado - Salud": {"precio_credito_ects": 240.00, "precio_estimado_anual": 14400.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 195.00, "precio_estimado_anual": 11700.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Grado": {"precio_credito_ects": 195.00, "precio_estimado_anual": 11700.00},
        "Máster": {"precio_credito_ects": 240.00, "precio_estimado_anual": 14400.00},
        "Doctorado": {"precio_credito_ects": 500.00, "precio_estimado_anual": 500.00},
        "fuente": "Tarifario Oficial Institución Privada - UIC Barcelona"
    },
    # 082 / 081: Universidad Europea de Valencia
    "082": {
        "nombre": "Universidad Europea de Valencia",
        "Grado - Salud": {"precio_credito_ects": 220.00, "precio_estimado_anual": 13200.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Máster": {"precio_credito_ects": 210.00, "precio_estimado_anual": 12600.00},
        "Doctorado": {"precio_credito_ects": 480.00, "precio_estimado_anual": 480.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Europea de Valencia"
    },
    "081": {
        "nombre": "Universidad Europea de Valencia",
        "Grado - Salud": {"precio_credito_ects": 220.00, "precio_estimado_anual": 13200.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado": {"precio_credito_ects": 175.00, "precio_estimado_anual": 10500.00},
        "Máster": {"precio_credito_ects": 210.00, "precio_estimado_anual": 12600.00},
        "Doctorado": {"precio_credito_ects": 480.00, "precio_estimado_anual": 480.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Europea de Valencia"
    },
    # 069: Universidad Europea Miguel de Cervantes (UEMC)
    "069": {
        "nombre": "Universidad Europea Miguel de Cervantes",
        "Grado - Salud": {"precio_credito_ects": 145.00, "precio_estimado_anual": 8700.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 125.00, "precio_estimado_anual": 7500.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 115.00, "precio_estimado_anual": 6900.00},
        "Grado": {"precio_credito_ects": 125.00, "precio_estimado_anual": 7500.00},
        "Máster": {"precio_credito_ects": 140.00, "precio_estimado_anual": 8400.00},
        "Doctorado": {"precio_credito_ects": 400.00, "precio_estimado_anual": 400.00},
        "fuente": "Tarifario Oficial Institución Privada - UEMC"
    },
    # 059: Universidad Católica Santa Teresa de Jesús de Ávila (UCAV)
    "059": {
        "nombre": "Universidad Católica Santa Teresa de Jesús de Ávila",
        "Grado - Salud": {"precio_credito_ects": 120.00, "precio_estimado_anual": 7200.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 105.00, "precio_estimado_anual": 6300.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 95.00, "precio_estimado_anual": 5700.00},
        "Grado": {"precio_credito_ects": 100.00, "precio_estimado_anual": 6000.00},
        "Máster": {"precio_credito_ects": 115.00, "precio_estimado_anual": 6900.00},
        "Doctorado": {"precio_credito_ects": 380.00, "precio_estimado_anual": 380.00},
        "fuente": "Tarifario Oficial Institución Privada - UCAV"
    },
    # 073: Universidad San Jorge (USJ)
    "073": {
        "nombre": "Universidad San Jorge",
        "Grado - Salud": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 145.00, "precio_estimado_anual": 8700.00},
        "Grado": {"precio_credito_ects": 155.00, "precio_estimado_anual": 9300.00},
        "Máster": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad San Jorge"
    },
    # 088 / 091: Universidad Villanueva
    "088": {
        "nombre": "Universidad Internacional Villanueva",
        "Grado - Salud": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 150.00, "precio_estimado_anual": 9000.00},
        "Grado": {"precio_credito_ects": 155.00, "precio_estimado_anual": 9300.00},
        "Máster": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Villanueva"
    },
    "091": {
        "nombre": "Universidad Villanueva",
        "Grado - Salud": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 160.00, "precio_estimado_anual": 9600.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 150.00, "precio_estimado_anual": 9000.00},
        "Grado": {"precio_credito_ects": 155.00, "precio_estimado_anual": 9300.00},
        "Máster": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Villanueva"
    },
    # 033: Universidad Pontificia Comillas
    "033": {
        "nombre": "Universidad Pontificia Comillas",
        "Grado - Salud": {"precio_credito_ects": 210.00, "precio_estimado_anual": 12600.00},
        "Grado - Ciencias e Ingeniería": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Grado - Ciencias Sociales y Humanidades": {"precio_credito_ects": 180.00, "precio_estimado_anual": 10800.00},
        "Grado": {"precio_credito_ects": 185.00, "precio_estimado_anual": 11100.00},
        "Máster": {"precio_credito_ects": 230.00, "precio_estimado_anual": 13800.00},
        "Doctorado": {"precio_credito_ects": 500.00, "precio_estimado_anual": 500.00},
        "fuente": "Tarifario Oficial Institución Privada - Universidad Pontificia Comillas"
    },
    # 100: UDIT
    "100": {
        "nombre": "Universidad de Diseño, Innovación y Tecnología (UDIT)",
        "Grado": {"precio_credito_ects": 190.00, "precio_estimado_anual": 11400.00},
        "Máster": {"precio_credito_ects": 230.00, "precio_estimado_anual": 13800.00},
        "Doctorado": {"precio_credito_ects": 450.00, "precio_estimado_anual": 450.00},
        "fuente": "Tarifario Oficial Institución Privada - UDIT"
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



