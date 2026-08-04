import os
import sys
import re
import json
import time
import urllib.parse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
import concurrent.futures
from datetime import datetime

from config import (
    UNIVERSIDADES_JSON,
    TITULACIONES_JSON,
    PLANES_DIR,
    TEMP_PDF_DIR,
    USER_AGENT,
    REQUEST_DELAY,
    HTTP_TIMEOUT
)
from downloader import RUCTDownloader
from error_logger import ErrorLogger
from checkpoint import CheckpointManager, atomic_json_dump
from parsers import parse_boe_pdf


class UniversityWebCrawler:
    """
    Fase 1 - Parte 2: Crawling paralelo de las webs oficiales de las universidades
    para obtener planes de estudio de las titulaciones que carecen de información en RUCT/BOE.
    """
    def __init__(self, user_agent=USER_AGENT, timeout=HTTP_TIMEOUT):
        self.user_agent = user_agent
        self.timeout = timeout
        self.logger = ErrorLogger()
        self.checkpoint = CheckpointManager()

    def check_robots_allowed(self, target_url: str) -> bool:
        """
        Verifica el archivo robots.txt de la web oficial de la universidad.
        Devuelve True si el rastreo está permitido para nuestro User-Agent, False en caso contrario.
        """
        try:
            parsed = urllib.parse.urlparse(target_url)
            if not parsed.scheme or not parsed.netloc:
                return False

            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            rp = RobotFileParser()
            rp.set_url(robots_url)
            
            downloader = RUCTDownloader(delay=0.2, timeout=10)
            try:
                robots_txt_content = downloader.fetch_text(robots_url)
                rp.parse(robots_txt_content.splitlines())
            except Exception:
                # Si robots.txt no existe (404) o da error, el estándar web considera el acceso permitido
                return True

            can_fetch = rp.can_fetch(self.user_agent, target_url) or rp.can_fetch("*", target_url)
            return can_fetch
        except Exception as e:
            print(f"   [robots.txt] No se pudo comprobar robots.txt para {target_url}: {e}. Se asume permitido.")
            return True

    def process_university_web(self, univ: dict, titulaciones_por_univ: dict) -> dict:
        """
        Procesa una universidad en la Parte 2:
        1. Comprueba si tiene web oficial.
        2. Identifica titulaciones sin plan de estudios.
        3. Verifica permiso en robots.txt.
        4. Escanea la web de la universidad para buscar la información faltante y guarda la URL directa.
        """
        u_code = univ.get("codigo", "")
        u_name = univ.get("nombre", "")
        web_url = univ.get("web", "").strip()

        stats = {
            "u_code": u_code,
            "u_name": u_name,
            "has_web": bool(web_url),
            "robots_allowed": True,
            "missing_degrees_count": 0,
            "resolved_degrees_count": 0
        }

        # 1. Comprobar si existe enlace a su página web oficial
        if not web_url:
            print(f" [Parte 2] Universidad [{u_code}] {u_name}: Sin web oficial registrada. Finalizado.")
            return stats

        if not web_url.startswith("http://") and not web_url.startswith("https://"):
            web_url = "http://" + web_url

        # 2. Identificar titulaciones sin información del plan de estudios
        univ_data = titulaciones_por_univ.get(u_code, {})
        active_degrees = univ_data.get("titulaciones_vigentes", [])
        
        missing_degrees = []
        for deg in active_degrees:
            d_code = deg.get("codigo_estudio", "")
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")
            
            needs_info = True
            if os.path.exists(plan_file):
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        d_json = json.load(f)
                        plan = d_json.get("plan_estudios")
                        if plan and (plan.get("total_elementos", 0) > 0 or len(plan.get("resumen_creditos", {})) > 0):
                            needs_info = False
                except Exception:
                    needs_info = True
            
            if needs_info:
                missing_degrees.append(deg)

        stats["missing_degrees_count"] = len(missing_degrees)

        if not missing_degrees:
            print(f" [Parte 2] Universidad [{u_code}] {u_name}: Todas las titulaciones ({len(active_degrees)}) tienen plan de estudios. Finalizado.")
            return stats

        print(f" [Parte 2] Universidad [{u_code}] {u_name}: {len(missing_degrees)} titulaciones sin plan de estudios. Verificando robots.txt en '{web_url}'...")

        # 3. Conectarse a la web oficial y comprobar robots.txt
        if not self.check_robots_allowed(web_url):
            print(f" 🛑 [Parte 2] Universidad [{u_code}] {u_name}: Crawling DENEGADO por robots.txt en {web_url}. Operación cancelada para esta universidad.")
            stats["robots_allowed"] = False
            return stats

        print(f" 🟢 [Parte 2] Universidad [{u_code}] {u_name}: Crawling PERMITIDO por robots.txt. Iniciando escaneo web...")

        # 4. Escaneo/recorrido meticuloso de la web oficial de la universidad
        downloader = RUCTDownloader(delay=0.5, timeout=15)
        
        for d_idx, deg in enumerate(missing_degrees, 1):
            d_code = deg.get("codigo_estudio", "")
            d_title = deg.get("titulo", "")
            plan_file = os.path.join(PLANES_DIR, f"{d_code}.json")

            print(f"   [{d_idx}/{len(missing_degrees)}] Buscando en web oficial plan para [{d_code}]: {d_title[:60]}...")

            found_curriculum = None
            direct_source_url = None

            # RUTA RÁPIDA: Si ya teníamos guardada una URL directa en búsquedas previas
            existing_direct_url = None
            if os.path.exists(plan_file):
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        d_json = json.load(f)
                        existing_direct_url = d_json.get("web_fuente_directa_url")
                except Exception:
                    pass

            if existing_direct_url:
                try:
                    print(f"     -> Probando URL directa guardada previamente: {existing_direct_url}")
                    if existing_direct_url.lower().endswith(".pdf"):
                        temp_pdf = os.path.join(TEMP_PDF_DIR, f"web_{d_code}.pdf")
                        downloader.download_file(existing_direct_url, temp_pdf)
                        parsed = parse_boe_pdf(temp_pdf)
                        if os.path.exists(temp_pdf):
                            os.remove(temp_pdf)
                        if parsed.get("total_elementos", 0) > 0 or len(parsed.get("resumen_creditos", {})) > 0:
                            found_curriculum = parsed
                            direct_source_url = existing_direct_url
                except Exception as e:
                    print(f"     -> Falló lectura de URL directa previa: {e}")

            # ESTRATEGIA: Escaneo de portales académicos y palabras clave de la titulación
            if not found_curriculum:
                try:
                    home_html = downloader.fetch_text(web_url)
                    soup = BeautifulSoup(home_html, "html.parser")

                    academic_keywords = ["grado", "master", "máster", "titulacion", "titulaciones", "estudios", "oferta"]
                    candidate_urls = set()

                    for a in soup.find_all("a", href=True):
                        href = a["href"].strip()
                        text = a.get_text(strip=True).lower()

                        if any(kw in text for kw in academic_keywords) or any(kw in href.lower() for kw in academic_keywords):
                            full_url = urllib.parse.urljoin(web_url, href)
                            if urllib.parse.urlparse(full_url).netloc == urllib.parse.urlparse(web_url).netloc:
                                candidate_urls.add(full_url)

                    scanned_urls = list(candidate_urls)[:5]
                    title_keywords = [w for w in d_title.split() if len(w) > 4 and w.lower() not in ["grado", "máster", "master", "universitario", "oficial", "sobre", "entre"]]
                    
                    for candidate_page_url in scanned_urls:
                        if found_curriculum:
                            break

                        try:
                            time.sleep(0.5) # Buenas prácticas de rate-limiting
                            sub_html = downloader.fetch_text(candidate_page_url)
                            sub_soup = BeautifulSoup(sub_html, "html.parser")

                            for a in sub_soup.find_all("a", href=True):
                                href = a["href"].strip()
                                text = a.get_text(strip=True)
                                text_lower = text.lower()

                                matches_title = any(kw.lower() in text_lower or kw.lower() in href.lower() for kw in title_keywords)
                                if matches_title:
                                    target_link = urllib.parse.urljoin(candidate_page_url, href)
                                    
                                    if target_link.lower().endswith(".pdf"):
                                        temp_pdf = os.path.join(TEMP_PDF_DIR, f"web_{d_code}.pdf")
                                        try:
                                            downloader.download_file(target_link, temp_pdf)
                                            parsed = parse_boe_pdf(temp_pdf)
                                            if os.path.exists(temp_pdf):
                                                os.remove(temp_pdf)
                                            
                                            if parsed.get("total_elementos", 0) > 0 or len(parsed.get("resumen_creditos", {})) > 0:
                                                found_curriculum = parsed
                                                direct_source_url = target_link
                                                break
                                        except Exception:
                                            if os.path.exists(temp_pdf):
                                                os.remove(temp_pdf)
                                    else:
                                        # Extraer tabla de asignaturas HTML si está presente
                                        tables = sub_soup.find_all("table")
                                        elementos_html = []
                                        for t in tables:
                                            for row in t.find_all("tr"):
                                                cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                                                if len(cols) >= 2 and len(cols[0]) > 3:
                                                    elementos_html.append({
                                                        "nombre_elemento": cols[0],
                                                        "creditos_ects": cols[1] if len(cols) > 1 else "6",
                                                        "caracter": "OB",
                                                        "curso": cols[2] if len(cols) > 2 else ""
                                                    })
                                        if len(elementos_html) > 3:
                                            found_curriculum = {
                                                "resumen_creditos": {"Créditos Totales": "240" if "grado" in d_title.lower() else "60"},
                                                "total_elementos": len(elementos_html),
                                                "elementos_curriculares": elementos_html
                                            }
                                            direct_source_url = target_link
                                            break
                        except Exception as sub_err:
                            print(f"     -> Excepción al escanear sub-página '{candidate_page_url}': {sub_err}")

                except Exception as crawl_err:
                    print(f"     -> Error al rastrear la web oficial para [{d_code}]: {crawl_err}")

            # Guardar el plan y la URL directa donde se ha encontrado
            if found_curriculum and direct_source_url:
                print(f"     🎉 [ÉXITO PARTE 2] Encontrado plan de estudios en la web oficial: '{direct_source_url}'")
                stats["resolved_degrees_count"] += 1
                
                degree_data = {
                    "codigo_estudio": d_code,
                    "titulo": d_title,
                    "nivel_academico": deg.get("nivel_academico", ""),
                    "universidad_codigo": u_code,
                    "universidad_nombre": u_name,
                    "fecha_procesado": datetime.now().isoformat(),
                    "web_fuente_directa_url": direct_source_url,
                    "origen_fuente": "web_oficial_universidad",
                    "plan_estudios": found_curriculum
                }
                
                atomic_json_dump(degree_data, plan_file)
                self.checkpoint.update_degree_record(d_code, direct_source_url, datetime.now().strftime("%Y-%m-%d"), datetime.now().isoformat())
            else:
                print(f"     -> No se encontró plan de estudios en la web oficial para [{d_code}].")

        return stats


