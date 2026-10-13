# SismoSantander · Integración con el frontend

Documento 4 de 5 (ver [README](README.md)). Cubre los entregables 8 (matriz de integración), 9 (interfaces
TypeScript), la centralización con Axios, 14 (archivos del backend) y 15 (plan por fases).

> El código del frontend **no se pudo inspeccionar** (no está en los repositorios accesibles). Los nombres de
> componentes de esta matriz son **sugeridos** a partir de la descripción de las páginas; hay que ajustarlos a los
> nombres reales cuando se comparta el repositorio (decisión D1).

---

## 1. Principios de integración

1. **Un solo estado de filtros** para toda la aplicación, guardado en la URL (`?start_date=…&min_magnitude=…`) con
   `useSearchParams` de React Router: todas las páginas leen lo mismo, los enlaces se pueden compartir y el botón
   "atrás" funciona.
2. **Un solo cliente Axios** (`src/api/client.ts`) y **una sola función** para convertir filtros en parámetros
   (`toParams`). Ningún componente arma URLs a mano.
3. **Mismos filtros → mismos números:** el dashboard, el mapa, el comparativo y el histórico llaman endpoints que
   usan el mismo constructor de filtros del backend. Si dos componentes muestran cifras distintas con los mismos
   filtros, es un error.
4. **Recarga por versión de datos:** los datos solo cambian cuando se importa algo nuevo. Al abrir la app se pide
   `GET /meta`; si `data_version` cambió respecto a la guardada, se invalidan las respuestas en memoria. No hace
   falta *polling* frecuente.
5. **Estados explícitos** en cada componente: *cargando* (esqueleto), *sin resultados* (mensaje + sugerencia de
   ampliar filtros), *error* (mensaje del backend `error.message` + `request_id` + botón "reintentar").
6. **Avisos de datos:** si `meta.data_mode !== "real"`, banner fijo "Datos de demostración"; si `meta.warnings` no
   está vacío, se muestran junto al gráfico afectado.

---

## 2. Matriz de integración por página (entregable 8)

Frecuencia: "al cambiar filtros" = se vuelve a pedir cuando cambian los filtros globales; "por versión" = solo al
cambiar `data_version` (caché en memoria mientras tanto).

### 2.1 Layout global

| Componente | Endpoint | Parámetros | Campos que lee | Frecuencia | Cargando | Sin resultados | Error |
|---|---|---|---|---|---|---|---|
| `AppShell` / pie de página | `GET /meta` | — | `data_mode`, `coverage.temporal`, `last_import_at`, `sources[].name/url`, `realtime` | al iniciar y cada 10 min | pie con "cargando fuente…" | — | "No se pudo conectar con la API" + reintentar |
| `GlobalFilters` | `GET /municipalities`, `GET /meta` | — | `code`, `name`; `coverage` (límites del selector de fechas), `completeness_magnitude` (ayuda junto a magnitud mínima) | por versión | selectores deshabilitados | — | selectores deshabilitados + aviso |
| `DataModeBanner` | (usa `meta` de cualquier respuesta) | — | `meta.data_mode` | — | — | — | — |

### 2.2 Dashboard

| Componente | Endpoint | Parámetros | Campos que lee | Frecuencia | Cargando | Sin resultados | Error |
|---|---|---|---|---|---|---|---|
| `KpiCards` | `GET /stats/summary` | filtros globales | `indicators[]`: `label`, `value`, `unit`, `definition` (tooltip), `denominator`, `null_reason`; `period`, `comparison_period` | al cambiar filtros | 6 tarjetas esqueleto | `event_count = 0` → "Sin eventos para estos filtros"; valores `null` → "—" con `null_reason` en tooltip | tarjeta con mensaje |
| `MagnitudeHistogram` (Recharts `BarChart`) | `GET /stats/distribution` | filtros + `field=magnitude` | `bins[].label/count/percent` | al cambiar filtros | barras esqueleto | `total = 0` → gráfico vacío con mensaje | mensaje |
| `DepthHistogram` | `GET /stats/distribution` | filtros + `field=depth` | ídem | al cambiar filtros | ídem | ídem | ídem |
| `MagnitudeTypePie` | `GET /stats/distribution` | filtros + `field=magnitude_type` | `bins[]` | al cambiar filtros | ídem | ídem | ídem |
| `EventsTimeline` (`LineChart`/`AreaChart`) | `GET /stats/timeseries` | filtros + `interval` (selector) + `metric=count,max_magnitude` | `points[].bucket_start` (eje X con `date-fns`), `count`, `max_magnitude`; `complete_buckets` | al cambiar filtros o intervalo | línea esqueleto | todos los `count = 0` → mensaje | mensaje; 422 `TOO_MANY_BUCKETS` → sugerir intervalo mayor |
| `QualityPanel` | `GET /stats/quality` | filtros | `reliable_pct`, `flags[]`, `missing_values` | al cambiar filtros | esqueleto | `total = 0` | mensaje |

