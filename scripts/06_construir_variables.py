"""
Paso 06 · Variables por municipio (una fila = un municipio) + variable objetivo + diccionario de datos.

- Vecindario: círculo de RADIO_INFLUENCIA_KM (30 km) alrededor del punto representativo del municipio
  (misma área para todos -> comparación justa). La densidad de epicentros propios usa el polígono oficial.
- Conteos con M >= Mc homogéneo (el peor año) para no confundir "mejor red" con "más sismos".
- Sismos mal localizados excluidos (la calidad es filtro, no variable).
- Variables con el periodo de VARIABLES; la variable objetivo con el periodo OBJETIVO (posterior, sin solaparse).

Salidas: datos/processed/dataset_municipios.csv, municipios_variables.geojson, catalogo_con_municipio.csv,
         docs/diccionario_datos.md/.csv, docs/metadatos_origen.md, datos/interim/reporte_variables.md
"""
import numpy as np
import pandas as pd

from utils import (ARCHIVOS_SGC, CAT_FUENTES, CAT_USGS, DATASET, DATASET_GEO, DICCIONARIO_CSV, HISTORICO,
                   HISTORICO_META, NIDO_JSON, POBLACION, POBLACION_META, C, anios_periodo, asegurar_carpetas,
                   aviso, cargar_catalogo, cargar_municipios, en_periodo, energia_joules, escribir, escribir_json,
                   filtrar_calidad, fuente_desde_args, haversine_km, info, leer_json, matriz_distancias_km,
                   mc_homogeneo, ok, periodos_efectivos, rel, tabla_md, titulo, valor_b)

titulo("06 · Variables por municipio (una fila = un municipio)")
asegurar_carpetas()
fuente = fuente_desde_args()
cat_todo = cargar_catalogo(fuente)
per = periodos_efectivos(cat_todo)
if CAT_FUENTES.exists():
    f = pd.read_csv(CAT_FUENTES)
    cat_todo = cat_todo.merge(f, on="id_evento", how="left")
else:
    aviso("No está datos/interim/catalogo_con_fuente.csv (paso 05): las variables de fuentes quedan vacías.")
    for c in ("fuente_id", "fuente_codigo", "fuente", "fuente_tipo"):
        cat_todo[c] = np.nan
cat = filtrar_calidad(cat_todo)
mun = cargar_municipios().sort_values("cod_mpio").reset_index(drop=True)
lat_m, lon_m = mun["lat"].to_numpy(), mun["lon"].to_numpy()
R, RO = C.RADIO_INFLUENCIA_KM, C.RADIO_OBJETIVO_KM

var = en_periodo(cat, per["variables"]).reset_index(drop=True)
obj = en_periodo(cat, per["objetivo"]).reset_index(drop=True)
T_var, T_obj = anios_periodo(per["variables"]), anios_periodo(per["objetivo"])
info(f"Periodo de variables {per['variables'][0]} a {per['variables'][1]} ({T_var:.2f} años): {len(var):,} sismos")
info(f"Periodo objetivo     {per['objetivo'][0]} a {per['objetivo'][1]} ({T_obj:.2f} años): {len(obj):,} sismos")
if per["ajustado"]:
    aviso("Periodos ajustados a los datos disponibles (los de config.py no están cubiertos por los exports).")

# ----------------------------------------------------------------------------
# Completitud y referencias
# ----------------------------------------------------------------------------
mc, mc_anual = mc_homogeneo(var)
var_c = var[var["mag"] >= mc - 1e-9].reset_index(drop=True)
b_regional = valor_b(var_c["mag"].to_numpy(), mc)
nido = leer_json(NIDO_JSON, None) or dict(**C.NIDO_REFERENCIA, origen="referencia")
info(f"Mc homogéneo = {mc:.1f} (máxima curvatura + 0.2, peor año) · {len(var_c):,} sismos con M ≥ Mc · "
     f"b regional = {b_regional:.2f}")

# ----------------------------------------------------------------------------
# Distancias municipio -> sismos (epicentrales)
# ----------------------------------------------------------------------------
D = matriz_distancias_km(lat_m, lon_m, var_c["lat"], var_c["lon"])
dentro = D <= R
mag_c, prof_c = var_c["mag"].to_numpy(), var_c["prof_km"].to_numpy()
tipo_c = var_c["fuente_tipo"].fillna("Difusa (ruido)").to_numpy()
fid_c = var_c["fuente_id"].fillna(-1).to_numpy()
sup = prof_c < C.PROF_SUPERFICIAL_KM

D_all = matriz_distancias_km(lat_m, lon_m, var["lat"], var["lon"])     # todas las magnitudes (máximos y energía)
dentro_all = D_all <= R
mag_all = var["mag"].to_numpy()
E_all = energia_joules(mag_all)

