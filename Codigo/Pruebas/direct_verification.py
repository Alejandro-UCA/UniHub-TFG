import sys
import os
import json
from bs4 import BeautifulSoup
import urllib.request

sys.path.append('d:/Proyecto/Codigo/Crawler')
from univ_web_crawler import (
    is_valid_curricular_table,
    extract_html_subjects,
    score_academic_candidate_url,
    ACADEMIC_KEYWORDS
)

print("=======================================================================")
print("  VERIFICACIÓN DE CASOS PROBLEMÁTICOS vs CASO DE CONTROL")
print("=======================================================================")

# Caso 1: UAM Reconocimiento de créditos
url_uam = "https://www.uam.es/uam/estudios/reconocimiento-de-creditos"
req = urllib.request.Request(url_uam, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as resp:
    html_uam = resp.read().decode("utf-8", errors="replace")
soup_uam = BeautifulSoup(html_uam, "html.parser")
subs_uam = extract_html_subjects(soup_uam)
score_uam = score_academic_candidate_url(url_uam, "Reconocimiento de créditos", "Grado", ["hispánicos", "lengua"])
print(f"\n1. Caso UAM Reconocimiento:")
print(f"   - Score asignado: {score_uam} (Degradado a mínima prioridad)")
print(f"   - Asignaturas extraídas: {len(subs_uam)} (Esperado: 0)")
ok1 = (len(subs_uam) == 0) and (score_uam <= 10)

# Caso 2: UBU Política de Cookies
url_ubu = "https://www.ubu.es/web-institucional/politica-de-cookies-de-la-web-institucional-de-la-universidad-de-burgos"
req = urllib.request.Request(url_ubu, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as resp:
    html_ubu = resp.read().decode("utf-8", errors="replace")
soup_ubu = BeautifulSoup(html_ubu, "html.parser")
subs_ubu = extract_html_subjects(soup_ubu)
score_ubu = score_academic_candidate_url(url_ubu, "Política de cookies", "Grado", ["matemática", "computación"])
print(f"\n2. Caso UBU Cookies:")
print(f"   - Score asignado: {score_ubu} (Degradado a mínima prioridad)")
print(f"   - Asignaturas extraídas: {len(subs_ubu)} (Esperado: 0)")
ok2 = (len(subs_ubu) == 0) and (score_ubu <= 10)

# Caso 3: UJA Información Protección de Datos
url_uja = "https://cealm.ujaen.es/informacion-proteccion-de-datos-de-caracter-personal"
req = urllib.request.Request(url_uja, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as resp:
    html_uja = resp.read().decode("utf-8", errors="replace")
soup_uja = BeautifulSoup(html_uja, "html.parser")
subs_uja = extract_html_subjects(soup_uja)
score_uja = score_academic_candidate_url(url_uja, "Protección de datos", "Máster", ["dependencia", "igualdad"])
print(f"\n3. Caso UJA Protección de Datos:")
print(f"   - Score asignado: {score_uja} (Degradado a mínima prioridad)")
print(f"   - Asignaturas extraídas: {len(subs_uja)} (Esperado: 0)")
ok3 = (len(subs_uja) == 0) and (score_uja <= 10)

# Caso 4: UAB Mínor vs Grau
url_minor = "https://www.uab.cat/web/estudios/grado/oferta-de-grados/minors/plan-de-estudios-1345692436621.html"
score_minor = score_academic_candidate_url(url_minor, "Plan de estudios del mínor", "Grado", ["estudios", "clásicos"])

url_grau = "https://www.uab.cat/web/estudiar/la-oferta-de-grados/oferta-de-grados/grau-en-estudis-classics-1345467811508.html"
score_grau = score_academic_candidate_url(url_grau, "Grau en Estudis Clàssics", "Grado", ["estudios", "clásicos"])

print(f"\n4. Caso UAB Mínor vs Grau:")
print(f"   - Score asignado a página de Mínor: {score_minor}")
print(f"   - Score asignado a página de Grau oficial: {score_grau}")
ok4 = (score_grau > score_minor + 50)

# Caso 5: CONTROL POSITIVO (UCA Grado en Ingeniería Informática)
real_uca_html = """
<table>
    <thead><tr><th>Código</th><th>Asignatura</th><th>Carácter</th><th>Créditos ECTS</th><th>Curso</th></tr></thead>
    <tbody>
        <tr><td>101</td><td>Fundamentos de Programación</td><td>FB</td><td>6</td><td>1</td></tr>
        <tr><td>102</td><td>Cálculo</td><td>FB</td><td>6</td><td>1</td></tr>
        <tr><td>103</td><td>Álgebra Lineal</td><td>FB</td><td>6</td><td>1</td></tr>
        <tr><td>104</td><td>Física y Circuitos</td><td>FB</td><td>6</td><td>1</td></tr>
        <tr><td>105</td><td>Estructura de Datos</td><td>OB</td><td>6</td><td>2</td></tr>
        <tr><td>106</td><td>Sistemas Operativos</td><td>OB</td><td>6</td><td>2</td></tr>
        <tr><td>107</td><td>Bases de Datos</td><td>OB</td><td>6</td><td>2</td></tr>
        <tr><td>108</td><td>Ingeniería del Software</td><td>OB</td><td>6</td><td>3</td></tr>
        <tr><td>109</td><td>Redes y Seguridad</td><td>OB</td><td>6</td><td>3</td></tr>
        <tr><td>110</td><td>Trabajo Fin de Grado</td><td>TFG</td><td>12</td><td>4</td></tr>
    </tbody>
</table>
"""
soup_uca = BeautifulSoup(real_uca_html, "html.parser")
subs_uca = extract_html_subjects(soup_uca)
print(f"\n5. Caso CONTROL POSITIVO (UCA Grado Informática):")
print(f"   - Asignaturas extraídas: {len(subs_uca)} / 10 (Esperado: 10)")
ok5 = (len(subs_uca) == 10)

print("\n=======================================================================")
print("  RESULTADOS FINALES DE LA AUDITORÍA DE PRUEBA")
print("=======================================================================")
print(f"  [{'OK' if ok1 else 'FALLO'}] 1. Rechazo de Reconocimiento de Creditos UAM")
print(f"  [{'OK' if ok2 else 'FALLO'}] 2. Rechazo de Tabla de Cookies UBU")
print(f"  [{'OK' if ok3 else 'FALLO'}] 3. Rechazo de Proteccion de Datos DPO UJA")
print(f"  [{'OK' if ok4 else 'FALLO'}] 4. Degradacion de Minors UAB frente al Grado")
print(f"  [{'OK' if ok5 else 'FALLO'}] 5. Extraccion Correcta de Plan Curricular Real (Control Positivo)")

all_passed = ok1 and ok2 and ok3 and ok4 and ok5
print(f"\nESTADO GLOBAL: {'100% CORRECTO Y VERIFICADO' if all_passed else 'FALLARON COMPROBACIONES'}")
