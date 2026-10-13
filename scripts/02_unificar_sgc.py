"""
Paso 02 · Unifica y limpia TODOS los exports del catálogo SGC (RSNC) que haya en datos/raw/sgc/.

- Lee .xlsx, .xls (también HTML disfrazado de .xls) y .csv, con cualquier nombre de archivo.
- Detecta la fila de encabezado y reconoce las columnas por su nombre, así que sirve para las dos
  consultas del portal: la antigua (jun-1993 a feb-2018: FECHA + HORA_UTC, MAGNITUD Ml / Mw, …) y la
  nueva (desde mar-2018: FECHA - HORA UTC, MAGNITUD + TIPO MAGNITUD, …).
- Guarda los parámetros de búsqueda que trae cada export (bloque "PARAMETROS DE BUSQUEDA").
- Limpieza: inválidos, fuera de zona/fechas, duplicados exactos y casi-duplicados (<= 3 s y <= 10 km),
  y marca (no borra) los sismos mal localizados según Gap, RMS, errores y fases.

Salidas: datos/interim/catalogo_sgc_unificado.csv, datos/interim/archivos_sgc.csv,
         datos/interim/reporte_limpieza_sgc.md
"""
import re
import sys

import numpy as np
import pandas as pd

from utils import (ARCHIVOS_SGC, CAT_SGC, C, a_numero, asegurar_carpetas, aviso, escribir,
                   fecha_creacion_xlsx, haversine_km, info, leer_tabla, normalizar, ok,
                   periodos_efectivos, rel, tabla_md, titulo)

titulo("02 · Unificar y limpiar el catálogo SGC")
asegurar_carpetas()

EXT = {".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".tsv"}
archivos = sorted(p for p in C.RAW_SGC.rglob("*") if p.is_file() and p.suffix.lower() in EXT
                  and not p.name.startswith(("~$", ".")))
if not archivos:
    sys.exit(f"""✗ No hay exports del SGC en {rel(C.RAW_SGC)}/.
  Descárgalos de {C.URL_SGC_CATALOGO} (consulta antigua hasta 2018-02-28 y nueva desde 2018-03-01),
  año por año, con la caja lat {C.BBOX['lat_min']}–{C.BBOX['lat_max']}, lon {C.BBOX['lon_min']}–{C.BBOX['lon_max']},
  sin filtro de magnitud ni profundidad, y guárdalos ahí (el nombre no importa).""")


def mapear_columnas(columnas):
    """Nombre original -> nombre estándar. Si el portal cambia un nombre, agrega la palabra aquí."""
    mapa = {}
    for c in columnas:
        n = normalizar(c)
        if not n:
            continue
        if "ERROR" in n and "LAT" in n:
            k = "err_lat"
        elif "ERROR" in n and "LON" in n:
            k = "err_lon"
        elif "ERROR" in n and "PROF" in n:
            k = "err_prof"
        elif "FECHA" in n and "HORA" in n:
            k = "fecha_hora"
        elif n.startswith("FECHA") or n == "DATE":
            k = "fecha"
        elif "HORA" in n or n in ("TIME", "TIEMPO"):
            k = "hora"
        elif n.startswith("LAT"):
            k = "lat"
        elif n.startswith("LON"):
            k = "lon"
        elif n.startswith("PROF") or n.startswith("DEPTH"):
            k = "prof"
        elif "TIPO" in n and "MAG" in n:
            k = "mag_tipo"
        elif "MAG" in n and re.search(r"\bMW\b", n):
            k = "mag_mw"
        elif "MAG" in n and re.search(r"\bML\b", n):
            k = "mag_ml"
        elif n.startswith("MAG"):
            k = "mag"
        elif "FASES" in n or n.startswith("NUM"):
            k = "fases"
        elif n.startswith("RMS"):
            k = "rms"
        elif n.startswith("GAP"):
            k = "gap"
        elif n.startswith("REGION") or n.startswith("MUNICIPIO") or n.startswith("LOCALIZ"):
            k = "region"
        elif n.startswith("DEPARTAMENTO"):
            k = "depto"
        elif n.startswith("ESTADO") or n.startswith("STATUS"):
            k = "estado"
        elif n.startswith("CALIDAD"):
            k = "calidad"
        else:
            continue
        mapa.setdefault(k, c)
    return mapa


def es_encabezado(fila):
    m = mapear_columnas([x for x in fila if isinstance(x, str)])
    tiene_fecha = "fecha_hora" in m or "fecha" in m
    return tiene_fecha and {"lat", "lon", "prof"} <= set(m) and bool({"mag", "mag_ml", "mag_mw"} & set(m))


def parametros_busqueda(bloque):
    """Pares clave-valor del bloque 'PARAMETROS DE BUSQUEDA' que antecede a la tabla."""
    p = {}
    for _, fila in bloque.iterrows():
        vals = list(fila.values)
        for i in range(0, len(vals) - 1, 2):
            k, v = vals[i], vals[i + 1]
            if isinstance(k, str) and k.strip() and not (isinstance(v, float) and np.isnan(v)):
                p[k.strip()] = str(v).strip()
    return p


def a_fecha(s):
    s = s.astype(str).str.strip().replace({"nan": None, "NaT": None, "None": None})
    t = pd.to_datetime(s, errors="coerce", format="ISO8601")
    if t.isna().mean() > 0.05:
        t = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=True)
    return t