# Flujo de energía sísmica en el sitio con distancia HIPOCENTRAL (todos los sismos, sin radio):
# Σ E / (4π R²). Para sismos del Nido a ~140 km de profundidad, 30 km de distancia epicentral cambian poco la
# distancia real a la fuente; este flujo lo refleja (el conteo a ≤ 30 km no).
R_hipo_m = np.sqrt(D_all ** 2 + var["prof_km"].to_numpy()[None, :] ** 2) * 1000
flujo = np.log10((E_all[None, :] / (4 * np.pi * R_hipo_m ** 2)).sum(axis=1) / T_var)
del R_hipo_m

filas, imput = [], {}


def imputar(nombre, valor):
    imput[nombre] = imput.get(nombre, 0) + 1
    return valor


prof_regional = float(np.median(prof_c))
for i in range(len(mun)):
    m = dentro[i]
    n = int(m.sum())
    ma = dentro_all[i]
    r = {"n_sismos_r30": n}
    r["tasa_sismos_r30"] = n / T_var
    r["tasa_m3_r30"] = np.sum(m & (mag_c >= 3.0)) / T_var
    r["tasa_fuertes_r30"] = np.sum(ma & (mag_all >= C.MAG_FUERTE)) / T_var
    r["mag_max_r30"] = float(mag_all[ma].max()) if ma.any() else imputar("mag_max_r30", mc)
    r["mag_p95_r30"] = float(np.quantile(mag_c[m], 0.95)) if n else imputar("mag_p95_r30", mc)
    r["valor_b_r30"] = valor_b(mag_c[m], mc) if n >= C.MIN_EVENTOS_B else imputar("valor_b_r30", b_regional)
    r["log_energia_anual_r30"] = np.log10(E_all[ma].sum() / T_var) if ma.any() else imputar(
        "log_energia_anual_r30", np.log10(energia_joules(mc) / T_var))
    r["prof_mediana_r30"] = float(np.median(prof_c[m])) if n else imputar("prof_mediana_r30", prof_regional)
    r["frac_superficiales_r30"] = float(np.mean(sup[m])) if n else imputar("frac_superficiales_r30", 0.0)
    r["tasa_superficiales_r30"] = np.sum(m & sup) / T_var
    ms = m & sup
    r["mag_max_superficial_r30"] = float(mag_c[ms].max()) if ms.any() else imputar("mag_max_superficial_r30", mc)
    for t, col in (("Nido de Bucaramanga", "frac_nido_r30"), ("Cortical", "frac_cortical_r30"),
                   ("Difusa (ruido)", "frac_difusa_r30")):
        r[col] = float(np.mean(tipo_c[m] == t)) if n else imputar(col, 0.0)
    ids, cnt = np.unique(fid_c[m & (fid_c >= 0)], return_counts=True)
    r["n_fuentes_r30"] = int(np.sum(cnt >= 5))
    filas.append(r)
X = pd.DataFrame(filas)
X["log_flujo_energia_hipo"] = flujo

# Densidad de epicentros dentro del polígono oficial (sismos/año por 100 km²)
import geopandas as gpd  # noqa: E402

pts = gpd.GeoDataFrame(var_c[["id_evento"]], geometry=gpd.points_from_xy(var_c["lon"], var_c["lat"]), crs="EPSG:4326")
sj = gpd.sjoin(pts, mun[["cod_mpio", "geometry"]], how="inner", predicate="within")
n_poli = sj.groupby("cod_mpio").size().reindex(mun["cod_mpio"], fill_value=0).to_numpy()
X["n_epicentros_propios"] = n_poli
X["densidad_epicentros"] = n_poli / T_var / mun["area_km2"].to_numpy() * 100

# Distancias a fuentes y a sismos relevantes
X["dist_nido_km"] = haversine_km(lat_m, lon_m, nido["lat"], nido["lon"])
f4 = var[var["mag"] >= C.MAG_FUERTE]
X["dist_sismo_fuerte_km"] = (matriz_distancias_km(lat_m, lon_m, f4["lat"], f4["lon"]).min(axis=1)
                             if len(f4) else np.nan)
s3 = var_c[(var_c["mag"] >= 3.0) & (var_c["prof_km"] < C.PROF_SUPERFICIAL_KM)]
X["dist_sismo_superficial_m3_km"] = (matriz_distancias_km(lat_m, lon_m, s3["lat"], s3["lon"]).min(axis=1)
                                     if len(s3) else np.nan)
fuentes_csv = C.SALIDAS / "fuentes_sismicas.csv"
fz = pd.read_csv(fuentes_csv) if fuentes_csv.exists() else pd.DataFrame()
fc = fz[fz["tipo"] == "Cortical"] if len(fz) else fz
X["dist_fuente_cortical_km"] = (matriz_distancias_km(lat_m, lon_m, fc["lat"], fc["lon"]).min(axis=1)
                                if len(fc) else np.nan)
for c in ("dist_sismo_fuerte_km", "dist_sismo_superficial_m3_km", "dist_fuente_cortical_km"):
    if X[c].isna().all():
        aviso(f"{c}: no hay sismos/fuentes de ese tipo; se deja fuera del modelo.")

