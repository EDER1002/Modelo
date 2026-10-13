# Reporte de construcción de variables

Generado por `scripts/06_construir_variables.py` con el catálogo **SGC**.

## Periodos

| | Desde | Hasta | Años | Sismos (bien localizados) |
|---|---|---|---:|---:|
| Variables (entrada del modelo) | 2020-03-02 | 2023-02-28 | 3.00 | 30,983 |
| Objetivo (validación, no entra al modelo) | 2023-03-01 | 2025-03-01 | 2.00 | 25,372 |

**Periodos ajustados a los datos**: los exports no cubren los periodos de `config.py` (('2006-01-01', '2020-12-31') / ('2021-01-01', '2025-12-31')). Con los Excel 2006–2025 el pipeline vuelve solo a esos periodos.

## Magnitud de completitud (Mc)

Máxima curvatura + 0.2 por año; se toma el **peor año** como Mc homogéneo = **2.0**. Los conteos usan M ≥ Mc
(9,911 sismos). Valor b regional (Aki-Utsu) = **1.10**.

|   Año |   Mc (máx. curvatura + 0.2) |
|------:|----------------------------:|
|  2020 |                         1.9 |
|  2021 |                         1.9 |
|  2022 |                         2.0 |
|  2023 |                         2.0 |

## Centro del Nido de Bucaramanga

HDBSCAN (mediana de los sismos de la fuente Nido): lat **6.788**, lon **-73.166**, profundidad **141.3 km**
(referencia Prieto et al., 2012: 6.8, -73.1, 150 km;
diferencia 7.4 km).

## Imputaciones

Municipios sin sismos suficientes en su vecindario: magnitudes -> Mc, profundidad -> mediana regional,
fracciones -> 0, valor b -> b regional (si hay < 50 sismos).

| Variable                |   Municipios imputados |
|:------------------------|-----------------------:|
| mag_max_superficial_r30 |                      6 |
| valor_b_r30             |                     25 |

## Variables muy correlacionadas (|Spearman| ≥ 0.9)

Se mantienen porque miden aspectos distintos (p. ej. conteo vs. energía); K-Means las ve estandarizadas y la
comparación con PCA en el paso 07 controla el efecto de la redundancia.

| Variable A             | Variable B            |   Spearman |
|:-----------------------|:----------------------|-----------:|
| tasa_sismos_r30        | tasa_m3_r30           |       0.92 |
| tasa_sismos_r30        | log_energia_anual_r30 |       0.91 |
| tasa_sismos_r30        | frac_difusa_r30       |      -0.92 |
| tasa_m3_r30            | log_energia_anual_r30 |       0.95 |
| mag_max_r30            | log_energia_anual_r30 |       0.90 |
| log_flujo_energia_hipo | dist_nido_km          |      -0.99 |

## Validación cruzada con USGS

No se usó (no hay `datos/interim/catalogo_usgs.csv`; correr `python run_all.py --usgs` con internet).

## Resumen

- 87 municipios × 21 variables de modelo (31 columnas en total con identificadores,
  descriptivas y objetivo).
- Sismicidad histórica: no (falta el archivo) · Población: no (falta el archivo).
