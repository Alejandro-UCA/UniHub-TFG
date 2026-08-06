import os
import sys
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add API parent directory to import path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from models.models import (
    Base,
    Universidad,
    Titulacion,
    PlanEstudios,
    ResumenCreditos,
    ElementoCurricular,
    ErrorCrawler,
    EstadisticaRendimiento
)

def run_etl():
    print("=" * 70)
    print("     INICIANDO PROCESO ETL: MIGRACIÓN DE JSON (FASE 1) A POSTGRESQL")
    print("======================================================================")
    
    # Path to Phase 1 data directory (Check Docker path /app/Datos first, fallback to local path)
    base_api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    crawler_datos_dir = "/app/Datos"
    if not os.path.exists(crawler_datos_dir):
        crawler_datos_dir = os.path.join(os.path.dirname(base_api_dir), "Crawler", "Datos")
    
    if not os.path.exists(crawler_datos_dir):
        print(f"[ERROR] No se encontró el directorio de datos del crawler en '{crawler_datos_dir}'.")
        return

    print(f"Directorio de datos localizado en: '{crawler_datos_dir}'")

    # Database engine and tables setup
    print("Conectando a la base de datos PostgreSQL...")
    try:
        engine = create_engine(settings.DATABASE_URL)
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a PostgreSQL: {e}")
        print("Asegúrate de que PostgreSQL está iniciado y las credenciales son correctas.")
        return

    # 1. Migrar Universidades
    univ_json_path = os.path.join(crawler_datos_dir, "universidades_list.json")
    if not os.path.exists(univ_json_path):
        univ_json_path = os.path.join(crawler_datos_dir, "universidades.json")

    if os.path.exists(univ_json_path):
        with open(univ_json_path, "r", encoding="utf-8") as f:
            univ_list = json.load(f)
            
        print(f"Migrando {len(univ_list)} universidades a PostgreSQL...")
        for u in univ_list:
            code = u.get("codigo")
            existing = db.query(Universidad).filter(Universidad.codigo == code).first()
            if not existing:
                univ_obj = Universidad(
                    codigo=code,
                    nombre=u.get("nombre", ""),
                    tipo=u.get("tipo", ""),
                    comunidad_autonoma=u.get("comunidad_autonoma", ""),
                    municipio=u.get("municipio", ""),
                    provincia=u.get("provincia", ""),
                    web=u.get("web", ""),
                    email=u.get("email", ""),
                    telefono=u.get("telefono", "")
                )
                db.add(univ_obj)
        db.commit()
        print(" -> Universidades migradas con éxito.")

    # 2. Migrar Titulaciones
    tit_json_path = os.path.join(crawler_datos_dir, "titulaciones_universidad.json")
    if os.path.exists(tit_json_path):
        with open(tit_json_path, "r", encoding="utf-8") as f:
            tit_data = json.load(f)
            
        total_tits = 0
        for u_code, u_info in tit_data.items():
            vigentes = u_info.get("titulaciones_vigentes", [])
            total_tits += len(vigentes)
            for t in vigentes:
                d_code = t.get("codigo_estudio")
                existing = db.query(Titulacion).filter(Titulacion.codigo_estudio == d_code).first()
                if not existing:
                    tit_obj = Titulacion(
                        codigo_estudio=d_code,
                        titulo=t.get("titulo", ""),
                        nivel_academico=t.get("nivel_academico", ""),
                        estado=t.get("estado", ""),
                        universidad_codigo=u_code,
                        precio_credito_ects=t.get("precio_credito_ects"),
                        precio_estimado_anual=t.get("precio_estimado_anual"),
                        fuente_precio=t.get("fuente_precio")
                    )
                    db.add(tit_obj)
                else:
                    existing.precio_credito_ects = t.get("precio_credito_ects")
                    existing.precio_estimado_anual = t.get("precio_estimado_anual")
                    existing.fuente_precio = t.get("fuente_precio")
        db.commit()
        print(f" -> {total_tits} titulaciones vigentes migradas con éxito.")

    # 3. Migrar Planes de Estudio y Elementos Curriculares (Optimizado con Bulk Save)
    planes_dir = os.path.join(os.path.dirname(crawler_datos_dir), "planes_estudio")
    if not os.path.exists(planes_dir):
        planes_dir = os.path.join(crawler_datos_dir, "planes_estudio")
    if not os.path.exists(planes_dir):
        planes_dir = os.path.join(crawler_datos_dir, "Planes")

    if os.path.exists(planes_dir):
        plan_files = [f for f in os.listdir(planes_dir) if f.endswith(".json")]
        print(f"Migrando {len(plan_files)} planes de estudio desde '{planes_dir}'...")
        
        resumenes_bulk = []
        elementos_bulk = []

        for p_file in plan_files:
            p_path = os.path.join(planes_dir, p_file)
            with open(p_path, "r", encoding="utf-8") as f:
                p_data = json.load(f)
                
            d_code = p_data.get("codigo_estudio")
            if not d_code:
                continue
                
            # Verify degree exists and update price fields
            tit_obj = db.query(Titulacion).filter(Titulacion.codigo_estudio == d_code).first()
            if not tit_obj:
                continue

            tit_obj.precio_credito_ects = p_data.get("precio_credito_ects")
            tit_obj.precio_estimado_anual = p_data.get("precio_estimado_anual")
            tit_obj.fuente_precio = p_data.get("fuente_precio")
                
            boe_date_val = None
            if p_data.get("boe_fecha"):
                try:
                    boe_date_val = datetime.strptime(p_data["boe_fecha"], "%Y-%m-%d").date()
                except ValueError:
                    pass

            plan_obj = db.query(PlanEstudios).filter(PlanEstudios.codigo_estudio == d_code).first()
            if not plan_obj:
                plan_obj = PlanEstudios(
                    codigo_estudio=d_code,
                    boe_url=p_data.get("boe_url"),
                    boe_fecha=boe_date_val,
                    fecha_procesado=datetime.now()
                )
                db.add(plan_obj)
                db.flush()
            else:
                # Si el plan ya existe, actualizar metadatos y limpiar asignaturas previas para refrescar limpiamente
                plan_obj.boe_url = p_data.get("boe_url") or plan_obj.boe_url
                plan_obj.boe_fecha = boe_date_val or plan_obj.boe_fecha
                plan_obj.fecha_procesado = datetime.now()
                db.query(ResumenCreditos).filter(ResumenCreditos.plan_estudio_id == plan_obj.id).delete()
                db.query(ElementoCurricular).filter(ElementoCurricular.plan_estudio_id == plan_obj.id).delete()
            
            # Acumular en lote para inserción masiva (Bulk Save)
            pe_data = p_data.get("plan_estudios") or {}
            res_cred = pe_data.get("resumen_creditos") or {}
            for k, v in res_cred.items():
                resumenes_bulk.append(ResumenCreditos(plan_estudio_id=plan_obj.id, tipo_credito=str(k), cantidad_creditos=str(v)))
                
            elems = pe_data.get("elementos_curriculares") or []
            for elem in elems:
                elementos_bulk.append(ElementoCurricular(
                    plan_estudio_id=plan_obj.id,
                    modulo=elem.get("modulo"),
                    materia=elem.get("materia"),
                    nombre_elemento=elem.get("nombre_elemento", ""),
                    creditos_ects=elem.get("creditos_ects"),
                    caracter=elem.get("caracter"),
                    curso=elem.get("curso"),
                    cuatrimestre=elem.get("cuatrimestre")
                ))

        if resumenes_bulk:
            db.bulk_save_objects(resumenes_bulk)
        if elementos_bulk:
            db.bulk_save_objects(elementos_bulk)

        db.commit()
        print(" -> Planes de estudio y asignaturas migradas en lote con éxito.")

    # 4. Migrar Registro de Errores con Desduplicación
    err_json_path = os.path.join(crawler_datos_dir, "errores_crawler.json")
    if os.path.exists(err_json_path):
        with open(err_json_path, "r", encoding="utf-8") as f:
            err_list = json.load(f)
        for err in err_list:
            ts = None
            if err.get("timestamp"):
                try:
                    ts = datetime.fromisoformat(err["timestamp"])
                except Exception:
                    pass
            
            # Desduplicación: Verificar si ya existe este fallo
            id_ent = err.get("id_entidad")
            motivo = err.get("motivo_fallo")
            existing_err = db.query(ErrorCrawler).filter(
                ErrorCrawler.id_entidad == id_ent,
                ErrorCrawler.motivo_fallo == motivo,
                ErrorCrawler.timestamp == ts
            ).first()

            if not existing_err:
                db.add(ErrorCrawler(
                    timestamp=ts,
                    fase=err.get("fase"),
                    id_entidad=id_ent,
                    url=err.get("url"),
                    motivo_fallo=motivo,
                    detalles_excepcion=err.get("detalles_excepcion")
                ))
        db.commit()
        print(" -> Registro de errores migrado con éxito (desduplicado).")

    # 5. Migrar Estadísticas de Rendimiento con Desduplicación
    stat_json_path = os.path.join(crawler_datos_dir, "estadisticas_rendimiento.json")
    if os.path.exists(stat_json_path):
        with open(stat_json_path, "r", encoding="utf-8") as f:
            st = json.load(f)
            
        mem = st.get("rendimiento_memoria") or {}
        time_info = st.get("rendimiento_tiempo") or {}
        ops = st.get("operaciones_crawler") or {}
        
        ts_rep = None
        if st.get("timestamp_reporte"):
            try:
                ts_rep = datetime.fromisoformat(st["timestamp_reporte"])
            except Exception:
                pass
                
        # Desduplicación: Verificar si la estadística con este timestamp_reporte ya fue migrada
        existing_stat = None
        if ts_rep:
            existing_stat = db.query(EstadisticaRendimiento).filter(
                EstadisticaRendimiento.timestamp_reporte == ts_rep
            ).first()

        if not existing_stat:
            db.add(EstadisticaRendimiento(
                timestamp_reporte=ts_rep,
                uso_memoria_actual_mb=mem.get("uso_memoria_actual_mb"),
                pico_maximo_memoria_mb=mem.get("pico_maximo_memoria_mb"),
                porcentaje_uso_memoria=mem.get("porcentaje_uso_memoria_sistema"),
                tiempo_total_ejecucion_seg=time_info.get("tiempo_total_ejecucion_seg"),
                tiempo_procesamiento_cpu_seg=time_info.get("tiempo_procesamiento_cpu_seg"),
                tiempo_espera_io_red_seg=time_info.get("tiempo_espera_io_red_seg"),
                universidades_inspeccionadas=ops.get("universidades_inspeccionadas"),
                titulaciones_inspeccionadas=ops.get("titulaciones_inspeccionadas"),
                titulaciones_al_dia=ops.get("titulaciones_al_dia_sin_cambios"),
                titulaciones_actualizadas=ops.get("titulaciones_nuevas_o_actualizadas"),
                pdfs_parseados=ops.get("pdfs_boe_descargados_y_parseados"),
                errores_registrados=ops.get("errores_registrados")
            ))
            db.commit()
            print(" -> Estadísticas de rendimiento migradas con éxito (desduplicadas).")

    db.close()
    print("=" * 70)
    print("     PROCESO ETL FINALIZADO CON ÉXITO")
    print("======================================================================")

if __name__ == "__main__":
    run_etl()
