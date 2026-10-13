# SismoSantander · Requerimientos de la API

Documento 1 de 5 de la especificación de la API (ver [README](README.md)). Cubre los entregables 1, 2, 3 y 16:
requerimientos detectados, inventario de variables, fuentes verificadas y decisiones pendientes.

> **Estado:** especificación (contrato). La API de este documento se implementa por fases (ver
> [frontend-integration.md §6](frontend-integration.md#6-plan-de-implementación-por-fases)). Lo que hoy existe en el
> repositorio es `api.py` (API del modelo, rutas en español, sin prefijo `/api/v1`), que esta especificación
> reemplaza de forma gradual.

---

## 1. Resumen de los requerimientos detectados

### 1.1 Qué se pudo inspeccionar y qué no

| Elemento | ¿Inspeccionado? | Consecuencia |
|---|---|---|
| Frontend React (Dashboard, Mapa, Comparativo, Zonas prioritarias, Agente, Histórico, Acerca de) | **No.** No está en ninguno de los repositorios accesibles desde esta sesión. | Los requerimientos por página salen de la descripción del prompt del equipo, no del código. Cuando el frontend esté disponible hay que confrontar nombres de props y componentes con la [matriz de integración](frontend-integration.md). |
| Datos simulados del frontend (Los Santos, Zapatoca, Betulia, Málaga, Aratoca, San Andrés, Barrancabermeja) | No | Se tratan **solo como ejemplos de interfaz**. Ningún valor de esta especificación sale de ellos. |
| Exports reales del catálogo SGC en `datos/raw/sgc/` (5 archivos `.xlsx`) | **Sí** | Base verificada del inventario de variables (§2). |
| Pipeline y modelo (`scripts/00–07`, `modelo/modelo_kmeans.json`, `salidas/`) | **Sí** | Base de las variables derivadas, del ranking y de las fuentes sísmicas. |
| Documentación en línea del SGC | **No se pudo** (ver §3) | No se asume ninguna API oficial del SGC; la API propia se alimenta de archivos exportados. |

### 1.2 Requerimientos funcionales por área

| Área (página) | Necesita de la API | Endpoints (ver [api-endpoints.md](api-endpoints.md)) |
|---|---|---|
| Estado y metadatos | Salud, versión, fuente, fecha de actualización, periodo cubierto, nº de registros, cobertura, variables y unidades, modo de datos (real/simulado) | `GET /health`, `GET /meta`, `GET /meta/variables` |
| Dashboard | Indicadores con definición, unidad, periodo, filtros y denominador; distribuciones por magnitud, profundidad y tipo de magnitud; variación vs periodo anterior; serie temporal; municipios con eventos; calidad | `GET /stats/summary`, `GET /stats/distribution`, `GET /stats/timeseries`, `GET /stats/quality` |
| Mapa interactivo | Epicentros filtrables (bbox, fechas, magnitud, profundidad, municipio) en formato Leaflet; detalle para popup; agregación por celdas sin confundirla con epicentros; coropleta por municipio | `GET /events/geojson`, `GET /events/grid`, `GET /events/{id}`, `GET /municipalities/geojson`, `GET /stats/by-municipality`, `GET /seismic-sources` |
| Análisis comparativo | Comparar municipios y periodos con el mismo criterio de agregación; series alineadas; distribuciones | `GET /compare/municipalities`, `GET /compare/periods`, `GET /stats/by-municipality` |
| Zonas prioritarias | Ranking con puntuación explicada, variables usadas, versión del método y fecha de cálculo, **sin llamarlo riesgo ni probabilidad** | `GET /priority-zones`, `GET /priority-zones/{code}`, `GET /priority-zones/methods` |
| Agente de recomendación | Indicadores de un municipio, reglas explícitas, qué variables activaron cada recomendación, advertencias por datos insuficientes, registro opcional de consultas, IA futura sin simularla | `GET /recommendations/rules`, `POST /recommendations/evaluate`, `POST /assistant/ask` (501 hasta implementarse) |
| Histórico | Lista paginada con filtros y orden estable, detalle, exportación CSV, campos originales y normalizados, procedencia y calidad | `GET /events`, `GET /events/{id}`, `GET /events/export`, `GET /meta/variables` |
| Importación y calidad (admin) | Subir exports, validar columnas y codificación, duplicados, normalizar, informe de calidad, estado e historial de importaciones; protegido | `POST /admin/imports`, `GET /admin/imports`, `GET /admin/imports/{id}`, `POST /admin/recompute`, `GET /admin/query-log` |
| Acerca de (pendiente) | Fuentes, método, limitaciones y versión | `GET /meta`, `GET /priority-zones/methods` (no requiere endpoint propio) |

### 1.3 Requerimientos transversales

1. **Una sola fuente de verdad:** todas las cifras salen de la misma tabla de eventos y del mismo constructor de
   filtros. Con los mismos filtros, dashboard, mapa, comparativo e histórico devuelven los mismos conteos.
2. **Trazabilidad:** cada evento conserva su fila original sin modificar y su procedencia (archivo, fila, fecha de
   importación, fecha de descarga declarada, parámetros de la consulta del portal).
3. **Separación de orígenes:** cada campo se marca como `original` (tal como lo publica el SGC), `normalizado`
   (mismo dato, tipo/unidad homogénea), `derivado` (calculado por el sistema), `asociado` (asignación geográfica
   con un método) o `modelo` (salida de HDBSCAN/K-Means). Nada calculado se atribuye al SGC.
4. **Sin cifras inventadas:** si un indicador no se puede calcular devuelve `value: null` con `null_reason`.
5. **Conceptos separados:** *magnitud* (tamaño del sismo en la fuente) ≠ *intensidad* (efecto en un lugar, no
   está en el catálogo) ≠ *amenaza* (probabilidad de exceder un movimiento del suelo; requiere un modelo
   probabilístico) ≠ *riesgo* (amenaza × exposición × vulnerabilidad). Con el catálogo solo se mide **actividad
   sísmica observada**; ver §2.5.
6. **Prototipo de hackathon:** implementable por dos estudiantes con FastAPI + SQLite (ver
   [data-model.md](data-model.md)).

---

## 2. Inventario de variables

### 2.1 Variables originales verificadas (exports del catálogo SGC en `datos/raw/sgc/`)

Archivos verificados: `Csg_2020.xlsx` … `Csg_2024.xlsx` (hoja *Reporte Eventos*). Cada archivo trae primero un
bloque **PARAMETROS DE BUSQUEDA** (13 filas) y luego la tabla. Encabezados exactos (fila 14):

| # | Columna original (exacta) | Tipo observado | Unidad | Nulos en los 5 archivos | Campo normalizado |
|---|---|---|---|---|---|
| 1 | `FECHA - HORA UTC` | texto `YYYY-MM-DD HH:MM:SS` | UTC (lo dice el encabezado) | 0 | `origin_time_utc` |
| 2 | `LATITUD (°)` | número | grados decimales | 0 | `latitude` |
| 3 | `LONGITUD (°)` | número | grados decimales (oeste negativo) | 0 | `longitude` |
| 4 | `PROF. (Km)` | número | km | 0 | `depth_km` |
| 5 | `MAGNITUD` | número | adimensional | 0 | `magnitude` |
| 6 | `TIPO MAGNITUD` | texto (12 valores: `MLr_3`, `MLr_vmm`, `MLr`, `MLr_2`, `M_MLr`, `M`, `Mw(mB)`, `Mw`, `MLr_4`, `MLr_1`, `mb`, `MLv`) | — | 0 | `magnitude_type` (original) + `magnitude_type_group` (derivado: `ML`, `Mw`, `mb`, `M`) |
| 7 | `FASES` | entero | nº de fases | 0 | `phase_count` |
| 8 | `RMS (Seg)` | número | s | 0 | `rms_s` |
| 9 | `GAP (°)` | número | grados | 0 | `azimuthal_gap_deg` |
| 10 | `ERROR LATITUD (Km)` | número | km | 0 | `latitude_error_km` |
| 11 | `ERROR LONGITUD (Km)` | número | km | 0 | `longitude_error_km` |
| 12 | `ERROR PROFUNDIDAD (Km)` | número | km | 0 | `depth_error_km` |
| 13 | `REGION` | texto `Municipio - Departamento, País` (100 % de las filas siguen ese patrón) | — | 0 | `region_reported` (original) |
| 14 | `ESTADO` | texto: `manual` (63 996), `automatic` (31) | — | 0 | `review_status` |

Parámetros de búsqueda del bloque superior (también originales, se guardan por importación): `DEPARTAMENTO`,
`MUNICIPIO`, `FECHA_INICIAL`, `FECHA_FINAL`, `TIPO CONSULTA`, `TOTAL REGISTROS`, `LONGITUD/LATITUD MINIMA/MAXIMA`,
`MAGNITUD MINIMA/MAXIMA`, `PROFUNDIDAD MINIMA/MAXIMA`, `RMS`, `GAP` y `ERROR … MIN./MAX.`. Los 5 exports se pidieron
con `DEPARTAMENTO = Santander`, `TIPO CONSULTA = cuadrante`, sin filtro efectivo de magnitud ni de profundidad.

Contenido: 64 037 filas, del 2020-03-02 al 2025-03-01; magnitud 0.2–5.6; profundidad 0–212.8 km (75 valores
originales entre −5 y 0 km). **No traen identificador de evento ni enlaces** (QuakeML, mapa).

### 2.2 Columnas mencionadas por el equipo y NO verificadas

El prompt del equipo menciona otro formato de export: `Fecha-Hora (UTC)`, `Lat(Â°)`, `Long(Â°)`, `Prof(Km)`, `Mag.`,
`Tipo Mag.`, `Fases`, `Rms(Seg)`, `Gap(°)`, `Error Lat(Km)`, `Error Long(Km)`, `Error Prof(Km)`, `Region`, `QuakeML`,
`Mapa`, `Estado`. **No hay ningún archivo con ese formato en el repositorio**, así que:

- Sus 14 primeras columnas se diseñan como **alias** de las de §2.1 (misma semántica, distinto nombre). El
  reconocedor de columnas actual (`scripts/02_unificar_sgc.py → mapear_columnas`) ya las reconoce por prefijo
  (`LAT…`, `LON…`, `PROF…`, `MAG…`, `TIPO … MAG`, `FECHA … HORA`).
- `Lat(Â°)` y `Long(Â°)` son **mojibake** (UTF-8 leído como Latin-1) de `Lat(°)` y `Long(°)`. El importador debe
  detectarlo, repararlo y anotarlo en el informe de calidad (ver [data-model.md §6](data-model.md#6-estrategia-de-importación)).
- `QuakeML` y `Mapa` se modelan como campos **opcionales** (`quakeml_url`, `map_url`). Si `QuakeML` trae un
  identificador del evento del SGC, se usará como `source_event_id` (formato **por verificar** con un archivo real).
- **Acción:** pedir al equipo un archivo de ejemplo de ese export para confirmar nombres, codificación y zona horaria.

Columnas del **formato antiguo** del portal (consulta jun-1993 a feb-2018; *FECHA*, *HORA_UTC*, *MAGNITUD Ml*,
*MAGNITUD Mw*, …): el importador ya las contempla, pero **no hay ningún archivo de ese formato** para verificarlas.
El reto exige unificar ambos formatos: es la principal brecha de datos (ver §4).

### 2.3 Variables normalizadas y derivadas (calculadas por el sistema, nunca atribuidas al SGC)

| Campo | Origen | Cómo se obtiene |
|---|---|---|
| `event_id` | derivado | Identificador estable propio: `sgc-` + 16 hex de SHA-1 sobre (`origin_time_utc`, `latitude`, `longitude`, `depth_km`, `magnitude`) normalizados; si existe `source_event_id`, se usa ese. |
| `origin_time_utc` | normalizado | ISO 8601 con `Z`. Si una fuente declara hora local (Colombia, UTC−5) se convierte y se guarda `time_zone_declared`. |
| `origin_time_raw`, `time_zone_declared` | original | Texto tal como venía y la zona horaria que indica el encabezado (`UTC`, `local`, `no declarada`). |
| `magnitude_type_group` | derivado | Familia de magnitud: `ML` (todas las `MLr*`, `M_MLr`, `MLv`), `Mw` (`Mw`, `Mw(mB)`), `mb`, `M` (sin especificar). |
| `department_reported`, `country_reported` | derivado de un original | Separados del texto `REGION` (`… - Santander, Colombia`). |
| `municipality_code`, `municipality_name` | asociado | Polígono DANE MGN 2018 que contiene el epicentro (`method: point_in_polygon_mgn2018`). En 2020–2025 el 99.93 % de los epicentros cae en un polígono de Santander. |
| `municipality_match_region` | derivado | Si el municipio del polígono coincide con el de `REGION`. Coincide en el **90.8 %** de los eventos: por eso el municipio original y el asociado se exponen por separado. |
| `quality_flags`, `is_reliable` | derivado | Criterios de localización: `gap_gt_270`, `rms_gt_1_2_m_lt_3`, `horizontal_error_gt_10km`, `depth_error_gt_10km`, `phases_lt_6`. `is_reliable = sin banderas`. No elimina eventos. |
| `duplicate_of` | derivado | Evento canónico si es casi-duplicado (≤ 3 s y ≤ 10 km). |
| `depth_class` | derivado | Clase descriptiva por rango: `0-30`, `30-70`, `70-300`, `>300` km. |
| `energy_joules` | derivado | log10 E = 1.5 M + 4.8 (Gutenberg–Richter). Aproximación; mezcla tipos de magnitud. |
| `seismic_source_code`, `seismic_source_type` | modelo | Fuente asignada por HDBSCAN (nivel 1): `Nido de Bucaramanga`, `Cortical`, `Intermedia`, `Difusa (ruido)`. |
| Variables por municipio (21 de modelo) | derivado / modelo | Ver `docs/diccionario_datos.md`: tasas, magnitudes, energía, profundidad, distancias y fuentes. |
| `cluster_level`, `catalog_index` | modelo | Nivel K-Means (5 niveles) e índice 0–100 del pipeline (ver §2.5). |
| `import_id`, `imported_at`, `source_file`, `source_row` | procedencia | Registro de la importación. |

### 2.4 Datos simulados

- El backend **no contiene datos simulados**. `GET /meta` devuelve `data_mode: "real"` mientras todas las fuentes
  cargadas sean exports reales.
- Si el equipo necesita datos de demostración, se cargan como una **fuente distinta** (`source.kind = "simulated"`)
  y la API pasa a `data_mode: "mixed"`; cada evento expone `source.kind` y el frontend debe mostrar un aviso.
- Los municipios de ejemplo del frontend se reemplazan por `GET /municipalities` (87 municipios reales del DANE).

### 2.5 Actividad, amenaza, exposición y vulnerabilidad: qué se puede afirmar con estos datos

| Dimensión | ¿Disponible? | Qué devuelve la API |
|---|---|---|
| **Actividad sísmica observada** | Sí (catálogo SGC) | Conteos, tasas, magnitudes, profundidades, energía, cercanía a fuentes. |
| **Amenaza sísmica** | **No.** Requiere un modelo probabilístico de movimiento del suelo (tipo PSHA). | `null` con `availability: "not_computed"`. El índice del pipeline es un *proxy relativo de actividad y cercanía a fuentes*, no una amenaza. |
| **Exposición** | No (falta población DANE; el pipeline la admite como opcional) | `null` con `availability: "missing_data"`. |
| **Vulnerabilidad** | No (no hay datos de tipología constructiva) | `null` con `availability: "missing_data"`. |

Consecuencias en el contrato:
- El ranking se llama **"zonas prioritarias por actividad sísmica observada"**; la puntuación se llama
  `observed_activity_score`, nunca *riesgo* ni *probabilidad*.
- El nivel K-Means se expone como `cluster_level` ("nivel relativo de actividad sísmica").
- El README del modelo y la convocatoria hablan de "riesgo sísmico relativo". Para la presentación conviene decir
  *"clasificación relativa de la actividad sísmica observada, primer componente del riesgo"* (ver §4, decisión D5).

---

## 3. Fuentes oficiales: verificación y limitaciones

| Fuente | URL | Verificada | Qué se sabe con certeza | Limitaciones |
|---|---|---|---|---|
| Catálogo sísmico SGC – RSNC (portal de consultas) | <http://bdrsnc.sgc.gov.co/paginas1/catalogo/> | **Solo a través de los archivos.** El dominio no resolvió desde esta sesión. | Los 5 exports: columnas de §2.1, bloque de parámetros, fecha de creación interna 2026-10-13. | No se conoce una API pública documentada; la vía de obtención es exportar desde el portal. No se pudo confirmar términos de uso ni límites. |
| Catálogo de sismos SGC (sitio nuevo) | <https://www.sgc.gov.co/catalogo> | **No.** Aparece en buscadores; la página no se pudo abrir. | — | Un resumen de buscador indica que ahí las fechas están en **hora local (UTC−5)**; **no verificado**. Nuestros exports dicen explícitamente `UTC`. El importador respeta lo que diga cada encabezado (decisión D2). |
| Visor de sismos SGC | <https://www.sgc.gov.co/sismos> | No | — | No se usa como fuente en tiempo real. |
| Portal de datos abiertos SGC | <https://datos.sgc.gov.co/> | No | — | Podría ofrecer descargas (CSV/GeoJSON); **no se confirmó** que publique el catálogo sísmico. |
| Catálogo Sísmico Integrado (CSI) | <https://revistas.sgc.gov.co/index.php/boletingeo/article/view/665> | No (dominio no resolvió) | — | Producto distinto del catálogo RSNC (integra fuentes y usa Mw); útil a futuro, no se mezcla con el RSNC. |
| Sismicidad histórica SGC (SISH) | <https://sish.sgc.gov.co/visor/> | No | — | El pipeline la admite como opcional; hoy no hay archivo. |
| DANE MGN 2018 (municipios) | <https://geoportal.dane.gov.co/servicios/descarga-y-metadatos/descarga-mgn-marco-geoestadistico-nacional/> | **Sí, el archivo** (copia GeoJSON simplificada de <https://github.com/caticoa3/colombia_mapa>) | 87 municipios de Santander, código DIVIPOLA, área oficial (`MPIO_NAREA`). | El GeoJSON está simplificado (área calculada ≈ 5 % distinta de la oficial): los epicentros a < 1 km de un límite pueden asociarse al municipio vecino. |
| USGS ComCat | <https://earthquake.usgs.gov/fdsnws/event/1/> | No (bloqueado desde esta sesión) | — | API FDSN pública conocida; solo validación cruzada opcional, nunca fuente principal. |

Consecuencias de diseño:
1. **No se diseña ningún endpoint que dependa de una API externa del SGC.** La API propia se alimenta de exports
   (`.xlsx`/`.csv`) importados con trazabilidad.
2. La API **no consulta al SGC en tiempo real**: `GET /meta` informa `last_import_at`, `coverage.end` y
   `realtime: false`. El frontend nunca debe presentar los datos como "actualizados a hoy".
3. Si más adelante se verifica una fuente automática (USGS FDSN, datos abiertos del SGC), entra como otra `source`
   con su propio `import_id`, sin cambiar el contrato.

---

## 4. Preguntas y decisiones pendientes (entregable 16)

| # | Pregunta / decisión | Por qué importa | Propuesta por defecto |
|---|---|---|---|
| D1 | ¿Dónde está el código del frontend? | Validar nombres de componentes, props y estados de la [matriz](frontend-integration.md). | Compartir el repositorio o un `.zip`. |
| D2 | ¿Qué export usa el equipo (el `.xlsx` del portal o un `.csv` con `QuakeML`/`Mapa`)? ¿Hora UTC o local? | Nombres de columnas, codificación, `source_event_id`, zona horaria. | Mandar un archivo de ejemplo. Mientras tanto: respetar el encabezado (`UTC` → UTC; `local` → +5 h). |
| D3 | Exports del **formato antiguo** (antes de 2018-03) | Requisito obligatorio del reto (unificar ambos formatos). | Descargar al menos 2006–2018 por cuadrante y verificar el importador con ellos. |
| D4 | Área de estudio: ¿solo Santander (filtro por departamento) o cuadrante con margen de 50 km? | Los municipios de borde ven menos sismos con el filtro por departamento. | Cuadrante lat 5.2–8.7, lon −75.0 a −72.0; `department` filtra por el texto `REGION`. |
| D5 | Nombre de la puntuación en la UI | El reto dice "riesgo"; los datos solo sostienen "actividad observada". | UI: "Nivel relativo de actividad sísmica" con nota "no incluye exposición ni vulnerabilidad". |
| D6 | Filtro de calidad por defecto | Cambia los conteos. | `quality=all` en exploración (dashboard, mapa, histórico); los indicadores del modelo siempre usan `reliable` y lo declaran. |
| D7 | Mezcla de tipos de magnitud (ML y Mw) | Estadísticas de magnitud con tipos mezclados. | Se permite, con `meta.warnings` cuando hay más de una familia; filtro `magnitude_type`. |
| D8 | Textos de las recomendaciones | Deben ser responsables y revisados por alguien del equipo. | Reglas de ejemplo en [api-endpoints.md §G](api-endpoints.md#g-agente-de-recomendación); textos finales a validar. |
| D9 | ¿Importación desde la API en la demo o solo con el pipeline? | Seguridad y despliegue (sistema de archivos efímero). | Fase 1: solo pipeline (`run_all.py` + `08_cargar_base.py`). Admin en fase 3. |
| D10 | Asistente con IA generativa: ¿proveedor y presupuesto? | Costo, privacidad y riesgo de cifras inventadas. | `POST /assistant/ask` devuelve 501 hasta decidirlo; contrato de *grounding* ya definido. |
| D11 | Despliegue y origen del frontend | CORS, URL base. | Local: `http://localhost:5173` (Vite). Producción: definir dominio. |
| D12 | ¿Se agregará población DANE? | Habilita la dimensión de exposición. | Opcional; si llega, `exposure` pasa a `available`. |