# ----------------------------------------------------------------------------
# Sismicidad histórica (opcional): solo sismos ANTERIORES al fin del periodo de variables
# ----------------------------------------------------------------------------
hay_hist = HISTORICO.exists()
if hay_hist:
    h = pd.read_csv(HISTORICO)
    anio_fin = pd.Timestamp(per["variables"][1]).year
    h = h[h["anio"].isna() | (h["anio"] <= anio_fin)]
    Dh = matriz_distancias_km(lat_m, lon_m, h["lat"], h["lon"])
    mh = Dh <= C.RADIO_HISTORICO_KM
    X["hist_n_r100"] = mh.sum(axis=1)
    inten = h["intensidad_max"].to_numpy(float)
    X["hist_int_max_r100"] = [np.nanmax(inten[m]) if m.any() and np.isfinite(inten[m]).any() else 0.0 for m in mh]
    anios = h["anio"].to_numpy(float)
    ult = [np.nanmax(anios[m]) if m.any() and np.isfinite(anios[m]).any() else np.nan for m in mh]
    lejano = anio_fin - np.nanmin(anios) if np.isfinite(anios).any() else 400
    X["hist_anios_desde_ultimo"] = [anio_fin - u if np.isfinite(u) else lejano for u in ult]
    info(f"Sismicidad histórica: {len(h)} sismos hasta {anio_fin}")

# ----------------------------------------------------------------------------
# Población (opcional) -> exposición
# ----------------------------------------------------------------------------
hay_pob = POBLACION.exists()
if hay_pob:
    p = pd.read_csv(POBLACION, dtype={"cod_mpio": str}).set_index("cod_mpio")
    X["poblacion"] = p["poblacion"].reindex(mun["cod_mpio"]).to_numpy()
    X["densidad_poblacion"] = X["poblacion"] / mun["area_km2"].to_numpy()
    if "poblacion_cabecera" in p:
        X["frac_cabecera"] = (p["poblacion_cabecera"].reindex(mun["cod_mpio"]).to_numpy() / X["poblacion"])
    faltan = int(X["poblacion"].isna().sum())
    if faltan:
        aviso(f"{faltan} municipios sin población: se imputa la mediana.")
        for c in ("poblacion", "densidad_poblacion", "frac_cabecera"):
            if c in X:
                X[c] = X[c].fillna(X[c].median())

# ----------------------------------------------------------------------------
# Variable objetivo (periodo POSTERIOR; no entra al modelo, solo valida)
# ----------------------------------------------------------------------------
o4 = obj[obj["mag"] >= C.MAG_FUERTE]
Do = matriz_distancias_km(lat_m, lon_m, o4["lat"], o4["lon"])
X["obj_tasa_fuertes_futura_r50"] = (Do <= RO).sum(axis=1) / T_obj
oc = obj[obj["mag"] >= mc - 1e-9]
Doc = matriz_distancias_km(lat_m, lon_m, oc["lat"], oc["lon"])
X["obj_tasa_futura_r30"] = (Doc <= R).sum(axis=1) / T_obj
info(f"Objetivo: {len(o4)} sismos M ≥ {C.MAG_FUERTE} en el periodo objetivo")

