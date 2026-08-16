import os
import sys
import json
import tempfile
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Añadir el directorio padre de la API a la ruta de importación
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
    lock_file = os.path.join(tempfile.gettempdir(), "etl_running.lock")
    if os.path.exists(lock_file):
        # Check if the PID in the lock file is still alive.
        # If the container crashed previously the lock may be stale and must be removed.
        try:
            with open(lock_file, "r") as _lf:
                stale_pid = int(_lf.read().strip())
            os.kill(stale_pid, 0)  # Raises OSError if process does not exist
            print("[AVISO] El proceso ETL ya está en ejecución (PID activo). Abortando para evitar colisiones.")
            return
        except (OSError, ValueError):
            print("[AVISO] Se encontró un lock file huérfano (proceso anterior terminó de forma abrupta). Limpiando y continuando.")
            try:
                os.remove(lock_file)
            except Exception:
                pass
        
    db = None
    try:
        # Create lock file
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
            
        print("=" * 70)
        print("     INICIANDO PROCESO ETL: MIGRACIÓN DE JSON (FASE 1) A POSTGRESQL")
        print("======================================================================")
        
        # Ruta al directorio de datos de la Fase 1 (Comprobar primero la ruta Docker /app/Datos, fallback a ruta local)
        base_api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        crawler_datos_dir = "/app/Datos"
        if not os.path.exists(crawler_datos_dir):
            crawler_datos_dir = os.path.join(os.path.dirname(base_api_dir), "Crawler", "Datos")
    
        if not os.path.exists(crawler_datos_dir):
            print(f"[ERROR] No se encontró el directorio de datos del crawler en '{crawler_datos_dir}'.")
            return

        print(f"Directorio de datos localizado en: '{crawler_datos_dir}'")

        # Configuración del motor de base de datos y creación de tablas
        print("Conectando a la base de datos PostgreSQL...")
        try:
            from database.connection import SessionAdmin, engine_admin
            from sqlalchemy import text
            Base.metadata.create_all(bind=engine_admin)
            
            # Auto-migrar columnas adicionales si la BD venía de un esquema previo
            schema_alter_queries = [
                'ALTER TABLE universidades ADD COLUMN IF NOT EXISTS gestionado_por_admin BOOLEAN DEFAULT FALSE;',
                'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_credito_2 NUMERIC(6,2);',
                'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_credito_3 NUMERIC(6,2);',
                'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_credito_4 NUMERIC(6,2);',
                'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_estimado_anual NUMERIC(8,2);',
                'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS fuente_precio VARCHAR(100);',
                'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS gestionado_por_admin BOOLEAN DEFAULT FALSE;',
                'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS origen_fuente VARCHAR(100);',
                'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS pdf_sha256 VARCHAR(64);',
                'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS tipo_asistencia VARCHAR(50);',
                'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS calificacion_minima NUMERIC(4,2);',
                'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS departamento VARCHAR(255);'
            ]
            with engine_admin.connect() as _conn:
                for _q in schema_alter_queries:
                    try:
                        _conn.execute(text(_q))
                    except Exception:
                        pass
                _conn.commit()

            db = SessionAdmin()
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
            
            # Optimizacion: Cargar todas las universidades en memoria para evitar N+1 queries
            existing_univs = {u.codigo: u for u in db.query(Universidad).all()}
            
            for u in univ_list:
                code = u.get("codigo")
                existing = existing_univs.get(code)
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
                
            active_titulaciones_codes = set()
            total_tits = 0
            
            # Optimizacion: Cargar todas las titulaciones en memoria para evitar N+1 queries
            print(f"Cargando titulaciones existentes en memoria para optimizar...")
            existing_tits = {t.codigo_estudio: t for t in db.query(Titulacion).all()}
            
            for u_code, u_info in tit_data.items():
                vigentes = u_info.get("titulaciones_vigentes", [])
                total_tits += len(vigentes)
                for t in vigentes:
                    d_code = t.get("codigo_estudio")
                    if not d_code:
                        continue
                    active_titulaciones_codes.add(d_code)
                    existing = existing_tits.get(d_code)
                    if not existing:
                        tit_obj = Titulacion(
                            codigo_estudio=d_code,
                            titulo=t.get("titulo", ""),
                            nivel_academico=t.get("nivel_academico", ""),
                            estado=t.get("estado", ""),
                            universidad_codigo=u_code,
                            precio_credito_ects=t.get("precio_credito_ects"),
                            precio_credito_2=t.get("precio_credito_2"),
                            precio_credito_3=t.get("precio_credito_3"),
                            precio_credito_4=t.get("precio_credito_4"),
                            precio_estimado_anual=t.get("precio_estimado_anual"),
                            fuente_precio=t.get("fuente_precio")
                        )
                        db.add(tit_obj)
                        existing_tits[d_code] = tit_obj
                    else:
                        if not existing.gestionado_por_admin:
                            existing.titulo = t.get("titulo") or existing.titulo
                            existing.nivel_academico = t.get("nivel_academico")
                            existing.estado = t.get("estado")
                            existing.precio_credito_ects = t.get("precio_credito_ects") or existing.precio_credito_ects
                            existing.precio_credito_2 = t.get("precio_credito_2") or existing.precio_credito_2
                            existing.precio_credito_3 = t.get("precio_credito_3") or existing.precio_credito_3
                            existing.precio_credito_4 = t.get("precio_credito_4") or existing.precio_credito_4
                            existing.precio_estimado_anual = t.get("precio_estimado_anual") or existing.precio_estimado_anual
                            existing.fuente_precio = t.get("fuente_precio") or existing.fuente_precio
            
            # Eliminar las titulaciones en BD que ya no están vigentes en el JSON (solo si el conjunto es representativo)
            deleted_count = 0
            if active_titulaciones_codes and len(active_titulaciones_codes) >= 100:
                deleted_count = db.query(Titulacion).filter(
                    ~Titulacion.codigo_estudio.in_(active_titulaciones_codes),
                    Titulacion.gestionado_por_admin == False
                ).delete(synchronize_session=False)

            db.commit()
            print(f" -> {total_tits} titulaciones vigentes migradas con éxito. {deleted_count} titulaciones extintas borradas.")

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
            
            # Optimizacion: Cargar todos los planes y titulaciones en memoria para evitar N+1
            existing_plans_dict = {p.codigo_estudio: p for p in db.query(PlanEstudios).all()}
            existing_tits_dict = {t.codigo_estudio: t for t in db.query(Titulacion).all()}
            existing_univs_dict = {u.codigo: u for u in db.query(Universidad).all()}

            for p_file in plan_files:
                p_path = os.path.join(planes_dir, p_file)
                with open(p_path, "r", encoding="utf-8") as f:
                    p_data = json.load(f)
                    
                d_code = p_data.get("codigo_estudio")
                if not d_code:
                    continue
                    
                # Verify degree exists or auto-create if missing
                tit_obj = existing_tits_dict.get(d_code)
                if not tit_obj:
                    univ_code = str(p_data.get("universidad_codigo", "000")).zfill(3)
                    univ_obj = existing_univs_dict.get(univ_code)
                    if not univ_obj:
                        univ_obj = Universidad(
                            codigo=univ_code,
                            nombre=p_data.get("universidad_nombre", f"Universidad {univ_code}"),
                            tipo=p_data.get("tipo", "Desconocido")
                        )
                        db.add(univ_obj)
                        db.flush()
                        existing_univs_dict[univ_code] = univ_obj

                    tit_obj = Titulacion(
                        codigo_estudio=d_code,
                        titulo=p_data.get("titulo", f"Estudio {d_code}"),
                        nivel_academico=p_data.get("nivel_academico", ""),
                        estado=p_data.get("estado"),
                        universidad_codigo=p_data.get("universidad_codigo"),
                        precio_credito_ects=p_data.get("precio_credito_ects"),
                        precio_credito_2=p_data.get("precio_credito_2"),
                        precio_credito_3=p_data.get("precio_credito_3"),
                        precio_credito_4=p_data.get("precio_credito_4"),
                        precio_estimado_anual=p_data.get("precio_estimado_anual"),
                        fuente_precio=p_data.get("fuente_precio")
                    )
                    db.add(tit_obj)
                    db.flush()
                    existing_tits_dict[d_code] = tit_obj
                else:
                    # Update existing titulacion if it was created during RUCT phase without prices
                    tit_obj.precio_credito_ects = p_data.get("precio_credito_ects") or tit_obj.precio_credito_ects
                    tit_obj.precio_credito_2 = p_data.get("precio_credito_2") or tit_obj.precio_credito_2
                    tit_obj.precio_credito_3 = p_data.get("precio_credito_3") or tit_obj.precio_credito_3
                    tit_obj.precio_credito_4 = p_data.get("precio_credito_4") or tit_obj.precio_credito_4
                    tit_obj.precio_estimado_anual = p_data.get("precio_estimado_anual") or tit_obj.precio_estimado_anual
                    tit_obj.fuente_precio = p_data.get("fuente_precio") or tit_obj.fuente_precio
                    
                boe_date_val = None
                if p_data.get("boe_fecha"):
                    try:
                        boe_date_val = datetime.strptime(p_data["boe_fecha"], "%Y-%m-%d").date()
                    except ValueError:
                        pass

                plan_obj = existing_plans_dict.get(d_code)
                if not plan_obj:
                    plan_obj = PlanEstudios(
                        codigo_estudio=d_code,
                        boe_url=p_data.get("boe_url"),
                        boe_fecha=boe_date_val,
                        origen_fuente=p_data.get("origen_fuente"),
                        pdf_sha256=p_data.get("pdf_sha256"),
                        fecha_procesado=datetime.now()
                    )
                    db.add(plan_obj)
                    db.flush()
                    existing_plans_dict[d_code] = plan_obj
                else:
                    # Si el plan ya existe, actualizar metadatos y limpiar asignaturas previas para refrescar limpiamente
                    plan_obj.boe_url = p_data.get("boe_url") or plan_obj.boe_url
                    plan_obj.boe_fecha = boe_date_val or plan_obj.boe_fecha
                    plan_obj.origen_fuente = p_data.get("origen_fuente") or plan_obj.origen_fuente
                    plan_obj.pdf_sha256 = p_data.get("pdf_sha256") or plan_obj.pdf_sha256
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

    except Exception as e:
        print(f"\n[ERROR FATAL ETL] Excepción no controlada: {e}")
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
            
    print("=" * 70)
    print("     PROCESO ETL FINALIZADO CON ÉXITO")
    print("======================================================================")

if __name__ == "__main__":
    run_etl()
