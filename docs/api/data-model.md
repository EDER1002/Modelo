# SismoSantander · Arquitectura y modelo de datos

Documento 2 de 5 (ver [README](README.md)). Cubre los entregables 4 (arquitectura) y 5 (modelo de datos), más la
estrategia de importación, deduplicación, versionado, agregaciones y caché.

---

## 1. Arquitectura recomendada

```
 Exports SGC (.xlsx/.csv) ──► Pipeline Python (scripts/00–07)  ──► modelo + salidas (JSON/CSV/GeoJSON)
                                   │                                        │
                                   ▼                                        ▼
                         scripts/08_cargar_base.py  ───────────►  SQLite: datos/sismos.db
                                                                   (eventos, procedencia, municipios,
                                                                    fuentes, ranking, reglas)
                                                                            │  solo lectura
                                                                            ▼
                                       FastAPI /api/v1  (filtros comunes, validación, caché, CORS)
                                                                            │  JSON / GeoJSON / CSV
                                                                            ▼
                                       Frontend React + Vite (Axios, Recharts, React Leaflet)
```

- **Backend:** FastAPI (ya está en el repositorio) + **SQLite** con el módulo estándar `sqlite3`.
- **Procesamiento pesado** (unificación, HDBSCAN, K-Means, asociación a municipios): el pipeline existente, fuera de
  la API. La API **no entrena** modelos en una petición.
- **Carga:** `scripts/08_cargar_base.py` (nuevo) vuelca el catálogo normalizado y las salidas del modelo a SQLite.
  Las importaciones administrativas (fase 3) reutilizan el mismo código de normalización.
- **Despliegue:** un contenedor (el `Dockerfile` existente) con la base SQLite incluida o en un volumen.

### 1.1 Evaluación de opciones de almacenamiento

| Opción | A favor | En contra | Veredicto |
|---|---|---|---|
| **SQLite** | Un solo archivo, cero administración, viene con Python, SQL con parámetros, índices B-tree, transacciones. Sobra para 64 k eventos (y para cientos de miles si se suma 1993–2025). | Una sola escritura a la vez (irrelevante: las escrituras son importaciones esporádicas). Sin funciones espaciales nativas. | **Recomendada para el hackathon.** |
| PostgreSQL + PostGIS | Índices espaciales, consultas por polígono y radio en la base, multiusuario. | Servidor que instalar, desplegar y respaldar; curva de aprendizaje; el cálculo espacial costoso (punto en polígono) ya lo hace el pipeline al importar. | Ruta de crecimiento si el catálogo crece a millones o se necesitan consultas por polígono arbitrario. |
| PostgreSQL sin PostGIS | Robusto, multiusuario. | Mismo costo de despliegue que con PostGIS, sin la ventaja espacial. | No aporta frente a SQLite en este tamaño. |
| MySQL | Conocido por el equipo. | Mismo costo de despliegue; soporte espacial menos práctico. | No recomendado. |
| CSV en memoria (pandas) | Es lo que hace hoy `api.py`; trivial. | Sin historial de importaciones, sin integridad, la paginación y el orden se reimplementan a mano, todo el catálogo en RAM por proceso. | Válido solo para la fase 0. |

**Por qué no hace falta PostGIS:** las consultas geográficas del frontend son (a) caja (*bounding box*) → rango
sobre `latitude` y `longitude` con índice; (b) municipio → la asociación punto-polígono se calcula **una vez** al
importar y se guarda como columna; (c) radio alrededor de un municipio → se prefiltra por caja en SQL y se refina
con la fórmula de haversine en Python. Con decenas o cientos de miles de filas, todas responden en milisegundos.

---

## 2. Entidades y relaciones

```
source 1──* import_batch 1──* raw_event 1──1 event 1──1 event_derived *──1 municipality
                                                    │                    *──1 seismic_source *──1 model_run
municipality 1──* municipality_score *──1 model_run
recommendation_rule (versionadas)        query_log (opcional, anónimo)        api_user (admin)
```

