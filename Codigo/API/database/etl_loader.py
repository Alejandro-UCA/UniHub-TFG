import os
import sys
import json
import logging
import tempfile
import contextlib
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("unihub_etl")

PUBLISHABLE_PLAN_QUALITY_STATUSES = frozenset({
    "completo",
    "completo_normativo",
    "verificado_boe",
    "verificado_web",
    "verificado_universidad",
    "verificado_administracion",
    "verificado_programa_doctoral",
    "doctorado_verificado",
    "doctorado_estructural",
    "doctorado_oficial",
    "incompleto_parcial",
    "incompleto",
    "pendiente_revision",
})


def _update_if_present(instance, attribute: str, payload: dict, key: str) -> None:
    """Actualiza un campo solo cuando la fuente aporta un valor explícito."""
    if key not in payload or payload[key] is None:
        return
    if isinstance(payload[key], str) and not payload[key].strip():
        return
    setattr(instance, attribute, payload[key])


def _has_authoritative_plan_snapshot(plan_data: object, quality_status: object = None) -> bool:
    """Indica si la fuente aporta una instantánea curricular con asignaturas o créditos."""
    if not isinstance(plan_data, dict):
        return False
    if plan_data.get("tipo_estructura") == "programa_doctorado_investigacion" or "programa_doctoral" in plan_data:
        return True
    has_curriculum_key = "elementos_curriculares" in plan_data or "resumen_creditos" in plan_data
    if not has_curriculum_key:
        return False
    elems = plan_data.get("elementos_curriculares")
    res_cred = plan_data.get("resumen_creditos")
    if (elems and len(elems) > 0) or (res_cred and len(res_cred) > 0):
        return True
    return str(quality_status or "").strip().lower() in PUBLISHABLE_PLAN_QUALITY_STATUSES

# Añadir el directorio padre de la API a la ruta de importación
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from API.config import settings
    from API.database.connection import SessionAdmin, engine_admin
    from API.models.models import (
        Base,
        Universidad,
        Titulacion,
        PlanEstudios,
        ResumenCreditos,
        ElementoCurricular,
        ErrorCrawler,
        EstadisticaRendimiento
    )
except (ImportError, AttributeError):
    from config import settings
    from database.connection import SessionAdmin, engine_admin
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

@contextlib.contextmanager
def etl_lock_context():
    """
    Context manager that acquires and releases the ETL lock file atomically.
    Ensures file descriptors are cleanly closed and orphan locks are recovered.
    """
    lock_file = os.path.join(tempfile.gettempdir(), "etl_running.lock")
    acquired = False
    try:
        open_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            lock_fd = os.open(lock_file, open_flags)
            try:
                with os.fdopen(lock_fd, 'w') as f:
                    f.write(str(os.getpid()))
                acquired = True
            except OSError as cleanup_error:
                try:
                    os.close(lock_fd)
                except OSError as close_error:
                    logger.warning("No se pudo cerrar el descriptor del lock ETL: %s", close_error)
                logger.warning("No se pudo completar la escritura del lock ETL: %s", cleanup_error)
                raise
        except FileExistsError:
            try:
                with open(lock_file, "r") as _lf:
                    stale_pid = int(_lf.read().strip())
                os.kill(stale_pid, 0)
                logger.warning("[AVISO] El proceso ETL ya está en ejecución (PID activo). Abortando para evitar colisiones.")
                yield False
                return
            except (OSError, ValueError):
                logger.info("[AVISO] Se encontró un lock file huérfano. Limpiando y continuando.")
                try:
                    if os.path.exists(lock_file):
                        os.remove(lock_file)
                    lock_fd = os.open(lock_file, open_flags)
                    try:
                        with os.fdopen(lock_fd, 'w') as f:
                            f.write(str(os.getpid()))
                        acquired = True
                    except OSError as cleanup_error:
                        try:
                            os.close(lock_fd)
                        except OSError as close_error:
                            logger.warning("No se pudo cerrar el descriptor del lock ETL recreado: %s", close_error)
                        logger.warning("No se pudo completar la escritura del lock ETL recreado: %s", cleanup_error)
                        raise
                except Exception as e:
                    logger.error(f"[ERROR] No se pudo recrear el lock file de forma atómica: {e}")
                    yield False
                    return
        yield True
    finally:
        if acquired and os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception as e:
                logger.warning(f"Error al limpiar lock file: {e}")

