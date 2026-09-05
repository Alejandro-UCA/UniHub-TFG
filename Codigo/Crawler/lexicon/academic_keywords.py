"""Vocabulario académico multilingüe, stop-words, patrones y filtros de descarte."""

from __future__ import annotations

# Prefijos de subdominios especializados en gestión académica y guías docentes
ACADEMIC_SUBDOMAIN_PREFIXES = [
    "asignaturas.", "guiasdocentes.", "sia.", "geaservicios.", "grados.",
    "facultad.", "secretaria.", "graus.", "estudis.", "campusvirtual.", "docencia."
]

# Marcadores de páginas no docentes o títulos no oficiales a penalizar en la cola de hubs
NON_ACADEMIC_DEMOTION_MARKERS = [
    "/dep-", "/departamento", "/departament", "/departamendu", "/seccion-departamental",
    "/investigacion", "/recerca", "/ikerketa", "/grupos-investigacion",
    "/noticias", "/noticies", "/novas", "/albisteak", "/agenda", "/eventos",
    "/profesorado", "/directorio", "/pdi", "/pas", "/buzon", "/contacto",
    "/transparencia", "/normativa", "/empleo", "/convenios",
    "/cfp/", "/formacion-permanente", "/titulos-propios", "/titulospropios",
    "/estudios-propios", "/formacion-continua", "/cursos-verano", "/extension-universitaria"
]

SPIDER_TRAP_PATH_MARKERS = [
    "/agenda/", "/calendario/", "/calendar/", "/eventos/", "/events/", 
    "/noticias/", "/news/", "/actualidad/", "/tag/", "/category/", 
    "/etiqueta/", "/autor/", "/author/", "/login", "/signin", 
    "/user/login", "/search/node", "/comentarios/", "/feed", "/rss",
    "/aviso-legal", "/politica-privacidad", "/cookies", "/mapa-web"
]

HUB_ACADEMIC_KEYWORDS = [
    "grados", "graus", "graos", "graduak", "bachelor",
    "masteres", "masters", "màsters", "posgrado", "postgrado", "postgrau", "posgrao",
    "oferta-academica", "oferta_academica", "oferta-formativa", "oferta-de-grados", "oferta-de-masteres",
    "estudios", "estudis", "estudos", "estudios-ofertados", "titulaciones", "titulacions",
    "facultades", "facultats", "facultad", "facultat", "centros", "centres", "planes-de-estudio",
    "calidad", "qualitat", "kalitatea", "sgic", "verificacion", "verificacio", "memorias", "memoria-verificada"
]

# Palabras clave para la detección prioritaria de Memorias Verificadas (ANECA / AQU / ACCUA / SGIC)
MEMORIA_VERIFICADA_KEYWORDS = [
    "memoria", "verificad", "verificacio", "verificacion", "autoinforme",
    "acreditac", "acreditacio", "acreditacion", "informe-modificacion",
    "informemod", "sgic", "calidad", "qualitat", "kalitatea"
]

# Palabras clave para la detección dinámica de subpáginas docentes dentro de la ficha de titulación
ACADEMIC_SUBPAGE_KEYWORDS = [
    "plan de estudios", "plan d'estudis", "pla d'estudis", "pla de estudis", "plan", "pla",
    "seccions/pla-estudis", "seccions/plan-estudios", "seccions", "malla", "malla-curricular",
    "asignaturas", "assignatures", "subjects", "materias", "guia docente", "guía docente",
    "guias docentes", "guies docents", "itinerario", "itineraris", "itinerarios", "docencia",
    "estructura", "curriculum", "syllabus", "irakasgaiak", "ikasketa-plana", "courses", "sia", "apps"
]

# Palabras clave y subdominios institucionales de portales de gestión docente y centros
INSTITUTIONAL_PORTAL_KEYWORDS = [
    "apps", "sia", "secretaria", "portal", "sies", "cvnet", "guias", "gestion", "ujiapps", "academico", "estudis",
    "centros", "centres", "facultades", "facultats", "facultade", "escuelas", "escoles", "escolas", "ikastegiak", "campus"
]