| Entidad | Qué guarda | Origen de los datos |
|---|---|---|
| `source` | Fuentes de datos (SGC-RSNC, USGS, simulado) | catálogo propio |
| `import_batch` | Cada archivo importado: hash, fecha de descarga declarada, parámetros de búsqueda del portal, conteos e informe de calidad | procedencia |
| `raw_event` | La fila original **exacta** (todas las columnas como texto) | original |
| `event` | El evento normalizado (tipos y unidades homogéneos) | normalizado |
| `event_derived` | Asociación a municipio, banderas de calidad, duplicados, fuente sísmica, clases | derivado / asociado / modelo |
| `municipality` | 87 municipios DANE MGN 2018 con geometría simplificada | DANE |
| `seismic_source` | Fuentes de HDBSCAN (nivel 1) | modelo |
| `model_run` | Versión, parámetros, métricas y periodos de cada corrida del modelo | modelo |
| `municipality_score` | Índice, nivel K-Means, componentes y explicación por municipio y corrida | modelo |
| `recommendation_rule` | Reglas explícitas versionadas del agente | configuración |
| `query_log` | Consultas al agente sin datos personales (opcional) | uso |
| `api_user` | Administradores (hash del token) | seguridad |

---

## 3. Esquema SQL (SQLite)

Archivo propuesto: `sql/schema.sql`. Fechas en texto ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`), que en SQLite ordena
y compara correctamente.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE source (
  source_id      TEXT PRIMARY KEY,                       -- 'SGC-RSNC', 'USGS-COMCAT', 'DEMO'
  name           TEXT NOT NULL,
  kind           TEXT NOT NULL CHECK (kind IN ('real','simulated')),
  url            TEXT,
  description    TEXT,
  terms_note     TEXT                                    -- límites/condiciones conocidas (o 'no verificados')
);

CREATE TABLE import_batch (
  import_id          TEXT PRIMARY KEY,                   -- 'imp_20261013_0001'
  source_id          TEXT NOT NULL REFERENCES source(source_id),
  file_name          TEXT NOT NULL,
  file_sha256        TEXT NOT NULL,
  file_format        TEXT NOT NULL,                      -- 'sgc_portal_xlsx_2018', 'sgc_portal_pre2018', 'sgc_csv_quakeml', ...
  encoding_detected  TEXT,                               -- 'utf-8', 'latin-1', 'utf-8 (mojibake reparado)'
  downloaded_at      TEXT,                               -- fecha declarada de descarga del portal
  portal_created_at  TEXT,                               -- fecha interna del .xlsx (docProps/core.xml), si existe
  query_params_json  TEXT,                               -- bloque PARAMETROS DE BUSQUEDA tal cual
  imported_at        TEXT NOT NULL,
  imported_by        TEXT,                               -- usuario admin o 'pipeline'
  origin             TEXT,                               -- 'pipeline' | 'admin_upload'
  status             TEXT NOT NULL CHECK (status IN ('pending','validating','importing','completed',
                                                     'completed_with_warnings','failed','reverted')),
  rows_read          INTEGER, rows_inserted INTEGER, rows_duplicate INTEGER,
  rows_invalid       INTEGER, rows_flagged INTEGER,
  quality_report_json TEXT,
  UNIQUE (source_id, file_sha256)                        -- el mismo archivo no se importa dos veces
);

CREATE TABLE raw_event (
  raw_id        INTEGER PRIMARY KEY,
  import_id     TEXT NOT NULL REFERENCES import_batch(import_id),
  row_number    INTEGER NOT NULL,                        -- fila en el archivo original (1 = primera de datos)
  raw_json      TEXT NOT NULL,                           -- {"FECHA - HORA UTC": "2024-03-02 00:12:34", ...} SIN modificar
  parse_errors  TEXT,                                    -- JSON con errores de conversión, si hubo
  UNIQUE (import_id, row_number)
);

CREATE TABLE event (
  event_id               TEXT PRIMARY KEY,               -- 'sgc-3f9a1c0b2d4e5f60' (estable, ver §7)
  source_id              TEXT NOT NULL REFERENCES source(source_id),
  canonical_raw_id       INTEGER NOT NULL REFERENCES raw_event(raw_id),
  source_event_id        TEXT,                           -- id del SGC si el export lo trae (p. ej. en QuakeML)
  origin_time_utc        TEXT NOT NULL,
  origin_time_raw        TEXT NOT NULL,
  time_zone_declared     TEXT NOT NULL CHECK (time_zone_declared IN ('UTC','local_UTC-5','not_declared')),
  latitude               REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude              REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  depth_km               REAL,                           -- puede ser negativo pequeño (sobre el nivel del mar): no se descarta
  magnitude              REAL,
  magnitude_type         TEXT,                           -- original: 'MLr_3', 'Mw(mB)', ...
  magnitude_type_group   TEXT CHECK (magnitude_type_group IN ('ML','Mw','mb','M','other')),
  phase_count            INTEGER,
  rms_s                  REAL,
  azimuthal_gap_deg      REAL,
  latitude_error_km      REAL,
  longitude_error_km     REAL,
  depth_error_km         REAL,
  region_reported        TEXT,                           -- 'Zapatoca - Santander, Colombia'
  department_reported    TEXT,                           -- derivado del texto REGION
  country_reported       TEXT,                           -- derivado del texto REGION
  review_status          TEXT,                           -- 'manual' | 'automatic' (original)
  quakeml_url            TEXT,
  map_url                TEXT,
  first_import_id        TEXT NOT NULL REFERENCES import_batch(import_id),
  last_import_id         TEXT NOT NULL REFERENCES import_batch(import_id),
  imported_at            TEXT NOT NULL
);

CREATE TABLE event_derived (
  event_id                  TEXT PRIMARY KEY REFERENCES event(event_id) ON DELETE CASCADE,
  municipality_code         TEXT REFERENCES municipality(code),   -- NULL si el epicentro no cae en Santander
  municipality_method       TEXT NOT NULL DEFAULT 'point_in_polygon_mgn2018_simplified',
  distance_to_boundary_km   REAL,                       -- < 1 km = asociación menos fiable
  municipality_match_region INTEGER,                    -- 1/0: coincide con el municipio de REGION
  quality_flags             TEXT NOT NULL DEFAULT '[]',  -- JSON: ["depth_error_gt_10km", ...]
  is_reliable               INTEGER NOT NULL,           -- 1 = sin banderas de localización
  duplicate_of              TEXT REFERENCES event(event_id),
  in_study_area             INTEGER NOT NULL,           -- dentro de la caja de estudio
  depth_class               TEXT,                       -- '0-30','30-70','70-300','>300'
  energy_log10_j            REAL,                       -- 1.5 M + 4.8
  seismic_source_code       TEXT,                       -- 'F1'..'Fn' | 'F0' (difusa)
  seismic_source_type       TEXT,
  model_version             TEXT                        -- corrida que asignó la fuente
);

CREATE TABLE municipality (
  code              TEXT PRIMARY KEY CHECK (length(code) = 5),   -- DIVIPOLA '68001'
  name              TEXT NOT NULL,
  name_official     TEXT NOT NULL,
  department_code   TEXT NOT NULL,
  area_km2          REAL NOT NULL,                      -- área oficial MGN
  rep_lat REAL NOT NULL, rep_lon REAL NOT NULL,         -- punto representativo (dentro del polígono)
  in_focus_zone     INTEGER NOT NULL,                   -- AMB + Los Santos
  geometry_geojson  TEXT NOT NULL                       -- simplificada para el mapa
);

CREATE TABLE model_run (
  model_version     TEXT PRIMARY KEY,                   -- 'kmeans-2026.10.13-a35dcf9'
  computed_at       TEXT NOT NULL,
  data_version      TEXT NOT NULL,                      -- hash de los import_id usados
  training_period_start TEXT NOT NULL, training_period_end TEXT NOT NULL,
  validation_period_start TEXT NOT NULL, validation_period_end TEXT NOT NULL,
  params_json       TEXT NOT NULL, metrics_json TEXT NOT NULL
);

CREATE TABLE seismic_source (
  model_version TEXT NOT NULL REFERENCES model_run(model_version),
  code TEXT NOT NULL, type TEXT NOT NULL, name TEXT NOT NULL,
  center_lat REAL, center_lon REAL, depth_median_km REAL, depth_p10_km REAL, depth_p90_km REAL,
  event_count INTEGER, max_magnitude REAL, nearest_municipality TEXT,
  PRIMARY KEY (model_version, code)
);

CREATE TABLE municipality_score (
  model_version     TEXT NOT NULL REFERENCES model_run(model_version),
  municipality_code TEXT NOT NULL REFERENCES municipality(code),
  method            TEXT NOT NULL CHECK (method IN ('catalog_index_v1','kmeans_levels_v1')),
  score             REAL,                               -- 0–100 (índice) o NULL (método solo de niveles)
  level             TEXT, level_order INTEGER,
  rank              INTEGER NOT NULL,
  components_json   TEXT NOT NULL,                      -- valor, percentil y aporte de cada componente
  variables_json    TEXT NOT NULL,                      -- las 21 variables usadas
  mixed_profile     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (model_version, municipality_code, method)
);

CREATE TABLE recommendation_rule (
  rule_id TEXT NOT NULL, version INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  definition_json TEXT NOT NULL,                        -- condición, textos, severidad, fundamento
  created_at TEXT NOT NULL,
  PRIMARY KEY (rule_id, version)
);

CREATE TABLE query_log (                                -- opcional, sin IP ni texto libre por defecto
  log_id INTEGER PRIMARY KEY, logged_at TEXT NOT NULL, endpoint TEXT NOT NULL,
  municipality_code TEXT, params_json TEXT, session_hash TEXT  -- hash diario rotado, no identifica personas
);

CREATE TABLE api_user (
  user_id TEXT PRIMARY KEY, token_sha256 TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL CHECK (role IN ('admin')), created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
```