### 2.3 Mapa interactivo

| Componente | Endpoint | Parámetros | Campos que lee | Frecuencia | Cargando | Sin resultados | Error |
|---|---|---|---|---|---|---|---|
| `EpicenterLayer` (React Leaflet `GeoJSON` o `CircleMarker`) | `GET /events/geojson` | filtros + `bbox` del mapa + `limit` | `features[].geometry.coordinates` (`[lon, lat]`), `properties.magnitude` (radio), `depth_km` (color), `event_id`; `meta.truncated` | al cambiar filtros y al terminar de mover el mapa (`moveend`, con espera de 400 ms) | indicador en la esquina del mapa | capa vacía + aviso "sin epicentros en esta vista" | aviso en el mapa |
| `GridLayer` (alternativa con zoom bajo o `truncated`) | `GET /events/grid` | filtros + `bbox` + `cell_size_deg` | `properties.bounds` (rectángulo), `event_count`, `magnitude_max`; `meta.note` en la leyenda | ídem | ídem | ídem | ídem |
| `EventPopup` | `GET /events/{event_id}` | `event_id` | `normalized.origin_time_utc/magnitude/magnitude_type/depth_km/region_reported`, `derived.municipality.name`, `derived.quality.is_reliable`, `provenance.source_id` | al hacer clic | "cargando…" en el popup | — | 404 → "Evento no encontrado" |
| `MunicipalityChoropleth` | `GET /municipalities/geojson` | `include=stats` + filtros (o `include=classification`) | `properties.code/name/event_count` o `cluster_level` | al cambiar filtros (stats) / por versión (classification) | polígonos grises | municipios con 0 → color neutro | mensaje |
| `SourcesLayer` (opcional) | `GET /seismic-sources` | — | `center`, `type`, `name`, `event_count` | por versión | — | — | capa oculta |
| `MapLegend` | (datos de las capas) | — | escala de magnitud, colores de profundidad, `meta.note` de celdas | — | — | — | — |

### 2.4 Análisis comparativo

| Componente | Endpoint | Parámetros | Campos que lee | Frecuencia | Cargando | Sin resultados | Error |
|---|---|---|---|---|---|---|---|
| `MunicipalityPicker` | `GET /municipalities` | — | `code`, `name` | por versión | deshabilitado | — | mensaje |
| `ComparisonTable` / `ComparisonBars` | `GET /compare/municipalities` | filtros + `municipalities` (2–5) + `metrics` | `entities[].municipality`, `indicators`, `units`, `aggregation_note` | al cambiar filtros o selección | esqueleto | indicadores `null` → "—" | 422 → mensaje del campo |
| `ComparisonTimeline` | `GET /compare/municipalities` (misma respuesta) | `interval` | `entities[].series[]` (cubetas idénticas: se pueden fusionar por `bucket_start`) | ídem | ídem | ídem | ídem |
| `ComparisonDistribution` | `GET /compare/municipalities` | `distribution=magnitude\|depth` | `entities[].distribution.bins` | ídem | ídem | ídem | ídem |
| `PeriodComparison` | `GET /compare/periods` | filtros + periodos A y B | `periods[]`, `differences[]`, `warnings` (completitud) | al cambiar | esqueleto | `covered: false` → "periodo sin datos" | 422 `UNEQUAL_PERIODS` → mensaje |
| `RankingBars` (todos los municipios) | `GET /stats/by-municipality` | filtros + `sort_by` | `municipality.name`, `event_count`, `magnitude_max` | al cambiar filtros | esqueleto | — | mensaje |

### 2.5 Zonas prioritarias

