# Reporte de limpieza · Catálogo SGC (RSNC)

Generado por `scripts/02_unificar_sgc.py`. Fuente: Servicio Geológico Colombiano, Red Sismológica Nacional
de Colombia, http://bdrsnc.sgc.gov.co/paginas1/catalogo/. Fecha de descarga declarada en `config.py`: **2026-10-13**.

## Archivos leídos (5)

| archivo       | formato               |   filas | total_registros_declarado   | consulta_fecha_inicial   | consulta_fecha_final   | tipo_consulta   | departamento   | creado_por_portal         |
|:--------------|:----------------------|--------:|:----------------------------|:-------------------------|:-----------------------|:----------------|:---------------|:--------------------------|
| Csg_2020.xlsx | nuevo (desde 2018-03) |   12437 | 12437                       | 2020-03-02               | 2021-03-01             | cuadrante       | Santander      | 2026-10-13T09:56:03-04:00 |
| Csg_2021.xlsx | nuevo (desde 2018-03) |   12069 | 12069                       | 2021-03-02               | 2022-03-01             | cuadrante       | Santander      | 2026-10-13T10:01:16-04:00 |
| Csg_2022.xlsx | nuevo (desde 2018-03) |   11230 | 11230                       | 2022-03-02               | 2023-03-01             | cuadrante       | Santander      | 2026-10-13T10:06:28-04:00 |
| Csg_2023.xlsx | nuevo (desde 2018-03) |   13373 | 13373                       | 2023-03-02               | 2024-03-01             | cuadrante       | Santander      | 2026-10-13T10:10:15-04:00 |
| Csg_2024.xlsx | nuevo (desde 2018-03) |   14928 | 14928                       | 2024-03-02               | 2025-03-01             | cuadrante       | Santander      | 2026-10-13T10:14:21-04:00 |

Parámetros de búsqueda de cada export (tal como los escribe el portal): ver `datos/interim/archivos_sgc.csv`.

## Pasos de limpieza

| Paso                                                            |   Sismos (+ leídos / − quitados) |
|:----------------------------------------------------------------|---------------------------------:|
| Filas leídas (todos los archivos)                               |                            64037 |
| Sin fecha, coordenadas, profundidad o magnitud                  |                                0 |
| Magnitud fuera de (-1.0, 9.5)                                   |                                0 |
| Profundidad < 0 o > 300 km (75 entre −5 y 0 km se fijaron en 0) |                                0 |
| Fuera de la caja de estudio (BBOX)                              |                                0 |
| Fuera de 2006-01-01 a 2025-12-31                                |                                0 |
| Duplicados exactos (mismo sismo en dos archivos)                |                                0 |
| Casi-duplicados (≤ 3 s y ≤ 10 km)                               |                              -10 |
| **Sismos en el catálogo unificado**                             |                            64027 |

Hora: UTC. Magnitud homogénea: Mw cuando existe y, si no, la
reportada (familia ML); el tipo original queda en `mag_tipo_original`.

## Calidad de localización (filtro, no variable del modelo)

Fases, RMS, Gap y errores describen la red de estaciones, no la amenaza. Se **marcan** los sismos mal
localizados (`mala_localizacion = True`) y se excluyen al construir las variables
(`EXCLUIR_ATIPICOS = True`). Un sismo puede cumplir varios criterios.

| Criterio                                        |   Sismos | %     |
|:------------------------------------------------|---------:|:------|
| Gap > 270°                                      |     1512 | 2.4%  |
| RMS > 1.2 s (solo M < 3)                        |     1591 | 2.5%  |
| Error horizontal > 10 km                        |     1620 | 2.5%  |
| Error de profundidad > 10 km                    |     3770 | 5.9%  |
| Menos de 6 fases                                |      300 | 0.5%  |
| **Total marcados (excluidos de las variables)** |     7672 | 12.0% |

El RMS no se aplica a M ≥ 3: los sismos grandes los registran estaciones lejanas y su RMS
sube aunque estén bien localizados. Sin esta excepción se perdería el 33% de los sismos
M ≥ 4, justo los que más importan para la amenaza. Calidad de los M ≥ 4:

| Estadístico   |   rms_s |   err_prof_km |   gap_grados |   fases |
|:--------------|--------:|--------------:|-------------:|--------:|
| mediana       |     1.2 |           4.3 |         63.0 |    75.0 |
| máximo        |     2.0 |           7.8 |        181.0 |   114.0 |

## Valores faltantes

| Columna     |   % faltante |
|:------------|-------------:|
| prof_km     |            0 |
| mag         |            0 |
| fases       |            0 |
| rms_s       |            0 |
| gap_grados  |            0 |
| err_lat_km  |            0 |
| err_lon_km  |            0 |
| err_prof_km |            0 |

## Tipos de magnitud

| Tipo de magnitud   |   Sismos |
|:-------------------|---------:|
| MLr_3              |    52032 |
| MLr_vmm            |    11691 |
| MLr                |       94 |
| MLr_2              |       78 |
| M_MLr              |       52 |
| M                  |       45 |
| Mw(mB)             |       17 |
| Mw                 |        8 |
| MLr_4              |        6 |
| MLr_1              |        2 |
| mb                 |        1 |
| MLv                |        1 |

## Sismos por año

|   Año |   sismos |   M_max |   M4_o_mas |   prof_mediana_km |
|------:|---------:|--------:|-----------:|------------------:|
|  2020 |    10588 |     5.3 |         40 |             142.8 |
|  2021 |    11766 |     5.1 |         47 |             137.3 |
|  2022 |    11242 |     5.0 |         32 |             136.3 |
|  2023 |    12249 |     5.6 |         37 |             138.3 |
|  2024 |    15974 |     5.0 |         34 |             141.4 |
|  2025 |     2208 |     4.6 |          8 |             140.0 |

## Observaciones

- Los exports se pidieron con **filtro por departamento** (Santander). Así faltan los sismos que caen justo fuera del límite departamental y los municipios de borde ven menos sismos en su vecindario de 30 km. Para próximas descargas conviene la consulta por cuadrante (lat 5.2–8.7, lon -75.0–-72.0).
- Los datos no cubren los periodos de `config.py` (variables 2006-01-01–2020-12-31, objetivo 2021-01-01–2025-12-31). Se usan periodos ajustados a los datos: **variables 2020-03-02 a 2023-02-28**, **objetivo 2023-03-01 a 2025-03-01**.