# ----------------------------------------------------------------------------
# Diccionario de datos
# ----------------------------------------------------------------------------
SGC = "SGC – catálogo RSNC"
PV = f"{per['variables'][0]} a {per['variables'][1]}"
PO = f"{per['objetivo'][0]} a {per['objetivo'][1]}"
V = [
    # nombre, grupo, descripción, tipo, unidad, fuente, periodo, uso, transformación, componente índice, justificación
    ("cod_mpio", "identificador", "Código DANE del municipio (DIVIPOLA)", "texto", "—", "DANE MGN 2018", "—",
     "identificador", "—", "", "Une las tablas y el mapa."),
    ("municipio", "identificador", "Nombre del municipio", "texto", "—", "DANE MGN 2018", "—", "identificador",
     "—", "", "Lectura del resultado."),
    ("zona_foco", "territorial", "Pertenece al Área Metropolitana de Bucaramanga + Los Santos", "booleana", "—",
     "config.py", "—", "descriptiva", "—", "", "Zona que se compara contra el resto del departamento."),
    ("area_km2", "territorial", "Área oficial del municipio", "numérica continua", "km²", "DANE MGN 2018", "—",
     "descriptiva", "—", "", "Normaliza la densidad de epicentros; no entra al modelo para no agrupar por tamaño."),
    ("lat", "territorial", "Latitud del punto representativo (centro del vecindario)", "numérica continua", "°",
     "DANE MGN 2018", "—", "descriptiva", "—", "", "Ubicación; no entra al modelo (agruparía por posición, no por amenaza)."),
    ("lon", "territorial", "Longitud del punto representativo", "numérica continua", "°", "DANE MGN 2018", "—",
     "descriptiva", "—", "", "Ídem."),
    ("n_sismos_r30", "actividad", f"Sismos con M ≥ Mc y epicentro a ≤ {R} km", "numérica discreta", "sismos", SGC,
     PV, "descriptiva", "—", "", "Base de los conteos; el modelo usa su tasa anual."),
    ("tasa_sismos_r30", "actividad", f"Sismos por año con M ≥ Mc a ≤ {R} km", "numérica continua", "sismos/año",
     SGC, PV, "modelo", "log1p", "actividad", "Actividad sísmica total del entorno, corregida por completitud."),
    ("tasa_m3_r30", "actividad", f"Sismos por año con M ≥ 3 a ≤ {R} km", "numérica continua", "sismos/año", SGC,
     PV, "modelo", "log1p", "actividad", "Sismos que la población suele sentir."),
    ("tasa_fuertes_r30", "actividad", f"Sismos por año con M ≥ {C.MAG_FUERTE} a ≤ {R} km", "numérica continua",
     "sismos/año", SGC, PV, "modelo", "log1p", "actividad", "Sismos sentidos ampliamente, capaces de daño leve."),
    ("n_epicentros_propios", "actividad", "Sismos con M ≥ Mc con epicentro dentro del polígono", "numérica discreta",
     "sismos", SGC, PV, "descriptiva", "—", "", "Base de la densidad de epicentros."),
    ("densidad_epicentros", "actividad", "Sismos M ≥ Mc por año y por 100 km² dentro del municipio",
     "numérica continua", "sismos/año/100 km²", f"{SGC} + DANE MGN", PV, "modelo", "log1p", "actividad",
     "Actividad propia del territorio municipal, normalizada por área."),
    ("mag_max_r30", "magnitud", f"Magnitud máxima a ≤ {R} km", "numérica continua", "M", SGC, PV, "modelo", "—",
     "magnitud", "Peor evento observado en el entorno."),
    ("mag_p95_r30", "magnitud", f"Percentil 95 de magnitud (M ≥ Mc) a ≤ {R} km", "numérica continua", "M", SGC, PV,
     "modelo", "—", "magnitud", "Magnitud alta típica, más robusta que el máximo."),
    ("valor_b_r30", "magnitud", f"Valor b de Gutenberg-Richter (Aki-Utsu) a ≤ {R} km", "numérica continua",
     "adimensional", SGC, PV, "modelo", "—", "", f"b bajo = proporción mayor de sismos grandes. Se imputa el b "
     f"regional si hay < {C.MIN_EVENTOS_B} sismos."),
    ("log_energia_anual_r30", "energía", f"log10 de la energía liberada por año a ≤ {R} km (log E = 1.5 M + 4.8)",
     "numérica continua", "log10(J/año)", SGC, PV, "modelo", "—", "energia",
     "Resume actividad y tamaño en una magnitud física."),
    ("log_flujo_energia_hipo", "energía", "log10 del flujo de energía sísmica que llega al municipio por año: "
     "Σ E / (4π R²), con R = distancia hipocentral (incluye la profundidad) y todos los sismos, sin radio",
     "numérica continua", "log10(J/m²/año)", SGC, PV, "modelo", "—", "sacudida",
     "Mide la sacudida en el sitio con la distancia real a la fuente: un sismo del Nido a 140 km de profundidad "
     "está casi igual de lejos de Bucaramanga que de Los Santos, aunque el epicentro no caiga a ≤ 30 km."),
    ("prof_mediana_r30", "profundidad", f"Profundidad mediana de los sismos a ≤ {R} km", "numérica continua", "km",
     SGC, PV, "modelo", "—", "", "Separa la sismicidad del Nido (~140 km) de la cortical."),
    ("frac_superficiales_r30", "profundidad", f"Fracción de sismos con profundidad < {C.PROF_SUPERFICIAL_KM} km",
     "proporción", "0–1", SGC, PV, "modelo", "—", "superficialidad",
     "Los sismos superficiales son los más dañinos a igual magnitud."),
    ("tasa_superficiales_r30", "profundidad", f"Sismos superficiales (< {C.PROF_SUPERFICIAL_KM} km) por año a ≤ {R} km",
     "numérica continua", "sismos/año", SGC, PV, "modelo", "log1p", "superficialidad",
     "Actividad de las fallas corticales cercanas."),
    ("mag_max_superficial_r30", "profundidad", f"Magnitud máxima de los sismos superficiales a ≤ {R} km",
     "numérica continua", "M", SGC, PV, "modelo", "—", "superficialidad", "Peor sismo cortical cercano."),
    ("dist_nido_km", "distancia", "Distancia epicentral al centro del Nido de Bucaramanga (estimado por HDBSCAN)",
     "numérica continua", "km", f"{SGC} (HDBSCAN)", PV, "modelo", "log1p", "distancia",
     "Los sismos del Nido son los más frecuentes y se sienten en todo el departamento."),
    ("dist_sismo_fuerte_km", "distancia", f"Distancia al epicentro M ≥ {C.MAG_FUERTE} más cercano",
     "numérica continua", "km", SGC, PV, "modelo", "log1p", "distancia", "Cercanía a sismos fuertes recientes."),
    ("dist_sismo_superficial_m3_km", "distancia", f"Distancia al sismo superficial (< {C.PROF_SUPERFICIAL_KM} km) "
     "M ≥ 3 más cercano", "numérica continua", "km", SGC, PV, "modelo", "log1p", "distancia",
     "Cercanía a fallas corticales activas."),
    ("frac_nido_r30", "fuentes (nivel 1)", f"Fracción de los sismos a ≤ {R} km que HDBSCAN asigna al Nido",
     "proporción", "0–1", f"{SGC} (HDBSCAN)", PV, "modelo", "—", "", "Qué tanto domina el Nido el entorno."),
    ("frac_cortical_r30", "fuentes (nivel 1)", f"Fracción de los sismos a ≤ {R} km en fuentes corticales (HDBSCAN)",
     "proporción", "0–1", f"{SGC} (HDBSCAN)", PV, "modelo", "—", "", "Peso de las fuentes superficiales."),
    ("frac_difusa_r30", "fuentes (nivel 1)", f"Fracción de los sismos a ≤ {R} km que HDBSCAN deja como difusos",
     "proporción", "0–1", f"{SGC} (HDBSCAN)", PV, "modelo", "—", "", "Sismicidad sin fuente concentrada."),
    ("n_fuentes_r30", "fuentes (nivel 1)", f"Número de fuentes HDBSCAN con ≥ 5 sismos a ≤ {R} km",
     "numérica discreta", "fuentes", f"{SGC} (HDBSCAN)", PV, "modelo", "—", "", "Diversidad de fuentes que afectan al municipio."),
    ("dist_fuente_cortical_km", "fuentes (nivel 1)", "Distancia al centro de la fuente cortical HDBSCAN más cercana",
     "numérica continua", "km", f"{SGC} (HDBSCAN)", PV, "modelo", "log1p", "distancia", "Cercanía a fuentes superficiales."),
]
if hay_hist:
    HS = "SGC – sismicidad histórica"
    V += [
        ("hist_n_r100", "historia", f"Sismos históricos con daño a ≤ {C.RADIO_HISTORICO_KM} km", "numérica discreta",
         "sismos", HS, f"hasta {pd.Timestamp(per['variables'][1]).year}", "modelo", "log1p", "historia",
         "Memoria de daño anterior al catálogo instrumental."),
        ("hist_int_max_r100", "historia", f"Intensidad máxima histórica a ≤ {C.RADIO_HISTORICO_KM} km",
         "numérica continua", "EMS-98/MSK", HS, f"hasta {pd.Timestamp(per['variables'][1]).year}", "modelo", "—",
         "historia", "Daño real observado (0 = sin registro)."),
        ("hist_anios_desde_ultimo", "historia", f"Años desde el último sismo histórico con daño a ≤ {C.RADIO_HISTORICO_KM} km",
         "numérica continua", "años", HS, f"hasta {pd.Timestamp(per['variables'][1]).year}", "modelo", "log1p", "",
         "Recencia del daño."),
    ]