| Componente | Endpoint | Parámetros | Campos que lee | Frecuencia | Cargando | Sin resultados | Error |
|---|---|---|---|---|---|---|---|
| `PriorityRanking` | `GET /priority-zones` | `method`, `focus_zone`, `level` | `rank`, `municipality`, `observed_activity_score`, `score_label`, `cluster_level`, `mixed_profile`, `period`, `computed_at`, `meta.interpretation` | por versión | tabla esqueleto | filtro sin coincidencias → mensaje | 503 → "El modelo no está calculado" |
| `PriorityDetail` (panel lateral) | `GET /priority-zones/{code}` | `method` | `explanation[]`, `components[]` (barras), `variables[]`, `dimensions`, `level_by_score` | al seleccionar | esqueleto | — | 404 |
| `MethodNote` | `GET /priority-zones/methods` | — | `what_it_measures`, `what_it_does_not_measure`, `formula`, `validation`, `limitations` | por versión | — | — | — |
| `DimensionsBadge` | (de `PriorityZone.dimensions`) | — | `observed_activity`, `hazard`, `exposure`, `vulnerability` | — | — | — | — |

Texto obligatorio en la UI: el valor de `meta.interpretation` ("No es riesgo ni probabilidad…").

### 2.6 Agente de recomendación

| Componente | Endpoint | Parámetros | Campos que lee | Frecuencia | Cargando | Sin resultados | Error |
|---|---|---|---|---|---|---|---|
| `AgentMunicipalitySelect` | `GET /municipalities` | — | `code`, `name` | por versión | — | — | — |
| `AgentIndicators` | `GET /priority-zones/{code}` | — | `indicators`, `variables` | al seleccionar | esqueleto | — | 404 |
| `RecommendationList` | `POST /recommendations/evaluate` | `{ municipality_code, log_query }` | `recommendations[].text/severity/evidence[]`, `warnings[]`, `disclaimer`, `rules_version` | al seleccionar | esqueleto | lista vacía → "Ninguna regla se activó para este municipio" (no es un error) | mensaje |
| `RulesExplainer` | `GET /recommendations/rules` | — | `title`, `condition`, `rationale` | por versión | — | — | — |
| `AssistantBox` (futuro) | `POST /assistant/ask` | `{ question, municipality_code }` | `answer`, `citations[]`, `refused` | al enviar | "pensando…" | `refused: true` → mensaje fijo | 501 → ocultar la caja (`meta.assistant_enabled = false`) |

### 2.7 Histórico de sismos

| Componente | Endpoint | Parámetros | Campos que lee | Frecuencia | Cargando | Sin resultados | Error |
|---|---|---|---|---|---|---|---|
| `EventsTable` | `GET /events` | filtros + `q` + `page`, `page_size`, `sort_by`, `sort_order` | `data[]` (columnas), `pagination.total/total_pages` | al cambiar filtros, página u orden | filas esqueleto | "No hay sismos con estos filtros" | mensaje + reintentar |
| `EventDetailDrawer` | `GET /events/{event_id}` | — | `original` (pestaña "Datos originales SGC"), `normalized`, `derived` (marcados "calculado por SismoSantander"), `provenance` | al abrir | esqueleto | — | 404 |
| `ExportButton` | `GET /events/export` | filtros + orden + `columns` | archivo (`blob`), cabeceras `X-Total-Rows`, `X-Truncated` | al hacer clic | botón con spinner | descarga con solo cabecera | 413 → "Demasiados resultados" |
| `FieldsHelp` | `GET /meta/variables` | `scope=event` | `field`, `label`, `unit`, `origin`, `original_columns` | por versión | — | — | — |

### 2.8 Acerca del proyecto

| Componente | Endpoint | Campos que lee |
|---|---|---|
| `AboutSources` | `GET /meta` | `sources[]` (nombre, URL, fecha de descarga, forma de obtención, `terms_note`), `coverage`, `record_counts`, `dimensions` |
| `AboutMethod` | `GET /priority-zones/methods`, `GET /seismic-sources` | métodos, validación, limitaciones, fuentes sísmicas |

---

## 3. Interfaces TypeScript (entregable 9)

Archivo sugerido: `src/api/types.ts`. Coinciden con [openapi.yaml](openapi.yaml); pueden regenerarse con
`npx openapi-typescript docs/api/openapi.yaml -o src/api/schema.d.ts`.