def a_hora(s):
    if pd.api.types.is_numeric_dtype(s):                       # fracción de día de Excel
        return pd.to_timedelta(pd.to_numeric(s, errors="coerce"), unit="D")
    txt = s.astype(str).str.strip().str.extract(r"(\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)")[0]
    txt = txt.where(txt.str.count(":") == 2, txt + ":00")
    return pd.to_timedelta(txt, errors="coerce")


def estandarizar(df, mapa, nombre):
    out = pd.DataFrame(index=df.index)
    zona = "UTC"
    if "fecha_hora" in mapa:
        out["fecha_utc"] = a_fecha(df[mapa["fecha_hora"]])
        col_t = normalizar(mapa["fecha_hora"])
    else:
        f = a_fecha(df[mapa["fecha"]]).dt.normalize()
        h = a_hora(df[mapa["hora"]]) if "hora" in mapa else pd.to_timedelta(0, unit="s")
        out["fecha_utc"] = f + h
        col_t = normalizar(mapa.get("hora", mapa["fecha"]))
    if "LOCAL" in col_t:
        out["fecha_utc"] = out["fecha_utc"] + pd.Timedelta(hours=5)     # Colombia = UTC-5
        zona = "local -> UTC (+5 h)"
    elif "UTC" not in col_t and "GMT" not in col_t:
        zona = "SUPUESTA UTC, verificar"

    for k_std, k in (("lat", "lat"), ("lon", "lon"), ("prof_km", "prof"), ("fases", "fases"),
                     ("rms_s", "rms"), ("gap_grados", "gap"), ("err_lat_km", "err_lat"),
                     ("err_lon_km", "err_lon"), ("err_prof_km", "err_prof")):
        out[k_std] = a_numero(df[mapa[k]]) if k in mapa else np.nan

    # Magnitud homogénea: Mw cuando existe; si no, la reportada (ML)
    if "mag_mw" in mapa or "mag_ml" in mapa:
        mw = a_numero(df[mapa["mag_mw"]]) if "mag_mw" in mapa else pd.Series(np.nan, index=df.index)
        ml = a_numero(df[mapa["mag_ml"]]) if "mag_ml" in mapa else pd.Series(np.nan, index=df.index)
        if "mag" in mapa:
            ml = ml.fillna(a_numero(df[mapa["mag"]]))
        usa_mw = mw.notna()
        out["mag"] = mw.where(usa_mw, ml)
        out["mag_tipo"] = np.where(usa_mw, "Mw", "ML")
        out["mag_tipo_original"] = np.where(usa_mw, "Mw", "Ml")
        formato = "antiguo (1993-06 a 2018-02)"
    else:
        out["mag"] = a_numero(df[mapa["mag"]])
        tipo = df[mapa["mag_tipo"]].astype(str).str.strip() if "mag_tipo" in mapa else pd.Series("ML", index=df.index)
        out["mag_tipo_original"] = tipo
        out["mag_tipo"] = np.where(tipo.str.upper().str.startswith("MW"), "Mw", "ML")
        formato = "nuevo (desde 2018-03)"

    out["region"] = df[mapa["region"]].astype(str).str.strip() if "region" in mapa else None
    if "depto" in mapa and "region" in mapa:
        out["region"] = out["region"] + " - " + df[mapa["depto"]].astype(str).str.strip()
    est = df[mapa["estado"]].astype(str).str.strip().str.lower() if "estado" in mapa else pd.Series("", index=df.index)
    out["estado"] = est
    out["revisado"] = est.str.contains("manual|revis|review|final", regex=True) & ~est.str.contains("autom")
    out["archivo"] = nombre
    out["formato"] = formato
    out["zona_horaria"] = zona
    return out