### 3.1 Índices

```sql
CREATE INDEX ix_event_time        ON event(origin_time_utc);
CREATE INDEX ix_event_mag         ON event(magnitude);
CREATE INDEX ix_event_depth       ON event(depth_km);
CREATE INDEX ix_event_lat_lon     ON event(latitude, longitude);      -- filtros por caja
CREATE INDEX ix_event_magtype     ON event(magnitude_type_group);
CREATE INDEX ix_event_department  ON event(department_reported);
CREATE INDEX ix_derived_mpio      ON event_derived(municipality_code);
CREATE INDEX ix_derived_reliable  ON event_derived(is_reliable);
CREATE INDEX ix_derived_dup       ON event_derived(duplicate_of);
CREATE INDEX ix_raw_import        ON raw_event(import_id);
CREATE INDEX ix_score_rank        ON municipality_score(model_version, method, rank);
```

### 3.2 Restricciones de integridad

- Claves foráneas activas (`PRAGMA foreign_keys = ON` en cada conexión).
- `CHECK` en latitud y longitud (rango físico) y en enumeraciones. **No** hay `CHECK` de rango sobre magnitud ni
  profundidad: valores raros pero posibles se conservan y se marcan en el informe de calidad.
- `UNIQUE(source_id, file_sha256)`: el mismo archivo no se importa dos veces.
- `UNIQUE(import_id, row_number)` en `raw_event`.
- `event_id` estable y único (ver §7); los duplicados no se borran: apuntan a su canónico con `duplicate_of` y
  quedan fuera de los conteos por defecto.