if hay_pob:
    PB = f"DANE – proyecciones de población {C.ANIO_POBLACION}"
    V += [
        ("poblacion", "exposición", "Población total del municipio", "numérica discreta", "habitantes", PB,
         str(C.ANIO_POBLACION), "modelo", "log1p", "exposicion", "Personas expuestas."),
        ("densidad_poblacion", "exposición", "Habitantes por km²", "numérica continua", "hab/km²", PB,
         str(C.ANIO_POBLACION), "modelo", "log1p", "exposicion", "Concentración de la exposición."),
    ]
    if "frac_cabecera" in X:
        V.append(("frac_cabecera", "exposición", "Fracción de la población en la cabecera municipal", "proporción",
                  "0–1", PB, str(C.ANIO_POBLACION), "modelo", "—", "exposicion", "Exposición urbana."))
V += [
    ("obj_tasa_fuertes_futura_r50", "objetivo", f"Sismos M ≥ {C.MAG_FUERTE} por año a ≤ {RO} km en el periodo objetivo",
     "numérica continua", "sismos/año", SGC, PO, "objetivo", "—", "",
     "Variable objetivo: periodo POSTERIOR y distinto al de las variables. No entra al modelo; valida los grupos."),
    ("obj_tasa_futura_r30", "objetivo", f"Sismos M ≥ Mc por año a ≤ {R} km en el periodo objetivo",
     "numérica continua", "sismos/año", SGC, PO, "objetivo", "—", "", "Validación complementaria (menos ruidosa)."),
]
dic = pd.DataFrame(V, columns=["variable", "grupo", "descripcion", "tipo", "unidad", "fuente", "periodo", "uso",
                               "transformacion", "componente_indice", "justificacion"])