# ----------------------------------------------------------------------------
# 1) Leer todos los archivos
# ----------------------------------------------------------------------------
partes, meta = [], []
for ruta in archivos:
    try:
        hojas = leer_tabla(ruta)
    except ValueError as e:
        aviso(str(e))
        continue
    leidas = 0
    for hoja, raw in hojas.items():
        raw = raw.dropna(how="all")
        if raw.empty:
            continue
        cab = next((i for i, (_, fila) in enumerate(raw.head(80).iterrows()) if es_encabezado(fila.values)), None)
        if cab is None:
            continue
        params = parametros_busqueda(raw.iloc[:cab])
        df = raw.iloc[cab + 1:].copy()
        df.columns = [str(c).strip() for c in raw.iloc[cab].values]
        df = df.loc[:, [c for c in df.columns if c and c != "nan"]].dropna(how="all")
        mapa = mapear_columnas(df.columns)
        claves = {"lat", "lon", "prof"} | ({"fecha_hora"} if "fecha_hora" in mapa else {"fecha"})
        faltan = claves - set(mapa)
        if faltan or not ({"mag", "mag_ml", "mag_mw"} & set(mapa)):
            sys.exit(f"✗ No reconozco columnas clave {sorted(faltan) or ['magnitud']} en {ruta.name} "
                     f"(hoja {hoja}). Columnas encontradas: {list(df.columns)}.\n"
                     f"  Agrega la palabra que falte en mapear_columnas() de scripts/02_unificar_sgc.py.")
        std = estandarizar(df, mapa, ruta.name)
        partes.append(std)
        leidas += len(std)
        meta.append({
            "archivo": ruta.name, "hoja": hoja, "formato": std["formato"].iat[0],
            "filas": len(std), "desde": std["fecha_utc"].min(), "hasta": std["fecha_utc"].max(),
            "total_registros_declarado": params.get("TOTAL REGISTROS"),
            "consulta_fecha_inicial": params.get("FECHA_INICIAL"), "consulta_fecha_final": params.get("FECHA_FINAL"),
            "tipo_consulta": params.get("TIPO CONSULTA"), "departamento": params.get("DEPARTAMENTO"),
            "municipio": params.get("MUNICIPIO"),
            "lat": f"{params.get('LATITUD MINIMA', '?')} a {params.get('LATITUD MAXIMA', '?')}" if params else None,
            "lon": f"{params.get('LONGITUD MINIMA', '?')} a {params.get('LONGITUD MAXIMA', '?')}" if params else None,
            "magnitud": f"{params.get('MAGNITUD MINIMA', '?')} a {params.get('MAGNITUD MAXIMA', '?')}" if params else None,
            "profundidad_km": f"{params.get('PROFUNDIDAD MINIMA', '?')} a {params.get('PROFUNDIDAD MAXIMA', '?')}" if params else None,
            "creado_por_portal": fecha_creacion_xlsx(ruta) if ruta.suffix.lower() in (".xlsx", ".xlsm") else None,
            "columnas": " | ".join(df.columns),
        })
    if leidas:
        info(f"{ruta.name}: {leidas:,} filas ({meta[-1]['formato']})")
    else:
        aviso(f"{ruta.name}: no encontré una tabla de sismos (se ignora)")

if not partes:
    sys.exit("✗ Ningún archivo de datos/raw/sgc/ tenía una tabla de sismos reconocible.")
