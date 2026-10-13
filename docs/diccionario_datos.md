# Diccionario de datos · `datos/processed/dataset_municipios.csv`

Una fila = un municipio de Santander (87 filas). **21 variables entran al modelo** (uso = modelo);
las demás identifican, describen o validan. Generado por `scripts/06_construir_variables.py`.

- Vecindario: círculo de **30 km** alrededor del punto representativo del municipio (misma área para todos).
- Conteos con **M ≥ Mc = 2.0** (completitud homogénea). Sismos mal localizados excluidos (Gap > 270°,
  RMS > 1.2 s, error horizontal o de profundidad > 10 km, < 6 fases).
- **Variables: 2020-03-02 a 2023-02-28** · **Objetivo: 2023-03-01 a 2025-03-01** (periodos distintos, sin fuga de información).
- Transformación `log1p` = log(1 + x) antes de estandarizar (variables muy sesgadas). Luego todas se estandarizan (z).
- **No entran al modelo**: Fases, RMS, Gap y errores de localización (solo filtran) ni hora/día/mes (sin poder
  discriminativo en sismos tectónicos).

| Variable | Grupo | Descripción | Tipo | Unidad | Fuente | Periodo | Uso | Transf. | Rango | Imput. | Justificación |
|---|---|---|---|---|---|---|---|---|---|---:|---|
| `cod_mpio` | identificador | Código DANE del municipio (DIVIPOLA) | texto | — | DANE MGN 2018 | — | **identificador** | — |  | 0 | Une las tablas y el mapa. |
| `municipio` | identificador | Nombre del municipio | texto | — | DANE MGN 2018 | — | **identificador** | — |  | 0 | Lectura del resultado. |
| `zona_foco` | territorial | Pertenece al Área Metropolitana de Bucaramanga + Los Santos | booleana | — | config.py | — | **descriptiva** | — |  | 0 | Zona que se compara contra el resto del departamento. |
| `area_km2` | territorial | Área oficial del municipio | numérica continua | km² | DANE MGN 2018 | — | **descriptiva** | — | 19.7 – 3.17e+03 | 0 | Normaliza la densidad de epicentros; no entra al modelo para no agrupar por tamaño. |
| `lat` | territorial | Latitud del punto representativo (centro del vecindario) | numérica continua | ° | DANE MGN 2018 | — | **descriptiva** | — | 5.76 – 7.67 | 0 | Ubicación; no entra al modelo (agruparía por posición, no por amenaza). |
| `lon` | territorial | Longitud del punto representativo | numérica continua | ° | DANE MGN 2018 | — | **descriptiva** | — | -74.2 – -72.5 | 0 | Ídem. |
| `n_sismos_r30` | actividad | Sismos con M ≥ Mc y epicentro a ≤ 30 km | numérica discreta | sismos | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **descriptiva** | — | 1 – 8.95e+03 | 0 | Base de los conteos; el modelo usa su tasa anual. |
| `tasa_sismos_r30` | actividad | Sismos por año con M ≥ Mc a ≤ 30 km | numérica continua | sismos/año | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 0.334 – 2.99e+03 | 0 | Actividad sísmica total del entorno, corregida por completitud. |
| `tasa_m3_r30` | actividad | Sismos por año con M ≥ 3 a ≤ 30 km | numérica continua | sismos/año | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 0 – 281 | 0 | Sismos que la población suele sentir. |
| `tasa_fuertes_r30` | actividad | Sismos por año con M ≥ 4.0 a ≤ 30 km | numérica continua | sismos/año | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 0 – 41.7 | 0 | Sismos sentidos ampliamente, capaces de daño leve. |
| `n_epicentros_propios` | actividad | Sismos con M ≥ Mc con epicentro dentro del polígono | numérica discreta | sismos | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **descriptiva** | — | 0 – 6.06e+03 | 0 | Base de la densidad de epicentros. |
| `densidad_epicentros` | actividad | Sismos M ≥ Mc por año y por 100 km² dentro del municipio | numérica continua | sismos/año/100 km² | SGC – catálogo RSNC + DANE MGN | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 0 – 698 | 0 | Actividad propia del territorio municipal, normalizada por área. |
| `mag_max_r30` | magnitud | Magnitud máxima a ≤ 30 km | numérica continua | M | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 2.1 – 5.3 | 0 | Peor evento observado en el entorno. |
| `mag_p95_r30` | magnitud | Percentil 95 de magnitud (M ≥ Mc) a ≤ 30 km | numérica continua | M | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 2.1 – 3.84 | 0 | Magnitud alta típica, más robusta que el máximo. |
| `valor_b_r30` | magnitud | Valor b de Gutenberg-Richter (Aki-Utsu) a ≤ 30 km | numérica continua | adimensional | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 0.839 – 2.87 | 25 | b bajo = proporción mayor de sismos grandes. Se imputa el b regional si hay < 50 sismos. |
| `log_energia_anual_r30` | energía | log10 de la energía liberada por año a ≤ 30 km (log E = 1.5 M + 4.8) | numérica continua | log10(J/año) | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 8.46 – 13.3 | 0 | Resume actividad y tamaño en una magnitud física. |
| `log_flujo_energia_hipo` | energía | log10 del flujo de energía sísmica que llega al municipio por año: Σ E / (4π R²), con R = distancia hipocentral (incluye la profundidad) y todos los sismos, sin radio | numérica continua | log10(J/m²/año) | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 1.6 – 1.92 | 0 | Mide la sacudida en el sitio con la distancia real a la fuente: un sismo del Nido a 140 km de profundidad está casi igual de lejos de Bucaramanga que de Los Santos, aunque el epicentro no caiga a ≤ 30 km. |
| `prof_mediana_r30` | profundidad | Profundidad mediana de los sismos a ≤ 30 km | numérica continua | km | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 11.9 – 154 | 0 | Separa la sismicidad del Nido (~140 km) de la cortical. |
| `frac_superficiales_r30` | profundidad | Fracción de sismos con profundidad < 30 km | proporción | 0–1 | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 0 – 1 | 0 | Los sismos superficiales son los más dañinos a igual magnitud. |
| `tasa_superficiales_r30` | profundidad | Sismos superficiales (< 30 km) por año a ≤ 30 km | numérica continua | sismos/año | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 0 – 6.68 | 0 | Actividad de las fallas corticales cercanas. |
| `mag_max_superficial_r30` | profundidad | Magnitud máxima de los sismos superficiales a ≤ 30 km | numérica continua | M | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | — | 2 – 3.7 | 6 | Peor sismo cortical cercano. |
| `dist_nido_km` | distancia | Distancia epicentral al centro del Nido de Bucaramanga (estimado por HDBSCAN) | numérica continua | km | SGC – catálogo RSNC (HDBSCAN) | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 6.4 – 144 | 0 | Los sismos del Nido son los más frecuentes y se sienten en todo el departamento. |
| `dist_sismo_fuerte_km` | distancia | Distancia al epicentro M ≥ 4.0 más cercano | numérica continua | km | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 1.23 – 138 | 0 | Cercanía a sismos fuertes recientes. |
| `dist_sismo_superficial_m3_km` | distancia | Distancia al sismo superficial (< 30 km) M ≥ 3 más cercano | numérica continua | km | SGC – catálogo RSNC | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 2.1 – 107 | 0 | Cercanía a fallas corticales activas. |
| `frac_nido_r30` | fuentes (nivel 1) | Fracción de los sismos a ≤ 30 km que HDBSCAN asigna al Nido | proporción | 0–1 | SGC – catálogo RSNC (HDBSCAN) | 2020-03-02 a 2023-02-28 | **modelo** | — | 0 – 0.98 | 0 | Qué tanto domina el Nido el entorno. |
| `frac_cortical_r30` | fuentes (nivel 1) | Fracción de los sismos a ≤ 30 km en fuentes corticales (HDBSCAN) | proporción | 0–1 | SGC – catálogo RSNC (HDBSCAN) | 2020-03-02 a 2023-02-28 | **modelo** | — | 0 – 0.545 | 0 | Peso de las fuentes superficiales. |
| `frac_difusa_r30` | fuentes (nivel 1) | Fracción de los sismos a ≤ 30 km que HDBSCAN deja como difusos | proporción | 0–1 | SGC – catálogo RSNC (HDBSCAN) | 2020-03-02 a 2023-02-28 | **modelo** | — | 0.0186 – 1 | 0 | Sismicidad sin fuente concentrada. |
| `n_fuentes_r30` | fuentes (nivel 1) | Número de fuentes HDBSCAN con ≥ 5 sismos a ≤ 30 km | numérica discreta | fuentes | SGC – catálogo RSNC (HDBSCAN) | 2020-03-02 a 2023-02-28 | **modelo** | — | 0 – 4 | 0 | Diversidad de fuentes que afectan al municipio. |
| `dist_fuente_cortical_km` | fuentes (nivel 1) | Distancia al centro de la fuente cortical HDBSCAN más cercana | numérica continua | km | SGC – catálogo RSNC (HDBSCAN) | 2020-03-02 a 2023-02-28 | **modelo** | log1p | 2.03 – 102 | 0 | Cercanía a fuentes superficiales. |
| `obj_tasa_fuertes_futura_r50` | objetivo | Sismos M ≥ 4.0 por año a ≤ 50 km en el periodo objetivo | numérica continua | sismos/año | SGC – catálogo RSNC | 2023-03-01 a 2025-03-01 | **objetivo** | — | 0 – 34.9 | 0 | Variable objetivo: periodo POSTERIOR y distinto al de las variables. No entra al modelo; valida los grupos. |
| `obj_tasa_futura_r30` | objetivo | Sismos M ≥ Mc por año a ≤ 30 km en el periodo objetivo | numérica continua | sismos/año | SGC – catálogo RSNC | 2023-03-01 a 2025-03-01 | **objetivo** | — | 0.499 – 3.75e+03 | 0 | Validación complementaria (menos ruidosa). |