```ts
// ---------- Comunes ----------
export type DataMode = "real" | "simulated" | "mixed";
export type FieldOrigin = "original" | "normalized" | "derived" | "associated" | "model";
export type Availability = "available" | "not_computed" | "missing_data";
export type ISODate = string;      // "2024-01-01"
export type ISODateTime = string;  // "2024-01-01T00:00:00Z"

export interface ApiWarning { code: string; message: string; }

export interface ApiMeta {
  api_version: string;
  request_id: string;
  generated_at: ISODateTime;
  data_mode: DataMode;
  data_version: string;
  sources: string[];
  coverage: { start: ISODate; end: ISODate };
  applied_filters: Record<string, string | number | boolean | number[] | null>;
  warnings: ApiWarning[];
  [extra: string]: unknown; // campos propios de algunos endpoints (total_matching, interpretation, note…)
}

export interface ApiResponse<T> { data: T; meta: ApiMeta; }

export interface Pagination { page: number; page_size: number; total: number; total_pages: number; }

export interface Paginated<T> { data: T[]; pagination: Pagination; meta: ApiMeta; }

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: { field: string; issue: string; value: string | null }[];
    request_id: string;
    documentation_url: string | null;
  };
}

// ---------- Filtros globales ----------
export type MagnitudeTypeGroup = "ML" | "Mw" | "mb" | "M";
export type SpatialScope = "epicenter" | "sgc_region" | "radius";

export interface EventFilters {
  start_date?: ISODate | ISODateTime;
  end_date?: ISODate | ISODateTime;
  timezone?: "UTC" | "America/Bogota";
  department?: string;
  municipality?: string[];          // códigos DANE
  spatial_scope?: SpatialScope;
  radius_km?: number;
  min_magnitude?: number;
  max_magnitude?: number;
  min_depth?: number;               // km
  max_depth?: number;               // km
  magnitude_type?: MagnitudeTypeGroup[];
  quality?: "all" | "reliable";
  review_status?: "manual" | "automatic" | "all";
  source?: string[];
  include_duplicates?: boolean;
}

export interface PageParams {
  page?: number;
  page_size?: number;
  sort_by?: "origin_time" | "magnitude" | "depth";
  sort_order?: "asc" | "desc";
}

/** [min_lon, min_lat, max_lon, max_lat] — mismo orden que map.getBounds().toBBoxString() */
export type BBox = [number, number, number, number];

// ---------- Metadatos de la fuente ----------
export interface SourceInfo {
  source_id: string;
  name: string;
  kind: "real" | "simulated";
  url: string | null;
  obtained_by: string;
  downloaded_at: ISODate | null;
  imports: number;
  terms_note: string | null;
}

export interface Meta {
  api_version: string;
  data_mode: DataMode;
  realtime: false;
  data_version: string;
  last_import_at: ISODateTime | null;
  record_counts: { events: number; events_reliable: number; duplicates_excluded: number; raw_rows: number };
  coverage: {
    temporal: { start: ISODate; end: ISODate; timezone: "UTC" };
    spatial: { study_area_bbox: BBox; department_filter_in_source_query: string | null;
               municipalities: number; events_inside_a_municipality_pct: number };
  };
  sources: SourceInfo[];
  model: { model_version: string; computed_at: ISODateTime;
           training_period: { start: ISODate; end: ISODate };
           validation_period: { start: ISODate; end: ISODate } } | null;
  completeness_magnitude: number | null;
  dimensions: { observed_activity: Availability; hazard: Availability; exposure: Availability; vulnerability: Availability };
  assistant_enabled: boolean;
}

export interface VariableInfo {
  field: string; scope: "event" | "municipality"; label: string;
  type: "string" | "number" | "integer" | "boolean"; format: string | null; unit: string | null;
  origin: FieldOrigin; original_columns: string[]; nullable: boolean; description: string;
}

// ---------- Evento sísmico ----------
export interface MunicipalityRef { code: string; name: string; }

export interface SeismicEvent {
  event_id: string;
  origin_time_utc: ISODateTime;
  latitude: number;
  longitude: number;
  depth_km: number | null;          // km
  magnitude: number | null;
  magnitude_type: string | null;    // original: "MLr_3", "Mw(mB)", …
  magnitude_type_group: MagnitudeTypeGroup | "other" | null;
  region_reported: string | null;   // original del SGC
  municipality: (MunicipalityRef & { method: string }) | null;  // asociado (cálculo propio)
  review_status: "manual" | "automatic" | null;
  is_reliable: boolean;
  quality_flags: string[];
  seismic_source: { code: string; type: string } | null;        // modelo
  source_id: string;
}

export interface SeismicEventDetail {
  event_id: string;
  original: Record<string, string>;                              // fila tal cual
  normalized: {
    origin_time_utc: ISODateTime; origin_time_raw: string;
    time_zone_declared: "UTC" | "local_UTC-5" | "not_declared";
    latitude: number; longitude: number; depth_km: number | null;
    magnitude: number | null; magnitude_type: string | null; magnitude_type_group: string | null;
    phase_count: number | null; rms_s: number | null; azimuthal_gap_deg: number | null;
    latitude_error_km: number | null; longitude_error_km: number | null; depth_error_km: number | null;
    region_reported: string | null; department_reported: string | null; country_reported: string | null;
    review_status: string | null; source_event_id: string | null; quakeml_url: string | null; map_url: string | null;
  };
  derived: {
    municipality: (MunicipalityRef & { method: string; distance_to_boundary_km: number | null;
                                       matches_region_reported: boolean | null }) | null;
    quality: { is_reliable: boolean; flags: string[]; note: string | null };
    duplicate_of: string | null;
    depth_class: "0-30" | "30-70" | "70-300" | ">300" | null;
    energy_log10_j: number | null;
    seismic_source: { code: string; type: string; model_version: string } | null;
  };
  provenance: {
    source_id: string; source_kind: "real" | "simulated"; import_id: string; file_name: string; file_row: number;
    downloaded_at: ISODate | null; portal_created_at: string | null; imported_at: ISODateTime;
    source_query: Record<string, string>;
  };
}

// ---------- GeoJSON para Leaflet (usa @types/geojson) ----------
import type { FeatureCollection, Point, Polygon, MultiPolygon } from "geojson";

export interface EpicenterProps {
  event_id: string; kind: "epicenter"; origin_time_utc: ISODateTime;
  magnitude: number | null; magnitude_type: string | null; depth_km: number | null;
  region_reported: string | null; municipality_name: string | null;
  is_reliable: boolean; seismic_source_type: string | null;
}
export type EventFeatureCollection = FeatureCollection<Point, EpicenterProps> & {
  meta: ApiMeta & { total_matching: number; returned: number; truncated: boolean };
};

export interface GridCellProps {
  kind: "aggregation_cell"; cell_size_deg: number;
  bounds: { south: number; west: number; north: number; east: number };
  event_count: number; magnitude_max: number | null; depth_mean: number | null;
}
export type GridFeatureCollection = FeatureCollection<Polygon, GridCellProps> & { meta: ApiMeta };

export type MunicipalityFeatureCollection = FeatureCollection<Polygon | MultiPolygon,
  { code: string; name: string; area_km2: number; in_focus_zone: boolean; [k: string]: unknown }> & { meta: ApiMeta };

// ---------- Dashboard ----------
export type Aggregation = "count" | "count_distinct" | "min" | "max" | "mean" | "median" | "ratio";
export type NullReason = "NO_EVENTS" | "PREVIOUS_PERIOD_NOT_COVERED" | "PREVIOUS_PERIOD_ZERO" | "FIELD_NOT_AVAILABLE";

export interface Indicator {
  key: string; label: string; value: number | null; unit: string; definition: string;
  aggregation: Aggregation; denominator: { label: string; value: number } | null; null_reason: NullReason | null;
}

export interface Period { start: ISODate; end: ISODate; timezone: string; days: number; }

export interface Summary { period: Period; comparison_period: Period | null; indicators: Indicator[]; }

export interface DistributionBin { label: string; lower: number | null; upper: number | null; count: number; percent: number; }
export interface Distribution {
  field: "magnitude" | "depth" | "magnitude_type"; unit: string | null;
  total: number; null_count: number; bins: DistributionBin[];
}

export interface QualitySummary {
  total: number; reliable: number; reliable_pct: number | null;
  flags: { flag: string; label: string; count: number }[];
  review_status: Record<string, number>;
  missing_values: Record<string, number>;
  criteria_note: string;
}

// ---------- Serie temporal ----------
export type Interval = "day" | "week" | "month" | "quarter" | "year";
export interface TimeSeriesPoint {
  bucket_start: ISODate; bucket_end: ISODate;
  count?: number; max_magnitude?: number | null; mean_magnitude?: number | null; mean_depth?: number | null;
}
export interface TimeSeries {
  interval: Interval; timezone: string;
  metrics: { key: string; unit: string }[];
  points: TimeSeriesPoint[];
  complete_buckets: boolean;
}

// ---------- Comparación territorial ----------
export interface MunicipalityStats {
  municipality: MunicipalityRef; event_count: number; events_per_year: number;
  magnitude_max: number | null; magnitude_mean: number | null; magnitude_median: number | null;
  depth_mean: number | null; depth_median: number | null; reliable_pct: number | null;
}

export interface MunicipalityComparison {
  period: Period; spatial_scope: SpatialScope;
  entities: {
    municipality: MunicipalityRef;
    indicators: Record<string, number | null>;
    series: { bucket_start: ISODate; count: number }[];
    distribution: Distribution | null;
  }[];
  units: Record<string, string>;
  aggregation_note: string;
}

export interface PeriodComparison {
  periods: { label: "A" | "B"; start: ISODate; end: ISODate; days: number;
             indicators: Record<string, number | null>; covered: boolean }[];
  differences: { metric: string; absolute: number | null; percent: number | null; unit: string }[];
}

// ---------- Zona prioritaria ----------
export type ScoringMethodId = "catalog_index_v1" | "kmeans_levels_v1";
export type ClusterLevel = "Muy bajo" | "Bajo" | "Medio" | "Alto" | "Muy alto";

export interface ScoreComponent { key: string; z_mean: number; percentile: number; direction: "+" | "−"; note?: string; }

export interface PriorityZone {
  rank: number;
  municipality: MunicipalityRef & { in_focus_zone: boolean };
  observed_activity_score: number | null;    // 0–100, relativo; NO es riesgo ni probabilidad
  score_label: string;
  cluster_level: ClusterLevel | null;
  cluster_level_order: number | null;
  mixed_profile: boolean;
  indicators: Record<string, number | null>;
  components: ScoreComponent[];
  explanation: string[];
  quality: { events_used: number; reliable_only: boolean; b_value_imputed: boolean };
  dimensions: { observed_activity: Availability; hazard: Availability; exposure: Availability; vulnerability: Availability };
  method: ScoringMethodId; method_version: string; model_version: string;
  computed_at: ISODateTime; period: { start: ISODate; end: ISODate };
}

export interface PriorityZoneDetail extends PriorityZone {
  level_by_score: ClusterLevel | null;
  variables: { key: string; label: string; value: number | null; unit: string; percentile: number | null; imputed: boolean }[];
  neighbors_in_ranking: { previous: { rank: number; code: string } | null; next: { rank: number; code: string } | null };
}

export interface ScoringMethod {
  method: ScoringMethodId; version: string; name: string;
  what_it_measures: string; what_it_does_not_measure: string[];
  components: { key: string; variables: string[]; direction: "+" | "−"; weight: number }[];
  formula: string; period: { start: ISODate; end: ISODate };
  validation: Record<string, number>; limitations: string[];
}

// ---------- Recomendación ----------
export interface RuleCondition {
  indicator: string; operator: ">=" | "<=" | ">" | "<" | "==";
  value: number | boolean; value_type: "absolute" | "percentile";
}
export interface RecommendationRule {
  rule_id: string; version: number; title: string;
  condition: { all?: RuleCondition[]; any?: RuleCondition[] };
  recommendation: string; severity: "info" | "attention" | "priority" | "data_warning";
  kind: "recommendation" | "data_warning"; rationale: string; evidence_fields: string[]; active: boolean;
}
export interface Recommendation {
  rule_id: string; severity: "info" | "attention" | "priority"; kind: "recommendation"; text: string;
  evidence: { indicator: string; value: number | boolean | null; unit: string | null; threshold: number | boolean;
              operator: string; value_type: "absolute" | "percentile"; percentile: number | null }[];
}
export interface RecommendationResult {
  municipality: MunicipalityRef; evaluated_at: ISODateTime; rules_version: string;
  recommendations: Recommendation[];
  warnings: { rule_id: string; text: string }[];
  rules_not_triggered: string[];
  disclaimer: string; generated_by: "rules_engine"; logged: boolean;
}

// ---------- Territorio y fuentes ----------
export interface Municipality {
  code: string; name: string; name_official: string; department_code: string; area_km2: number;
  representative_point: { latitude: number; longitude: number }; in_focus_zone: boolean;
}
export interface SeismicSource {
  code: string; type: string; name: string; center: { latitude: number; longitude: number };
  depth_median_km: number | null; depth_p10_km: number | null; depth_p90_km: number | null;
  event_count: number; max_magnitude: number | null; nearest_municipality: string | null;
}
```

