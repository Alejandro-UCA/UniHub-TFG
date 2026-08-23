import json
import os

path = 'd:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva/progreso_fase1_parte2_por_universidad.json'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        d = json.load(f)
    print(f"Universidades procesadas: {d.get('universidades_procesadas')} / {d.get('total_universidades')}")
    for u in d.get('resultados', []):
        print(f"-> [{u['universidad_codigo']}] {u['universidad_nombre']}: {u['titulaciones_completadas_con_exito']} rescatadas completas de {u['titulaciones_pendientes_iniciales']} (Parciales: {u.get('titulaciones_parciales')}, Sin plan: {u.get('titulaciones_sin_plan')})")
else:
    print("El archivo de reporte aún no se ha creado (primera universidad en progreso).")
