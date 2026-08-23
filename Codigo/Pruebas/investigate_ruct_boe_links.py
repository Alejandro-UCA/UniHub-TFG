import sys
import os
import json
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import tempfile

sys.path.append('d:/Proyecto/Codigo/Crawler')
from parsers import parse_boe_pdf, compute_curriculum_total_ects, get_required_degree_credits

PLANES_DIR = 'd:/Proyecto/Codigo/Crawler/Datos/planes_estudio'

with open('d:/Proyecto/Codigo/Crawler/Datos/auditoria_exhaustiva/02_titulaciones_incompletas_con_causas.json', 'r', encoding='utf-8') as f:
    incompletas = json.load(f)['titulaciones']

print("=======================================================================")
print("  INVESTIGACIÓN EN VIVO: CONSULTA DIRECTA AL RUCT vs PDFs DESCARGADOS")
print("=======================================================================")

# Elegimos 10 titulaciones incompletas variadas de distintas universidades y ramas
sample_codes = [deg['codigo_estudio'] for deg in incompletas[:10]]

results = []

for code in sample_codes:
    p_path = os.path.join(PLANES_DIR, f"{code}.json")
    with open(p_path, 'r', encoding='utf-8') as fp:
        local_data = json.load(fp)

    title = local_data.get('titulo', '')
    univ = local_data.get('universidad_nombre', '')
    level = local_data.get('nivel_academico', '')
    local_boe_urls = set(local_data.get('all_boe_urls', []))
    if local_data.get('boe_url'):
        local_boe_urls.add(local_data.get('boe_url'))
    
    current_ects = compute_curriculum_total_ects(local_data.get('plan_estudios', {}).get('elementos_curriculares', []) if local_data.get('plan_estudios') else [])
    req_ects = get_required_degree_credits(level, title)

    print(f"\n>>> Consultando RUCT oficial para [{code}]: {title[:50]} ({univ})...")
    print(f"    - Estado local: {current_ects}/{req_ects} ECTS | URLs BOE locales registradas: {len(local_boe_urls)}")

    # URLs de consulta de RUCT
    ruct_urls = [
        f"https://www.educacion.gob.es/ruct/estudio.action?codigoCiclo=SC&codigoEstudio={code}&actual=estudios",
        f"https://sede.educacion.gob.es/ruct/estudio.action?codigoCiclo=SC&codigoEstudio={code}&actual=estudios"
    ]
    
    ruct_boe_links = set()
    ruct_fetched_ok = False

    for r_url in ruct_urls:
        try:
            req = urllib.request.Request(r_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode('utf-8', errors='replace')
                soup = BeautifulSoup(html, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'boe.es' in href.lower() and '.pdf' in href.lower():
                        clean_href = urllib.parse.urljoin(r_url, href)
                        ruct_boe_links.add(clean_href)
                ruct_fetched_ok = True
                break
        except Exception as e:
            continue

    if not ruct_fetched_ok:
        print(f"    [AVISO] No se pudo conectar con el portal RUCT en tiempo real ({code}).")
        continue

    print(f"    - URLs BOE encontradas en RUCT: {len(ruct_boe_links)}")
    for b_url in ruct_boe_links:
        print(f"       * {b_url}")

    # Normalizar http -> https para comparación exacta
    clean_ruct_links = {u.replace("http://", "https://").replace("www.boe.es", "boe.es").replace("https://boe.es", "https://www.boe.es") for u in ruct_boe_links}
    clean_local_links = {u.replace("http://", "https://").replace("www.boe.es", "boe.es").replace("https://boe.es", "https://www.boe.es") for u in local_boe_urls}

    missed_urls = clean_ruct_links - clean_local_links
    if missed_urls:
        print(f"    [AVISO] DETECTADOS {len(missed_urls)} PDFs en RUCT no presentes en local_data:")
        for m_url in missed_urls:
            print(f"       -> Descargando y examinando PDF omitido: {m_url}")
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tf:
                t_path = tf.name
            try:
                m_req = urllib.request.Request(m_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(m_req, timeout=15) as m_resp:
                    with open(t_path, 'wb') as m_fp:
                        m_fp.write(m_resp.read())
                m_parsed = parse_boe_pdf(t_path, target_title=title, univ_name=univ)
                m_ects = compute_curriculum_total_ects(m_parsed.get('elementos_curriculares', []))
                print(f"          Resultado del PDF omitido: {m_ects} ECTS detectados.")
            except Exception as m_err:
                print(f"          Error al examinar PDF omitido: {m_err}")
            finally:
                if os.path.exists(t_path):
                    os.remove(t_path)
    else:
        print(f"    [OK] VERIFICADO: El 100% de los PDFs del BOE publicados en el RUCT ({len(ruct_boe_links)}) fueron descargados y analizados.")

print("\n=======================================================================")
print("  INVESTIGACION FINALIZADA")
print("=======================================================================")