# Metadatos de ficha administrativa a descartar para evitar confusión con asignaturas (Multilingüe: ES, CA, GL, EU)
INVALID_METADATA_LABELS = {
    "cuota de reserva", "precio total", "importe total", "coste total",
    "centro", "modalidad", "idioma", "matricula", "matrícula",
    # ES
    "centro de gestión", "centro de gestion", "modalidad de docencia", "ámbito de conocimiento",
    "ambito de conocimiento", "idioma de impartición", "idioma de imparticion", "idioma de docencia",
    "nota de corte", "precio orientativo por crédito", "precio orientativo", "plazas de nuevo ingreso",
    "plazas", "duración de los estudios", "duración", "duracion", "datos del grado", "datos del máster",
    "jefe de estudios", "coordinador", "coordinación", "dirección de correo", "prácticas externas", "practicas externas",
    # CA / VA
    "centre de gestió", "centre de gestio", "modalitat de docència", "modalitat de docencia",
    "àmbit de coneixement", "ambit de coneixement", "idioma de docència", "idioma de docencia",
    "nota de tall", "nota de tall / preinscripció", "preu orientatiu per crèdit", "preu orientatiu",
    "places de nou ingrés", "places", "durada", "dades del grau", "dades del màster", "dades del master",
    "cap d'estudis", "adreça electrònica", "pràctiques externes", "practiques externes",
    # GL
    "centro de xestión", "modalidade de docencia", "lingua de docencia", "nota de corte",
    "prezo por crédito", "prazas", "duración", "datos do grao", "datos do máster", "prácticas externas",
    # EU
    "kudeaketa zentroa", "irakaskuntza modalitatea", "ebaki nota", "kredituko prezioa",
    "plazak", "iraupena", "graduaren datuak", "masterraren datuak", "kanpoko praktikak"
}

ORGANIC_AFFILIATED_HUB_KEYWORDS = [
    "adscrit", "adscrito", "adscrita", "centres adscrits", "centros adscritos",
    "escuela adscrita", "instituto adscrito", "escola", "escuela", "institut", "instituto",
    "fundacio", "fundacion", "consorcio", "alianza", "sea-eu", "erasmus", "eunice", 
    "charmeu", "arqus", "civica", "civis", "eut+"
]

# Dominios externos que pueden contener enlaces institucionales pero no planes curriculares
ORGANIC_EXTERNAL_DOMAIN_DENYLIST = frozenset({
    "erasmusplay.com",
    "sepie.es",
    "juntadeandalucia.es",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "pinterest.com",
    "sharepoint.com",
    "dropbox.com",
    "drive.google.com",
    "docs.google.com",
    "forms.office.com",
})

EUROPEAN_ALLIANCES_KEYWORDS = [
    "erasmus mundus", "joint master", "european master", "sea-eu", "eunice", 
    "charmeu", "charm-eu", "arqus", "civica", "civis", "eut+", "neurotecheu", 
    "circle u", "unite!", "enlight", "4eu+", "una europa", "eureca-pro", "ingenium"
]

# Inferencia de esquemas en resoluciones BOE (RD 822/2021)
BOE_SCHEMA_CONCEPT_VOCABULARY = {
    "modulo": ["modulo", "módulo", "modul", "mòdul"],
    "materia": ["materia", "materias"],
    "asignatura": [
        "asignatura", "asignaturas", "denominación", "denominacion",
        "nombre", "actividad", "assignatura", "irakasgaia"
    ],
    "tipo": ["tipo", "carácter", "caracter", "tipus", "mota", "modalidad"],
    "creditos": ["créditos", "creditos", "crèdits", "credits", "ects", "kredituak"],
    "curso": ["curso", "curs", "año", "ano", "maila"],
    "semestre": ["semestre", "cuatrimestre", "quadrimestre", "lauhilekoa", "organización temporal", "organizacion temporal"],
    "especialidad": ["especialidad", "mención", "mencion", "itinerario"]
}