# variables de modelo que quedaron vacías (sin sismos de ese tipo) -> descriptivas
for c in dic.loc[dic["uso"] == "modelo", "variable"]:
    if c not in X or X[c].isna().all() or X[c].nunique() <= 1:
        dic.loc[dic["variable"] == c, "uso"] = "descriptiva"
        aviso(f"{c} es constante o vacía: pasa a descriptiva.")

# ----------------------------------------------------------------------------
# Dataset final
# ----------------------------------------------------------------------------
ds = pd.concat([mun[["cod_mpio", "municipio", "zona_foco", "area_km2", "lat", "lon"]].reset_index(drop=True),
                X.reset_index(drop=True)], axis=1)
orden = [v for v in dic["variable"] if v in ds.columns]
ds = ds[orden]
num = ds.select_dtypes("number").columns
ds[num] = ds[num].round(4)
ds.to_csv(DATASET, index=False)
mun[["cod_mpio", "geometry"]].merge(ds, on="cod_mpio").to_file(DATASET_GEO, driver="GeoJSON")

estad = ds[[c for c in orden if c in num]].describe().T[["min", "50%", "max"]].rename(
    columns={"min": "mín", "50%": "mediana", "max": "máx"})
dic = dic.merge(estad, left_on="variable", right_index=True, how="left")
dic["imputados"] = dic["variable"].map(imput).fillna(0).astype(int)
dic.to_csv(DICCIONARIO_CSV, index=False)
n_modelo = int((dic["uso"] == "modelo").sum())

# Catálogo con municipio (todos los sismos limpios, con su fuente, su municipio y su periodo)
cm = cat_todo.copy()
pts_all = gpd.GeoDataFrame(cm[["id_evento"]], geometry=gpd.points_from_xy(cm["lon"], cm["lat"]), crs="EPSG:4326")
sja = gpd.sjoin(pts_all, mun[["cod_mpio", "municipio", "geometry"]], how="left", predicate="within")
sja = sja.drop_duplicates("id_evento")
cm = cm.merge(sja[["id_evento", "cod_mpio", "municipio"]], on="id_evento", how="left")
iv, fv = pd.Timestamp(per["variables"][0]), pd.Timestamp(per["variables"][1]) + pd.Timedelta(days=1)
io_, fo = pd.Timestamp(per["objetivo"][0]), pd.Timestamp(per["objetivo"][1]) + pd.Timedelta(days=1)
cm["periodo"] = np.select([(cm.fecha_utc >= iv) & (cm.fecha_utc < fv), (cm.fecha_utc >= io_) & (cm.fecha_utc < fo)],
                          ["variables", "objetivo"], "fuera")
cm["usado_en_variables"] = (cm["periodo"] == "variables") & cm["id_evento"].isin(var["id_evento"])
cm.to_csv(C.PROCESSED / "catalogo_con_municipio.csv", index=False)

# ----------------------------------------------------------------------------
# Validación cruzada con USGS (si existe)
# ----------------------------------------------------------------------------
txt_usgs = "No se usó (no hay `datos/interim/catalogo_usgs.csv`; correr `python run_all.py --usgs` con internet)."
if fuente == "sgc" and CAT_USGS.exists():
    u = pd.read_csv(CAT_USGS, parse_dates=["fecha_utc"])
    u = en_periodo(u, (cat_todo.fecha_utc.min().date().isoformat(), cat_todo.fecha_utc.max().date().isoformat()))
    s4 = cat_todo[cat_todo["mag"] >= C.MAG_FUERTE].reset_index(drop=True)
    u4 = u[u["mag"] >= C.MAG_FUERTE].reset_index(drop=True)
    if len(s4) and len(u4):
        dt = np.abs(s4["fecha_utc"].to_numpy()[:, None] - u4["fecha_utc"].to_numpy()[None, :]) / np.timedelta64(1, "s")
        dd = matriz_distancias_km(s4["lat"], s4["lon"], u4["lat"], u4["lon"])
        par = (dt <= 30) & (dd <= 50)
        emp = int(par.any(axis=1).sum())
        j = np.where(par.any(axis=1), np.argmin(np.where(par, dt, np.inf), axis=1), -1)
        k = j >= 0
        dmag = (s4.loc[k, "mag"].to_numpy() - u4.loc[j[k], "mag"].to_numpy())
        ddep = (s4.loc[k, "prof_km"].to_numpy() - u4.loc[j[k], "prof_km"].to_numpy())
        txt_usgs = (f"Sismos M ≥ {C.MAG_FUERTE}: SGC {len(s4)}, USGS {len(u4)}; emparejados (≤ 30 s y ≤ 50 km) "
                    f"{emp} ({emp / len(s4):.0%} de los del SGC). Diferencia mediana de magnitud SGC − USGS "
                    f"{np.median(dmag):+.2f}; de profundidad {np.median(ddep):+.1f} km.")

