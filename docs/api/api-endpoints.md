# SismoSantander · Catálogo y contratos de los endpoints

Documento 3 de 5 (ver [README](README.md)). Cubre los entregables 6 (catálogo), 7 (contrato JSON de cada endpoint),
10 (filtros globales), 11 (errores) y 12 (seguridad y rendimiento). La versión formal está en
[openapi.yaml](openapi.yaml).

> **Sobre los ejemplos:** los valores de los ejemplos JSON se calcularon con el catálogo SGC real del repositorio
> (exports 2020-03-02 a 2025-03-01) y el pipeline actual. Sirven de referencia: cambian cuando se importen más datos.
> Los `request_id`, `data_version` y fechas de generación son ilustrativos.

---

## 0. Convenciones

| Tema | Regla |
|---|---|
| URL base | `http://localhost:8000/api/v1` (desarrollo). Versión en la ruta: un cambio incompatible crea `/api/v2`. |
| Formato | JSON UTF-8 (`application/json`). `/events/geojson`, `/events/grid` y `/municipalities/geojson` devuelven `application/geo+json`. `/events/export` devuelve `text/csv`. |
| Nombres | Campos y parámetros en inglés `snake_case`; textos para el usuario (`label`, `message`, `definition`) en español. |
| Fechas | Respuestas en ISO 8601 UTC con `Z` (`2024-03-02T00:12:34Z`). Fechas sin hora como `YYYY-MM-DD`. |
| Números | Siempre `number` JSON (nunca texto). Magnitud con 1 decimal; profundidad y errores en km con 2 decimales; porcentajes en 0–100 con 1 decimal. |
| Coordenadas | Grados decimales WGS84. En objetos JSON: `latitude`, `longitude`. En GeoJSON: `[longitude, latitude]` (orden del estándar). Para Leaflet: `L.latLng(lat, lon)`. |
| Unidades | Magnitud: adimensional (el tipo va aparte). Profundidad, distancias y errores: km. RMS: s. Gap: grados. Energía: log10(J). Tasas: eventos/año. |
| Campo ausente vs `null` vs vacío | **Ausente:** nunca; todos los campos del contrato están siempre presentes. **`null`:** el dato no existe en la fuente o no se puede calcular (los indicadores traen `null_reason`). **Vacío:** `data: []` con `pagination.total = 0` y HTTP 200; no es un error. **404:** solo cuando se pide un recurso concreto por ID que no existe. |
| Origen de cada dato | Los campos del evento se agrupan en bloques `original`, `normalized`, `derived` y `provenance` en el detalle; el diccionario `GET /meta/variables` indica el `origin` de cada campo. |

### 0.1 Sobres de respuesta

**Recurso o resumen:**
```json
{ "data": { }, "meta": { } }
```
**Colección paginada:**
```json
{ "data": [ ], "pagination": { "page": 1, "page_size": 50, "total": 0, "total_pages": 0 }, "meta": { } }
```
**GeoJSON:** `FeatureCollection` estándar con un miembro adicional `meta` (permitido por RFC 7946 como *foreign member*).

**Error:** ver §4.

### 0.2 Bloque `meta` (en todas las respuestas)