BOE_SPURIOUS_MARKERS = [
    "boletín oficial del estado", "boletin oficial", "cve: boe-", "el rector", "la rectora",
    "el decano", "la decana", "el secretario", "la secretaria", "doy fe", "ante mí",
    "distribución de créditos", "total de créditos", "rama de conocimiento", "ámbito de conocimiento",
    "centro de impartición", "menciones: no tiene", "condiciones de terminación"
]

# Stop words en español para extracción discriminativa de lemas
SPANISH_STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "a", "al", "por", "con", "sin", "sobre", "para", "entre", "hacia", "desde", "hasta", "segun", "tras", "durante", "mediante",
    "y", "e", "o", "u", "ni", "que", "como", "donde", "cuando",
    "graduado", "graduada", "graduados", "graduadas", "grado", "grados",
    "master", "masteres", "máster", "másteres",
    "doctor", "doctora", "doctorado", "doctorados",
    "titulo", "titulos", "titulacion", "titulaciones", "título", "títulos", "titulación", "titulaciones",
    "estudio", "estudios", "plan", "planes", "oficial", "oficiales",
    "universidad", "universidades", "universitaria", "universitarias", "universitario", "universitarios",
    "conducente", "conducentes", "obtencion", "obtención", "superacion", "superación",
    "anexo", "anexos", "resolucion", "resolución", "decreto", "orden", "acuerdo",
    "centro", "centros", "facultad", "facultades", "escuela", "escuelas",
    "programa", "programas", "ensenanzas", "enseñanzas", "ensenanza", "enseñanza",
    "rama", "ramas", "conocimiento", "conocimientos", "mencion", "mención", "menciones",
    "distribucion", "distribución", "creditos", "créditos", "resumen", "estructura",
    "apartado", "materia", "materias", "asignatura", "asignaturas", "modulo", "módulo",
    "docon", "rector", "rectora", "secretario", "secretaria", "emilio", "lora", "tamayo",
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    "bachelor", "bachelors", "master", "masters", "doctor", "phd", "degree", "degrees",
    "and", "in", "of", "for", "with", "the", "an", "science", "sciences",
    "engineering", "studies", "study", "university", "business", "management", "international",
    "applied", "advanced", "official", "curriculum", "syllabus",
    "grau", "graus", "estudis", "estudi", "pla", "plans", "oficial", "oficials",
    "universitat", "universitats", "universitari", "universitaris", "universitaria", "universitaries",
    "ciencies", "ciències", "socials", "juridiques", "jurídiques", "humanitats", "enginyeria", "enginyeries", "dels", "deles", "dela", "per", "amb",
    "grao", "graos", "estudos", "estudo", "plano", "planos", "universidade", "gradua", "graduak", "masterra", "unibertsitatea",
    "avanzado", "avanzada", "avanzados", "avanzadas", "avancat", "avancats", "avancada", "avancades", "advanced",
    "aplicado", "aplicada", "aplicados", "aplicadas", "aplicat", "aplicats", "applied",
    "fundamental", "fundamentales", "basic", "basico", "basica",
    "contemporaneo", "contemporanea", "contemporani", "contemporania", "contemporary",
    "comparado", "comparada", "comparat", "comparats", "comparative",
    "interdisciplinar", "interdisciplinario", "interdisciplinaria", "multidisciplinar",
    "internacional", "international", "global", "europeo", "europea", "european",
    "http", "https", "www", "html", "htm", "php", "asp", "aspx", "pdf", 
    "com", "org", "net", "edu", "cat", "index", "web", "portal", "default",
    "site", "sites", "page", "pages", "view", "link", "param", "param1", "param2", "grau", "graus"
}

