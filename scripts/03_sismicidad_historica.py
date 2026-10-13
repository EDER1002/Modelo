"""
Paso 03 · Sismicidad histórica del SGC (sismos con daño, intensidad EMS-98 / MSK).

Entrada: datos/raw/sgc_historico/*.xls|.xlsx|.csv (export del visor SISH: https://sish.sgc.gov.co/visor/).
Salida : datos/interim/sismicidad_historica.csv  (fecha, lat, lon, prof_km, mag, intensidad_max, localidad)

Es opcional: si no hay archivo, el pipeline sigue sin las variables históricas.
"""
import re
import sys

import numpy as np
import pandas as pd

from utils import (C, HISTORICO, HISTORICO_META, a_numero, asegurar_carpetas, aviso, escribir_json, info,
                   leer_tabla, normalizar, ok, rel, titulo)

titulo("03 · Sismicidad histórica (SGC)")
asegurar_carpetas()
C.RAW_HISTORICO.mkdir(parents=True, exist_ok=True)

archivos = sorted(p for p in C.RAW_HISTORICO.iterdir()
                  if p.suffix.lower() in (".xls", ".xlsx", ".csv") and not p.name.startswith("~$"))
for viejo in (HISTORICO, HISTORICO_META):
    viejo.unlink(missing_ok=True)          # que no quede un resultado viejo si quitaste el archivo
if not archivos:
    aviso(f"No hay archivo de sismicidad histórica en {rel(C.RAW_HISTORICO)}/: se omiten las variables históricas.")
    aviso(f"Para incluirlas exporta la tabla del visor {C.URL_SGC_HISTORICO} y guárdala ahí.")
    sys.exit(0)

ROMANOS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
           "XI": 11, "XII": 12}


def a_intensidad(v):
    """'VIII' -> 8 ; 'VII-VIII' -> 7.5 ; '7' -> 7."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    s = normalizar(v).replace(" ", "")
    nums = []
    for parte in re.split(r"[-/]", s):
        if parte in ROMANOS:
            nums.append(ROMANOS[parte])
        else:
            try:
                nums.append(float(parte.replace(",", ".")))
            except ValueError:
                pass
    return float(np.mean(nums)) if nums else np.nan


def mapear(columnas):
    m = {}
    for c in columnas:
        n = normalizar(c)
        if n.startswith("LAT"):
            k = "lat"
        elif n.startswith("LON"):
            k = "lon"
        elif n.startswith("PROF"):
            k = "prof"
        elif "INTENSIDAD" in n or n in ("I0", "IO", "IMAX", "I MAX", "I_MAX"):
            k = "intensidad"
        elif n.startswith("MAG") or n in ("MW", "M"):
            k = "mag"
        elif n.startswith("FECHA") or n == "DATE":
            k = "fecha"
        elif n.startswith(("ANO", "AÑO", "ANIO", "YEAR")):
            k = "anio"
        elif n.startswith(("LOCALIDAD", "EPICENTRO", "MUNICIPIO", "NOMBRE", "SISMO", "LUGAR")):
            k = "localidad"
        else:
            continue
        m.setdefault(k, c)
    return m


partes = []
for ruta in archivos:
    try:
        hojas = leer_tabla(ruta)
    except ValueError as e:
        aviso(str(e))
        continue
    for hoja, raw in hojas.items():
        raw = raw.dropna(how="all")
        cab = next((i for i, (_, f) in enumerate(raw.head(40).iterrows())
                    if {"lat", "lon"} <= set(mapear([x for x in f.values if isinstance(x, str)]))), None)
        if cab is None:
            continue
        df = raw.iloc[cab + 1:].copy()
        df.columns = [str(c).strip() for c in raw.iloc[cab].values]
        m = mapear(df.columns)
        out = pd.DataFrame({"lat": a_numero(df[m["lat"]]), "lon": a_numero(df[m["lon"]])})
        out["prof_km"] = a_numero(df[m["prof"]]) if "prof" in m else np.nan
        out["mag"] = a_numero(df[m["mag"]]) if "mag" in m else np.nan
        out["intensidad_max"] = df[m["intensidad"]].map(a_intensidad) if "intensidad" in m else np.nan
        if "fecha" in m:
            f = pd.to_datetime(df[m["fecha"]].astype(str), errors="coerce", format="mixed", dayfirst=True)
            anio = f.dt.year.astype(float)
            # fechas antiguas (p. ej. 1644) que pandas no convierte: se toma el año del texto
            txt = df[m["fecha"]].astype(str).str.extract(r"(1[5-9]\d\d|20\d\d)")[0]
            out["anio"] = anio.fillna(pd.to_numeric(txt, errors="coerce"))
        elif "anio" in m:
            out["anio"] = a_numero(df[m["anio"]])
        else:
            out["anio"] = np.nan
        out["localidad"] = df[m["localidad"]].astype(str) if "localidad" in m else ""
        out["archivo"] = ruta.name
        partes.append(out)
        info(f"{ruta.name} ({hoja}): {len(out)} filas · columnas reconocidas: {sorted(m)}")

if not partes:
    aviso("No reconocí la tabla de sismicidad histórica (faltan latitud/longitud). Se omiten las variables históricas.")
    sys.exit(0)

h = pd.concat(partes, ignore_index=True).dropna(subset=["lat", "lon"])
if h["lon"].median() > 0:
    h["lon"] = -h["lon"]
h = h.drop_duplicates(subset=["anio", "lat", "lon"])
if h["intensidad_max"].isna().all() and h["mag"].isna().all():
    aviso("La tabla histórica no trae intensidad ni magnitud: solo se usará el conteo de sismos.")
h.to_csv(HISTORICO, index=False)
escribir_json(HISTORICO_META, {"archivos": [a.name for a in archivos], "n": int(len(h)),
                               "anio_min": h["anio"].min(), "anio_max": h["anio"].max(),
                               "fecha_descarga": C.FECHA_DESCARGA_HISTORICO})
ok(f"{len(h)} sismos históricos ({h['anio'].min():.0f}–{h['anio'].max():.0f}) -> {rel(HISTORICO)}")
