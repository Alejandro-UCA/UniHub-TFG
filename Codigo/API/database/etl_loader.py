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
    
    # Path to Phase 1 data directory
    base_api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    crawler_datos_dir = os.path.join(os.path.dirname(base_api_dir), "Crawler", "Datos")
    
    if not os.path.exists(crawler_datos_dir):
        print(f"[ERROR] No se encontró el directorio de datos del crawler en '{crawler_datos_dir}'.")
        return

    # Database engine and tables setup
    print("Conectando a la base de datos PostgreSQL...")
    try:
        engine = create_engine(settings.DATABASE_URL)
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a PostgreSQL: {e}")
        print("Asegúrate de que PostgreSQL está iniciado y las credenciales en config.py / .env son correctas.")
        return

    # 1. Migrar Universidades
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
                        universidad_codigo=u_code
                    )
                    db.add(tit_obj)
        db.commit()
        print(f" -> {total_tits} titulaciones vigentes migradas con éxito.")

    # 3. Migrar Planes de Estudio y Elementos Curriculares
    planes_dir = os.path.join(crawler_datos_dir, "planes_estudio")
    if os.path.exists(planes_dir):
        plan_files = [f for f in os.listdir(planes_dir) if f.endswith(".json")]
        print(f"Migrando {len(plan_files)} planes de estudio en PDF...")
        
        for p_file in plan_files:
            p_path = os.path.join(planes_dir, p_file)
            with open(p_path, "r", encoding="utf-8") as f:
                p_data = json.load(f)
                
            d_code = p_data.get("codigo_estudio")
            if not d_code:
                continue
                
            # Verify degree exists
            tit_obj = db.query(Titulacion).filter(Titulacion.codigo_estudio == d_code).first()
            if not tit_obj:
                continue
                
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
            
            # Migrate credit summaries & subjects
            pe_data = p_data.get("plan_estudios") or {}
            res_cred = pe_data.get("resumen_creditos") or {}
            for k, v in res_cred.items():
                db.add(ResumenCreditos(plan_estudio_id=plan_obj.id, tipo_credito=str(k), cantidad_creditos=str(v)))
                
            elems = pe_data.get("elementos_curriculares") or []
            for elem in elems:
                db.add(ElementoCurricular(
                    plan_estudio_id=plan_obj.id,
                    modulo=elem.get("modulo"),
                    materia=elem.get("materia"),
                    nombre_elemento=elem.get("nombre_elemento", ""),
                    creditos_ects=elem.get("creditos_ects"),
                    caracter=elem.get("caracter"),
                    curso=elem.get("curso"),
                    cuatrimestre=elem.get("cuatrimestre")
                ))
        db.commit()
        print(" -> Planes de estudio y asignaturas migradas con éxito.")

    # 4. Migrar Registro de Errores
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
            db.add(ErrorCrawler(
                timestamp=ts,
                fase=err.get("fase"),
                id_entidad=err.get("id_entidad"),
                url=err.get("url"),
                motivo_fallo=err.get("motivo_fallo"),
                detalles_excepcion=err.get("detalles_excepcion")
            ))
        db.commit()
        print(" -> Registro de errores migrado con éxito.")

    # 5. Migrar Estadísticas de Rendimiento
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
        print(" -> Estadísticas de rendimiento migradas con éxito.")

    db.close()
    print("=" * 70)
    print("     PROCESO ETL FINALIZADO CON ÉXITO")
    print("======================================================================")

if __name__ == "__main__":
    run_etl()