# Stopwords de títulos académicos multilingües (ES / CA / GL / EU / EN)
TITLE_STOPWORDS = {
    "grado", "grados", "graduado", "graduada", "graduats", "graduades", "grau", "graus", "grao", "graos", "gradua", "graduak", "bachelor", "undergraduate",
    "máster", "master", "másteres", "masteres", "màster", "màsters", "masterra", "masterrak", "postgrado", "posgrado", "postgrau", "posgrao", "postgraduate",
    "doctor", "doctora", "doctorado", "doctorados", "doctorat", "doctorats", "doutoramento", "doktoregoa", "doctorate", "phd",
    "universitario", "universitaria", "universitaris", "universitaries", "oficial", "oficials", "programa", "programas", "título", "titulo", "titulacion", "titulaciones", "titulacions",
    "estudio", "estudios", "estudis", "estudos", "ikasketak", "enseñanza", "ensenanza", "mención", "mencion",
    "universidad", "universidades", "universitat", "universitats", "universidade", "unibertsitatea", "university",
    "sobre", "entre", "para", "como", "esta", "este", "estos", "estas", "del", "los", "las", "por", "con", "una", "uno", "que", "sus", "mas", "más",
    "autónoma", "autonoma", "politécnica", "politecnica", "internacional", "nacional", "distancia",
    "en", "the", "and", "for", "of", "in", "to", "i", "de", "a", "el", "la", "l'", "d'", "els", "les", "o", "u",
    "avanzado", "avanzada", "avanzados", "avanzadas", "avancat", "avancats", "avancada", "avancades", "advanced",
    "aplicado", "aplicada", "aplicados", "aplicadas", "aplicat", "aplicats", "applied",
    "fundamental", "fundamentales", "basic", "basico", "basica",
    "contemporaneo", "contemporanea", "contemporani", "contemporania", "contemporary",
    "comparado", "comparada", "comparat", "comparats", "comparative",
    "http", "https", "www", "html", "htm", "php", "asp", "aspx", "pdf", "edu", "cat", "com", "org", "net"
}

# Cabeceras de tabla canónicas en planes de estudio multilingües
HEADER_KEYWORDS = [
    "código", "codigo", "asignatura", "asignaturas", "materia", "materias", "denominación", "denominacion",
    "nombre", "créditos", "creditos", "ects", "carácter", "caracter", "tipo", "curso", "cuatrimestre", "semestre", "modulo", "módulo",
    "assignatura", "assignatures", "matèria", "materies", "crèdits", "credits", "caràcter", "tipus", "curs", "quadrimestre", "modul",
    "asineira", "asineiras", "créditos", "carácter", "ano", "cuadrimestre", "módulo",
    "irakasgaia", "irakasgaiak", "kredituak", "maila", "ikasturtea", "mota", "lauhilekoa",
    "subject", "subjects", "course", "courses", "module", "credits", "type", "year", "semester", "term", "syllabus"
]

# Palabras clave y metadatos no curriculares a descartar
INVALID_SUBJECT_KEYWORDS = [
    "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado",
    "dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte",
    "luns", "mércores", "venres",
    "astelehena", "asteartea", "asteazkena", "osteguna", "ostirala", "larunbata",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "aula magna", "aula virtual", "número de aula", "numero de aula",
    "horario de clases", "horari de classes", "timetable", "schedule",
    "calendario de exámenes", "calendari d'exàmens", "egutegia",
    "convocatoria ordinaria", "convocatoria extraordinaria",
    "suspenso", "aprobado", "notable", "sobresaliente", "matrícula de honor", "matricula de honor",
    "calificación cualitativa", "calificacion cualitativa", "calificación numérica", "calificacion numerica",
    "calificación estándar", "calificacion estandar", "escala de calificaciones", "tabla de equivalencias",
    "baremo", "convalidación", "convalidacion", "reconocimiento de créditos", "reconocimiento de creditos",
    "suspes", "suspès", "aprovat", "excel·lent", "matricula d'honor", "matricula de honor",
    "qualificació qualitativa", "qualificacio qualitativa", "qualificació numèrica", "qualificacio numerica",
    "escala de qualificacions", "taula d'equivalències", "taula dequivalencies", "reconeixement de crèdits", "reconeixement de credits",
    "sobresalinte", "cualificación cualitativa", "cualificacion cualitativa", "táboa de equivalencias", "taboa de equivalencias", "recoñecemento de créditos",
    "ez-gai", "oso ondo", "bikain", "ohorezko matrikula", "kalifikazio kualitatiboa", "kalifikazio numerikoa", "kreditu-aitorpena",
    "grading scale", "qualitative grade", "numerical grade", "credit recognition",
    "buscar por", "1º apellido", "2º apellido", "listado simple", "listado detallado", "cerca per", "bilatu",
    "plazas ofertadas", "plazas de nuevo ingreso", "plazas disponibles", "places de nou ingrés", "prazas",
    "nota de corte", "notas de corte", "nota de tall", "ebaki nota", "precios públicos", "prezo por crédito",
    "política de cookies", "politica de cookies", "política de privacidad", "politica de privacidad",
    "protección de datos", "proteccion de datos", "datos de carácter personal", "datos de caracter personal",
    "responsable del tratamiento", "delegado de protección", "delegado de proteccion", "dpo",
    "derechos de los interesados", "base jurídica", "base juridica", "ejercicio de derechos",
    "cookie", "cookies", "google analytics", "_ga", "_gid", "_fbp", "consentimiento", "duración de la cookie"
]