---

## 4. Cliente Axios centralizado

```ts
// src/api/client.ts
import axios, { AxiosError } from "axios";
import type { ApiErrorBody } from "./types";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1",
  timeout: 15_000,
});

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string,
              public details: ApiErrorBody["error"]["details"] = [], public requestId?: string) { super(message); }
}

api.interceptors.response.use(
  (r) => r,
  (e: AxiosError<ApiErrorBody>) => {
    if (axios.isCancel(e)) return Promise.reject(e);
    const body = e.response?.data?.error;
    return Promise.reject(new ApiError(
      e.response?.status ?? 0,
      body?.code ?? (e.code === "ECONNABORTED" ? "TIMEOUT" : "NETWORK_ERROR"),
      body?.message ?? "No se pudo conectar con la API.",
      body?.details ?? [], body?.request_id));
  });
```

```ts
// src/api/filters.ts — ÚNICO lugar que convierte filtros en parámetros
import type { EventFilters, PageParams, BBox } from "./types";

export function toParams(f: EventFilters & PageParams & { bbox?: BBox } = {}): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(f)) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    out[k] = Array.isArray(v) ? v.join(",") : String(v);
  }
  return out;
}

// Lee y escribe los filtros en la URL para que todas las páginas compartan el mismo estado
import { useSearchParams } from "react-router-dom";
const LIST = new Set(["municipality", "magnitude_type", "source"]);
const NUM = new Set(["min_magnitude", "max_magnitude", "min_depth", "max_depth", "radius_km"]);

export function useGlobalFilters() {
  const [sp, setSp] = useSearchParams();
  const filters: EventFilters = {};
  sp.forEach((v, k) => { (filters as any)[k] = LIST.has(k) ? v.split(",") : NUM.has(k) ? Number(v) : v; });
  const setFilters = (f: EventFilters) => setSp(toParams(f), { replace: true });
  return { filters, setFilters };
}
```