# ----------------------------------------------------------------------------
# Reportes
# ----------------------------------------------------------------------------
modelo_vars = dic.loc[dic["uso"] == "modelo", "variable"].tolist()
corr = ds[modelo_vars].corr(method="spearman")
pares = [(a, b_, corr.loc[a, b_]) for i_, a in enumerate(modelo_vars) for b_ in modelo_vars[i_ + 1:]
         if abs(corr.loc[a, b_]) >= 0.9]
mc_tab = pd.DataFrame(sorted(mc_anual.items()), columns=["Año", "Mc (máx. curvatura + 0.2)"])
imp_tab = pd.DataFrame(sorted(imput.items()), columns=["Variable", "Municipios imputados"])
escribir(C.INTERIM / "reporte_variables.md", f"""# Reporte de construcción de variables

Generado por `scripts/06_construir_variables.py` con el catálogo **{fuente.upper()}**.

## Periodos

| | Desde | Hasta | Años | Sismos (bien localizados) |
|---|---|---|---:|---:|
| Variables (entrada del modelo) | {per['variables'][0]} | {per['variables'][1]} | {T_var:.2f} | {len(var):,} |
| Objetivo (validación, no entra al modelo) | {per['objetivo'][0]} | {per['objetivo'][1]} | {T_obj:.2f} | {len(obj):,} |

{"**Periodos ajustados a los datos**: los exports no cubren los periodos de `config.py` (" + str(C.PERIODO_VARIABLES) + " / " + str(C.PERIODO_OBJETIVO) + "). Con los Excel 2006–2025 el pipeline vuelve solo a esos periodos." if per['ajustado'] else "Periodos de `config.py`."}

## Magnitud de completitud (Mc)

Máxima curvatura + 0.2 por año; se toma el **peor año** como Mc homogéneo = **{mc:.1f}**. Los conteos usan M ≥ Mc
({len(var_c):,} sismos). Valor b regional (Aki-Utsu) = **{b_regional:.2f}**.

{tabla_md(mc_tab, floatfmt='.1f')}

## Centro del Nido de Bucaramanga

{nido.get('origen', '')}: lat **{nido['lat']}**, lon **{nido['lon']}**, profundidad **{nido.get('prof_km', '—')} km**
(referencia Prieto et al., 2012: {C.NIDO_REFERENCIA['lat']}, {C.NIDO_REFERENCIA['lon']}, {C.NIDO_REFERENCIA['prof_km']:g} km;
diferencia {nido.get('dist_a_referencia_km', 0)} km).

## Imputaciones

Municipios sin sismos suficientes en su vecindario: magnitudes -> Mc, profundidad -> mediana regional,
fracciones -> 0, valor b -> b regional (si hay < {C.MIN_EVENTOS_B} sismos).

{tabla_md(imp_tab) if len(imp_tab) else 'Ninguna.'}

## Variables muy correlacionadas (|Spearman| ≥ 0.9)

Se mantienen porque miden aspectos distintos (p. ej. conteo vs. energía); K-Means las ve estandarizadas y la
comparación con PCA en el paso 07 controla el efecto de la redundancia.

{tabla_md(pd.DataFrame(pares, columns=['Variable A', 'Variable B', 'Spearman']), floatfmt='.2f') if pares else 'Ninguna.'}

## Validación cruzada con USGS

{txt_usgs}

## Resumen

- {len(ds)} municipios × {n_modelo} variables de modelo ({len(dic)} columnas en total con identificadores,
  descriptivas y objetivo).
- Sismicidad histórica: {'sí' if hay_hist else 'no (falta el archivo)'} · Población: {'sí' if hay_pob else 'no (falta el archivo)'}.
""")

# Diccionario en Markdown
filas_md = []
for _, r in dic.iterrows():
    rango = "" if pd.isna(r["mín"]) else f"{r['mín']:.3g} – {r['máx']:.3g}"
    filas_md.append(f"| `{r['variable']}` | {r['grupo']} | {r['descripcion']} | {r['tipo']} | {r['unidad']} | "
                    f"{r['fuente']} | {r['periodo']} | **{r['uso']}** | {r['transformacion']} | {rango} | "
                    f"{r['imputados']} | {r['justificacion']} |")
escribir(C.DOCS / "diccionario_datos.md", f"""# Diccionario de datos · `datos/processed/dataset_municipios.csv`

Una fila = un municipio de Santander ({len(ds)} filas). **{n_modelo} variables entran al modelo** (uso = modelo);
las demás identifican, describen o validan. Generado por `scripts/06_construir_variables.py`.

- Vecindario: círculo de **{R} km** alrededor del punto representativo del municipio (misma área para todos).
- Conteos con **M ≥ Mc = {mc:.1f}** (completitud homogénea). Sismos mal localizados excluidos (Gap > {C.GAP_MAX}°,
  RMS > {C.RMS_MAX_S} s, error horizontal o de profundidad > {C.ERROR_H_MAX_KM:g} km, < {C.FASES_MIN} fases).
- **Variables: {PV}** · **Objetivo: {PO}** (periodos distintos, sin fuga de información).
- Transformación `log1p` = log(1 + x) antes de estandarizar (variables muy sesgadas). Luego todas se estandarizan (z).
- **No entran al modelo**: Fases, RMS, Gap y errores de localización (solo filtran) ni hora/día/mes (sin poder
  discriminativo en sismos tectónicos).

| Variable | Grupo | Descripción | Tipo | Unidad | Fuente | Periodo | Uso | Transf. | Rango | Imput. | Justificación |
|---|---|---|---|---|---|---|---|---|---|---:|---|
{chr(10).join(filas_md)}
""")

