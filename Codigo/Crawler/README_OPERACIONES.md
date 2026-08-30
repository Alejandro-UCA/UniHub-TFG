# Operación y reproducibilidad del crawler

Este documento resume los procedimientos mínimos para ejecutar y auditar la Fase 1 de UniHub. La información publicada debe proceder de una fuente verificable; una extracción incompleta se conserva como diagnóstico, pero no se presenta como plan curricular completo.

## Entorno de pruebas

Desde `D:\Proyecto`, instalar las dependencias en un entorno aislado y ejecutar la batería completa:

```powershell
$env:PYTHONPATH='D:\Proyecto\.testdeps'
& 'C:\Users\aleja\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s Codigo\Pruebas -p 'test*.py' -v
```

La suite cubre parsers BOE/HTML/PDF, estrategias genéricas, persistencia, concurrencia, robots.txt, seguridad de la API, contrato de publicación y frontend.

El diagnóstico de capacidades se puede consultar con:

```powershell
& 'C:\Users\aleja\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' Codigo\Crawler\runtime_capabilities.py
```

La imagen Docker del crawler instala Chromium y Tesseract con idiomas
español, catalán, gallego, euskera e inglés. Si alguna capacidad falta, debe
aparecer en `missing`; no se debe interpretar un resultado vacío de OCR/SPA
como ausencia de datos sin revisar ese diagnóstico.

La ejecución normal es incremental: `CRAWLER_FULL_REVALIDATION=0` por defecto
y la caché de guías caduca a los siete días. Para una auditoría completa se
puede usar `CRAWLER_FULL_REVALIDATION=1` o `force`; el TTL se ajusta con
`CRAWLER_SUBJECT_GUIDE_CACHE_TTL` (segundos, `0` desactiva la caducidad). Cada
manifiesto guarda además las capacidades detectadas en
`execution.runtime_capabilities`, de modo que una ejecución degradada queda
identificada y no se confunde con una ausencia real de datos.

Cuando una ejecución limita el número de planes por universidad, `limit_degrees`
prioriza planes verificados y con asignaturas reales. Para asignaturas sin código,
`CRAWLER_MAX_SUBJECT_GUIDE_NO_CODE_CANDIDATES` limita las rutas heurísticas
(por defecto, 6; se puede reducir durante pruebas de coste).

## Diagnóstico y recuperación de SQLite

La caché SQLite es aceleradora; los JSON de planes son la referencia persistida del crawler. Antes de reparar una caché, detener las ejecuciones del crawler y realizar un diagnóstico de solo lectura:

```powershell
& 'C:\Users\aleja\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' Codigo\Crawler\cache_recovery.py Codigo\Crawler\Datos\unihub_cache.sqlite3
```

Si el diagnóstico confirma corrupción, la reparación conserva el fichero original y sus acompañantes WAL/SHM en una cuarentena recuperable, y crea una base nueva en la ruta original:

```powershell
& 'C:\Users\aleja\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' Codigo\Crawler\cache_recovery.py Codigo\Crawler\Datos\unihub_cache.sqlite3 --repair
```

No se debe borrar manualmente una caché corrupta ni sustituir un plan verificado por un candidato parcial. La persistencia aplica el mismo principio mediante el control de calidad y la cuarentena de candidatos.

Durante una ejecución, una SQLite ilegible o no disponible no aborta una parte:
checkpoint, ledger y caché de guías pasan automáticamente a modo degradado y
continúan con JSON o memoria. El resultado de cada parte lo deja explícito en
`persistence`; `completed` significa que el trabajo terminó sin excepción,
mientras que `degraded` identifica una incidencia de infraestructura que debe
revisarse antes de la siguiente campaña. El fichero original no se sobrescribe
automáticamente.

## Auditoría de una ejecución

Cada ejecución debe conservar su manifiesto JSON. Además del estado global, el manifiesto registra:

- titulaciones inspeccionadas;
- asignaturas consideradas y guías localizadas/no localizadas;
- planes reconciliados con los datos oficiales disponibles;
- asignaturas cargadas desde las fuentes institucionales localizadas;
- incidencias controladas y errores reales;
- universidades únicas procesadas y códigos de universidad;
- URL candidatas generadas/solicitadas, respuestas HTTP, bloqueos robots y
  errores de petición de la Parte 4.
- capacidades disponibles del entorno (navegador, OCR y dependencias faltantes).

La cobertura de guías se calcula sobre el conjunto de asignaturas que declara el plan oficial, no sobre una estimación artificial del total. Esto permite distinguir “sin guía pública localizada” de “no procesado”.

Para evitar regresiones entre universidades se puede versionar un corpus local
de HTML/PDF en un JSON con casos y expectativas (`*_min` para listas):

```powershell
& 'D:\Proyecto\.venv\Scripts\python.exe' Codigo\Crawler\parser_regression.py Codigo\Crawler\Datos\parser_corpus\corpus.json --output Codigo\Crawler\Datos\parser_corpus\last_report.json
```