```json
"meta": {
  "api_version": "1.0.0",
  "request_id": "req_01J9ZK7M4Q",
  "generated_at": "2026-10-13T18:00:00Z",
  "data_mode": "real",
  "data_version": "dv_6f1c2a9e",
  "sources": ["SGC-RSNC"],
  "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
  "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31", "timezone": "UTC", "quality": "all" },
  "warnings": []
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `api_version` | string | Versión semántica de la API. |
| `request_id` | string | Identificador de la petición (también en la cabecera `X-Request-ID`); útil para reportar errores. |
| `generated_at` | string (date-time) | Momento en que se generó la respuesta. |
| `data_mode` | `"real" \| "simulated" \| "mixed"` | Si hay datos simulados cargados. |
| `data_version` | string | Huella de las importaciones vigentes; cambia con cada importación. |
| `sources` | string[] | Fuentes que alimentan la respuesta. |
| `coverage` | `{start, end}` (date) | Periodo cubierto por los datos cargados (no por los filtros). |
| `applied_filters` | object | Filtros efectivamente aplicados, **incluidos los valores por defecto**. El frontend puede mostrarlos tal cual. |
| `warnings` | `{code, message}[]` | Advertencias no bloqueantes (p. ej. `MIXED_MAGNITUDE_TYPES`, `PERIOD_PARTIALLY_COVERED`, `RESULT_TRUNCATED`). |

---

## 1. Filtros globales (entregable 10)

Todos los endpoints de eventos y estadísticas aceptan **el mismo conjunto de filtros** y los interpreta **un solo
módulo** (`api/filters.py`), que genera la cláusula `WHERE` parametrizada. Así un mismo filtro da el mismo número en
el dashboard, el mapa, el comparativo y el histórico.

### 1.1 Filtros de eventos (`EventFilters`)

| Parámetro | Tipo / formato | Unidad | Por defecto | Validación |
|---|---|---|---|---|
| `start_date` | `YYYY-MM-DD` o `YYYY-MM-DDTHH:MM:SSZ` | — | inicio de la cobertura | fecha válida; ≤ `end_date` |
| `end_date` | ídem; **inclusiva** (una fecha sin hora incluye todo ese día) | — | fin de la cobertura | fecha válida |
| `timezone` | `UTC` \| `America/Bogota` | — | `UTC` | interpreta `start_date`/`end_date` sin hora y las cubetas de las series |
| `department` | texto (nombre, sin distinguir tildes/mayúsculas) | — | sin filtro | se compara con `department_reported` (del texto `REGION` del SGC) |
| `municipality` | código DANE de 5 dígitos; varios separados por coma (máx. 10) | — | sin filtro | cada código debe existir (`GET /municipalities`) |
| `spatial_scope` | `epicenter` \| `sgc_region` \| `radius` | — | `epicenter` | cómo se decide que un evento "es" de un municipio (ver §1.3) |
| `radius_km` | número | km | `30` | 1–100; solo con `spatial_scope=radius` |
| `min_magnitude`, `max_magnitude` | número | magnitud | sin filtro | −2 a 10; mín ≤ máx; ambos inclusivos |
| `min_depth`, `max_depth` | número | km | sin filtro | −10 a 800; mín ≤ máx; inclusivos |
| `magnitude_type` | `ML`, `Mw`, `mb`, `M` (familias); varios separados por coma | — | todas | valores del enum |
| `quality` | `all` \| `reliable` | — | `all` | `reliable` excluye eventos con banderas de localización |
| `review_status` | `manual` \| `automatic` \| `all` | — | `all` | — |
| `source` | id de fuente (`SGC-RSNC`, …); varios separados por coma | — | todas las `kind=real` | debe existir (`GET /meta`) |
| `include_duplicates` | booleano | — | `false` | los casi-duplicados nunca entran en conteos salvo que se pida |

### 1.2 Filtros geográficos (endpoints de mapa)

| Parámetro | Formato | Por defecto | Validación |
|---|---|---|---|
| `bbox` | `min_lon,min_lat,max_lon,max_lat` (orden GeoJSON). Desde Leaflet: `map.getBounds().toBBoxString()` devuelve exactamente ese orden. | sin filtro | 4 números; lon −180..180, lat −90..90; mín < máx; área ≤ 100 grados² |

### 1.3 Qué significa "eventos de un municipio" (`spatial_scope`)

| Valor | Regla | Origen |
|---|---|---|
| `epicenter` (por defecto) | El epicentro cae dentro del polígono DANE MGN 2018 del municipio. | asociado (cálculo propio) |
| `sgc_region` | El texto `REGION` del SGC nombra ese municipio. | original del SGC |
| `radius` | El epicentro está a ≤ `radius_km` del punto representativo del municipio (criterio del modelo). | derivado |

En 2020–2025 `epicenter` y `sgc_region` coinciden en el 90.8 % de los eventos: no son intercambiables y la UI debe
indicar cuál usa. Con `radius` un mismo evento puede contar para varios municipios (el conteo departamental se
calcula sin `municipality`, así que no hay doble conteo en el total).

### 1.4 Paginación y orden

| Parámetro | Por defecto | Validación |
|---|---|---|
| `page` | `1` | entero ≥ 1. Página mayor que `total_pages` → `200` con `data: []`. |
| `page_size` | `50` | 1–500 (`/events`). |
| `sort_by` | `origin_time` | `origin_time`, `magnitude`, `depth`, `municipality` (según el endpoint) |
| `sort_order` | `desc` | `asc` \| `desc` |

El orden siempre agrega `event_id` como desempate (`ORDER BY <campo> <orden>, event_id ASC`), así la paginación es
estable aunque haya valores repetidos. Los nulos van al final en ambos sentidos.

### 1.5 Comportamiento ante filtros inválidos

- Valor con formato inválido, fuera de rango, mín > máx o código inexistente → **422 `INVALID_FILTER`** con un
  detalle por campo (no se "corrige" en silencio).
- Parámetro desconocido → **400 `UNKNOWN_PARAMETER`** (detecta errores de escritura del frontend).
- Filtros válidos que no dejan resultados → **200** con datos vacíos o indicadores con `value: null` /
  `null_reason: "NO_EVENTS"`.

---

## 2. Catálogo de endpoints (entregable 6)

Prefijo: `/api/v1`. Auth = requiere token de administrador.

| # | Método | Ruta | Para qué | Filtros comunes | Auth | Fase |
|---|---|---|---|---|---|---|
| A1 | GET | `/health` | El backend responde y la base está accesible | — | no | 1 |
| A2 | GET | `/meta` | Versión, fuentes, cobertura, nº de registros, modo de datos, última importación | — | no | 1 |
| A3 | GET | `/meta/variables` | Diccionario: campos originales y normalizados, unidades, origen | — | no | 1 |
| B1 | GET | `/stats/summary` | Indicadores del dashboard con definición y denominador | sí | no | 1 |
| B2 | GET | `/stats/distribution` | Histograma por magnitud, profundidad o tipo de magnitud | sí | no | 1 |
| B3 | GET | `/stats/timeseries` | Evolución temporal (día…año) | sí | no | 1 |
| B4 | GET | `/stats/quality` | Calidad y disponibilidad de los registros filtrados | sí | no | 2 |
| B5 | GET | `/stats/by-municipality` | Indicadores por municipio (coropleta, tablas, barras) | sí | no | 2 |
| C1 | GET | `/events` | Histórico paginado | sí + orden | no | 1 |
| C2 | GET | `/events/geojson` | Epicentros para el mapa (marcadores) | sí + `bbox` | no | 1 |
| C3 | GET | `/events/grid` | Conteo por celdas para volúmenes altos | sí + `bbox` | no | 2 |
| C4 | GET | `/events/{event_id}` | Detalle: original, normalizado, derivado y procedencia | — | no | 1 |
| C5 | GET | `/events/export` | CSV de los eventos filtrados | sí + orden | no | 2 |
| T1 | GET | `/municipalities` | Lista de los 87 municipios (selectores, filtros) | — | no | 1 |
| T2 | GET | `/municipalities/geojson` | Polígonos municipales | — | no | 1 |
| T3 | GET | `/seismic-sources` | Fuentes sísmicas del modelo HDBSCAN | — | no | 2 |
| D1 | GET | `/compare/municipalities` | Comparar 2–5 municipios con series alineadas | sí | no | 2 |
| D2 | GET | `/compare/periods` | Comparar dos periodos de igual duración | sí | no | 2 |
| E1 | GET | `/priority-zones` | Ranking por actividad sísmica observada | ver E1 | no | 2 |
| E2 | GET | `/priority-zones/{municipality_code}` | Explicación detallada de un municipio | — | no | 2 |
| E3 | GET | `/priority-zones/methods` | Métodos de puntuación, variables, pesos, validación y límites | — | no | 2 |
| G1 | GET | `/recommendations/rules` | Reglas explícitas del agente | — | no | 3 |
| G2 | POST | `/recommendations/evaluate` | Recomendaciones para un municipio con evidencia | — | no | 3 |
| G3 | POST | `/assistant/ask` | Futuro asistente con IA (hoy `501`) | — | no | 4 |
| H1 | POST | `/admin/imports` | Importar (o validar con `dry_run`) un export del SGC | — | **sí** | 3 |
| H2 | GET | `/admin/imports` | Historial de importaciones | — | **sí** | 3 |
| H3 | GET | `/admin/imports/{import_id}` | Estado e informe de calidad | — | **sí** | 3 |
| H4 | POST | `/admin/recompute` | Recalcular derivados y modelo tras importar | — | **sí** | 3 |
| H5 | GET | `/admin/query-log` | Consultas anónimas al agente | — | **sí** | 3 |

**Por qué no son redundantes:**
- `/events` (C1) vs `/events/geojson` (C2): C1 trae filas completas paginadas para tablas; C2 trae solo lo necesario
  para pintar marcadores, con un límite más alto y sin paginación.
- `/stats/by-municipality` (B5) vs `/priority-zones` (E1): B5 son **estadísticas descriptivas** con cualquier filtro;
  E1 es un **método de puntuación** precalculado por el modelo, con su periodo fijo, explicación y versión.
- `/compare/*` (D) vs varias llamadas a `/stats/*`: D garantiza los mismos filtros, las mismas cubetas temporales y
  los mismos intervalos de histograma para todas las entidades en una sola respuesta (sin ejes desalineados).

---

## 3. Contratos por endpoint (entregable 7)

En cada endpoint: códigos comunes **400** (`UNKNOWN_PARAMETER`), **422** (`INVALID_FILTER`), **429**
(`RATE_LIMITED`), **500** (`INTERNAL_ERROR`) y **503** (`DATA_NOT_LOADED`). Solo se listan además los propios.

En los ejemplos de Axios, `api` es la instancia centralizada y `toParams(filters)` serializa `EventFilters`
(ver [frontend-integration.md §4](frontend-integration.md#4-cliente-axios-centralizado)).

### A. Estado y metadatos

#### A1. `GET /api/v1/health` — salud del backend

- **Descripción:** comprueba que el proceso responde y que la base de datos y los archivos del modelo están
  accesibles. No calcula estadísticas (respuesta rápida, apta para *health checks* del despliegue).
- **Parámetros:** ninguno.
- **Respuesta 200:**
```json
{
  "data": {
    "status": "ok",
    "checks": { "database": "ok", "model_files": "ok" },
    "uptime_s": 5321
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4Q", "generated_at": "2026-10-13T18:00:00Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
- **Tipos:** `status`: `"ok" | "degraded"`; `checks.*`: `"ok" | "error"`; `uptime_s`: integer (s).
- **Códigos:** 200; **503** con `status: "degraded"` si la base no responde (mismo cuerpo, `checks.database: "error"`).
- **Axios:** `const { data } = await api.get<ApiResponse<Health>>("/health");`

#### A2. `GET /api/v1/meta` — metadatos de la fuente y del conjunto de datos

- **Descripción:** todo lo que el frontend necesita para el pie "Fuente: …", la página *Acerca de* y para saber si
  los datos son reales.
- **Parámetros:** ninguno.
- **Respuesta 200:**
```json
{
  "data": {
    "api_version": "1.0.0",
    "data_mode": "real",
    "realtime": false,
    "data_version": "dv_6f1c2a9e",
    "last_import_at": "2026-10-13T15:25:00Z",
    "record_counts": { "events": 64027, "events_reliable": 56355, "duplicates_excluded": 10, "raw_rows": 64037 },
    "coverage": {
      "temporal": { "start": "2020-03-02", "end": "2025-03-01", "timezone": "UTC" },
      "spatial": {
        "study_area_bbox": [-75.0, 5.2, -72.0, 8.7],
        "department_filter_in_source_query": "Santander",
        "municipalities": 87,
        "events_inside_a_municipality_pct": 99.9
      }
    },
    "sources": [
      {
        "source_id": "SGC-RSNC",
        "name": "Servicio Geológico Colombiano – Red Sismológica Nacional de Colombia (catálogo sísmico)",
        "kind": "real",
        "url": "http://bdrsnc.sgc.gov.co/paginas1/catalogo/",
        "obtained_by": "export manual del portal (no se usa API externa)",
        "downloaded_at": "2026-10-13",
        "imports": 5,
        "terms_note": "Términos de uso y límites del portal no verificados por el equipo."
      },
      {
        "source_id": "DANE-MGN2018",
        "name": "DANE – Marco Geoestadístico Nacional 2018 (municipios)",
        "kind": "real",
        "url": "https://geoportal.dane.gov.co/servicios/descarga-y-metadatos/descarga-mgn-marco-geoestadistico-nacional/",
        "obtained_by": "GeoJSON simplificado (copia pública https://github.com/caticoa3/colombia_mapa)",
        "downloaded_at": null,
        "imports": 1,
        "terms_note": null
      }
    ],
    "model": {
      "model_version": "kmeans-2026.10.13-a35dcf9",
      "computed_at": "2026-10-13T15:39:58Z",
      "training_period": { "start": "2020-03-02", "end": "2023-02-28" },
      "validation_period": { "start": "2023-03-01", "end": "2025-03-01" }
    },
    "completeness_magnitude": 2.0,
    "dimensions": {
      "observed_activity": "available",
      "hazard": "not_computed",
      "exposure": "missing_data",
      "vulnerability": "missing_data"
    },
    "assistant_enabled": false
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4R", "generated_at": "2026-10-13T18:00:01Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC", "DANE-MGN2018"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
- **Campos clave:** `realtime` (boolean, siempre `false`: no hay consulta en vivo al SGC); `last_import_at`
  (date-time | null); `record_counts.*` (integer, eventos); `completeness_magnitude` (number | null, magnitud por
  encima de la cual el catálogo se considera completo en todo el periodo: útil como `min_magnitude` para comparar
  años); `dimensions.*`: `"available" | "not_computed" | "missing_data"`.
- **Códigos:** 200, 503.
- **Axios:** `const meta = (await api.get<ApiResponse<Meta>>("/meta")).data.data;`

#### A3. `GET /api/v1/meta/variables` — diccionario de variables

- **Descripción:** lista de campos que expone la API con su origen, columna original, tipo y unidad. Sirve para
  tooltips de "¿qué significa?" y para la vista de campos originales del histórico.
- **Parámetros de consulta:** `scope` = `event` | `municipality` | `all` (por defecto `all`).
- **Respuesta 200 (extracto con 4 de los campos):**
```json
{
  "data": [
    { "field": "origin_time_utc", "scope": "event", "label": "Fecha y hora (UTC)", "type": "string",
      "format": "date-time", "unit": null, "origin": "normalized",
      "original_columns": ["FECHA - HORA UTC", "Fecha-Hora (UTC)", "FECHA + HORA_UTC (formato antiguo)"],
      "nullable": false, "description": "Hora de origen del sismo normalizada a UTC." },
    { "field": "depth_km", "scope": "event", "label": "Profundidad", "type": "number", "format": null,
      "unit": "km", "origin": "normalized", "original_columns": ["PROF. (Km)", "Prof(Km)", "PROFUNDIDAD (Km)"],
      "nullable": true, "description": "Profundidad del hipocentro. Valores negativos pequeños se conservan." },
    { "field": "municipality_code", "scope": "event", "label": "Municipio (epicentro)", "type": "string",
      "format": "divipola", "unit": null, "origin": "associated", "original_columns": [],
      "nullable": true, "description": "Municipio DANE cuyo polígono contiene el epicentro (cálculo propio, no del SGC)." },
    { "field": "tasa_fuertes_r30", "scope": "municipality", "label": "Sismos M ≥ 4 por año a ≤ 30 km",
      "type": "number", "format": null, "unit": "eventos/año", "origin": "derived", "original_columns": [],
      "nullable": false, "description": "Variable del modelo (periodo de entrenamiento)." }
  ],
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4S", "generated_at": "2026-10-13T18:00:02Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": { "scope": "all" }, "warnings": [] }
}
```
- **Tipos:** `origin`: `"original" | "normalized" | "derived" | "associated" | "model"`; `original_columns`: string[]
  (alias reconocidos; vacío si el campo no viene del SGC).
- **Códigos:** 200, 422 (`scope` inválido).
- **Axios:** `api.get<ApiResponse<VariableInfo[]>>("/meta/variables", { params: { scope: "event" } })`

---

### B. Dashboard

#### B1. `GET /api/v1/stats/summary` — indicadores

- **Descripción:** KPIs del periodo filtrado. Cada indicador trae definición, unidad, agregación y denominador.
  La variación se calcula contra el periodo **inmediatamente anterior de igual duración**.
- **Parámetros:** filtros comunes (§1.1).
- **Respuesta 200** (`start_date=2024-01-01&end_date=2024-12-31`):
```json
{
  "data": {
    "period": { "start": "2024-01-01", "end": "2024-12-31", "timezone": "UTC", "days": 366 },
    "comparison_period": { "start": "2023-01-01", "end": "2023-12-31", "timezone": "UTC", "days": 365 },
    "indicators": [
      { "key": "event_count", "label": "Eventos", "value": 15974, "unit": "eventos",
        "definition": "Número de eventos que cumplen los filtros.", "aggregation": "count",
        "denominator": null, "null_reason": null },
      { "key": "event_count_change_pct", "label": "Variación frente al periodo anterior", "value": 30.4,
        "unit": "%", "definition": "(eventos del periodo − eventos del periodo anterior de igual duración) / eventos del periodo anterior × 100.",
        "aggregation": "ratio", "denominator": { "label": "Eventos del periodo anterior", "value": 12249 },
        "null_reason": null },
      { "key": "magnitude_max", "label": "Magnitud máxima", "value": 5.0, "unit": "magnitud",
        "definition": "Mayor magnitud reportada entre los eventos filtrados (tipos de magnitud mezclados, ver warnings).",
        "aggregation": "max", "denominator": null, "null_reason": null },
      { "key": "magnitude_min", "label": "Magnitud mínima", "value": 0.2, "unit": "magnitud",
        "definition": "Menor magnitud reportada. Depende de la capacidad de detección de la red.",
        "aggregation": "min", "denominator": null, "null_reason": null },
      { "key": "magnitude_mean", "label": "Magnitud media", "value": 1.88, "unit": "magnitud",
        "definition": "Media aritmética de la magnitud.", "aggregation": "mean",
        "denominator": { "label": "Eventos con magnitud", "value": 15974 }, "null_reason": null },
      { "key": "magnitude_median", "label": "Magnitud mediana", "value": 1.8, "unit": "magnitud",
        "definition": "Mediana de la magnitud.", "aggregation": "median",
        "denominator": { "label": "Eventos con magnitud", "value": 15974 }, "null_reason": null },
      { "key": "depth_mean", "label": "Profundidad media", "value": 136.3, "unit": "km",
        "definition": "Media de la profundidad del hipocentro.", "aggregation": "mean",
        "denominator": { "label": "Eventos con profundidad", "value": 15974 }, "null_reason": null },
      { "key": "depth_median", "label": "Profundidad mediana", "value": 141.4, "unit": "km",
        "definition": "Mediana de la profundidad del hipocentro.", "aggregation": "median",
        "denominator": { "label": "Eventos con profundidad", "value": 15974 }, "null_reason": null },
      { "key": "municipalities_with_events", "label": "Municipios con epicentros", "value": 77,
        "unit": "municipios", "definition": "Municipios de Santander cuyo polígono contiene al menos un epicentro filtrado.",
        "aggregation": "count_distinct", "denominator": { "label": "Municipios de Santander", "value": 87 },
        "null_reason": null },
      { "key": "reliable_events_pct", "label": "Eventos bien localizados", "value": 89.7, "unit": "%",
        "definition": "Porcentaje de eventos sin banderas de calidad de localización.", "aggregation": "ratio",
        "denominator": { "label": "Eventos", "value": 15974 }, "null_reason": null }
    ]
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4T", "generated_at": "2026-10-13T18:00:03Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31", "timezone": "UTC", "quality": "all",
                                 "review_status": "all", "include_duplicates": false, "spatial_scope": "epicenter" },
            "warnings": [ { "code": "MIXED_MAGNITUDE_TYPES",
                            "message": "Las estadísticas de magnitud mezclan familias: ML (15 970), Mw (3), M (1)." } ] }
}
```
- **Tipos del indicador:** `key` string; `value` number | null; `unit` string; `aggregation`: `"count" | "count_distinct"
  | "min" | "max" | "mean" | "median" | "ratio"`; `denominator`: `{label: string, value: number} | null`;
  `null_reason`: `null | "NO_EVENTS" | "PREVIOUS_PERIOD_NOT_COVERED" | "PREVIOUS_PERIOD_ZERO" | "FIELD_NOT_AVAILABLE"`.
- **Reglas:** si no hay eventos → `event_count = 0` y el resto `null` con `NO_EVENTS`. Si el periodo anterior no
  está totalmente cubierto por los datos (p. ej. 2020 con datos desde 2020-03-02) → `event_count_change_pct: null`
  con `PREVIOUS_PERIOD_NOT_COVERED` y `comparison_period` igualmente informado.
- **Códigos:** 200, 422.
- **Axios:** `api.get<ApiResponse<Summary>>("/stats/summary", { params: toParams(filters) })`

#### B2. `GET /api/v1/stats/distribution` — distribuciones

- **Parámetros:** filtros comunes +
  - `field` (obligatorio): `magnitude` | `depth` | `magnitude_type`.
  - `bins` (opcional, solo `magnitude`/`depth`): bordes separados por coma, crecientes, 2–20 valores. Por defecto
    magnitud `0,2,3,4,5` y profundidad `0,30,70,300`. Se agregan automáticamente un intervalo inferior y uno superior
    abiertos para que no se pierda ningún evento. Intervalos cerrados a la izquierda `[a, b)`.
- **Respuesta 200** (`field=magnitude`, 2024):
```json
{
  "data": {
    "field": "magnitude", "unit": "magnitud", "total": 15974, "null_count": 0,
    "bins": [
      { "label": "< 2",   "lower": null, "upper": 2,    "count": 10985, "percent": 68.8 },
      { "label": "2–3",   "lower": 2,    "upper": 3,    "count": 4659,  "percent": 29.2 },
      { "label": "3–4",   "lower": 3,    "upper": 4,    "count": 296,   "percent": 1.9 },
      { "label": "4–5",   "lower": 4,    "upper": 5,    "count": 32,    "percent": 0.2 },
      { "label": "≥ 5",   "lower": 5,    "upper": null, "count": 2,     "percent": 0.0 }
    ]
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4U", "generated_at": "2026-10-13T18:00:04Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31", "field": "magnitude", "bins": "0,2,3,4,5" },
            "warnings": [] }
}
```
  Con `field=depth` (mismos filtros): `0–30 km`: 296, `30–70 km`: 126, `70–300 km`: 15 552, `≥ 300 km`: 0.
  Con `field=magnitude_type`: `bins` son categorías (`{ "label": "ML", "lower": null, "upper": null, "count": 15970, … }`).
- **Tipos:** `percent` number 0–100 sobre `total`; `lower`/`upper` number | null (null = abierto).
- **Códigos:** 200, 422 (`field` ausente o inválido, `bins` no creciente).
- **Axios:** `api.get<ApiResponse<Distribution>>("/stats/distribution", { params: { ...toParams(filters), field: "depth" } })`

#### B3. `GET /api/v1/stats/timeseries` — evolución temporal

- **Parámetros:** filtros comunes +
  - `interval`: `day` | `week` | `month` | `quarter` | `year` (por defecto `month`). Semanas ISO (lunes).
  - `metric`: `count` | `max_magnitude` | `mean_magnitude` | `mean_depth` (por defecto `count`); varias separadas por coma.
  - Máximo **1 000 cubetas**: si el rango × intervalo lo supera → 422 sugiriendo un intervalo mayor.
- **Respuesta 200** (`interval=month&metric=count,max_magnitude`, 2024, primeras 3 cubetas):
```json
{
  "data": {
    "interval": "month", "timezone": "UTC",
    "metrics": [ { "key": "count", "unit": "eventos" }, { "key": "max_magnitude", "unit": "magnitud" } ],
    "points": [
      { "bucket_start": "2024-01-01", "bucket_end": "2024-01-31", "count": 1674, "max_magnitude": 5.0 },
      { "bucket_start": "2024-02-01", "bucket_end": "2024-02-29", "count": 1529, "max_magnitude": 4.7 },
      { "bucket_start": "2024-03-01", "bucket_end": "2024-03-31", "count": 1662, "max_magnitude": 4.1 }
    ],
    "complete_buckets": true
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4V", "generated_at": "2026-10-13T18:00:05Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31", "interval": "month", "metric": "count,max_magnitude" },
            "warnings": [] }
}
```
- **Reglas:** cubetas sin eventos aparecen con `count: 0` y las demás métricas `null`. Si la primera o la última
  cubeta solo está cubierta en parte por los datos, `complete_buckets: false` y `warnings` incluye
  `PARTIAL_BUCKETS` (Recharts puede pintarlas con otro estilo).
- **Códigos:** 200, 422.
- **Axios:** `api.get<ApiResponse<TimeSeries>>("/stats/timeseries", { params: { ...toParams(filters), interval: "month" } })`

#### B4. `GET /api/v1/stats/quality` — calidad de los registros

- **Parámetros:** filtros comunes (el parámetro `quality` se ignora aquí: siempre se analizan todos).
- **Respuesta 200** (2024):
```json
{
  "data": {
    "total": 15974, "reliable": 14324, "reliable_pct": 89.7,
    "flags": [
      { "flag": "depth_error_gt_10km", "label": "Error de profundidad > 10 km", "count": 545 },
      { "flag": "horizontal_error_gt_10km", "label": "Error horizontal > 10 km", "count": 521 },
      { "flag": "gap_gt_270", "label": "Gap azimutal > 270°", "count": 378 },
      { "flag": "rms_gt_1_2_m_lt_3", "label": "RMS > 1.2 s (solo M < 3)", "count": 349 },
      { "flag": "phases_lt_6", "label": "Menos de 6 fases", "count": 21 }
    ],
    "review_status": { "manual": 15974, "automatic": 0 },
    "missing_values": { "depth_km": 0, "magnitude": 0, "phase_count": 0, "rms_s": 0, "azimuthal_gap_deg": 0,
                        "latitude_error_km": 0, "longitude_error_km": 0, "depth_error_km": 0,
                        "quakeml_url": 15974, "map_url": 15974 },
    "criteria_note": "Un evento puede tener varias banderas. Las banderas no eliminan eventos; quality=reliable los excluye."
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4W", "generated_at": "2026-10-13T18:00:06Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31" }, "warnings": [] }
}
```
  (En 2024 no hay eventos `automatic`; en todo el catálogo hay 31.)
- **Códigos:** 200, 422.
- **Axios:** `api.get<ApiResponse<QualitySummary>>("/stats/quality", { params: toParams(filters) })`

#### B5. `GET /api/v1/stats/by-municipality` — indicadores por municipio

- **Descripción:** una fila por municipio de Santander con los indicadores del periodo filtrado. Alimenta la
  coropleta del mapa, las barras del comparativo y tablas.
- **Parámetros:** filtros comunes (salvo `municipality`) + `sort_by` = `event_count` | `magnitude_max` |
  `magnitude_mean` | `depth_median` | `name` (por defecto `event_count`), `sort_order`, `include_zero` (bool, por
  defecto `true`: incluye los 87 municipios aunque tengan 0 eventos).
- **Respuesta 200** (2024, `spatial_scope=epicenter`, primeras 2 filas):
```json
{
  "data": [
    { "municipality": { "code": "68418", "name": "Los Santos" }, "event_count": 9741, "events_per_year": 9721.0,
      "magnitude_max": 5.0, "magnitude_mean": 1.94, "magnitude_median": 1.9,
      "depth_mean": 143.0, "depth_median": 143.2, "reliable_pct": 89.2 },
    { "municipality": { "code": "68895", "name": "Zapatoca" }, "event_count": 1626, "events_per_year": 1622.7,
      "magnitude_max": 4.7, "magnitude_mean": 1.89, "magnitude_median": 1.8,
      "depth_mean": 141.4, "depth_median": 142.1, "reliable_pct": 87.2 }
  ],
  "pagination": { "page": 1, "page_size": 87, "total": 87, "total_pages": 1 },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4X", "generated_at": "2026-10-13T18:00:07Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31", "spatial_scope": "epicenter",
                                 "sort_by": "event_count", "sort_order": "desc" }, "warnings": [] }
}
```
- **Reglas:** municipios sin eventos: `event_count: 0`, demás indicadores `null`. `events_per_year` = eventos /
  años del periodo filtrado (días / 365.25; 366 días = 1.0021 años).
- **Códigos:** 200, 422.
- **Axios:** `api.get<Paginated<MunicipalityStats>>("/stats/by-municipality", { params: toParams(filters) })`

---

### C. Eventos (mapa e histórico)

#### C1. `GET /api/v1/events` — histórico paginado

- **Parámetros:** filtros comunes + paginación y orden (§1.4; `sort_by`: `origin_time` | `magnitude` | `depth`) +
  `q` (texto, opcional, 2–60 caracteres: busca en `region_reported` y en el nombre del municipio asociado, sin
  distinguir tildes).
- **Respuesta 200** (`min_magnitude=5&sort_by=magnitude`):
```json
{
  "data": [
    {
      "event_id": "sgc-016b4dee901f5991",
      "origin_time_utc": "2023-09-14T07:01:04Z",
      "latitude": 6.804, "longitude": -73.238, "depth_km": 150.57,
      "magnitude": 5.6, "magnitude_type": "Mw(mB)", "magnitude_type_group": "Mw",
      "region_reported": "Zapatoca - Santander, Colombia",
      "municipality": { "code": "68895", "name": "Zapatoca", "method": "point_in_polygon_mgn2018_simplified" },
      "review_status": "manual", "is_reliable": true, "quality_flags": [],
      "seismic_source": { "code": "F1", "type": "Nido de Bucaramanga" },
      "source_id": "SGC-RSNC"
    }
  ],
  "pagination": { "page": 1, "page_size": 50, "total": 15, "total_pages": 1 },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4Y", "generated_at": "2026-10-13T18:00:08Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "min_magnitude": 5, "sort_by": "magnitude", "sort_order": "desc", "page": 1, "page_size": 50 },
            "warnings": [] }
}
```
  (Se muestra 1 de los 15 eventos M ≥ 5 del catálogo actual.)
- **Paginación:** `total` cuenta todas las filas que cumplen los filtros; `total_pages = ceil(total / page_size)`.
  Orden estable con desempate por `event_id`. Para recorrer un histórico grande use `/events/export`.
- **Códigos:** 200, 400, 422.
- **Axios:** `api.get<Paginated<SeismicEvent>>("/events", { params: { ...toParams(filters), page, page_size: 50, sort_by: "origin_time", sort_order: "desc" } })`

#### C2. `GET /api/v1/events/geojson` — epicentros para el mapa

- **Parámetros:** filtros comunes + `bbox` + `limit` (por defecto 2 000, máximo 10 000).
- **Orden:** magnitud descendente y luego fecha descendente: si se trunca, se conservan los eventos mayores.
- **Respuesta 200** (`application/geo+json`):
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "sgc-016b4dee901f5991",
      "geometry": { "type": "Point", "coordinates": [-73.238, 6.804] },
      "properties": {
        "event_id": "sgc-016b4dee901f5991",
        "kind": "epicenter",
        "origin_time_utc": "2023-09-14T07:01:04Z",
        "magnitude": 5.6, "magnitude_type": "Mw(mB)", "depth_km": 150.57,
        "region_reported": "Zapatoca - Santander, Colombia",
        "municipality_name": "Zapatoca",
        "is_reliable": true,
        "seismic_source_type": "Nido de Bucaramanga"
      }
    }
  ],
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M4Z", "generated_at": "2026-10-13T18:00:09Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "bbox": [-74.6, 5.6, -72.4, 8.2], "min_magnitude": 4, "limit": 2000 },
            "total_matching": 198, "returned": 198, "truncated": false, "warnings": [] }
}
```
- **Reglas:** `geometry.coordinates` = `[longitude, latitude]` (el `GeoJSON` de React Leaflet lo maneja solo;
  para `CircleMarker` use `[lat, lon]`). `kind: "epicenter"` siempre (las celdas agregadas de C3 tienen otro `kind`).
  Si `total_matching > limit` → `truncated: true` y `warnings` incluye `RESULT_TRUNCATED` con la sugerencia de usar
  `/events/grid` o acercar el mapa.
- **Códigos:** 200, 422 (`bbox` inválido o `limit` > 10 000).
- **Axios:** `api.get<EventFeatureCollection>("/events/geojson", { params: { ...toParams(filters), bbox: map.getBounds().toBBoxString() } })`

#### C3. `GET /api/v1/events/grid` — agregación por celdas

- **Descripción:** cuenta eventos por celdas regulares de latitud/longitud. Cada celda es un **rectángulo** con su
  conteo; no se devuelve ningún punto que pueda confundirse con un epicentro.
- **Parámetros:** filtros comunes + `bbox` + `cell_size_deg` (`0.05` | `0.1` | `0.25` | `0.5`, por defecto `0.1`).
  Máximo 5 000 celdas con eventos (si no → 422 pidiendo una celda mayor o un `bbox` menor).
- **Respuesta 200** (2024, `cell_size_deg=0.1`, primera celda):
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "cell_0.1_6.7_-73.2",
      "geometry": { "type": "Polygon",
                    "coordinates": [[[-73.2, 6.7], [-73.1, 6.7], [-73.1, 6.8], [-73.2, 6.8], [-73.2, 6.7]]] },
      "properties": {
        "kind": "aggregation_cell", "cell_size_deg": 0.1,
        "bounds": { "south": 6.7, "west": -73.2, "north": 6.8, "east": -73.1 },
        "event_count": 5734, "magnitude_max": 5.0, "depth_mean": 141.27
      }
    }
  ],
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M50", "generated_at": "2026-10-13T18:00:10Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31", "cell_size_deg": 0.1 },
            "cells": 253, "events_aggregated": 15974,
            "note": "Celdas de agregación: no representan epicentros ni zonas de amenaza.", "warnings": [] }
}
```
- **Códigos:** 200, 422.
- **Axios:** `api.get<GridFeatureCollection>("/events/grid", { params: { ...toParams(filters), bbox, cell_size_deg: 0.1 } })`

#### C4. `GET /api/v1/events/{event_id}` — detalle de un evento

- **Parámetros de ruta:** `event_id` (string, patrón `^sgc-[0-9a-f]{16}$` o `^sgc-[A-Za-z0-9_.-]+$`).
- **Respuesta 200:**
```json
{
  "data": {
    "event_id": "sgc-016b4dee901f5991",
    "original": {
      "FECHA - HORA UTC": "2023-09-14 07:01:04", "LATITUD (°)": "6.804", "LONGITUD (°)": "-73.238",
      "PROF. (Km)": "150.57", "MAGNITUD": "5.6", "TIPO MAGNITUD": "Mw(mB)", "FASES": "105", "RMS (Seg)": "1.3",
      "GAP (°)": "58", "ERROR LATITUD (Km)": "2.066", "ERROR LONGITUD (Km)": "2.541",
      "ERROR PROFUNDIDAD (Km)": "3.8", "REGION": "Zapatoca - Santander, Colombia", "ESTADO": "manual"
    },
    "normalized": {
      "origin_time_utc": "2023-09-14T07:01:04Z", "origin_time_raw": "2023-09-14 07:01:04", "time_zone_declared": "UTC",
      "latitude": 6.804, "longitude": -73.238, "depth_km": 150.57,
      "magnitude": 5.6, "magnitude_type": "Mw(mB)", "magnitude_type_group": "Mw",
      "phase_count": 105, "rms_s": 1.3, "azimuthal_gap_deg": 58,
      "latitude_error_km": 2.066, "longitude_error_km": 2.541, "depth_error_km": 3.8,
      "region_reported": "Zapatoca - Santander, Colombia", "department_reported": "Santander", "country_reported": "Colombia",
      "review_status": "manual", "source_event_id": null, "quakeml_url": null, "map_url": null
    },
    "derived": {
      "municipality": { "code": "68895", "name": "Zapatoca", "method": "point_in_polygon_mgn2018_simplified",
                        "distance_to_boundary_km": 4.1, "matches_region_reported": true },
      "quality": { "is_reliable": true, "flags": [],
                   "note": "RMS 1.3 s no se marca: el criterio de RMS solo aplica a M < 3." },
      "duplicate_of": null,
      "depth_class": "70-300",
      "energy_log10_j": 13.2,
      "seismic_source": { "code": "F1", "type": "Nido de Bucaramanga", "model_version": "kmeans-2026.10.13-a35dcf9" }
    },
    "provenance": {
      "source_id": "SGC-RSNC", "source_kind": "real",
      "import_id": "imp_20261013_0004", "file_name": "Csg_2023.xlsx", "file_row": 5080,
      "downloaded_at": "2026-10-13", "portal_created_at": "2026-10-13T10:10:15-04:00",
      "imported_at": "2026-10-13T15:25:00Z",
      "source_query": { "DEPARTAMENTO": "Santander", "FECHA_INICIAL": "2023-03-02", "FECHA_FINAL": "2024-03-01",
                        "TIPO CONSULTA": "cuadrante" }
    }
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M51", "generated_at": "2026-10-13T18:00:11Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
  (`distance_to_boundary_km` e `import_id` ilustrativos; `file_row` es la fila real de datos en `Csg_2023.xlsx`,
  contando desde 1 después del encabezado.)
- **Reglas:** `original` reproduce la fila **tal como venía** (valores como texto, encabezados exactos). Los enlaces
  (`quakeml_url`, `map_url`) son `null` porque los exports actuales no los traen.
- **Códigos:** 200; **404** `EVENT_NOT_FOUND`; 422 si el ID no cumple el patrón.
- **Axios:** `api.get<ApiResponse<SeismicEventDetail>>(\`/events/${id}\`)`

#### C5. `GET /api/v1/events/export` — exportar CSV

- **Parámetros:** filtros comunes + orden + `columns` = `normalized` (por defecto) | `original` | `all` +
  `max_rows` (por defecto y máximo 100 000).
- **Respuesta 200:** `text/csv; charset=utf-8` con BOM (para que Excel lea tildes), separador `,`, decimal `.`,
  cabecera `Content-Disposition: attachment; filename="sismos_santander_2024-01-01_2024-12-31.csv"`. Primeras
  líneas de comentario no; los metadatos van en cabeceras: `X-Data-Version`, `X-Total-Rows`, `X-Truncated`.
```
event_id,origin_time_utc,latitude,longitude,depth_km,magnitude,magnitude_type,magnitude_type_group,region_reported,municipality_code,municipality_name,review_status,is_reliable,quality_flags,source_id
sgc-016b4dee901f5991,2023-09-14T07:01:04Z,6.804,-73.238,150.57,5.6,Mw(mB),Mw,"Zapatoca - Santander, Colombia",68895,Zapatoca,manual,true,,SGC-RSNC
```
- **Códigos:** 200; 413 `EXPORT_TOO_LARGE` si los filtros superan `max_rows` (mensaje con el total).
- **Axios:**
```ts
const res = await api.get("/events/export", { params: toParams(filters), responseType: "blob" });
const url = URL.createObjectURL(res.data); // luego <a download> o window.open
```

---

### T. Territorio y fuentes sísmicas

#### T1. `GET /api/v1/municipalities` — municipios

- **Parámetros:** `focus_zone` (bool, opcional).
- **Respuesta 200** (extracto):
```json
{
  "data": [
    { "code": "68001", "name": "Bucaramanga", "name_official": "BUCARAMANGA", "department_code": "68",
      "area_km2": 152.92, "representative_point": { "latitude": 7.16181, "longitude": -73.10602 }, "in_focus_zone": true },
    { "code": "68418", "name": "Los Santos", "name_official": "LOS SANTOS", "department_code": "68",
      "area_km2": 290.13, "representative_point": { "latitude": 6.79619, "longitude": -73.10866 }, "in_focus_zone": true }
  ],
  "pagination": { "page": 1, "page_size": 87, "total": 87, "total_pages": 1 },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M52", "generated_at": "2026-10-13T18:00:12Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["DANE-MGN2018"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
  (Valores del MGN 2018 cargado en el repositorio.)
- **Códigos:** 200.
- **Axios:** `api.get<Paginated<Municipality>>("/municipalities")` — cachear: cambia casi nunca.

#### T2. `GET /api/v1/municipalities/geojson` — polígonos

- **Parámetros:** `include` = `none` | `stats` | `classification` (por defecto `none`). Con `stats` agrega a cada
  polígono los indicadores de B5 con los filtros comunes; con `classification` agrega el nivel y el índice de E1.
- **Respuesta 200:** `FeatureCollection` de 87 `Polygon`/`MultiPolygon` (simplificados, tolerancia ≈ 200 m) con
  `properties: { code, name, area_km2, in_focus_zone, ...stats|classification }`.
- **Códigos:** 200, 422.
- **Axios:** `api.get<MunicipalityFeatureCollection>("/municipalities/geojson", { params: { include: "classification" } })`

#### T3. `GET /api/v1/seismic-sources` — fuentes del modelo HDBSCAN

- **Respuesta 200** (extracto):
```json
{
  "data": [
    { "code": "F1", "type": "Nido de Bucaramanga", "name": "F1 · Nido de Bucaramanga (Los Santos)",
      "center": { "latitude": 6.787, "longitude": -73.164 }, "depth_median_km": 141.5,
      "depth_p10_km": 133.2, "depth_p90_km": 148.3, "event_count": 21347, "max_magnitude": 5.3,
      "nearest_municipality": "Los Santos" }
  ],
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M53", "generated_at": "2026-10-13T18:00:13Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {},
            "model_version": "kmeans-2026.10.13-a35dcf9", "training_period": { "start": "2020-03-02", "end": "2023-02-28" },
            "note": "Fuentes inferidas por un modelo de agrupamiento (HDBSCAN) con el periodo de entrenamiento; no son un producto del SGC.",
            "warnings": [] }
}
```
  (Valores de `salidas/fuentes_sismicas.csv`. El centro del Nido que usan las distancias, 6.788 / −73.166, es la
  mediana de todas las fuentes tipo Nido, F1 y F3.)
- **Códigos:** 200, 503 si el modelo no se ha calculado.
- **Axios:** `api.get<ApiResponse<SeismicSource[]>>("/seismic-sources")`

---

### D. Análisis comparativo

#### D1. `GET /api/v1/compare/municipalities`

- **Parámetros:** filtros comunes (sin `municipality`) + `municipalities` (obligatorio, 2–5 códigos DANE) +
  `metrics` (de B1, por defecto `event_count,magnitude_max,magnitude_mean,magnitude_median,depth_mean,depth_median`)
  + `interval` (para la serie, por defecto `month`) + `distribution` = `none` | `magnitude` | `depth`.
- **Respuesta 200** (Los Santos vs Zapatoca, 2024, `interval=year`):
```json
{
  "data": {
    "period": { "start": "2024-01-01", "end": "2024-12-31", "timezone": "UTC", "days": 366 },
    "spatial_scope": "epicenter",
    "entities": [
      { "municipality": { "code": "68418", "name": "Los Santos" },
        "indicators": { "event_count": 9741, "magnitude_max": 5.0, "magnitude_mean": 1.94, "magnitude_median": 1.9,
                        "depth_mean": 143.0, "depth_median": 143.2 },
        "series": [ { "bucket_start": "2024-01-01", "count": 9741 } ],
        "distribution": null },
      { "municipality": { "code": "68895", "name": "Zapatoca" },
        "indicators": { "event_count": 1626, "magnitude_max": 4.7, "magnitude_mean": 1.89, "magnitude_median": 1.8,
                        "depth_mean": 141.4, "depth_median": 142.1 },
        "series": [ { "bucket_start": "2024-01-01", "count": 1626 } ],
        "distribution": null }
    ],
    "units": { "event_count": "eventos", "magnitude_max": "magnitud", "magnitude_mean": "magnitud",
               "magnitude_median": "magnitud", "depth_mean": "km", "depth_median": "km" },
    "aggregation_note": "Eventos con epicentro dentro del polígono de cada municipio (spatial_scope=epicenter). Las cubetas y los intervalos son idénticos para todas las entidades."
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M54", "generated_at": "2026-10-13T18:00:14Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "start_date": "2024-01-01", "end_date": "2024-12-31", "municipalities": "68418,68895", "interval": "year" },
            "warnings": [] }
}
```
- **Reglas:** si un municipio no tiene eventos, sus indicadores (salvo `event_count: 0`) son `null`.
  Comparar conteos entre municipios de distinto tamaño: el frontend puede pedir `spatial_scope=radius` (mismo círculo
  para todos) y lo debe indicar en la gráfica.
- **Códigos:** 200, 422 (menos de 2 o más de 5 municipios, código inexistente).
- **Axios:** `api.get<ApiResponse<MunicipalityComparison>>("/compare/municipalities", { params: { ...toParams(filters), municipalities: "68418,68895" } })`

#### D2. `GET /api/v1/compare/periods`

- **Parámetros:** filtros comunes **sin** `start_date`/`end_date` + `period_a_start`, `period_a_end`,
  `period_b_start`, `period_b_end` (obligatorios) + `metrics`, `interval`, `distribution` (como D1) +
  `allow_unequal_length` (bool, por defecto `false`).
- **Reglas:** por defecto ambos periodos deben durar lo mismo (± 1 día por años bisiestos); si no → 422
  `UNEQUAL_PERIODS`. Con `allow_unequal_length=true` los conteos se comparan como tasa por año y se avisa en
  `warnings`. Si algún periodo no está cubierto por los datos → indicadores `null` con `PERIOD_NOT_COVERED`.
- **Respuesta 200** (Los Santos, 2023 vs 2024):
```json
{
  "data": {
    "periods": [
      { "label": "A", "start": "2023-01-01", "end": "2023-12-31", "days": 365,
        "indicators": { "event_count": 6440 }, "covered": true },
      { "label": "B", "start": "2024-01-01", "end": "2024-12-31", "days": 366,
        "indicators": { "event_count": 9741 }, "covered": true }
    ],
    "differences": [
      { "metric": "event_count", "absolute": 3301, "percent": 51.3, "unit": "eventos" }
    ]
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M55", "generated_at": "2026-10-13T18:00:15Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" },
            "applied_filters": { "municipality": "68418", "period_a_start": "2023-01-01", "period_a_end": "2023-12-31",
                                 "period_b_start": "2024-01-01", "period_b_end": "2024-12-31", "metrics": "event_count" },
            "warnings": [ { "code": "COMPLETENESS",
                            "message": "Las diferencias de conteo pueden reflejar cambios en la detección de la red. Para comparar actividad use min_magnitude ≥ 2.0 (magnitud de completitud)." } ] }
}
```
- **Códigos:** 200, 422.
- **Axios:** `api.get<ApiResponse<PeriodComparison>>("/compare/periods", { params: { municipality: "68418", period_a_start, period_a_end, period_b_start, period_b_end } })`

---

### E. Zonas prioritarias (actividad sísmica observada)

> Esta sección **no** calcula riesgo ni probabilidad de terremoto. Con el catálogo solo se mide actividad sísmica
> observada y cercanía a fuentes. La respuesta separa las cuatro dimensiones y marca las que no existen.

Métodos disponibles (ambos precalculados por el pipeline, con el **periodo de entrenamiento** fijo):

| `method` | Qué es | Puntuación |
|---|---|---|
| `catalog_index_v1` (por defecto) | Índice transparente: promedio de componentes estandarizados (+ actividad, + magnitud, + energía liberada, + energía que llega al sitio, + superficialidad, − distancia a fuentes), escalado 0–100 entre los 87 municipios. | `observed_activity_score` 0–100 (relativo) |
| `kmeans_levels_v1` | Niveles del modelo no supervisado (K-Means k = 5 sobre 21 variables), ordenados por el índice anterior. | `cluster_level` (Muy bajo … Muy alto) |

#### E1. `GET /api/v1/priority-zones` — ranking

- **Parámetros:** `method` (por defecto `catalog_index_v1`), `focus_zone` (bool), `level` (filtra por nivel),
  `page`, `page_size` (por defecto 87). **No acepta filtros de fechas ni de magnitud** (el método tiene periodo
  fijo): si se envían → 422 `FILTER_NOT_SUPPORTED` con explicación.
- **Respuesta 200** (primera fila):
```json
{
  "data": [
    {
      "rank": 1,
      "municipality": { "code": "68418", "name": "Los Santos", "in_focus_zone": true },
      "observed_activity_score": 100.0,
      "score_label": "Índice relativo de actividad sísmica observada (0–100)",
      "cluster_level": "Muy alto", "cluster_level_order": 5, "mixed_profile": false,
      "indicators": {
        "events_per_year_r30": 2983.4, "m3_events_per_year_r30": 280.4, "m4_events_per_year_r30": 41.7,
        "magnitude_max_r30": 5.3, "depth_median_r30_km": 140.9, "shallow_fraction_r30": 0.0013,
        "distance_to_nest_km": 6.4, "energy_flux_log10_j_m2_yr": 1.894
      },
      "components": [
        { "key": "actividad", "z_mean": 2.73, "percentile": 99, "direction": "+" },
        { "key": "magnitud", "z_mean": 1.35, "percentile": 84, "direction": "+" },
        { "key": "energia", "z_mean": 1.93, "percentile": 99, "direction": "+" },
        { "key": "sacudida", "z_mean": 1.16, "percentile": 97, "direction": "+" },
        { "key": "superficialidad", "z_mean": 0.21, "percentile": 49, "direction": "+" },
        { "key": "distancia", "z_mean": 1.79, "percentile": 98, "direction": "−",
          "note": "Ya invertido: valor alto = más cerca de las fuentes." }
      ],
      "explanation": [
        "Tiene más sismos por año a ≤ 30 km que el 98 % de los municipios (2 983/año con M ≥ 2.0).",
        "Su centro está a 6.4 km del epicentro del Nido de Bucaramanga.",
        "La energía sísmica que llega al municipio supera a la del 97 % de los municipios.",
        "Casi toda su sismicidad es profunda (mediana 141 km): por eso la superficialidad no suma."
      ],
      "quality": { "events_used": 8936, "reliable_only": true, "b_value_imputed": false },
      "dimensions": { "observed_activity": "available", "hazard": "not_computed",
                      "exposure": "missing_data", "vulnerability": "missing_data" },
      "method": "catalog_index_v1", "method_version": "1.0.0",
      "model_version": "kmeans-2026.10.13-a35dcf9", "computed_at": "2026-10-13T15:39:58Z",
      "period": { "start": "2020-03-02", "end": "2023-02-28" }
    }
  ],
  "pagination": { "page": 1, "page_size": 87, "total": 87, "total_pages": 1 },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M56", "generated_at": "2026-10-13T18:00:16Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC", "DANE-MGN2018"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": { "method": "catalog_index_v1" },
            "interpretation": "Ordena municipios por actividad sísmica observada y cercanía a fuentes. No es riesgo ni probabilidad: no incluye amenaza probabilística, exposición ni vulnerabilidad.",
            "warnings": [] }
}
```
  (Algunos valores de `indicators` y `quality.events_used` se tomarán de `salidas/municipios_clasificados.csv` al
  implementar; los de este ejemplo provienen de ese archivo y de `docs/diccionario_datos.md`.)
- **Campos:** `observed_activity_score` number 0–100 (relativo al conjunto de 87; no comparable entre corridas con
  datos distintos); `percentile` integer 0–100 (porcentaje de municipios con valor menor); `mixed_profile` boolean
  (el índice y el nivel K-Means difieren en ≥ 2 niveles); `dimensions.*` como en `/meta`.
- **Códigos:** 200, 422, 503 (modelo no calculado).
- **Axios:** `api.get<Paginated<PriorityZone>>("/priority-zones", { params: { method: "catalog_index_v1" } })`

#### E2. `GET /api/v1/priority-zones/{municipality_code}` — explicación de un municipio

- **Parámetros de ruta:** `municipality_code` (5 dígitos). Consulta: `method`.
- **Respuesta 200:** el mismo objeto de E1 para ese municipio más `variables` (las 21 variables del modelo con
  valor, unidad, percentil y si fue imputada) y `neighbors_in_ranking` (posiciones anterior y siguiente).
  Ejemplo de perfil mixto (Bucaramanga):
```json
{
  "data": {
    "rank": 20,
    "municipality": { "code": "68001", "name": "Bucaramanga", "in_focus_zone": true },
    "observed_activity_score": 56.7,
    "cluster_level": "Bajo", "cluster_level_order": 2, "mixed_profile": true,
    "level_by_score": "Alto",
    "explanation": [
      "Su índice (56.7) lo ubicaría en 'Alto', pero su perfil de 21 variables se parece al grupo 'Bajo'.",
      "El epicentro del Nido queda a 42.1 km: pocos epicentros caen a ≤ 30 km (53 sismos/año, percentil 48).",
      "La energía que llega con distancia hipocentral es alta (percentil 68) porque el Nido está a ~140 km de profundidad.",
      "Hubo un sismo M ≥ 4 a 4.3 km de su centro en el periodo de entrenamiento (más cerca que el 98 % de los municipios)."
    ],
    "variables": [
      { "key": "tasa_sismos_r30", "label": "Sismos por año con M ≥ Mc a ≤ 30 km", "value": 53.08, "unit": "eventos/año",
        "percentile": 48, "imputed": false },
      { "key": "dist_nido_km", "label": "Distancia epicentral al centro del Nido", "value": 42.09, "unit": "km",
        "percentile": 29, "imputed": false }
    ],
    "neighbors_in_ranking": { "previous": { "rank": 19, "code": "68xxx" }, "next": { "rank": 21, "code": "68yyy" } },
    "method": "catalog_index_v1", "method_version": "1.0.0", "model_version": "kmeans-2026.10.13-a35dcf9",
    "computed_at": "2026-10-13T15:39:58Z", "period": { "start": "2020-03-02", "end": "2023-02-28" }
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M57", "generated_at": "2026-10-13T18:00:17Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC", "DANE-MGN2018"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": { "method": "catalog_index_v1" }, "warnings": [] }
}
```
  (`variables` recortado a 2 de 21; `neighbors_in_ranking` con códigos de marcador de posición.)
- **Códigos:** 200, 404 `MUNICIPALITY_NOT_FOUND`, 422.
- **Axios:** `api.get<ApiResponse<PriorityZoneDetail>>(\`/priority-zones/${code}\`)`

#### E3. `GET /api/v1/priority-zones/methods` — métodos

- **Respuesta 200:**
```json
{
  "data": [
    {
      "method": "catalog_index_v1", "version": "1.0.0",
      "name": "Índice relativo de actividad sísmica observada",
      "what_it_measures": "Actividad sísmica registrada en el catálogo SGC y cercanía a fuentes, relativa entre los 87 municipios.",
      "what_it_does_not_measure": ["Probabilidad de terremoto", "Amenaza probabilística (PSHA)", "Exposición", "Vulnerabilidad", "Pérdidas"],
      "components": [
        { "key": "actividad", "variables": ["tasa_sismos_r30", "tasa_m3_r30", "tasa_fuertes_r30", "densidad_epicentros"], "direction": "+", "weight": 1 },
        { "key": "magnitud", "variables": ["mag_max_r30", "mag_p95_r30"], "direction": "+", "weight": 1 },
        { "key": "energia", "variables": ["log_energia_anual_r30"], "direction": "+", "weight": 1 },
        { "key": "sacudida", "variables": ["log_flujo_energia_hipo"], "direction": "+", "weight": 1 },
        { "key": "superficialidad", "variables": ["frac_superficiales_r30", "tasa_superficiales_r30", "mag_max_superficial_r30"], "direction": "+", "weight": 1 },
        { "key": "distancia", "variables": ["dist_nido_km", "dist_sismo_fuerte_km", "dist_sismo_superficial_m3_km", "dist_fuente_cortical_km"], "direction": "−", "weight": 1 }
      ],
      "formula": "score = 100 · (S − min S) / (max S − min S), S = media de los componentes; cada componente = media de las variables estandarizadas (z) tras log1p en las sesgadas.",
      "period": { "start": "2020-03-02", "end": "2023-02-28" },
      "validation": {
        "target": "Sismos M ≥ 4 por año a ≤ 50 km en un periodo posterior (2023-03-01 a 2025-03-01) no usado en el cálculo",
        "spearman_score_vs_target": 0.83, "spearman_level_vs_target": 0.70,
        "baseline_persistence_spearman": 0.69
      },
      "limitations": [
        "Solo 3 años de entrenamiento (exports 2020-03 a 2025-03).",
        "Exports pedidos por departamento: los municipios de borde ven menos sismos.",
        "Magnitudes de tipos mezclados (mayoría ML)."
      ]
    },
    {
      "method": "kmeans_levels_v1", "version": "1.0.0",
      "name": "Niveles relativos por agrupamiento (K-Means)",
      "what_it_measures": "Grupos de municipios con perfil sísmico parecido (21 variables), nombrados de menor a mayor actividad.",
      "what_it_does_not_measure": ["Probabilidad de terremoto", "Exposición", "Vulnerabilidad"],
      "components": [],
      "formula": "K-Means k=5 (200 inicios) sobre 21 variables estandarizadas; el nivel se ordena por el índice medio del grupo.",
      "period": { "start": "2020-03-02", "end": "2023-02-28" },
      "validation": { "silhouette": 0.318, "bootstrap_ari": 0.78, "spearman_level_vs_target": 0.70 },
      "limitations": ["Los municipios con perfil mixto (8) se reportan aparte; no se reasignan a mano."]
    }
  ],
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M58", "generated_at": "2026-10-13T18:00:18Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
- **Códigos:** 200.
- **Axios:** `api.get<ApiResponse<ScoringMethod[]>>("/priority-zones/methods")`

---

### G. Agente de recomendación

Las recomendaciones salen de **reglas explícitas y versionadas**, evaluadas sobre indicadores del municipio. No hay
modelo de IA entrenado; el endpoint de IA (G3) está definido pero devuelve **501** hasta que se implemente.

**Formato de una regla** (guardada en `recommendation_rule.definition_json`, editable en `api/rules/recommendation_rules.yaml`):

| Campo | Tipo | Descripción |
|---|---|---|
| `rule_id`, `version` | string, integer | Identidad. |
| `title` | string | Nombre corto. |
| `condition` | `{ all: Condition[] }` o `{ any: Condition[] }` | `Condition = { indicator, operator: ">=" \| "<=" \| ">" \| "<" \| "==", value, value_type: "absolute" \| "percentile" }`. Los umbrales en **percentil** son relativos a los 87 municipios: evitan fijar umbrales científicos que no se pueden justificar. |
| `recommendation` | string | Texto para el usuario. |
| `severity` | `"info" \| "attention" \| "priority"` | No es una escala de riesgo; ordena la lista. |
| `kind` | `"recommendation" \| "data_warning"` | Las de datos insuficientes son advertencias. |
| `rationale` | string | Por qué existe la regla. |
| `evidence_fields` | string[] | Indicadores que se muestran como evidencia. |

**Reglas de ejemplo (borrador; textos a validar por el equipo, decisión D8):**

| `rule_id` | Condición | Texto | Severidad |
|---|---|---|---|
| `R01_actividad_alta` | `tasa_m3_r30` percentil ≥ 75 | "La frecuencia de sismos de magnitud ≥ 3 en un radio de 30 km está entre el 25 % más alto de Santander. Conviene priorizar este municipio en las actividades de preparación y comunicación del riesgo sísmico." | priority |
| `R02_sismo_fuerte_cercano` | `dist_sismo_fuerte_km` ≤ 20 (absoluto) | "Se registró al menos un sismo de magnitud ≥ 4 a menos de 20 km del municipio en el periodo analizado. Verifique que los planes municipales de respuesta contemplen sismos sentidos." | attention |
| `R03_sismicidad_superficial` | `tasa_superficiales_r30` percentil ≥ 75 | "Hay más sismicidad superficial (< 30 km) que en el 75 % de los municipios. Consulte la información de fallas activas del SGC para la zona." | attention |
| `R04_nido_cercano` | `dist_nido_km` ≤ 50 (absoluto) | "El municipio está a menos de 50 km del epicentro del Nido de Bucaramanga, fuente de sismos frecuentes a ~140 km de profundidad que suelen sentirse en amplias zonas." | info |
| `W01_pocos_eventos` | `n_sismos_r30` < 50 (absoluto) | "Hay menos de 50 sismos en el vecindario: los indicadores de magnitud y el valor b son poco robustos." | data_warning |
| `W02_perfil_mixto` | `mixed_profile` == true | "El índice y el nivel del modelo no coinciden; revise la explicación antes de concluir." | data_warning |
| `W03_periodo_corto` | años de entrenamiento < 5 | "El análisis usa menos de 5 años de datos." | data_warning |

#### G1. `GET /api/v1/recommendations/rules`

- **Parámetros:** `active` (bool, por defecto `true`).
- **Respuesta 200** (una regla):
```json
{
  "data": [
    { "rule_id": "R01_actividad_alta", "version": 1, "title": "Actividad sísmica frecuente",
      "condition": { "all": [ { "indicator": "tasa_m3_r30", "operator": ">=", "value": 75, "value_type": "percentile" } ] },
      "recommendation": "La frecuencia de sismos de magnitud ≥ 3 en un radio de 30 km está entre el 25 % más alto de Santander. Conviene priorizar este municipio en las actividades de preparación y comunicación del riesgo sísmico.",
      "severity": "priority", "kind": "recommendation",
      "rationale": "Regla relativa (percentil) para no fijar umbrales absolutos sin sustento.",
      "evidence_fields": ["tasa_m3_r30"], "active": true }
  ],
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M59", "generated_at": "2026-10-13T18:00:19Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": { "active": true },
            "rules_version": "2026-10-13", "warnings": [] }
}
```
- **Axios:** `api.get<ApiResponse<RecommendationRule[]>>("/recommendations/rules")`

#### G2. `POST /api/v1/recommendations/evaluate`

- **Cuerpo:**
```json
{ "municipality_code": "68001", "log_query": false }
```
  `municipality_code` (string, 5 dígitos, obligatorio); `log_query` (boolean, por defecto `false`: solo se registra
  si el usuario lo acepta; nunca se guarda IP ni texto libre).
- **Respuesta 200** (Bucaramanga):
```json
{
  "data": {
    "municipality": { "code": "68001", "name": "Bucaramanga" },
    "evaluated_at": "2026-10-13T18:00:20Z",
    "rules_version": "2026-10-13",
    "recommendations": [
      { "rule_id": "R02_sismo_fuerte_cercano", "severity": "attention", "kind": "recommendation",
        "text": "Se registró al menos un sismo de magnitud ≥ 4 a menos de 20 km del municipio en el periodo analizado. Verifique que los planes municipales de respuesta contemplen sismos sentidos.",
        "evidence": [ { "indicator": "dist_sismo_fuerte_km", "value": 4.29, "unit": "km", "threshold": 20,
                        "operator": "<=", "value_type": "absolute", "percentile": 2 } ] },
      { "rule_id": "R04_nido_cercano", "severity": "info", "kind": "recommendation",
        "text": "El municipio está a menos de 50 km del epicentro del Nido de Bucaramanga, fuente de sismos frecuentes a ~140 km de profundidad que suelen sentirse en amplias zonas.",
        "evidence": [ { "indicator": "dist_nido_km", "value": 42.09, "unit": "km", "threshold": 50,
                        "operator": "<=", "value_type": "absolute", "percentile": 29 } ] }
    ],
    "warnings": [
      { "rule_id": "W02_perfil_mixto", "text": "El índice y el nivel del modelo no coinciden; revise la explicación antes de concluir." },
      { "rule_id": "W03_periodo_corto", "text": "El análisis usa menos de 5 años de datos." }
    ],
    "rules_not_triggered": ["R01_actividad_alta", "R03_sismicidad_superficial", "W01_pocos_eventos"],
    "disclaimer": "Recomendaciones generadas por reglas explícitas sobre datos del catálogo SGC. No sustituyen la evaluación de las autoridades de gestión del riesgo.",
    "generated_by": "rules_engine",
    "logged": false
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M5A", "generated_at": "2026-10-13T18:00:20Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
  (Bucaramanga: `tasa_m3_r30` percentil 70 → R01 no se activa; `n_sismos_r30` = 159 → W01 no se activa.)
- **Códigos:** 200, 404 `MUNICIPALITY_NOT_FOUND`, 422.
- **Axios:** `api.post<ApiResponse<RecommendationResult>>("/recommendations/evaluate", { municipality_code: "68001" })`

#### G3. `POST /api/v1/assistant/ask` — asistente con IA (futuro)

- **Estado actual:** responde **501 `NOT_IMPLEMENTED`** y `GET /meta` informa `assistant_enabled: false`. El
  frontend debe ocultar o deshabilitar la función mientras tanto.
- **Cuerpo (contrato futuro):**
```json
{ "question": "¿Por qué Bucaramanga aparece con perfil mixto?", "municipality_code": "68001" }
```
  `question` 3–500 caracteres; `municipality_code` opcional.
- **Diseño anti-alucinación (para cuando se implemente):**
  1. El servidor arma el **contexto** solo con respuestas de esta API (E2, G2, B1 del municipio) en JSON; el modelo
     no consulta nada más.
  2. Instrucción de sistema: responder solo con cifras del contexto, citar el campo de cada cifra, decir "no hay
     datos" si falta información, no hablar de probabilidad de terremotos ni de riesgo.
  3. Salida estructurada: `{ answer, citations: [{ field, value, endpoint }], refused: boolean }`.
  4. **Verificación en el servidor:** cada número del texto debe aparecer en `citations` y en el contexto; si no,
     se descarta la respuesta y se devuelve `refused: true` con un mensaje fijo.
  5. La clave del proveedor vive solo en el servidor (variable de entorno), nunca en el frontend; límite de
     peticiones por IP más estricto (p. ej. 10/min).
- **Respuesta futura 200:**
```json
{
  "data": {
    "answer": "Bucaramanga tiene un índice de 56.7 (posición 20 de 87), pero su perfil de variables se parece al grupo 'Bajo' porque el epicentro del Nido está a 42.1 km.",
    "citations": [
      { "field": "observed_activity_score", "value": 56.7, "endpoint": "/priority-zones/68001" },
      { "field": "rank", "value": 20, "endpoint": "/priority-zones/68001" },
      { "field": "dist_nido_km", "value": 42.09, "endpoint": "/priority-zones/68001" }
    ],
    "refused": false, "generated_by": "llm", "model": "por definir"
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M5B", "generated_at": "2026-10-13T18:00:21Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
- **Códigos:** 501 (hoy); a futuro 200, 422, 429, 503 (`ASSISTANT_UNAVAILABLE`).

---

### H. Importación y calidad (administración, requiere token)

Autenticación: cabecera `Authorization: Bearer <ADMIN_TOKEN>`. El token se define en la variable de entorno
`ADMIN_TOKEN` del servidor (se guarda su SHA-256 en `api_user`). Sin token → 401; token inválido o sin rol → 403.
Estos endpoints no se exponen en el frontend público.

#### H1. `POST /api/v1/admin/imports`

- **Cuerpo:** `multipart/form-data`:

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `file` | archivo `.xlsx` / `.xls` / `.csv` | sí | máx. 20 MB |
| `source_id` | string | sí | p. ej. `SGC-RSNC` |
| `downloaded_at` | date | sí | fecha en que se descargó del portal (trazabilidad) |
| `query_description` | string | no | filtros usados en el portal si el archivo no los trae |
| `dry_run` | boolean | no (`false`) | `true` = solo valida y devuelve el informe, no guarda nada |

- **Respuesta 202** (proceso en segundo plano; con `dry_run=true` la respuesta es **200** con el informe directo):
```json
{
  "data": { "import_id": "imp_20261013_0006", "status": "validating",
            "status_url": "/api/v1/admin/imports/imp_20261013_0006" },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M5C", "generated_at": "2026-10-13T18:00:22Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
- **Códigos:** 202, 200 (`dry_run`), 401, 403, 409 `DUPLICATE_FILE`, 413 `FILE_TOO_LARGE`, 415
  `UNSUPPORTED_FORMAT`, 422 `MISSING_COLUMNS` (con columnas encontradas).
- **Axios (herramienta interna):**
```ts
const form = new FormData();
form.append("file", file); form.append("source_id", "SGC-RSNC"); form.append("downloaded_at", "2026-10-13");
await adminApi.post("/admin/imports", form);   // adminApi agrega Authorization desde un entorno seguro, no el frontend público
```

#### H2. `GET /api/v1/admin/imports` — historial

- Paginado (`page`, `page_size` ≤ 100). Cada fila: `import_id`, `file_name`, `source_id`, `status`, `imported_at`,
  `downloaded_at`, `rows_read`, `rows_inserted`, `rows_duplicate`, `rows_invalid`, `imported_by`, `origin`.

#### H3. `GET /api/v1/admin/imports/{import_id}` — estado e informe de calidad

- **Respuesta 200:**
```json
{
  "data": {
    "import_id": "imp_20261013_0005", "status": "completed_with_warnings",
    "file_name": "Csg_2024.xlsx", "file_sha256": "a6030fdb64b7f4d0…", "file_format": "sgc_portal_xlsx_2018",
    "encoding_detected": "utf-8", "downloaded_at": "2026-10-13", "portal_created_at": "2026-10-13T10:14:21-04:00",
    "imported_at": "2026-10-13T15:25:00Z", "imported_by": "pipeline", "origin": "pipeline",
    "source_query": { "DEPARTAMENTO": "Santander", "FECHA_INICIAL": "2024-03-02", "FECHA_FINAL": "2025-03-01",
                      "TIPO CONSULTA": "cuadrante", "TOTAL REGISTROS": "14928" },
    "columns": { "recognized": ["FECHA - HORA UTC", "LATITUD (°)", "LONGITUD (°)", "PROF. (Km)", "MAGNITUD", "TIPO MAGNITUD",
                                "FASES", "RMS (Seg)", "GAP (°)", "ERROR LATITUD (Km)", "ERROR LONGITUD (Km)",
                                "ERROR PROFUNDIDAD (Km)", "REGION", "ESTADO"],
                 "unrecognized": [], "repaired_encoding": [] },
    "counts": { "rows_read": 14928, "rows_inserted": 14928, "rows_duplicate": 0, "rows_invalid": 0, "rows_flagged": 1414 },
    "flags": { "gap_gt_270": 262, "rms_gt_1_2_m_lt_3": 319, "horizontal_error_gt_10km": 402,
               "depth_error_gt_10km": 578, "phases_lt_6": 19, "depth_negative": 7, "outside_study_area": 0 },
    "date_range": { "start": "2024-03-02T00:26:26Z", "end": "2025-03-01T23:29:07Z" },
    "declared_vs_read": { "declared_total": 14928, "read": 14928, "match": true },
    "errors": []
  },
  "meta": { "api_version": "1.0.0", "request_id": "req_01J9ZK7M5D", "generated_at": "2026-10-13T18:00:23Z",
            "data_mode": "real", "data_version": "dv_6f1c2a9e", "sources": ["SGC-RSNC"],
            "coverage": { "start": "2020-03-02", "end": "2025-03-01" }, "applied_filters": {}, "warnings": [] }
}
```
  (Valores reales de `Csg_2024.xlsx` con el pipeline actual; `import_id` ilustrativo. Hoy una corrección de la
  profundidad negativa la fija en 0 km: en la API se conserva el valor original y solo se marca.)
- **Códigos:** 200, 401, 403, 404 `IMPORT_NOT_FOUND`.

#### H4. `POST /api/v1/admin/recompute`

- **Cuerpo:** `{ "steps": ["derived", "model"] }` (`derived` = asociación a municipios, clases y calidad;
  `model` = re-ejecuta HDBSCAN + variables + K-Means con `run_all.py`).
- **Respuesta 202:** `{ "data": { "job_id": "job_20261013_0002", "status": "queued" }, "meta": {…} }`. El estado se
  consulta en `GET /admin/imports/{job_id}` (mismo esquema de estado). Mientras corre, la API sigue sirviendo la
  versión anterior; al terminar cambia `data_version`/`model_version` de forma atómica.
- **Códigos:** 202, 401, 403, 409 `JOB_ALREADY_RUNNING`.

#### H5. `GET /api/v1/admin/query-log`

- Paginado. Filas: `logged_at`, `endpoint`, `municipality_code`, `params` (sin IP ni texto libre), `session_hash`
  (hash diario rotado). Retención sugerida: 30 días.
- **Códigos:** 200, 401, 403.

---

## 4. Manejo de errores (entregable 11)

**Formato único:**
```json
{
  "error": {
    "code": "INVALID_FILTER",
    "message": "Algunos filtros no son válidos.",
    "details": [
      { "field": "min_magnitude", "issue": "Debe ser menor o igual que max_magnitude.", "value": "5" },
      { "field": "start_date", "issue": "Formato esperado YYYY-MM-DD.", "value": "13/10/2024" }
    ],
    "request_id": "req_01J9ZK7M5E",
    "documentation_url": "/docs#filtros-globales"
  }
}
```

| HTTP | `code` | Cuándo | Mensaje para el usuario (sugerido) |
|---|---|---|---|
| 400 | `UNKNOWN_PARAMETER` | Parámetro de consulta no definido | "La consulta tiene un parámetro no reconocido." |
| 400 | `MALFORMED_BODY` | JSON inválido | "La solicitud no tiene un formato válido." |
| 401 | `UNAUTHENTICATED` | Falta token en `/admin` | "Debe iniciar sesión como administrador." |
| 403 | `FORBIDDEN` | Token inválido o sin rol | "No tiene permisos para esta operación." |
| 404 | `EVENT_NOT_FOUND`, `MUNICIPALITY_NOT_FOUND`, `IMPORT_NOT_FOUND` | Recurso inexistente | "No se encontró el sismo / municipio / importación solicitado." |
| 409 | `DUPLICATE_FILE`, `JOB_ALREADY_RUNNING` | Conflicto | "Este archivo ya fue importado." |
| 413 | `FILE_TOO_LARGE`, `EXPORT_TOO_LARGE` | Tamaño excedido | "El resultado es demasiado grande; reduzca el rango de fechas." |
| 415 | `UNSUPPORTED_FORMAT` | Archivo no `.xlsx/.xls/.csv` | "Formato de archivo no soportado." |
| 422 | `INVALID_FILTER`, `FILTER_NOT_SUPPORTED`, `UNEQUAL_PERIODS`, `TOO_MANY_BUCKETS`, `MISSING_COLUMNS` | Validación | Mensaje con `details` por campo |
| 429 | `RATE_LIMITED` | Demasiadas peticiones (cabecera `Retry-After`) | "Demasiadas consultas; intente en unos segundos." |
| 500 | `INTERNAL_ERROR` | Error no controlado (sin trazas al cliente; se registran con `request_id`) | "Ocurrió un error inesperado. Código: {request_id}." |
| 501 | `NOT_IMPLEMENTED` | Asistente de IA | "Esta función aún no está disponible." |
| 503 | `DATA_NOT_LOADED`, `MODEL_NOT_COMPUTED`, `ASSISTANT_UNAVAILABLE` | Base o modelo no disponibles | "Los datos no están disponibles en este momento." |
| 504 | `QUERY_TIMEOUT` | Consulta > 10 s | "La consulta tardó demasiado; acote los filtros." |

Reglas: el `message` está pensado para mostrarse al usuario; `details[].issue` para mostrar junto al campo del
formulario; nunca se envían trazas ni SQL al cliente.

---

## 5. Seguridad y rendimiento (entregable 12)

| Medida | Cómo |
|---|---|
| No descargar todo el catálogo | Listas paginadas (`page_size` ≤ 500), `/events/geojson` con `limit` ≤ 10 000 y truncado explícito, agregación por celdas y por municipio, CSV limitado a 100 000 filas. |
| Consultas geográficas acotadas | `bbox` con área ≤ 100 grados²; celdas ≥ 0.05°; máx. 5 000 celdas; índices sobre (`latitude`, `longitude`). Punto-en-polígono precalculado al importar. |
| Validación de entrada | Modelos Pydantic para cada parámetro y cuerpo; rangos y enums de §1; parámetros desconocidos rechazados. |
| Inyección SQL | Solo consultas parametrizadas (`?`) desde `api/filters.py`; `sort_by` se traduce desde una lista blanca de columnas; nunca se interpola texto del usuario. |
| Tiempos de espera | `sqlite3.connect(timeout=5)`; tope de 10 s por consulta (`progress_handler` de SQLite) → 504; *timeout* del cliente Axios 15 s. |
| Errores del servidor | Manejador global → 500 con `request_id`; registro estructurado (JSON) en el servidor. |
| Límite de peticiones | Si se publica: 120 peticiones/min por IP en endpoints públicos, 5/min en `/events/export`, 10/min en `/assistant/ask` (p. ej. `slowapi` o el proxy del despliegue). |
| Endpoints administrativos | Token *Bearer* en variable de entorno (nunca en el repositorio ni en el frontend); comparación en tiempo constante; HTTPS en producción; `Cache-Control: no-store`; tamaño máximo de archivo 20 MB. |
| CORS | Lista blanca: `http://localhost:5173` (Vite) y el dominio de producción. Sin `*` en producción. |
| Secretos | Variables de entorno (`ADMIN_TOKEN`, clave del proveedor de IA si llega a existir). El frontend no recibe ninguna clave. |
| Fuente externa | No hay consultas en vivo al SGC: no hay límites de uso externos que respetar en tiempo de petición. Las descargas del portal se hacen manualmente y se registran con su fecha. |
| Indisponibilidad del SGC | No afecta a la API (datos almacenados). `/meta` muestra `last_import_at` y `coverage.end`; el frontend debe decir "datos hasta {coverage.end}", nunca "en tiempo real". |
| Histórico vs tiempo real | `realtime: false` en `/meta`. Si en el futuro se agrega una fuente en vivo, sus eventos llevarán otra `source_id` y `meta.sources` lo indicará. |
| Caché | LRU en memoria por filtros + `data_version`; `ETag`/`If-None-Match`; `Cache-Control: public, max-age=300` (ver [data-model.md §9](data-model.md#9-caché)). |
| Tamaño de respuestas | Compresión `gzip` (middleware `GZipMiddleware` de FastAPI) para JSON y GeoJSON > 1 KB; polígonos simplificados. |