# Marcadores de matrices tipográficas invertidas/espejadas en BOE antiguo (2009-2014)
REVERSED_SPANISH_MARKERS = [
    "oxena", "odnum", "airotsih", "soidutse", "sotidérc", "sotiderc", "odaudarg", "adaudarg",
    "retsám", "retsam", "odarg", "ohcered", "aígolocisp", "acitámrofni", "aírenigneg",
    "airenigneg", "aicneic", "lartsemes", "latot", "acisáb", "acisab", "sairotagilbo", "savitatpo", "laveidem"
]

# Marcadores para excluir plantillas de Curriculum Vitae (CVN)
CV_EXCLUSION_MARKERS = [
    "curriculum_modelo", "curriculum_vitae", "curriculum-vitae", "cv_normalizado",
    "cvn", "modelo_normalizado", "curriculum_normalizado", "anexo_iii_curriculum",
    "proyectos_", "proyectos-grupo", "proyecto_tesis", "lineas_investigacion",
    "modelo_cv", "cv_form"
]

# Patrones de preámbulo administrativo de resoluciones rectorales/ministeriales
PREAMBLE_REJECTION_PATTERNS = [
    r"relacionados\s+a\s+continuaci[oó]n",
    r"este\s+rectorado\s+ha\s+resuelto",
    r"publicar\s+(?:el|los)\s+plan(?:es)?\s+de\s+estudios",
    r"publicaci[oó]n\s+del?\s+plan\s+de\s+estudios",
    r"aprobar\s+(?:el|los)\s+plan",
    r"haberse\s+establecido",
    r"una\s+vez\s+homologad",
    r"homologado\s+por",
    r"inscrito\s+en\s+el\s+registro",
    r"previa\s+homologaci[oó]n",
    r"consejo\s+de\s+ministros",
    r"consejo\s+de\s+gobierno",
    r"t[ií]tulos\s+oficiales\s+de\s+grado\s+siguientes",
    r"siguientes\s+ense[ñn]anzas",
    r"siguientes\s+planes"
]

NON_OFFICIAL_COURSE_MARKERS = [
    "extension-universitaria", "cursos-extension", "precios-publicos", 
    "formacion-continua", "titulos-propios", "diploma-extension", "master-propio"
]

UMBRELLA_BRANCH_WORDS = {
    "ingenieria", "enginyeria", "engineering",
    "educacion", "educacio", "education",
    "comunicacion", "comunicacio", "communication",
    "administracion", "administracio", "administration",
    "ciencias", "ciencies", "sciences", "science",
    "humanidades", "humanitats", "humanities",
    "estudios", "estudis", "studies",
    "lengua", "lenguas", "llengua", "llengues", "language", "languages",
    "literatura", "literatures", "literature",
    "filologia", "filologies", "philology",
    "artes", "arts"
}