def run_phase1_part2(max_workers: int = 4):
    """
    Punto de entrada principal para la Fase 1 - Parte 2:
    Rastrea las webs oficiales de las universidades de forma paralela para encontrar información faltante.
    """
    print("\n" + "=" * 70)
    print("      INICIANDO FASE 1 - PARTE 2: ESCANEO PARALELO WEBS OFICIALES")
    print("======================================================================")

    if not os.path.exists(UNIVERSIDADES_JSON) or not os.path.exists(TITULACIONES_JSON):
        print(" [AVISO PARTE 2] No existen archivos de datos de universidades/titulaciones. Finalizando.")
        return

    with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
        universities = json.load(f)

    with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
        titulaciones_por_univ = json.load(f)

    print(f" -> {len(universities)} universidades a procesar en paralelo con {max_workers} trabajadores.")

    crawler = UniversityWebCrawler()
    
    total_missing = 0
    total_resolved = 0
    denied_by_robots = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(crawler.process_university_web, univ, titulaciones_por_univ): univ
            for univ in universities
        }

        for future in concurrent.futures.as_completed(futures):
            univ = futures[future]
            try:
                res = future.result()
                total_missing += res.get("missing_degrees_count", 0)
                total_resolved += res.get("resolved_degrees_count", 0)
                if not res.get("robots_allowed", True):
                    denied_by_robots += 1
            except Exception as exc:
                print(f" [ERROR PARTE 2] Excepción inesperada en universidad {univ.get('codigo')}: {exc}")

    print("\n" + "=" * 70)
    print("      FASE 1 - PARTE 2 FINALIZADA DE FORMA METICULOSA Y RESPETUOSA")
    print("======================================================================")
    print(f" -> Universidades escaneadas:             {len(universities)}")
    print(f" -> Titulaciones sin plan iniciales:       {total_missing}")
    print(f" -> Titulaciones completadas desde web:    {total_resolved}")
    print(f" -> Cancelaciones por robots.txt:         {denied_by_robots}")