---

## 4. Separación entre datos originales y procesados

| Capa | Tabla | Regla |
|---|---|---|
| Original | `raw_event.raw_json`, `import_batch.query_params_json` | Nunca se modifica. Es lo que se muestra como "valor original" en el detalle del evento. |
| Normalizado | `event` | El mismo dato con nombre, tipo y unidad homogéneos. Cada campo sabe de qué columna original salió (diccionario en `GET /meta/variables`). |
| Derivado / asociado | `event_derived` | Calculado por el sistema, con el método declarado (`municipality_method`, `model_version`). |
| Modelo | `seismic_source`, `municipality_score`, `model_run` | Salidas del pipeline, con versión y fecha de cálculo. |

En las respuestas JSON, el detalle de un evento separa los bloques `original`, `normalized`, `derived` y
`provenance` (ver [api-endpoints.md §C.4](api-endpoints.md#c4-get-apiv1eventsevent_id--detalle-de-un-evento)).

---

## 5. Fuente y versión de los datos

- `source_id` identifica la fuente; `source.kind` distingue real de simulado.
- `import_id` identifica cada archivo; `data_version` = SHA-256 corto de la lista ordenada de `import_id` en estado
  `completed`. Cambia con cada importación y se devuelve en `meta.data_version` de **todas** las respuestas.
- `model_version` identifica la corrida del modelo (fecha + commit). El ranking y las fuentes sísmicas se
  devuelven con su `model_version` y `computed_at`.
- `GET /meta` informa `data_mode`: `real` (todas las fuentes `kind = real`), `simulated` (todas simuladas) o `mixed`.

---

## 6. Estrategia de importación

Mismos pasos para el pipeline (`08_cargar_base.py`) y para `POST /admin/imports`:

1. **Huella:** SHA-256 del archivo; si ya existe para la fuente → `409 DUPLICATE_FILE`.
2. **Lectura:** `.xlsx` con `python-calamine` (evita el error de estilos de openpyxl), `.xls` (incluido HTML
   disfrazado) y `.csv` con detección de separador.
3. **Codificación:** se prueba `utf-8-sig`, luego `latin-1`. Si aparecen secuencias de mojibake típicas (`Â°`, `Ã©`,
   `Ã±`) se reparan con el viaje `latin-1 → utf-8`, y se anota `encoding_detected = "utf-8 (mojibake reparado)"`
   con la lista de encabezados reparados.
4. **Encabezado:** se busca en las primeras 80 filas la fila con fecha, latitud, longitud, profundidad y magnitud.
   Lo anterior es el bloque de parámetros de búsqueda → `query_params_json`.
5. **Mapeo de columnas:** tabla de alias por prefijo normalizado (sin tildes, mayúsculas). Columnas desconocidas
   **no se pierden**: quedan en `raw_json`. Si faltan columnas obligatorias → `422 MISSING_COLUMNS` con la lista
   encontrada.
6. **Tipos:** números con coma o punto decimal; fechas ISO o con día primero; hora separada (formato antiguo);
   zona horaria según el encabezado (`UTC`, `local` → +5 h, sin declarar → se supone UTC y se marca `not_declared`).
7. **Validación de rangos** (marca, no descarta):
   - **Inválido** (no se inserta en `event`, sí queda en `raw_event` con `parse_errors`): fecha o coordenadas
     ilegibles, latitud fuera de [−90, 90], longitud fuera de [−180, 180].
   - **Marcado** (`quality_flags`): magnitud fuera de [−1, 9.5], profundidad < −5 km o > 700 km, fuera de la caja
     de estudio, criterios de localización (gap, RMS para M < 3, errores, fases).
8. **Deduplicación** (§7).
9. **Derivados:** municipio por punto-en-polígono, `distance_to_boundary_km`, coincidencia con `REGION`, clases,
   energía. La fuente sísmica (HDBSCAN) se asigna en `POST /admin/recompute`, no al importar.
10. **Informe de calidad** en `quality_report_json` (columnas reconocidas/no reconocidas, codificación, filas
    leídas/insertadas/duplicadas/inválidas/marcadas por criterio, nulos por columna, rango de fechas, parámetros de
    la consulta del portal).
11. **Transacción:** todo o nada por archivo. Si algo falla → `status = failed` y la base queda como estaba.

---

## 7. Identificador estable y deduplicación

- `event_id = "sgc-" + sha1(f"{origin_time_utc}|{lat:.3f}|{lon:.3f}|{depth_km:.1f}|{magnitude:.1f}")[:16]`.
  Si el export trae un identificador del SGC (`source_event_id`), se usa `"sgc-" + source_event_id`. El ID es
  estable entre importaciones del mismo evento (requisito para enlaces del frontend y caché).
  > El pipeline actual genera `SGC-YYYYMMDDHHMMSS-n`, que **no** es estable si cambia el orden de los archivos:
  > se reemplaza en la fase 1.
- **Duplicado exacto** (mismo `event_id`): se actualiza `last_import_id`, no se crea otro evento; cuenta como
  `rows_duplicate`.
- **Casi-duplicado** (≤ 3 s y ≤ 10 km, mismo `source_id`): se conserva el de mejor calidad (revisado `manual` >
  `automatic`, luego más fases) como canónico; el otro queda con `duplicate_of`. Los casi-duplicados se excluyen de
  todos los conteos por defecto (`include_duplicates=false`).
- Entre fuentes distintas (SGC vs USGS) **no se deduplica**: son catálogos distintos; el emparejamiento solo se usa
  en la validación cruzada.

---

## 8. Cálculo de agregaciones

- **En línea con SQL** para todo lo que depende de filtros (conteos, máximos, medias, distribuciones, series,
  agregación por municipio y por celda). La mediana se calcula en Python sobre la columna filtrada (SQLite no la
  trae) o con `ORDER BY … LIMIT 1 OFFSET n/2`.
- **Precalculado por el pipeline** lo que depende del modelo (variables de los 87 municipios, índice, niveles,
  fuentes sísmicas). Esos endpoints no aceptan filtros de fecha: devuelven su periodo de cálculo.
- **Series temporales:** cubetas en UTC (o en `America/Bogota` si se pide `timezone`), rellenas con 0 para que las
  gráficas no salten periodos vacíos.
- **Un solo constructor de filtros** (`api/filters.py`) genera el `WHERE` parametrizado que usan todos los endpoints
  de eventos y estadísticas; así los mismos filtros dan los mismos números en todas las páginas.

---

## 9. Caché

- Caché en memoria (LRU, 256 entradas) para respuestas de `/stats/*`, `/events/grid` y `/compare/*`, con clave =
  ruta + filtros normalizados + `data_version`. Se invalida sola cuando cambia `data_version` (nueva importación).
- Cabeceras HTTP: `ETag` = hash de la respuesta; `Cache-Control: public, max-age=300` en endpoints públicos;
  `no-store` en `/admin/*`. El frontend puede usar `If-None-Match` → `304`.
- No se necesita Redis para el prototipo.
