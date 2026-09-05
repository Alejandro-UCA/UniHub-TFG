"""Extractores generales para planes curriculares publicados fuera de tablas HTML."""

from __future__ import annotations

from collections import defaultdict
import json
import re
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit


_CREDIT_UNIT = r"(?:ECTS|cr[eéè�]dit(?:os|s)?|credit(?:os|s)?)"
_CREDIT_RE = re.compile(rf"(?P<value>\d{{1,3}}(?:[.,]\d{{1,2}})?)\s*{_CREDIT_UNIT}\b", re.I)
_NAME_BEFORE_CREDIT_RE = re.compile(
    r"(?P<name>[A-Za-zÀ-ÿ0-9][^\n;|]{3,140}?)\s*(?:\(|\[|[-–—:]\s*)?\s*"
    rf"(?P<value>\d{{1,3}}(?:[.,]\d{{1,2}})?)\s*{_CREDIT_UNIT}\b",
    re.I,
)
_TOTAL_RE = re.compile(
    r"\b(?:carga\s+(?:lectiva|acad[eé]mica)|oferta\s+total|"
    r"dedicaci[oó]n(?:\s+total)?|"
    r"(?:consta|comprende|incluye)\s+(?:de\s+)?|"
    r"total\s+de\s+(?:cr[eéè]dits?|credits?))[^\n.;]{0,100}?"
    rf"(?P<value>\d{{2,3}}(?:[.,]\d{{1,2}})?)\s*{_CREDIT_UNIT}\b",
    re.I,
)
_DIRECT_TOTAL_RE = re.compile(
    r"\btotal(?:es|s)?\s*(?:(?:de(?:\s+(?:los|ellos\s+es\s+de))?|of)\s+)?"
    r"(?:cr[eéè�]dit(?:os|s)?\s*)?"
    r"[:=()\-–—\s]*"
    rf"(?P<value>\d{{2,3}}(?:[.,]\d{{1,2}})?)\s*{_CREDIT_UNIT}\b",
    re.I,
)
# Algunos CMS imprimen la etiqueta de total y el número en columnas
# independientes, por lo que no repiten «ECTS» junto al valor. La etiqueta
# debe mencionar inequívocamente créditos/carga total; nunca se acepta un
# «TOTAL 60» aislado, que podría ser el subtotal de un curso o módulo.
_TOTAL_LABEL_NO_UNIT_RE = re.compile(
    r"(?:cr[eéè�]ditos?\s+totales?|total\s+de\s+cr[eéè�]ditos?|"
    r"carga\s+(?:lectiva|acad[eé]mica)\s+total)"
    r"[^\d\n.;]{0,50}(?P<value>\d{2,3}(?:[.,]\d{1,2})?)",
    re.I,
)
_SUMMARY_MARKERS = (
    "total", "semestre", "semester", "cuatrimestre", "quadrimestre", "curso académico",
    "curs academic", "asignaturas", "assignatures", "modulo", "modul", "creditos",
    "credits", "ects", "oferta", "carga lectiva",
)
_INVALID_NAMES = {
    "ects", "créditos", "creditos", "crèdits", "credits", "total", "obligatoria",
    "obligatorio", "optativa", "optativo", "semester", "semestre", "curso", "year",
}
_ACADEMIC_HOST_MARKERS = (
    "estudio", "estudis", "master", "máster", "masteres", "masters", "posgrado",
    "grado", "grau", "bachelor", "doctorado", "doctorat", "phd", "curriculum",
    "plan", "asignatura", "assignatura", "docencia", "guia", "facultad", "facultat",
)


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.casefold().split())


def _encoding_text_variants(value: object) -> list[str]:
    """Devuelve el texto original y una reparación segura de mojibake UTF-8."""
    text = str(value or "")
    variants = [text]
    if any(marker in text for marker in ("Ã", "Â", "â", "ð")):
        repair_inputs = [text]
        # Un único carácter de reemplazo no debe impedir reparar el resto de
        # una página que mezcla UTF-8 mal interpretado y texto correcto.
        if "�" in text:
            repair_inputs.append(text.replace("�", ""))
        for repair_input in repair_inputs:
            try:
                repaired = repair_input.encode("cp1252", "ignore").decode(
                    "utf-8", "ignore"
                )
                if repaired and repaired not in variants:
                    variants.append(repaired)
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return variants


def _parse_credits(value: str, max_value: float = 60.0) -> float | None:
    match = re.search(r"\d{1,3}(?:[.,]\d{1,2})?", str(value or ""))
    if not match:
        return None
    try:
        number = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    return number if 0 < number <= float(max_value) else None