# Metadatos de origen
arch = pd.read_csv(ARCHIVOS_SGC) if ARCHIVOS_SGC.exists() else pd.DataFrame()
tabla_arch = tabla_md(arch[["archivo", "formato", "filas", "consulta_fecha_inicial", "consulta_fecha_final",
                            "tipo_consulta", "departamento", "lat", "lon", "magnitud", "profundidad_km",
                            "creado_por_portal"]]) if len(arch) else "_(sin archivos)_"
hmeta = leer_json(HISTORICO_META, None)
pmeta = leer_json(POBLACION_META, None)
tmeta = leer_json(C.INTERIM / "territorio_meta.json", {})
escribir(C.DOCS / "metadatos_origen.md", f"""# Metadatos de origen de los datos

| Dataset | Fuente / URL | Fecha de descarga | Uso |
|---|---|---|---|
| Catálogo sísmico RSNC | Servicio Geológico Colombiano, {C.URL_SGC_CATALOGO} | {C.FECHA_DESCARGA_SGC or 'NO REGISTRADA (llenar config.py)'} | Fuente principal: sismos, variables y objetivo |
| Límites municipales MGN 2018 | DANE, {C.URL_DANE_MGN} (copia GeoJSON: {C.URL_DANE_MGN_ESPEJO}) | archivo `{tmeta.get('archivo', '—')}` | 87 municipios, área oficial |
| Sismicidad histórica | SGC, {C.URL_SGC_HISTORICO} | {(hmeta or {}).get('fecha_descarga') or ('NO REGISTRADA' if hmeta else 'no incluida')} | {'Variables históricas' if hmeta else 'No se usó: falta el archivo en datos/raw/sgc_historico/'} |
| Población municipal | DANE, {C.URL_DANE_POBLACION} | {(pmeta or {}).get('fecha_descarga') or ('NO REGISTRADA' if pmeta else 'no incluida')} | {'Exposición' if pmeta else 'No se usó: falta el archivo en datos/raw/dane/'} |
| Catálogo USGS ComCat | {C.URL_USGS_API} | {'descargado por 01_descargar_usgs.py' if CAT_USGS.exists() else 'no incluido'} | Validación cruzada (opcional) |

## Exports del SGC usados

Cada fila es un archivo de `datos/raw/sgc/` con los parámetros de búsqueda que el portal escribe en él.
`creado_por_portal` es la fecha que el SGC guarda dentro del .xlsx al exportarlo.

{tabla_arch}

## Filtros y limpieza aplicados

- Caja de estudio: lat {C.BBOX['lat_min']} a {C.BBOX['lat_max']}, lon {C.BBOX['lon_min']} a {C.BBOX['lon_max']}.
  Fechas {C.FECHA_INICIO} a {C.FECHA_FIN}.
- Válidos: magnitud entre {C.MAG_VALIDA[0]} y {C.MAG_VALIDA[1]}, profundidad 0–{C.PROF_MAX_VALIDA_KM:g} km.
- Duplicados: exactos y a ≤ {C.VENTANA_DUPLICADO_S:g} s y ≤ {C.DIST_DUPLICADO_KM:g} km.
- Calidad (filtro): Gap ≤ {C.GAP_MAX}°, RMS ≤ {C.RMS_MAX_S} s, errores ≤ {C.ERROR_H_MAX_KM:g} km, ≥ {C.FASES_MIN} fases.
- Magnitud homogénea: Mw si existe; si no, la reportada (ML). Completitud Mc = {mc:.1f}.
- Detalle: `datos/interim/reporte_limpieza_sgc.md` y `datos/interim/reporte_variables.md`.
""")

ok(f"{len(ds)} municipios × {n_modelo} variables de modelo -> {rel(DATASET)}")
ok(f"Diccionario -> {rel(C.DOCS / 'diccionario_datos.md')} · metadatos -> {rel(C.DOCS / 'metadatos_origen.md')}")
if imput:
    info("Imputaciones: " + ", ".join(f"{k} ({v})" for k, v in imput.items()))
if pares:
    info(f"{len(pares)} pares de variables con |Spearman| ≥ 0.9 (ver reporte_variables.md)")
escribir_json(C.INTERIM / "periodos.json", dict(per, mc=mc, b_regional=b_regional, n_modelo=n_modelo,
                                                hay_historico=hay_hist, hay_poblacion=hay_pob, fuente=fuente))