cat = pd.concat(partes, ignore_index=True)
meta = pd.DataFrame(meta)
pasos = [("Filas leídas (todos los archivos)", len(cat))]

# ----------------------------------------------------------------------------
# 2) Limpieza
# ----------------------------------------------------------------------------
# Unidades: longitudes oeste deben ser negativas; profundidad en km
if cat["lon"].median() > 0 and C.BBOX["lon_max"] < 0:
    cat["lon"] = -cat["lon"]
    aviso("Las longitudes venían positivas: se pasaron a oeste (negativas).")
notas_unidades = []
if cat["prof_km"].quantile(0.99) > 1000:
    cat["prof_km"] = cat["prof_km"] / 1000
    notas_unidades.append("Profundidad venía en metros: se pasó a km.")

n0 = len(cat)
cat = cat.dropna(subset=["fecha_utc", "lat", "lon", "prof_km", "mag"])
pasos.append(("Sin fecha, coordenadas, profundidad o magnitud", -(n0 - len(cat))))

n0 = len(cat)
cat = cat[cat["mag"].between(*C.MAG_VALIDA)]
pasos.append((f"Magnitud fuera de {C.MAG_VALIDA}", -(n0 - len(cat))))

leve = cat["prof_km"].between(-5, 0, inclusive="left")
cat.loc[leve, "prof_km"] = 0.0
n0 = len(cat)
cat = cat[cat["prof_km"].between(0, C.PROF_MAX_VALIDA_KM)]
pasos.append((f"Profundidad < 0 o > {C.PROF_MAX_VALIDA_KM:g} km ({int(leve.sum())} entre −5 y 0 km se fijaron en 0)",
              -(n0 - len(cat))))

b = C.BBOX
n0 = len(cat)
cat = cat[cat["lat"].between(b["lat_min"], b["lat_max"]) & cat["lon"].between(b["lon_min"], b["lon_max"])]
pasos.append(("Fuera de la caja de estudio (BBOX)", -(n0 - len(cat))))

ini, fin = pd.Timestamp(C.FECHA_INICIO), pd.Timestamp(C.FECHA_FIN) + pd.Timedelta(days=1)
n0 = len(cat)
cat = cat[(cat["fecha_utc"] >= ini) & (cat["fecha_utc"] < fin)]
pasos.append((f"Fuera de {C.FECHA_INICIO} a {C.FECHA_FIN}", -(n0 - len(cat))))

# Duplicados exactos (archivos que se solapan)
n0 = len(cat)
cat = cat.sort_values(["fecha_utc", "revisado", "fases"], ascending=[True, False, False])
cat = cat.drop_duplicates(subset=["fecha_utc", "lat", "lon", "mag"], keep="first")
pasos.append(("Duplicados exactos (mismo sismo en dos archivos)", -(n0 - len(cat))))