def infer_declared_total_ects(source: object) -> float | None:
    """Obtiene un total declarado sin confundirlo con la suma de optativas."""
    if hasattr(source, "get_text"):
        text = source.get_text(" ", strip=True)
    else:
        text = str(source or "")
    values = []
    for text_variant in _encoding_text_variants(text):
        # «Estudios totales ... se reconozca un mínimo de 30 créditos» no
        # declara la carga del programa. Un total debe estar junto al valor;
        # las frases de carga/dedicación conservan su gramática independiente.
        for match in (*_TOTAL_RE.finditer(text_variant), *_DIRECT_TOTAL_RE.finditer(text_variant)):
            # El límite de una asignatura no aplica al total reglamentario del
            # programa, que puede ser 90, 120, 180 o 240 ECTS.
            value = _parse_credits(match.group("value"), max_value=360.0)
            if value is not None and 30 <= value <= 360:
                values.append(value)
        for match in _TOTAL_LABEL_NO_UNIT_RE.finditer(text_variant):
            value = _parse_credits(match.group("value"), max_value=360.0)
            if value is not None and 30 <= value <= 360:
                values.append(value)
    return max(values) if values else None


def _classify(name: str) -> str:
    low = _normalise(name)
    if any(marker in low for marker in ("trabajo fin", "treball de fi", "tfg", "tfm", "master thesis", "final project")):
        return "TFM"
    if any(marker in low for marker in ("practicas", "practiques", "internship", "placement")):
        return "PE"
    if any(marker in low for marker in ("optativ", "elective", "optional")):
        return "OP"
    if any(marker in low for marker in ("basica", "bàsica", "basic", "core")):
        return "FB"
    return "OB"


def _clean_name(value: str) -> str:
    name = re.sub(r"^[\s•*\-–—:]+", "", value or "").strip(" ,;:-–—")
    name = re.sub(r"\s+", " ", name)
    if len(name) < 4 or len(name) > 140:
        return ""
    low = _normalise(name)
    if low in _INVALID_NAMES or any(marker in low for marker in ("cookie", "privacidad", "contacto", "iniciar sesion", "login")):
        return ""
    if is_summary_curriculum_name(name):
        return ""
    if any(marker in low for marker in ("programa consta", "master consta", "màster consta", "plan consta", "carga lectiva")):
        return ""
    return name


def is_summary_curriculum_name(value: object) -> bool:
    """Distingue rótulos de distribución de créditos de elementos docentes."""
    low = _normalise(value)
    if not low:
        return True
    # Las declaraciones generales sobre la carga de las asignaturas pueden
    # contener el patrón «Nombre ... 6 ECTS» y ser capturadas por el extractor
    # de prosa. No son elementos curriculares individuales.
    if re.match(
        r"^(?:todas?|cada|all|each)\s+(?:las?\s+|los?\s+|as?\s+|the\s+)?"
        r"(?:asignaturas?|materias?|subjects?|courses?)\b",
        low,
    ):
        return True
    if low.startswith(_SUMMARY_MARKERS) and not re.search(
        r"\b(?:metod|derecho|analisis|analysis|research|project|treball)\b", low
    ):
        return True
    return low.startswith((
        "programa consta", "master consta", "màster consta", "plan consta",
        "carga lectiva", "carga acadèmica", "carga academica",
    ))


def _element(name: str, credits: float, source_url: str = "", context: str = "") -> dict:
    item = {
        "modulo": "",
        "materia": "",
        "codigo_asignatura": "",
        "nombre_elemento": name,
        "creditos_ects": str(int(credits)) if credits.is_integer() else str(credits),
        "caracter": _classify(f"{name} {context}"),
        "curso": "",
        "cuatrimestre": "",
    }
    if source_url:
        item["url_guia_docente"] = source_url
    return item