```ts
// src/api/endpoints.ts — una función por endpoint; los componentes solo llaman estas funciones
import { api } from "./client";
import { toParams } from "./filters";
import type * as T from "./types";

export const getMeta = () => api.get<T.ApiResponse<T.Meta>>("/meta").then(r => r.data);
export const getSummary = (f: T.EventFilters, signal?: AbortSignal) =>
  api.get<T.ApiResponse<T.Summary>>("/stats/summary", { params: toParams(f), signal }).then(r => r.data);
export const getDistribution = (f: T.EventFilters, field: T.Distribution["field"], signal?: AbortSignal) =>
  api.get<T.ApiResponse<T.Distribution>>("/stats/distribution", { params: { ...toParams(f), field }, signal }).then(r => r.data);
export const getTimeSeries = (f: T.EventFilters, interval: T.Interval, signal?: AbortSignal) =>
  api.get<T.ApiResponse<T.TimeSeries>>("/stats/timeseries", { params: { ...toParams(f), interval, metric: "count,max_magnitude" }, signal }).then(r => r.data);
export const getEvents = (f: T.EventFilters & T.PageParams & { q?: string }, signal?: AbortSignal) =>
  api.get<T.Paginated<T.SeismicEvent>>("/events", { params: toParams(f), signal }).then(r => r.data);
export const getEventsGeo = (f: T.EventFilters, bbox: T.BBox, signal?: AbortSignal) =>
  api.get<T.EventFeatureCollection>("/events/geojson", { params: toParams({ ...f, bbox }), signal }).then(r => r.data);
export const getEvent = (id: string) =>
  api.get<T.ApiResponse<T.SeismicEventDetail>>(`/events/${encodeURIComponent(id)}`).then(r => r.data);
export const getPriorityZones = (method: T.ScoringMethodId = "catalog_index_v1") =>
  api.get<T.Paginated<T.PriorityZone>>("/priority-zones", { params: { method } }).then(r => r.data);
export const evaluateRecommendations = (municipality_code: string) =>
  api.post<T.ApiResponse<T.RecommendationResult>>("/recommendations/evaluate", { municipality_code }).then(r => r.data);
// … una función por cada endpoint del catálogo
```

