# Metadatos de origen de los datos

| Dataset | Fuente / URL | Fecha de descarga | Uso |
|---|---|---|---|
| Catálogo sísmico RSNC | Servicio Geológico Colombiano, http://bdrsnc.sgc.gov.co/paginas1/catalogo/ | 2026-10-13 | Fuente principal: sismos, variables y objetivo |
| Límites municipales MGN 2018 | DANE, https://geoportal.dane.gov.co/servicios/descarga-y-metadatos/descarga-mgn-marco-geoestadistico-nacional/ (copia GeoJSON: https://github.com/caticoa3/colombia_mapa) | archivo `co_2018_MGN_MPIO_POLITICO.geojson` | 87 municipios, área oficial |
| Sismicidad histórica | SGC, https://sish.sgc.gov.co/visor/ | no incluida | No se usó: falta el archivo en datos/raw/sgc_historico/ |
| Población municipal | DANE, https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion | no incluida | No se usó: falta el archivo en datos/raw/dane/ |
| Catálogo USGS ComCat | https://earthquake.usgs.gov/fdsnws/event/1/query | no incluido | Validación cruzada (opcional) |

## Exports del SGC usados

Cada fila es un archivo de `datos/raw/sgc/` con los parámetros de búsqueda que el portal escribe en él.
`creado_por_portal` es la fecha que el SGC guarda dentro del .xlsx al exportarlo.

| archivo       | formato               |   filas | consulta_fecha_inicial   | consulta_fecha_final   | tipo_consulta   | departamento   | lat      | lon       | magnitud   | profundidad_km   | creado_por_portal         |
|:--------------|:----------------------|--------:|:-------------------------|:-----------------------|:----------------|:---------------|:---------|:----------|:-----------|:-----------------|:--------------------------|
| Csg_2020.xlsx | nuevo (desde 2018-03) |   12437 | 2020-03-02               | 2021-03-01             | cuadrante       | Santander      | -07 a 15 | -90 a -66 | 0 a 9      | 0 a 700          | 2026-10-13T09:56:03-04:00 |
| Csg_2021.xlsx | nuevo (desde 2018-03) |   12069 | 2021-03-02               | 2022-03-01             | cuadrante       | Santander      | -07 a 15 | -90 a -66 | 0 a 9      | 0 a 700          | 2026-10-13T10:01:16-04:00 |
| Csg_2022.xlsx | nuevo (desde 2018-03) |   11230 | 2022-03-02               | 2023-03-01             | cuadrante       | Santander      | -07 a 15 | -90 a -66 | 0 a 9      | 0 a 700          | 2026-10-13T10:06:28-04:00 |
| Csg_2023.xlsx | nuevo (desde 2018-03) |   13373 | 2023-03-02               | 2024-03-01             | cuadrante       | Santander      | -07 a 15 | -90 a -66 | 0 a 9      | 0 a 700          | 2026-10-13T10:10:15-04:00 |
| Csg_2024.xlsx | nuevo (desde 2018-03) |   14928 | 2024-03-02               | 2025-03-01             | cuadrante       | Santander      | -07 a 15 | -90 a -66 | 0 a 9      | 0 a 700          | 2026-10-13T10:14:21-04:00 |

## Filtros y limpieza aplicados

- Caja de estudio: lat 5.2 a 8.7, lon -75.0 a -72.0.
  Fechas 2006-01-01 a 2025-12-31.
- Válidos: magnitud entre -1.0 y 9.5, profundidad 0–300 km.
- Duplicados: exactos y a ≤ 3 s y ≤ 10 km.
- Calidad (filtro): Gap ≤ 270°, RMS ≤ 1.2 s, errores ≤ 10 km, ≥ 6 fases.
- Magnitud homogénea: Mw si existe; si no, la reportada (ML). Completitud Mc = 2.0.
- Detalle: `datos/interim/reporte_limpieza_sgc.md` y `datos/interim/reporte_variables.md`.