def _iter_structured_values(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_structured_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_structured_values(child)


def extract_structured_curriculum(soup, source_url: str = "") -> list[dict]:
    """Extrae objetos JSON-LD que declaren nombre y créditos de una materia."""
    found = []
    seen = set()
    for script in soup.find_all("script", type="application/ld+json") if soup else []:
        try:
            raw = script.string or script.get_text()
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for obj in _iter_structured_values(data):
            name = obj.get("name") or obj.get("title") or obj.get("nombre")
            credits = obj.get("credits") or obj.get("ects") or obj.get("creditos") or obj.get("creditos_ects")
            if isinstance(credits, dict):
                credits = credits.get("value") or credits.get("amount")
            parsed = _parse_credits(str(credits or ""))
            clean = _clean_name(str(name or ""))
            if not clean or parsed is None:
                continue
            key = _normalise(clean)
            if key not in seen:
                seen.add(key)
                found.append(_element(clean, parsed, source_url))
    return found


def extract_prose_curriculum(soup, source_url: str = "") -> list[dict]:
    """Extrae materias expresadas como «Nombre (6 ECTS)» o «Nombre — 6 ECTS»."""
    if not soup:
        return []
    found = []
    seen = set()
    nodes = soup.find_all(["p", "li", "dt", "dd", "div", "span"])
    for node in nodes:
        text = node.get_text(" ", strip=True)
        if not text or len(text) > 280:
            continue
        for match in _NAME_BEFORE_CREDIT_RE.finditer(text):
            name = _clean_name(match.group("name"))
            credits = _parse_credits(match.group("value"))
            if not name or credits is None:
                continue
            # Elimina prefijos narrativos y conserva el segmento académico.
            if ":" in name:
                name = name.rsplit(":", 1)[-1].strip()
            name = _clean_name(name)
            key = _normalise(name)
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(_element(name, credits, source_url, text))
    return found


_HYDRATION_NAME_KEYS = {
    "nombre", "nombre_asignatura", "nombreasignatura", "name", "subject", "subjectname",
    "subject_name", "asignatura", "title", "denominacion", "nom", "assignatura",
    "materia", "course_name", "coursename", "subjecttitle", "subject_title",
}
_HYDRATION_CREDIT_KEYS = {
    "creditos", "creditos_ects", "creditosects", "credits", "ects", "val",
    "num_creditos", "numcreditos", "credit", "carga_lectiva", "cargalectiva",
    "numerocreditos", "ects_credits", "ectscredits",
}
_HYDRATION_COURSE_KEYS = {"curso", "course", "year", "curs", "any", "nivel"}
_HYDRATION_TYPE_KEYS = {"tipo", "caracter", "character", "type", "tipologia", "modalidad", "nature", "tipus"}
_HYDRATION_TERM_KEYS = {"cuatrimestre", "semestre", "semester", "term", "periodo", "quadrimestre", "period"}
_HYDRATION_CODE_KEYS = {"codigo", "codigo_asignatura", "code", "id", "cod", "codasignatura", "cod_asignatura", "subject_code"}
_HYDRATION_URL_KEYS = {"url", "guiadocente", "guia_docente", "guia", "syllabus", "link", "href", "guia_url"}


def _parse_candidate_subject_dict(d: dict, source_url: str = "") -> dict | None:
    if not isinstance(d, dict):
        return None

    name = None
    for k, v in d.items():
        k_clean = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_clean in _HYDRATION_NAME_KEYS and isinstance(v, str) and len(v.strip()) >= 3:
            cand_name = _clean_name(v)
            if cand_name:
                name = cand_name
                break
    if not name:
        return None

    credits = None
    for k, v in d.items():
        k_clean = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_clean in _HYDRATION_CREDIT_KEYS:
            if isinstance(v, (int, float)):
                credits = float(v)
            elif isinstance(v, str):
                credits = _parse_credits(v)
            elif isinstance(v, dict):
                sub_val = v.get("value") or v.get("amount") or v.get("val") or v.get("creditos")
                if sub_val is not None:
                    credits = _parse_credits(str(sub_val))
            if credits is not None and 0 < credits <= 60:
                break
    if credits is None:
        return None

    curso = ""
    for k, v in d.items():
        k_clean = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_clean in _HYDRATION_COURSE_KEYS and v:
            curso = str(v).strip()
            break

    tipo = ""
    for k, v in d.items():
        k_clean = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_clean in _HYDRATION_TYPE_KEYS and v:
            tipo = str(v).strip()
            break

    cuatrimestre = ""
    for k, v in d.items():
        k_clean = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_clean in _HYDRATION_TERM_KEYS and v:
            cuatrimestre = str(v).strip()
            break

    codigo = ""
    for k, v in d.items():
        k_clean = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_clean in _HYDRATION_CODE_KEYS and v:
            codigo = str(v).strip()
            break

    guide_url = ""
    for k, v in d.items():
        k_clean = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k_clean in _HYDRATION_URL_KEYS and isinstance(v, str) and v.startswith("http"):
            guide_url = v.strip()
            break

    elem = _element(name, credits, guide_url or source_url, context=tipo)
    if curso:
        elem["curso"] = curso
    if cuatrimestre:
        elem["cuatrimestre"] = cuatrimestre
    if codigo:
        elem["codigo_asignatura"] = codigo
    if tipo:
        elem["caracter"] = _classify(f"{tipo} {name}")
    return elem


def extract_hydration_payload(soup, raw_html: str = "") -> list[dict]:
    """Extrae cargas útiles JSON de hidratación (Next.js __NEXT_DATA__, Nuxt, etc.)."""
    payloads = []
    if soup:
        # 1. Next.js: <script id="__NEXT_DATA__" type="application/json">
        for script in soup.find_all("script", id="__NEXT_DATA__"):
            text = script.string or script.get_text()
            if text:
                try:
                    payloads.append(json.loads(text.strip()))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass

        # 2. Scripts JSON genéricos
        for script in soup.find_all("script", type="application/json"):
            if script.get("id") == "__NEXT_DATA__":
                continue
            text = script.string or script.get_text()
            if text and len(text) > 30:
                try:
                    parsed = json.loads(text.strip())
                    if isinstance(parsed, (dict, list)):
                        payloads.append(parsed)
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass

    # 3. Nuxt / inline window.__NUXT__ o window.__INITIAL_STATE__
    search_texts = []
    if raw_html:
        search_texts.append(raw_html)
    elif soup:
        for script in soup.find_all("script"):
            if not script.get("src"):
                s_text = script.string or script.get_text()
                if s_text:
                    search_texts.append(s_text)

    nuxt_re = re.compile(
        r"(?:window\.__NUXT__|window\.__INITIAL_STATE__|window\.__DATA__)\s*=\s*(\{.*?\})(?:;\s*</script>|;\s*\n|;\s*$)",
        re.DOTALL,
    )
    for text in search_texts:
        for match in nuxt_re.finditer(text):
            try:
                payloads.append(json.loads(match.group(1).strip()))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

    return payloads


def extract_curriculum_from_json_tree(
    data: object,
    required_ects: float | None = None,
    source_url: str = "",
) -> list[dict]:
    """Extrae materias académicas recorriendo recursivamente árboles JSON hidratados."""
    if not data:
        return []

    collected_elements: list[dict] = []
    seen_names: set[str] = set()

    def _walk(node):
        if isinstance(node, dict):
            cand = _parse_candidate_subject_dict(node, source_url)
            if cand:
                key = _normalise(cand["nombre_elemento"])
                if key and key not in seen_names:
                    seen_names.add(key)
                    collected_elements.append(cand)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    if isinstance(data, list):
        for item in data:
            _walk(item)
    else:
        _walk(data)

    return collected_elements


def merge_curriculum_elements(primary: list[dict], recovered: list[dict]) -> list[dict]:
    """Combina dos extracciones conservando la primera evidencia por nombre."""
    result = []
    seen = set()
    for item in list(primary or []) + list(recovered or []):
        if not isinstance(item, dict):
            continue
        key = _normalise(item.get("nombre_elemento"))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _replacement_text_variants(value: object, limit: int = 64) -> list[str]:
    """Genera variantes acotadas para el marcador de carácter no decodificado."""
    variants = [str(value or "")]
    for marker in ("\ufffd", "�"):
        if not any(marker in item for item in variants):
            continue
        expanded = []
        for item in variants:
            if marker not in item:
                expanded.append(item)
                continue
            for replacement in ("a", "e", "i", "o", "u", ""):
                expanded.append(item.replace(marker, replacement, 1))
        variants = expanded[:limit]
    return variants


def _degree_slug_variants(title: object, academic_level: object = "") -> list[str]:
    """Genera slugs de titulación sin depender de catálogos institucionales."""
    raw_text = str(title or "")
    if not raw_text.strip():
        return []
    stopwords = {
        "el", "la", "los", "las", "de", "del", "en", "y", "e", "i", "a", "o",
        "graduado", "graduada", "graduats", "graduades",
        "un", "una", "the", "and", "of", "for", "universitario", "universitaria",
        "universitaris", "universitaries", "official", "oficial", "oficiales",
        "oficials", "programa", "programas", "master", "masteres", "máster",
        "másteres", "màster", "màsters", "posgrado", "postgrado", "postgrau",
        "posgrao", "grado", "grau", "graos", "bachelor", "undergraduate",
        "doctorado", "doctorat", "doctorate", "phd", "doctoral", "mster",
    }
    level_texts = _replacement_text_variants(academic_level)
    level = " ".join(_normalise(item) for item in level_texts)
    level_prefix = ""
    if any(token in level for token in ("master", "mster", "posgrado", "postgrado")):
        level_prefix = "master"
    elif any(token in level for token in ("grado", "bachelor", "undergraduate")):
        level_prefix = "grado"
    elif any(token in level for token in ("doctor", "phd")):
        level_prefix = "doctorado"

    slugs = []
    seen = set()
    for text_variant in _replacement_text_variants(raw_text):
        text = _normalise(text_variant)
        # La parte posterior suele enumerar universidades participantes y no
        # forma parte del identificador editorial de la ficha. Se corta sólo
        # ante conectores de atribución, nunca ante una palabra académica.
        text = re.split(r"\s+(?:por|per|by|pela|pelo)\s+", text, maxsplit=1)[0]
        words = [word for word in re.findall(r"[a-z0-9]+", text) if word not in stopwords]
        if not words:
            continue
        slug = "-".join(words[:12])
        for candidate in ([f"{level_prefix}-{slug}", slug] if level_prefix else [slug]):
            if candidate not in seen:
                seen.add(candidate)
                slugs.append(candidate)
    return slugs


def generic_curriculum_path_candidates(
    source_url: str, academic_level: str = "", degree_title: object = ""
) -> list[str]:
    """Genera rutas académicas convencionales relativas al dominio autorizado."""
    parsed = urlsplit(str(source_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []
    base = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    prefixes = [p for p in (parsed.path.rstrip("/"), "/estudios", "/estudiar", "/oferta-academica", "/programas") if p]
    level = _normalise(academic_level)
    if any(token in level for token in ("master", "posgrado", "postgrado")):
        prefixes.extend((
            "/masters", "/masteres", "/posgrados", "/postgrados",
            "/postgraus", "/postgraos", "/masterrak",
        ))
    elif any(token in level for token in ("grado", "bachelor", "undergraduate")):
        prefixes.extend((
            "/grados", "/graus", "/graos", "/graduak",
            "/estudios/grados", "/estudis/grau", "/estudos/grao",
        ))
    elif any(token in level for token in ("doctor", "phd", "doctoral", "doutor", "doktorego")):
        prefixes.extend((
            "/doctorado", "/doctorados", "/doctorat", "/doctorats",
            "/doutoramento", "/doutoramentos", "/doktoregoa",
            "/programas-de-doctorado", "/programes-de-doctorat",
        ))
    suffixes = (
        "plan-de-estudios", "plan_estudios", "plan-d-estudis", "pla-d-estudis",
        "curriculum", "malla-curricular", "estructura", "asignaturas", "assignatures",
        "study-plan", "course-structure",
    )
    candidates = []
    seen = set()

    # Algunos portales publican la ficha directamente en la raíz y no la
    # enlazan desde la portada ni desde un sitemap. El slug se deriva sólo del
    # título aportado por el catálogo y sigue sujeto a las validaciones del
    # llamador; no contiene reglas de una institución concreta.
    slugs = _degree_slug_variants(degree_title, academic_level)
    route_prefixes = ["", "/estudios", "/estudiar"]
    context_path = parsed.path.rstrip("/")
    if context_path and context_path not in route_prefixes:
        # Conservar el prefijo de contexto/idioma descubierto en una portada
        # (p. ej. un CMS que sirve las fichas bajo /contexto/idioma). No se
        # codifica ningún nombre de institución; el prefijo procede de la URL
        # ya validada por el llamador.
        route_prefixes.insert(0, context_path)
    if any(token in level for token in ("master", "posgrado", "postgrado")):
        route_prefixes.extend((
            "/masters", "/masteres", "/posgrados", "/postgrados",
            "/postgraus", "/postgraos", "/masterrak",
        ))
    elif any(token in level for token in ("grado", "bachelor", "undergraduate")):
        route_prefixes.extend((
            "/grados", "/graus", "/graos", "/graduak",
            "/estudios/grados", "/estudis/grau", "/estudos/grao",
        ))
    elif any(token in level for token in ("doctor", "phd", "doctoral", "doutor", "doktorego")):
        route_prefixes.extend((
            "/doctorado", "/doctorados", "/doctorat", "/doctorats",
            "/doutoramento", "/doutoramentos", "/doktoregoa",
            "/programas-de-doctorado", "/programes-de-doctorat",
        ))
    for prefix in route_prefixes:
        for slug in slugs:
            base_path = f"{prefix.rstrip('/')}/{slug}" if prefix else f"/{slug}"
            url = urljoin(base, base_path.lstrip("/"))
            if url not in seen:
                seen.add(url)
                candidates.append(url)

    # Portales docentes especializados suelen publicar el plan en una ruta
    # corta independiente de la ficha y sin enlazarla desde su portada.
    # Se prueban variantes editoriales genéricas, siempre bajo el origen ya
    # autorizado y con validación de identidad en el llamador.
    for compact_path in (
        "/planestudios.html", "/planestudios", "/plan-estudios.html",
        "/plan-de-estudios.html", "/plan-d-estudis.html", "/asignaturas.html",
        "/subjects.html", "/curriculum.html",
    ):
        url = urljoin(base, compact_path.lstrip("/"))
        if url not in seen:
            seen.add(url)
            candidates.append(url)

    # Priorizar todas las fichas directas antes de sus subrutas: una variante
    # de codificación posterior no debe quedar fuera por consumir el límite
    # de rutas con los sufijos de una variante anterior.
    for prefix in route_prefixes:
        for slug in slugs:
            base_path = f"{prefix.rstrip('/')}/{slug}" if prefix else f"/{slug}"
            url = urljoin(base, base_path.lstrip("/"))
            for suffix in ("plan-de-estudios", "plan_estudios", "curriculum", "estructura"):
                nested = urljoin(url.rstrip("/") + "/", suffix)
                if nested not in seen:
                    seen.add(nested)
                    candidates.append(nested)

    for prefix in prefixes[:8]:
        for suffix in suffixes:
            url = urljoin(base + (prefix if prefix.endswith("/") else prefix + "/"), suffix)
            if url not in seen:
                seen.add(url)
                candidates.append(url)
    return candidates


def _organisation_host(host: str) -> str:
    """Obtiene una clave conservadora para relacionar hosts de una misma organización."""
    clean = str(host or "").split(":", 1)[0].strip(".").casefold()
    if not clean or re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", clean):
        return clean
    parts = [part for part in clean.split(".") if part]
    if len(parts) < 2:
        return clean
    if len(parts) >= 3 and ".".join(parts[-2:]) in {"edu.es", "gob.es", "com.es", "org.es", "ac.uk", "co.uk"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def discover_related_academic_origins(soup, source_url: str, max_origins: int = 12) -> list[str]:
    """Descubre hosts académicos enlazados desde una portada sin salir de la organización."""
    if not soup:
        return []
    parsed = urlsplit(str(source_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return []
    organisation = _organisation_host(parsed.hostname)
    base_host = parsed.hostname.casefold()
    candidates = []

    organisation_root = urlunsplit((parsed.scheme, organisation, "", "", ""))
    if organisation and organisation != base_host:
        candidates.append(organisation_root)

    def consider(raw_url: object, context: object = ""):
        target = urlsplit(urljoin(str(source_url), str(raw_url or "").strip()))
        if target.scheme not in {"http", "https"} or not target.hostname:
            return
        target_host = target.hostname.casefold()
        if target_host == base_host or _organisation_host(target_host) != organisation:
            return
        haystack = f"{target.geturl()} {context}".casefold()
        if not any(marker in haystack for marker in _ACADEMIC_HOST_MARKERS):
            return
        origin = urlunsplit((target.scheme, target.netloc, "", "", ""))
        if origin not in candidates:
            candidates.append(origin)

    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or [])
        if any(token in _normalise(rel) for token in ("canonical", "alternate")):
            consider(link.get("href"), rel)
    for meta in soup.find_all("meta"):
        prop = str(meta.get("property") or meta.get("name") or "")
        if _normalise(prop) in {"og:url", "twitter:url"}:
            consider(meta.get("content"), prop)
    for anchor in soup.find_all("a", href=True):
        consider(anchor.get("href"), anchor.get_text(" ", strip=True))
        if len(candidates) >= max_origins:
            break
    return candidates[:max_origins]


def discover_linked_curriculum_documents(
    soup, page_url: str, max_documents: int = 12
) -> list[tuple[str, str]]:
    """Encuentra documentos curriculares enlazados desde una ficha académica."""
    if not soup:
        return []
    parsed = urlsplit(str(page_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return []
    organisation = _organisation_host(parsed.hostname)
    markers = (
        "plan", "estudio", "curriculum", "curriculo", "currículum", "malla",
        "estructura", "asignatura", "assignatura", "guia", "guía", "syllabus",
        "course", "subject", "credit", "ects", "programa",
    )
    candidates = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        target = urlsplit(urljoin(str(page_url), href))
        if target.scheme not in {"http", "https"} or not target.hostname:
            continue
        if _organisation_host(target.hostname) != organisation:
            continue
        if not target.path.casefold().endswith((".pdf", ".pdf.gz")):
            continue
        text = anchor.get_text(" ", strip=True)
        # Muchas fichas oficiales enlazan el documento con texto genérico
        # (p. ej. «Descargar PDF») y un nombre de fichero opaco. En esos casos
        # la señal curricular vive en el bloque semántico que contiene el
        # enlace, no en el href. Limitamos la subida por el DOM para no
        # convertir una página completa en una señal positiva.
        context_parts = [target.geturl(), text]
        for ancestor in list(anchor.parents)[:5]:
            if ancestor.name not in {"section", "article", "li", "details", "div", "aside"}:
                continue
            # No heredamos el texto de contenedores de navegación o de toda
            # la página: varios enlaces hermanos harían que un PDF ajeno
            # pareciera curricular por contaminación contextual.
            if len(ancestor.find_all("a", href=True)) > 3:
                continue
            ancestor_text = ancestor.get_text(" ", strip=True)
            if ancestor_text and len(ancestor_text) <= 2400:
                context_parts.append(ancestor_text)
        nearest_heading = anchor.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
        if nearest_heading:
            heading_text = nearest_heading.get_text(" ", strip=True)
            if heading_text:
                context_parts.append(heading_text)
        for attribute in ("aria-label", "title", "data-title"):
            value = anchor.get(attribute)
            if value:
                context_parts.append(str(value))
        context = _normalise(" ".join(context_parts))
        if not any(marker in context for marker in markers):
            continue
        canonical = target.geturl()
        if canonical in seen:
            continue
        seen.add(canonical)
        score = sum(20 for marker in ("plan", "curriculum", "malla", "estructura") if marker in context)
        score += sum(10 for marker in ("asignatura", "assignatura", "guia", "syllabus", "ects") if marker in context)
        if "plan" in context and any(marker in context for marker in ("estudio", "estudis", "study")):
            score += 80
        if any(marker in context for marker in ("estrategico", "estrategia", "informe", "curriculum vitae", "profesorado", "tutoria", "calendario")):
            score -= 45
        candidates.append((score, canonical, text))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [(url, text) for _, url, text in candidates[:max(1, int(max_documents))]]


def discover_linked_curriculum_pages(
    soup, page_url: str, max_pages: int = 8
) -> list[tuple[str, str]]:
    """Prioriza enlaces curriculares internos desde una ficha ya identificada.

    A diferencia de los documentos enlazados, esta ruta admite fichas HTML y
    PDF. Conserva el límite, la afinidad organizativa y las señales semánticas
    para que una página de presentación no desemboque en navegación masiva.
    """
    if not soup:
        return []
    parsed = urlsplit(str(page_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return []
    organisation = _organisation_host(parsed.hostname)
    markers = (
        "plan", "estudio", "estudis", "curriculum", "curriculo", "currículum",
        "malla", "estructura", "asignatura", "assignatura", "materia", "guia",
        "guía", "syllabus", "course", "subject", "credit", "ects", "programa",
    )
    excluded = (
        "curriculum vitae", "profesorado", "personal", "noticia", "news",
        "calendario", "horario", "matricula", "matrícula", "acceso",
    )
    candidates = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        target = urlsplit(urljoin(str(page_url), href))
        if target.scheme not in {"http", "https"} or not target.hostname:
            continue
        if _organisation_host(target.hostname) != organisation:
            continue
        canonical = target.geturl()
        if canonical == str(page_url) or canonical in seen:
            continue
        text = anchor.get_text(" ", strip=True)
        context = _normalise(f"{canonical} {text}")
        if not any(marker in context for marker in markers):
            continue
        if any(marker in context for marker in excluded):
            continue
        seen.add(canonical)
        score = sum(25 for marker in ("plan", "estudio", "estudis", "curriculum", "malla", "estructura") if marker in context)
        score += sum(10 for marker in ("asignatura", "assignatura", "materia", "syllabus", "ects") if marker in context)
        if target.path.casefold().endswith((".pdf", ".pdf.gz")):
            score += 20
        candidates.append((score, canonical, text))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [(url, text) for _, url, text in candidates[:max(1, int(max_pages))]]


def matches_academic_level(title: object, level: object, requested: str | None) -> bool:
    """Filtra niveles académicos sin depender de catálogos institucionales."""
    requested_key = _normalise(requested)
    if not requested_key:
        return True
    haystack = _normalise(f"{title} {level}")
    markers = {
        "master": ("master", "máster", "màster", "m�ster", "mster", "posgrado", "postgrado"),
        "grado": ("grado", "grau", "bachelor", "undergraduate"),
        "doctorado": ("doctorado", "doctorat", "doctorate", "phd", "doctoral"),
    }
    return any(marker in haystack for marker in markers.get(requested_key, (requested_key,)))


_RE_COURSE_SUBPAGE_MARKERS = [
    (re.compile(r"(?:^|[/_\-?&=\s])(?:1[oºªa]?[-_\s]?curso|primer[-_\s]?curso|primer[-_\s]?curs|1st[-_\s]?year|curso[-_\s]?1|curs[-_\s]?1)(?:[/_\-?&=\s.]|$)", re.I), "1º"),
    (re.compile(r"(?:^|[/_\-?&=\s])(?:2[oºªa]?[-_\s]?curso|segundo[-_\s]?curso|segon[-_\s]?curs|2nd[-_\s]?year|curso[-_\s]?2|curs[-_\s]?2)(?:[/_\-?&=\s.]|$)", re.I), "2º"),
    (re.compile(r"(?:^|[/_\-?&=\s])(?:3[oºªa]?[-_\s]?curso|tercer[-_\s]?curso|tercer[-_\s]?curs|3rd[-_\s]?year|curso[-_\s]?3|curs[-_\s]?3)(?:[/_\-?&=\s.]|$)", re.I), "3º"),
    (re.compile(r"(?:^|[/_\-?&=\s])(?:4[oºªa]?[-_\s]?curso|cuarto[-_\s]?curso|quart[-_\s]?curs|4th[-_\s]?year|curso[-_\s]?4|curs[-_\s]?4)(?:[/_\-?&=\s.]|$)", re.I), "4º"),
    (re.compile(r"(?:^|[/_\-?&=\s])(?:5[oºªa]?[-_\s]?curso|quinto[-_\s]?curso|cinque[-_\s]?curs|5th[-_\s]?year|curso[-_\s]?5|curs[-_\s]?5)(?:[/_\-?&=\s.]|$)", re.I), "5º"),
    (re.compile(r"(?:^|[/_\-?&=\s])(?:6[oºªa]?[-_\s]?curso|sexto[-_\s]?curso|sise[-_\s]?curs|6th[-_\s]?year|curso[-_\s]?6|curs[-_\s]?6)(?:[/_\-?&=\s.]|$)", re.I), "6º"),
]


def discover_course_partitioned_subpages(soup, page_url: str) -> list[tuple[str, str, str]]:
    """Descubre subpáginas curriculares particionadas por curso (1º a 6º) enlazadas desde una ficha."""
    if not soup:
        return []
    parsed = urlsplit(str(page_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return []
    organisation = _organisation_host(parsed.hostname)

    found_by_course: dict[str, tuple[str, str]] = {}

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        target_url = urljoin(str(page_url), href)
        target = urlsplit(target_url)
        if target.scheme not in {"http", "https"} or not target.hostname:
            continue
        if _organisation_host(target.hostname) != organisation:
            continue
        canonical = target.geturl().split("#", 1)[0]
        if canonical == str(page_url).split("#", 1)[0]:
            continue

        text = anchor.get_text(" ", strip=True)
        combo = f"{canonical} {text}"

        for pattern, course_label in _RE_COURSE_SUBPAGE_MARKERS:
            if course_label in found_by_course:
                continue
            if pattern.search(canonical) or pattern.search(text) or pattern.search(combo) or re.search(rf"\b{course_label}\s*(?:curso|curs|year)?\b", text, re.I):
                found_by_course[course_label] = (canonical, text)
                break

    sorted_courses = ["1º", "2º", "3º", "4º", "5º", "6º"]
    return [(found_by_course[c][0], found_by_course[c][1], c) for c in sorted_courses if c in found_by_course]


def matches_boe_credit_distribution(
    extracted_elements: list[dict],
    resumen_creditos: dict,
    tolerance: float = 6.0,
) -> bool:
    """Valida si un conjunto de asignaturas extraídas concuerda con el resumen oficial BOE.
    
    Verifica que la suma de ECTS de las asignaturas extraídas por tipología
    (FB, OB, OP, TFG/TFM) sea compatible con la plantilla del BOE dentro de la tolerancia.
    """
    if not isinstance(extracted_elements, list) or not extracted_elements:
        return False
    if not isinstance(resumen_creditos, dict) or not resumen_creditos:
        return False

    extracted_by_type: dict[str, float] = defaultdict(float)
    total_extracted = 0.0
    for el in extracted_elements:
        if not isinstance(el, dict):
            continue
        car = str(el.get("caracter") or el.get("tipo") or "OB").strip().upper()
        raw_cr = el.get("creditos_ects") or el.get("creditos") or el.get("ects")
        try:
            val = float(str(raw_cr).replace(",", ".")) if raw_cr is not None else 0.0
            if 0 < val <= 60:
                extracted_by_type[car] += val
                total_extracted += val
        except (ValueError, TypeError):
            continue

    if total_extracted <= 0:
        return False

    def _parse_res_cr(key_or_keys):
        keys = key_or_keys if isinstance(key_or_keys, tuple) else (key_or_keys,)
        for k in keys:
            for rk, rv in resumen_creditos.items():
                rk_clean = _normalise(rk).replace(" ", "_")
                if any(_normalise(cand) == rk_clean or _normalise(cand) in rk_clean for cand in keys):
                    try:
                        vf = float(str(rv).replace(",", ".").split()[0])
                        if vf > 0:
                            return vf
                    except (ValueError, TypeError, IndexError):
                        pass
        return None

    fb_target = _parse_res_cr(("formacion_basica", "formacion basica", "fb"))
    ob_target = _parse_res_cr(("obligatorias", "obligatoria", "ob"))
    tfg_target = _parse_res_cr(("trabajo_fin_grado", "trabajo fin de grado", "tfm", "tfg"))
    total_target = _parse_res_cr(("total", "total_creditos", "creditos_totales"))

    checks = []
    if fb_target is not None and fb_target > 0:
        checks.append(abs(extracted_by_type.get("FB", 0.0) - fb_target) <= tolerance)
    if ob_target is not None and ob_target > 0:
        checks.append(abs(extracted_by_type.get("OB", 0.0) - ob_target) <= tolerance)
    if tfg_target is not None and tfg_target > 0:
        tfg_extracted = extracted_by_type.get("TFG", 0.0) + extracted_by_type.get("TFM", 0.0)
        checks.append(abs(tfg_extracted - tfg_target) <= tolerance)

    if checks:
        return sum(checks) >= max(1, int(len(checks) * 0.6))

    if total_target is not None and total_target > 0:
        return abs(total_extracted - total_target) <= max(tolerance, total_target * 0.1)

    return False