# Casi-duplicados: <= VENTANA_DUPLICADO_S y <= DIST_DUPLICADO_KM -> el mismo sismo reportado dos veces
cat = cat.reset_index(drop=True)
t = (cat["fecha_utc"] - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()  # sin depender de la resolución
la, lo = cat["lat"].to_numpy(), cat["lon"].to_numpy()
puntaje = cat["revisado"].astype(int).to_numpy() * 1000 + cat["fases"].fillna(0).to_numpy()
borrar = np.zeros(len(cat), bool)
for lag in range(1, 6):
    i = np.arange(len(cat) - lag)
    j = i + lag
    par = (t[j] - t[i] <= C.VENTANA_DUPLICADO_S) & (haversine_km(la[i], lo[i], la[j], lo[j]) <= C.DIST_DUPLICADO_KM)
    i, j = i[par], j[par]
    peor = np.where(puntaje[j] > puntaje[i], i, j)
    borrar[peor] = True
pasos.append((f"Casi-duplicados (≤ {C.VENTANA_DUPLICADO_S:g} s y ≤ {C.DIST_DUPLICADO_KM:g} km)", -int(borrar.sum())))
cat = cat[~borrar].reset_index(drop=True)
pasos.append(("**Sismos en el catálogo unificado**", len(cat)))

# ----------------------------------------------------------------------------
# 3) Calidad de localización: se MARCA (filtro), no entra al modelo
# ----------------------------------------------------------------------------
eh = cat[["err_lat_km", "err_lon_km"]].max(axis=1)
criterios = {
    f"Gap > {C.GAP_MAX}°": cat["gap_grados"] > C.GAP_MAX,
    f"RMS > {C.RMS_MAX_S} s (solo M < {C.RMS_EXENTO_DESDE_M:g})": (cat["rms_s"] > C.RMS_MAX_S)
    & (cat["mag"] < C.RMS_EXENTO_DESDE_M),
    f"Error horizontal > {C.ERROR_H_MAX_KM:g} km": eh > C.ERROR_H_MAX_KM,
    f"Error de profundidad > {C.ERROR_PROF_MAX_KM:g} km": cat["err_prof_km"] > C.ERROR_PROF_MAX_KM,
    f"Menos de {C.FASES_MIN} fases": cat["fases"] < C.FASES_MIN,
}
mala = np.zeros(len(cat), bool)
motivo = pd.Series("", index=cat.index)
for nombre, m in criterios.items():
    m = m.fillna(False).to_numpy()
    mala |= m
    motivo[m] = motivo[m] + nombre + "; "
cat["mala_localizacion"] = mala
cat["motivo_calidad"] = motivo.str.rstrip("; ")
cat = cat.sort_values("fecha_utc").reset_index(drop=True)
cat.insert(0, "id_evento", "SGC-" + cat["fecha_utc"].dt.strftime("%Y%m%d%H%M%S") + "-" + cat.index.astype(str))

cols = ["id_evento", "fecha_utc", "lat", "lon", "prof_km", "mag", "mag_tipo", "mag_tipo_original", "fases",
        "rms_s", "gap_grados", "err_lat_km", "err_lon_km", "err_prof_km", "region", "estado", "revisado",
        "mala_localizacion", "motivo_calidad", "archivo", "formato", "zona_horaria"]
cat[cols].to_csv(CAT_SGC, index=False)
meta.to_csv(ARCHIVOS_SGC, index=False)

# ----------------------------------------------------------------------------
# 4) Reporte de limpieza
# ----------------------------------------------------------------------------
per = periodos_efectivos(cat)
calidad = pd.DataFrame([(k, int(v.fillna(False).sum()), f"{v.fillna(False).mean():.1%}") for k, v in criterios.items()],
                       columns=["Criterio", "Sismos", "%"])
calidad.loc[len(calidad)] = ["**Total marcados (excluidos de las variables)**", int(mala.sum()), f"{mala.mean():.1%}"]
faltantes = (cat[["prof_km", "mag", "fases", "rms_s", "gap_grados", "err_lat_km", "err_lon_km", "err_prof_km"]]
             .isna().mean().mul(100).round(2).rename("% faltante").reset_index().rename(columns={"index": "Columna"}))
anual = cat.groupby(cat["fecha_utc"].dt.year).agg(sismos=("mag", "size"), M_max=("mag", "max"),
                                                  M4_o_mas=("mag", lambda m: int((m >= 4).sum())),
                                                  prof_mediana_km=("prof_km", "median"))
fuertes = cat[cat["mag"] >= C.MAG_FUERTE]
pct_rms_fuertes = (fuertes["rms_s"] > C.RMS_MAX_S).mean() if len(fuertes) else 0.0
calidad_fuertes = (fuertes[["rms_s", "err_prof_km", "gap_grados", "fases"]].describe().loc[["50%", "max"]]
                   .rename(index={"50%": "mediana", "max": "máximo"}).rename_axis("Estadístico").reset_index())
tipos = cat["mag_tipo_original"].value_counts().rename_axis("Tipo de magnitud").reset_index(name="Sismos")
meses = cat.set_index("fecha_utc").resample("MS").size()
huecos = meses[meses == 0]
tabla_arch = meta[["archivo", "formato", "filas", "total_registros_declarado", "consulta_fecha_inicial",
                   "consulta_fecha_final", "tipo_consulta", "departamento", "creado_por_portal"]]

notas = []
if (meta["departamento"].fillna("").str.strip() != "").any():
    notas.append("Los exports se pidieron con **filtro por departamento** (" +
                 ", ".join(sorted(meta["departamento"].dropna().unique())) +
                 "). Así faltan los sismos que caen justo fuera del límite departamental y los municipios de "
                 "borde ven menos sismos en su vecindario de 30 km. Para próximas descargas conviene la consulta por "
                 f"cuadrante (lat {b['lat_min']}–{b['lat_max']}, lon {b['lon_min']}–{b['lon_max']}).")
if len(huecos):
    notas.append(f"Meses sin ningún sismo en el catálogo (posible hueco de descarga): "
                 f"{', '.join(huecos.index.strftime('%Y-%m'))}.")
if per["ajustado"]:
    notas.append(f"Los datos no cubren los periodos de `config.py` (variables {C.PERIODO_VARIABLES[0]}–"
                 f"{C.PERIODO_VARIABLES[1]}, objetivo {C.PERIODO_OBJETIVO[0]}–{C.PERIODO_OBJETIVO[1]}). "
                 f"Se usan periodos ajustados a los datos: **variables {per['variables'][0]} a {per['variables'][1]}**, "
                 f"**objetivo {per['objetivo'][0]} a {per['objetivo'][1]}**.")
if (cat["zona_horaria"] == "SUPUESTA UTC, verificar").any():
    notas.append("Algún archivo no decía si la hora es UTC o local: se supuso UTC (el catálogo SGC usa UTC).")
notas += notas_unidades

md = f"""# Reporte de limpieza · Catálogo SGC (RSNC)

Generado por `scripts/02_unificar_sgc.py`. Fuente: Servicio Geológico Colombiano, Red Sismológica Nacional
de Colombia, {C.URL_SGC_CATALOGO}. Fecha de descarga declarada en `config.py`: **{C.FECHA_DESCARGA_SGC or 'NO REGISTRADA'}**.

## Archivos leídos ({len(meta)})

{tabla_md(tabla_arch)}

Parámetros de búsqueda de cada export (tal como los escribe el portal): ver `datos/interim/archivos_sgc.csv`.

## Pasos de limpieza

{tabla_md(pd.DataFrame(pasos, columns=["Paso", "Sismos (+ leídos / − quitados)"]))}

Hora: {', '.join(sorted(cat['zona_horaria'].unique()))}. Magnitud homogénea: Mw cuando existe y, si no, la
reportada (familia ML); el tipo original queda en `mag_tipo_original`.

## Calidad de localización (filtro, no variable del modelo)

Fases, RMS, Gap y errores describen la red de estaciones, no la amenaza. Se **marcan** los sismos mal
localizados (`mala_localizacion = True`) y se excluyen al construir las variables
(`EXCLUIR_ATIPICOS = {C.EXCLUIR_ATIPICOS}`). Un sismo puede cumplir varios criterios.

{tabla_md(calidad)}

El RMS no se aplica a M ≥ {C.RMS_EXENTO_DESDE_M:g}: los sismos grandes los registran estaciones lejanas y su RMS
sube aunque estén bien localizados. Sin esta excepción se perdería el {pct_rms_fuertes:.0%} de los sismos
M ≥ {C.MAG_FUERTE:g}, justo los que más importan para la amenaza. Calidad de los M ≥ {C.MAG_FUERTE:g}:

{tabla_md(calidad_fuertes, floatfmt='.1f')}

## Valores faltantes

{tabla_md(faltantes)}

## Tipos de magnitud

{tabla_md(tipos)}

## Sismos por año

{tabla_md(anual.reset_index().rename(columns={'fecha_utc': 'Año'}), floatfmt='.1f')}

## Observaciones

{chr(10).join('- ' + n for n in notas) if notas else '- Sin observaciones.'}
"""
escribir(C.INTERIM / "reporte_limpieza_sgc.md", md)

ok(f"{len(cat):,} sismos únicos ({cat.fecha_utc.min():%Y-%m-%d} a {cat.fecha_utc.max():%Y-%m-%d}), "
   f"{int(mala.sum()):,} marcados por mala localización ({mala.mean():.1%})")
for n in notas:
    aviso(n.replace("**", ""))
ok(f"Guardado {rel(CAT_SGC)} y {rel(C.INTERIM / 'reporte_limpieza_sgc.md')}")