```ts
// src/hooks/useApi.ts — estados de carga, vacío y error en un solo lugar; cancela la petición anterior
import { useEffect, useState } from "react";
import { ApiError } from "../api/client";

export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean }>({ loading: true });
  useEffect(() => {
    const ctrl = new AbortController();
    setState(s => ({ ...s, loading: true, error: undefined }));
    fetcher(ctrl.signal)
      .then(data => setState({ data, loading: false }))
      .catch(e => { if (!ctrl.signal.aborted) setState({ error: e as ApiError, loading: false }); });
    return () => ctrl.abort();
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

// Uso en un componente:
// const { filters } = useGlobalFilters();
// const { data, loading, error } = useApi(s => getSummary(filters, s), [JSON.stringify(filters)]);
```

Reemplazo de los datos simulados: cada archivo de *mocks* se sustituye por la función de `endpoints.ts`
equivalente, y los mocks pueden quedarse solo en las pruebas. Ningún componente debe mezclar datos de mocks con
respuestas de la API.

---

## 5. Archivos que se deben crear en el backend (entregable 14)

| Archivo | Contenido | Fase |
|---|---|---|
| `sql/schema.sql` | Esquema SQLite e índices ([data-model.md §3](data-model.md#3-esquema-sql-sqlite)) | 1 |
| `scripts/08_cargar_base.py` | Carga a SQLite: fuentes, importaciones (con parámetros del portal), filas originales, eventos normalizados, derivados, municipios, modelo y ranking | 1 |
| `sismos/normalizacion.py` | Funciones de lectura, mapeo de columnas, codificación, tipos y calidad extraídas de `scripts/02_unificar_sgc.py` para que las use también el importador de la API | 1 |
| `api/__init__.py`, `api/main.py` | App FastAPI: routers, CORS, GZip, manejadores de errores, `request_id` | 1 |
| `api/settings.py` | Configuración por variables de entorno: `DATABASE_PATH`, `CORS_ORIGINS`, `ADMIN_TOKEN`, `DATA_MODE_OVERRIDE` | 1 |
| `api/db.py` | Conexión SQLite (solo lectura para endpoints públicos), `foreign_keys`, límite de tiempo | 1 |
| `api/filters.py` | `EventFilters` (Pydantic) + constructor de `WHERE` parametrizado + lista blanca de orden | 1 |
| `api/errors.py` | `ApiError`, códigos y formato único de error | 1 |
| `api/schemas.py` | Modelos Pydantic de respuesta (generan el OpenAPI de `/docs`) | 1 |
| `api/routers/meta.py` | A1–A3 | 1 |
| `api/routers/stats.py` | B1–B5 | 1–2 |
| `api/routers/events.py` | C1–C5 | 1–2 |
| `api/routers/territory.py` | T1–T3 | 1–2 |
| `api/routers/compare.py` | D1–D2 | 2 |
| `api/routers/priority.py` | E1–E3 | 2 |
| `api/routers/recommendations.py` | G1–G2 | 3 |
| `api/routers/assistant.py` | G3 (501) | 3 |
| `api/routers/admin.py` | H1–H5 con dependencia de autenticación | 3 |
| `api/services/stats.py`, `api/services/geo.py`, `api/services/rules.py`, `api/services/importer.py` | Lógica de agregación, celdas, motor de reglas e importación | 1–3 |
| `api/rules/recommendation_rules.yaml` | Reglas versionadas del agente | 3 |
| `tests/test_filters.py` | Validación de filtros y SQL parametrizado | 1 |
| `tests/test_consistency.py` | Mismos filtros → mismo conteo en `/stats/summary`, `/events`, `/stats/by-municipality` y `/events/grid` | 1 |
| `tests/test_events.py`, `tests/test_admin_auth.py` | Paginación estable, 404, export; 401/403 en admin | 1–3 |
| `docs/api/*` | Esta especificación | 0 |

`api.py` y `usar_modelo.py` actuales se mantienen hasta terminar la fase 2 (el frontend aún usa datos simulados, así
que no hay consumidores que romper); luego `api.py` se reemplaza por `api/main.py`.

---

## 6. Plan de implementación por fases

| Fase | Objetivo | Entregables | Criterio de terminado |
|---|---|---|---|
| **0 · Hecho** | Datos, pipeline, modelo y API inicial | `scripts/00–07`, `modelo/modelo_kmeans.json`, `api.py`, mapa y reporte | `python run_all.py` y `tests/probar_api.py` pasan |
| **1 · Dashboard, mapa e histórico con datos reales** (≈ 1 día) | Reemplazar los datos simulados de las 3 páginas principales | `schema.sql`, `08_cargar_base.py` (con `event_id` estable), `filters.py`, A1–A3, B1–B3, C1, C2, C4, T1, T2 | `test_consistency.py` pasa; el frontend muestra las cifras del catálogo SGC |
| **2 · Comparativo y zonas prioritarias** (≈ 1 día) | Páginas Comparativo y Zonas prioritarias | B4, B5, C3, C5, D1, D2, E1–E3, T3, caché + ETag | Ranking y comparaciones cuadran con `salidas/municipios_clasificados.csv` |
| **3 · Agente y administración** (≈ 1 día) | Recomendaciones por reglas, importación protegida | G1, G2, G3 (501), H1–H5, reglas YAML, límites de peticiones, token admin | Importar un export nuevo actualiza `data_version` y las cifras; 401/403 probados |
| **4 · Opcional** | Mejoras | Asistente con IA (con verificación de cifras), USGS como segunda fuente, PostGIS si el catálogo crece mucho | Según tiempo disponible |

**Antes de la fase 1:** conseguir el export del formato antiguo (D3) y un ejemplo del CSV con `QuakeML`/`Mapa` (D2),
para probar el importador con archivos reales.