El informe puntúa solo los campos declarados por cada caso y devuelve código
de salida distinto de cero si algún caso falla. Así se pueden añadir muestras
reales de cualquier universidad sin convertir el parser común en una colección
de reglas opacas por dominio.

## Fuentes y formatos

El núcleo no contiene ramas por universidad, código RUCT ni dominio. Parte 4
obtiene el dominio desde `universidades.json`, prioriza las URLs explícitas del
plan y usa el mismo descubrimiento acotado, descarga, validación de identidad,
caché y control de calidad para cualquier universidad española.

Las fuentes estructuradas se descubren por sus evidencias técnicas y se
procesan con la misma ruta común; nunca sustituyen la ruta genérica ni son
necesarias para procesar una universidad nueva. Los parsers HTML/PDF se seleccionan por la estructura y
las etiquetas del contenido, no por el host de la URL. Los planes sin código de
asignatura reciben candidatos acotados por nombre/slug; nunca se acepta una
respuesta solo porque devuelva HTTP 200.

Cuando una fuente presenta un formato nuevo, se añade un fixture de contenido
y una prueba de regresión para el parser o estrategia reutilizable. No se añade
una condición del tipo `u_code == ...` ni una cascada de URLs exclusiva de una
universidad.

Parte 4 construye una única vez por universidad un índice acotado desde
`robots.txt`, sitemaps XML/comprimidos y
unos pocos hubs académicos HTML. El índice se reutiliza para todas sus
asignaturas, conserva evidencias del origen (texto del enlace, título,
encabezado, ruta y `lastmod`), filtra al dominio institucional y se ordena por
código, nombre y señales de formato. Las cotas (`CRAWLER_SUBJECT_GUIDE_DISCOVERY_*`) impiden que esta
recuperación se convierta en un rastreo ilimitado; las métricas quedan en el
manifiesto como `guide_discovery_files` y `guide_discovery_urls`.
Las rutas con señales genéricas de noticias, personal, investigación,
convocatorias o contacto se descartan antes de entrar en el índice, salvo que
contengan una evidencia fuerte de guía o PDF. El ranking combina la ruta con
el texto visible del enlace y sus metadatos, sin consultar el dominio como una
regla de negocio.
El coste de resolución queda separado en `guide_candidate_urls_generated`,
`guide_candidate_urls_requested`, `guide_http_200`, `guide_http_404`,
`guide_http_other`, `guide_robots_denied` y `guide_request_errors`.
Los rechazos por robots.txt o por una política de acceso se contabilizan en
`guide_discovery_blocked`; así un cero de descubrimiento no se confunde con
una ausencia de guías en el portal.
Las guías recuperadas tras renderizar un shell JavaScript se contabilizan en
`guide_spa_fallbacks`.
Cada guía aceptada incorpora `calidad_extraccion`, con presencia y peso de
nombre, código, ECTS, temario, evaluación, competencias, resultados,
profesorado y departamento. La media se conserva en el manifiesto.

Los planes incorporan `snapshot_hash`. Cuando cambia el contenido estable se
archiva automáticamente la versión anterior bajo `history/planes_estudio`;
las marcas temporales no generan versiones nuevas.

Cada payload persistido incorpora `contrato_datos` con versión e incidencias
estructurales. El contrato no exige que el plan esté completo —eso lo decide
el control de calidad—, pero sí evita publicar estructuras malformadas o
valores numéricos imposibles.

Cada payload persistido incorpora `contrato_datos` con versión e incidencias
estructurales. El contrato no exige que el plan esté completo —eso lo decide
el control de calidad—, pero sí evita publicar estructuras malformadas o
valores numéricos imposibles.

La arquitectura no copia el crawler por universidad: el núcleo común resuelve
dominios, cursos, candidatos, descarga, parsing, identidad, caché y calidad.
Una universidad nueva comienza y permanece procesable mediante el núcleo
genérico, sin registrar su código, dominio o estructura en el código fuente.

Antes de guardar una guía, el control de identidad compara el nombre y el código solicitados con los extraídos. Las respuestas HTTP válidas pero pertenecientes a otra asignatura se rechazan y quedan contabilizadas en `guide_identity_rejected`.

## Criterios de calidad

Un resultado puede publicarse como verificado solo si mantiene la identidad de la titulación, una fuente institucional trazable y una estructura curricular coherente. Los planes sin BOE o sin contenido suficiente permanecen visibles como incompletos, con advertencia de calidad; nunca reciben texto curricular inventado.

El objetivo operativo no es forzar un 100 % ficticio, sino maximizar la recuperación real y medir explícitamente cada carencia: bloqueo por robots, ausencia de guía pública, cambio de formato, falta de resolución BOE o incompatibilidad entre catálogos.