def run_etl() -> bool:
    """
    Ejecuta el pipeline ETL de migración de datos desde los artefactos JSON de la Fase 1 a PostgreSQL (Fase 2).
    Retorna True si finalizó con éxito, False en caso de error.
    """
    with etl_lock_context() as acquired:
        if not acquired:
            return False
        
        db = None
        etl_success = False
        try:
            logger.info("INICIANDO PROCESO ETL: MIGRACIÓN DE JSON (FASE 1) A POSTGRESQL")

            # Ruta canónica al directorio de datos de la Fase 1
            crawler_datos_dir = settings.CRAWLER_DATA_DIR

            if not os.path.exists(crawler_datos_dir):
                logger.error(f"No se encontró el directorio de datos del crawler en '{crawler_datos_dir}'.")
                return False

            logger.info(f"Directorio de datos localizado en: '{crawler_datos_dir}'")

            # Configuración del motor de base de datos y creación de tablas
            logger.info("Conectando a la base de datos PostgreSQL...")
            try:
                Base.metadata.create_all(bind=engine_admin)

                # Auto-migrar columnas adicionales si la BD venía de un esquema previo
                schema_alter_queries = [
                    'ALTER TABLE universidades ADD COLUMN IF NOT EXISTS gestionado_por_admin BOOLEAN DEFAULT FALSE;',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_credito_2 NUMERIC(6,2);',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_credito_3 NUMERIC(6,2);',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_credito_4 NUMERIC(6,2);',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS precio_estimado_anual NUMERIC(8,2);',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS fuente_precio VARCHAR(255);',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS centro_adscrito TEXT;',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS es_alianza_europea BOOLEAN NOT NULL DEFAULT FALSE;',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS web_fuente_directa_url TEXT;',
                    'ALTER TABLE titulaciones ADD COLUMN IF NOT EXISTS gestionado_por_admin BOOLEAN DEFAULT FALSE;',
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS origen_fuente VARCHAR(100);',
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS pdf_sha256 VARCHAR(64);',
                    "ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS estado_calidad VARCHAR(64) NOT NULL DEFAULT 'pendiente_revision';",
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS motivos_calidad JSONB;',
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS fuente_verificada_url TEXT;',
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS verificado_en TIMESTAMP;',
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS tipo_estructura VARCHAR(100);',
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS ects_exigidos TEXT;',
                    'ALTER TABLE planes_estudio ADD COLUMN IF NOT EXISTS programa_doctoral JSONB;',
                    'CREATE INDEX IF NOT EXISTS idx_planes_estado_calidad ON planes_estudio(estado_calidad);',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS tipo_asistencia VARCHAR(50);',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS calificacion_minima NUMERIC(4,2);',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS departamento VARCHAR(255);',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS url_guia_docente TEXT;',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS temario JSONB;',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS sistema_evaluacion JSONB;',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS profesorado JSONB;',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS bibliografia JSONB;',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS idioma VARCHAR(50);',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS creditos_teoria NUMERIC(4,2);',
                    'ALTER TABLE elementos_curriculares ADD COLUMN IF NOT EXISTS creditos_practica NUMERIC(4,2);'
                ]
                with engine_admin.connect() as _conn:
                    for _q in schema_alter_queries:
                        try:
                            _conn.execute(text(_q))
                        except Exception as alt_err:
                            logger.debug(f"Migración preventiva de columna omitida: {_q} ({alt_err})")
                    _conn.commit()

                db = SessionAdmin()
            except Exception as e:
                logger.error(f"No se pudo conectar a PostgreSQL: {e}. Asegúrate de que PostgreSQL está iniciado.")
                return False

            # 1. Migrar Universidades
            univ_json_path = os.path.join(crawler_datos_dir, "universidades_list.json")
            if not os.path.exists(univ_json_path):
                univ_json_path = os.path.join(crawler_datos_dir, "universidades.json")

            if os.path.exists(univ_json_path):
                with open(univ_json_path, "r", encoding="utf-8") as f:
                    univ_list = json.load(f)

                logger.info(f"Migrando {len(univ_list)} universidades a PostgreSQL...")

                # Optimización: Cargar todas las universidades en memoria para evitar N+1 queries
                existing_univs = {u.codigo: u for u in db.query(Universidad).all()}

                for u in univ_list:
                    code = str(u.get("codigo", "")).strip().zfill(3)
                    if not code:
                        continue
                    nombre = str(u.get("nombre") or "").strip() or ("Otras Instituciones y Títulos Oficiales" if code == "000" else "")
                    if not nombre:
                        logger.error("Universidad %s omitida: falta el nombre en la fuente.", code)
                        continue
                    existing = existing_univs.get(code) or existing_univs.get(str(u.get("codigo", "")).strip())
                    if not existing:
                        univ_obj = Universidad(
                            codigo=code,
                            nombre=nombre,
                            tipo=u.get("tipo"),
                            comunidad_autonoma=u.get("comunidad_autonoma", ""),
                            municipio=u.get("municipio", ""),
                            provincia=u.get("provincia", ""),
                            web=u.get("web", ""),
                            email=u.get("email", ""),
                            telefono=u.get("telefono", "")
                        )
                        db.add(univ_obj)
                        existing_univs[code] = univ_obj
                db.flush()
                logger.info("Universidades migradas con éxito.")

            # 2. Migrar Titulaciones
            tit_json_path = os.path.join(crawler_datos_dir, "titulaciones_universidad.json")
            if os.path.exists(tit_json_path):
                with open(tit_json_path, "r", encoding="utf-8") as f:
                    tit_data = json.load(f)

                active_titulaciones_codes = set()
                total_tits = 0

                # Optimización: Cargar todas las titulaciones en memoria para evitar N+1 queries
                logger.info("Cargando titulaciones existentes en memoria para optimizar...")
                existing_tits = {t.codigo_estudio: t for t in db.query(Titulacion).all()}

                for u_code, u_info in tit_data.items():
                    normalized_u_code = str(u_code).strip().zfill(3)
                    vigentes = u_info.get("titulaciones_vigentes", [])
                    total_tits += len(vigentes)
                    for t in vigentes:
                        d_code = str(t.get("codigo_estudio", "")).strip()
                        if not d_code:
                            continue
                        active_titulaciones_codes.add(d_code)
                        existing = existing_tits.get(d_code)
                        if not existing:
                            tit_obj = Titulacion(
                                codigo_estudio=d_code,
                                titulo=t.get("titulo") or f"Titulación {d_code}",
                                nivel_academico=t.get("nivel_academico", ""),
                                estado=t.get("estado", ""),
                                universidad_codigo=normalized_u_code,
                                precio_credito_ects=t.get("precio_credito_ects"),
                                precio_credito_2=t.get("precio_credito_2"),
                                precio_credito_3=t.get("precio_credito_3"),
                                precio_credito_4=t.get("precio_credito_4"),
                                precio_estimado_anual=t.get("precio_estimado_anual"),
                                fuente_precio=t.get("fuente_precio"),
                                centro_adscrito=t.get("centro_adscrito"),
                                es_alianza_europea=bool(t.get("es_alianza_europea", False)),
                                web_fuente_directa_url=t.get("web_fuente_directa_url"),
                            )
                            db.add(tit_obj)
                            existing_tits[d_code] = tit_obj
                        else:
                            if not existing.gestionado_por_admin:
                                existing.titulo = t.get("titulo") or existing.titulo
                                _update_if_present(existing, "nivel_academico", t, "nivel_academico")
                                _update_if_present(existing, "estado", t, "estado")
                                _update_if_present(existing, "precio_credito_ects", t, "precio_credito_ects")
                                _update_if_present(existing, "precio_credito_2", t, "precio_credito_2")
                                _update_if_present(existing, "precio_credito_3", t, "precio_credito_3")
                                _update_if_present(existing, "precio_credito_4", t, "precio_credito_4")
                                _update_if_present(existing, "precio_estimado_anual", t, "precio_estimado_anual")
                                _update_if_present(existing, "fuente_precio", t, "fuente_precio")
                                _update_if_present(existing, "centro_adscrito", t, "centro_adscrito")
                                _update_if_present(existing, "es_alianza_europea", t, "es_alianza_europea")
                                _update_if_present(existing, "web_fuente_directa_url", t, "web_fuente_directa_url")

                # Las eliminaciones son destructivas y el JSON no contiene por sí
                # solo una prueba de cobertura completa. Requieren opt-in explícito.
                deleted_count = 0
                allow_deletions = os.getenv("ETL_ALLOW_DELETIONS", "false").lower() == "true"
                if allow_deletions and active_titulaciones_codes and len(active_titulaciones_codes) >= 100:
                    deleted_count = db.query(Titulacion).filter(
                        ~Titulacion.codigo_estudio.in_(active_titulaciones_codes),
                        Titulacion.gestionado_por_admin == False
                    ).delete(synchronize_session=False)
                elif active_titulaciones_codes:
                    logger.warning(
                        "Se omiten eliminaciones ETL: requieren ETL_ALLOW_DELETIONS=true "
                        "y una validación de cobertura independiente."
                    )

                db.flush()
                logger.info(f"{total_tits} titulaciones vigentes migradas con éxito. {deleted_count} titulaciones extintas borradas.")

            # 3. Migrar Planes de Estudio y Elementos Curriculares (Optimizado con Bulk Save)
            possible_planes_dirs = [
                os.path.join(crawler_datos_dir, "planes"),
                os.path.join(crawler_datos_dir, "planes_estudio"),
                os.path.join(crawler_datos_dir, "Planes"),
                os.path.join(os.path.dirname(crawler_datos_dir), "data", "planes_estudio"),
                os.path.join(os.path.dirname(crawler_datos_dir), "planes_estudio")
            ]
            planes_dir = None
            for p_dir in possible_planes_dirs:
                if os.path.exists(p_dir) and os.path.isdir(p_dir):
                    planes_dir = p_dir
                    break

            if planes_dir and os.path.exists(planes_dir):
                # Descubrir archivos de plan ordenados
                plan_files_by_code = {}
                for root, _, filenames in os.walk(planes_dir):
                    parent_name = os.path.basename(root)
                    inferred_univ = parent_name.zfill(3) if parent_name.isdigit() else ""
                    for filename in filenames:
                        if not filename.endswith(".json"):
                            continue
                        candidate = os.path.join(root, filename)
                        code = os.path.splitext(filename)[0]
                        key = (inferred_univ, code)
                        previous = plan_files_by_code.get(key)
                        if previous is None or candidate.count(os.sep) > previous.count(os.sep):
                            plan_files_by_code[key] = candidate

                plan_files = [plan_files_by_code[key] for key in sorted(plan_files_by_code)]
                logger.info(f"Migrando {len(plan_files)} planes de estudio desde '{planes_dir}'...")

                resumenes_bulk = []
                elementos_bulk = []

                # Optimización: Cargar todos los planes, titulaciones y universidades en memoria
                existing_plans_dict = {p.codigo_estudio: p for p in db.query(PlanEstudios).all()}
                existing_tits_dict = {t.codigo_estudio: t for t in db.query(Titulacion).all()}
                existing_univs_dict = {u.codigo: u for u in db.query(Universidad).all()}

                for idx, p_path in enumerate(plan_files, 1):
                    try:
                        with open(p_path, "r", encoding="utf-8") as f:
                            p_data = json.load(f)
                    except Exception as err:
                        logger.warning(f"Error al leer {p_path}: {err}")
                        continue

                    d_code = str(p_data.get("codigo_estudio") or "").strip()
                    if not d_code:
                        continue

                    # Verify degree exists or auto-create if missing
                    tit_obj = existing_tits_dict.get(d_code)
                    if not tit_obj:
                        univ_code = str(p_data.get("universidad_codigo", "000")).strip().zfill(3)
                        univ_obj = existing_univs_dict.get(univ_code)
                        if not univ_obj:
                            univ_name = str(p_data.get("universidad_nombre") or "").strip()
                            if not univ_name:
                                logger.error(
                                    "Plan %s omitido: no existe la universidad %s y falta su nombre.",
                                    d_code,
                                    univ_code,
                                )
                                continue
                            univ_obj = Universidad(
                                codigo=univ_code,
                                nombre=univ_name,
                                tipo=p_data.get("tipo")
                            )
                            db.add(univ_obj)
                            db.flush()
                            existing_univs_dict[univ_code] = univ_obj

                        degree_title = str(p_data.get("titulo") or "").strip()
                        if not degree_title:
                            logger.error(
                                "Plan %s omitido: falta el título de la titulación y no se generará un nombre sintético.",
                                d_code,
                            )
                            continue

                        tit_obj = Titulacion(
                            codigo_estudio=d_code,
                            titulo=degree_title,
                            nivel_academico=p_data.get("nivel_academico", ""),
                            estado=p_data.get("estado"),
                            universidad_codigo=univ_code,
                            precio_credito_ects=p_data.get("precio_credito_ects"),
                            precio_credito_2=p_data.get("precio_credito_2"),
                            precio_credito_3=p_data.get("precio_credito_3"),
                            precio_credito_4=p_data.get("precio_credito_4"),
                            precio_estimado_anual=p_data.get("precio_estimado_anual"),
                            fuente_precio=p_data.get("fuente_precio"),
                            centro_adscrito=p_data.get("centro_adscrito"),
                            es_alianza_europea=bool(p_data.get("es_alianza_europea", False)),
                            web_fuente_directa_url=p_data.get("web_fuente_directa_url"),
                        )
                        db.add(tit_obj)
                        db.flush()
                        existing_tits_dict[d_code] = tit_obj
                    else:
                        _update_if_present(tit_obj, "precio_credito_ects", p_data, "precio_credito_ects")
                        _update_if_present(tit_obj, "precio_credito_2", p_data, "precio_credito_2")
                        _update_if_present(tit_obj, "precio_credito_3", p_data, "precio_credito_3")
                        _update_if_present(tit_obj, "precio_credito_4", p_data, "precio_credito_4")
                        _update_if_present(tit_obj, "precio_estimado_anual", p_data, "precio_estimado_anual")
                        _update_if_present(tit_obj, "fuente_precio", p_data, "fuente_precio")
                        _update_if_present(tit_obj, "centro_adscrito", p_data, "centro_adscrito")
                        _update_if_present(tit_obj, "es_alianza_europea", p_data, "es_alianza_europea")
                        _update_if_present(tit_obj, "web_fuente_directa_url", p_data, "web_fuente_directa_url")

                    boe_date_val = None
                    if p_data.get("boe_fecha"):
                        try:
                            boe_date_val = datetime.strptime(str(p_data["boe_fecha"]).strip()[:10], "%Y-%m-%d").date()
                        except ValueError:
                            pass

                    raw_plan_data = p_data.get("plan_estudios")
                    quality_status = str(p_data.get("estado_calidad") or "").strip().lower()
                    has_plan_snapshot = _has_authoritative_plan_snapshot(raw_plan_data, quality_status)
                    quality_metadata = p_data.get("calidad_datos") if isinstance(p_data.get("calidad_datos"), dict) else None
                    plan_obj = existing_plans_dict.get(d_code)
                    if not plan_obj:
                        plan_obj = PlanEstudios(
                            codigo_estudio=d_code,
                            boe_url=p_data.get("boe_url") if has_plan_snapshot else None,
                            boe_fecha=boe_date_val if has_plan_snapshot else None,
                            origen_fuente=p_data.get("origen_fuente") if has_plan_snapshot else None,
                            pdf_sha256=p_data.get("pdf_sha256") if has_plan_snapshot else None,
                            estado_calidad=quality_status or "sin_datos_verificados",
                            motivos_calidad=quality_metadata,
                            fuente_verificada_url=(quality_metadata or {}).get("fuente_url") if has_plan_snapshot else None,
                            verificado_en=datetime.now() if has_plan_snapshot else None,
                            fecha_procesado=datetime.now(),
                            tipo_estructura=raw_plan_data.get("tipo_estructura") if has_plan_snapshot else None,
                            ects_exigidos=str(raw_plan_data.get("ects_exigidos")) if has_plan_snapshot and raw_plan_data.get("ects_exigidos") is not None else None,
                            programa_doctoral=p_data.get("programa_doctoral") if has_plan_snapshot else None,
                        )
                        db.add(plan_obj)
                        db.flush()
                        existing_plans_dict[d_code] = plan_obj
                    else:
                        if has_plan_snapshot:
                            plan_obj.boe_url = p_data.get("boe_url") or plan_obj.boe_url
                            plan_obj.boe_fecha = boe_date_val or plan_obj.boe_fecha
                            plan_obj.origen_fuente = p_data.get("origen_fuente") or plan_obj.origen_fuente
                            plan_obj.pdf_sha256 = p_data.get("pdf_sha256") or plan_obj.pdf_sha256
                            plan_obj.estado_calidad = quality_status
                            plan_obj.motivos_calidad = quality_metadata
                            plan_obj.fuente_verificada_url = (quality_metadata or {}).get("fuente_url")
                            plan_obj.verificado_en = datetime.now()
                            plan_obj.fecha_procesado = datetime.now()
                            plan_obj.tipo_estructura = raw_plan_data.get("tipo_estructura") or plan_obj.tipo_estructura
                            if p_data.get("programa_doctoral"):
                                plan_obj.programa_doctoral = p_data.get("programa_doctoral")
                            required_ects = raw_plan_data.get("ects_exigidos")
                            if required_ects is not None:
                                plan_obj.ects_exigidos = str(required_ects)
                            db.query(ResumenCreditos).filter(ResumenCreditos.plan_estudio_id == plan_obj.id).delete()
                            db.query(ElementoCurricular).filter(ElementoCurricular.plan_estudio_id == plan_obj.id).delete()
                        else:
                            if plan_obj.estado_calidad not in PUBLISHABLE_PLAN_QUALITY_STATUSES:
                                plan_obj.estado_calidad = quality_status or "sin_datos_verificados"
                                plan_obj.motivos_calidad = quality_metadata
                            logger.warning(
                                "Plan %s sin instantánea curricular publicable; se conservan los datos existentes.",
                                d_code,
                            )

                    # Acumular en lote para inserción masiva
                    pe_data = raw_plan_data if has_plan_snapshot else {}
                    res_cred = pe_data.get("resumen_creditos") or {}
                    for k, v in res_cred.items():
                        resumenes_bulk.append(ResumenCreditos(plan_estudio_id=plan_obj.id, tipo_credito=str(k), cantidad_creditos=str(v)))

                    elems = pe_data.get("elementos_curriculares") or []
                    for elem in elems:
                        guia_info = elem.get("guia_docente") or {}
                        cr_teoria = None
                        cr_practica = None
                        if guia_info.get("creditos"):
                            cr_teoria = guia_info["creditos"].get("teoria")
                            cr_practica = guia_info["creditos"].get("practicas")

                        sub_name = elem.get("nombre_elemento") or elem.get("materia") or "Materia sin especificar"

                        elementos_bulk.append(ElementoCurricular(
                            plan_estudio_id=plan_obj.id,
                            modulo=elem.get("modulo"),
                            materia=elem.get("materia"),
                            nombre_elemento=sub_name.strip() if isinstance(sub_name, str) else str(sub_name),
                            creditos_ects=elem.get("creditos_ects"),
                            caracter=elem.get("caracter"),
                            curso=elem.get("curso"),
                            cuatrimestre=elem.get("cuatrimestre"),
                            url_guia_docente=elem.get("url_guia_docente") or guia_info.get("url_guia_docente"),
                            temario=guia_info.get("temario") or elem.get("temario"),
                            sistema_evaluacion=guia_info.get("sistema_evaluacion") or elem.get("sistema_evaluacion"),
                            profesorado=guia_info.get("profesorado") or elem.get("profesorado"),
                            bibliografia=guia_info.get("bibliografia") or elem.get("bibliografia"),
                            idioma=guia_info.get("idioma") or elem.get("idioma"),
                            creditos_teoria=cr_teoria,
                            creditos_practica=cr_practica,
                            tipo_asistencia=elem.get("tipo_asistencia") or guia_info.get("tipo_asistencia"),
                            calificacion_minima=elem.get("calificacion_minima") or guia_info.get("calificacion_minima"),
                            departamento=elem.get("departamento") or guia_info.get("departamento")
                        ))

                    # Guardado por lotes periódicos para optimizar memoria
                    if len(elementos_bulk) >= 2000 or (idx % 200 == 0):
                        if resumenes_bulk:
                            db.bulk_save_objects(resumenes_bulk)
                            resumenes_bulk.clear()
                        if elementos_bulk:
                            db.bulk_save_objects(elementos_bulk)
                            elementos_bulk.clear()
                        db.flush()

                if resumenes_bulk:
                    db.bulk_save_objects(resumenes_bulk)
                if elementos_bulk:
                    db.bulk_save_objects(elementos_bulk)

                db.flush()
                logger.info("Planes de estudio y asignaturas migradas en lote con éxito.")

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
                        except ValueError as parse_error:
                            logger.warning("Timestamp de error crawler inválido: %r (%s)", err.get("timestamp"), parse_error)

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
                db.flush()
                logger.info("Registro de errores migrado con éxito (desduplicado).")

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
                    except ValueError as parse_error:
                        logger.warning("Timestamp de estadísticas inválido: %r (%s)", st.get("timestamp_reporte"), parse_error)

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
                    db.flush()
                    logger.info("Estadísticas de rendimiento migradas con éxito (desduplicadas).")
            # Publicar todo el snapshot en una sola transacción de sesión.
            db.commit()
            etl_success = True

        except Exception as e:
            etl_success = False
            logger.error(f"Excepción no controlada en proceso ETL: {e}")
            if db is not None:
                try:
                    db.rollback()
                except Exception as rollback_error:
                    logger.error("No se pudo hacer rollback de la ETL: %s", rollback_error, exc_info=True)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as close_error:
                    logger.error("No se pudo cerrar la sesión de la ETL: %s", close_error, exc_info=True)
            if etl_success:
                logger.info("PROCESO ETL FINALIZADO CON ÉXITO")
            else:
                logger.warning("PROCESO ETL FINALIZADO CON INCIDENCIAS O ERRORES")
        return etl_success

if __name__ == "__main__":
    run_etl()
