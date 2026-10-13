"""
Paso 04 · Población municipal DANE (exposición). Opcional.

Entrada (la primera que exista):
  1. datos/raw/dane/poblacion_manual.csv  con columnas cod_mpio,poblacion,poblacion_cabecera
  2. el Excel de proyecciones municipales por área del DANE en datos/raw/dane/
     (formato largo: DPMP / MPIO, AÑO, ÁREA GEOGRÁFICA, Población o Total)
Salida : datos/interim/poblacion_municipios.csv  (cod_mpio, poblacion, poblacion_cabecera)
"""
import sys

import pandas as pd

from utils import (C, POBLACION, POBLACION_META, a_numero, asegurar_carpetas, aviso, escribir_json, info,
                   leer_tabla, normalizar, ok, rel, titulo)

titulo("04 · Población DANE (exposición, opcional)")
asegurar_carpetas()
for viejo in (POBLACION, POBLACION_META):
    viejo.unlink(missing_ok=True)

pob = None
fuente = None
manual = C.RAW_DANE / "poblacion_manual.csv"
if manual.exists():
    p = pd.read_csv(manual, dtype={"cod_mpio": str})
    p["cod_mpio"] = p["cod_mpio"].str.zfill(5)
    pob = p[["cod_mpio", "poblacion"] + (["poblacion_cabecera"] if "poblacion_cabecera" in p else [])]
    fuente = manual.name
else:
    excels = [x for x in sorted(C.RAW_DANE.glob("*.xls*")) if not x.name.startswith("~$")]
    for ruta in excels:
        try:
            hojas = leer_tabla(ruta)
        except ValueError as e:
            aviso(str(e))
            continue
        for hoja, raw in hojas.items():
            cab = None
            for i, (_, f) in enumerate(raw.head(30).iterrows()):
                n = [normalizar(x) for x in f.values]
                if any(x in ("DPMP", "MPIO", "COD_MPIO", "CODIGO") for x in n) and any(x.startswith("ANO") for x in n):
                    cab = i
                    break
            if cab is None:
                continue
            df = raw.iloc[cab + 1:].copy()
            df.columns = [normalizar(c) for c in raw.iloc[cab].values]
            c_cod = next((c for c in ("DPMP", "COD_MPIO", "CODIGO", "MPIO") if c in df.columns), None)
            c_anio = next(c for c in df.columns if c.startswith("ANO"))
            c_area = next((c for c in df.columns if "AREA" in c), None)
            c_val = next((c for c in df.columns if c in ("POBLACION", "TOTAL", "POBLACION TOTAL")), None)
            if c_cod is None or c_val is None:
                continue
            df["cod_mpio"] = df[c_cod].astype(str).str.extract(r"(\d+)")[0].str.zfill(5)
            if c_cod == "MPIO" and "DP" in df.columns:
                df["cod_mpio"] = df["DP"].astype(str).str.zfill(2) + df["MPIO"].astype(str).str[-3:].str.zfill(3)
            df = df[df["cod_mpio"].str.startswith(C.COD_DEPTO) & (a_numero(df[c_anio]) == C.ANIO_POBLACION)]
            df["valor"] = a_numero(df[c_val])
            if c_area:
                area = df[c_area].map(normalizar)
                tot = df[area.str.startswith("TOTAL")].groupby("cod_mpio")["valor"].sum()
                cab_ = df[area.str.contains("CABECERA")].groupby("cod_mpio")["valor"].sum()
                pob = pd.DataFrame({"poblacion": tot, "poblacion_cabecera": cab_}).reset_index()
            else:
                pob = df.groupby("cod_mpio")["valor"].sum().rename("poblacion").reset_index()
            if len(pob):
                fuente = f"{ruta.name} ({hoja})"
                break
        if pob is not None and len(pob):
            break

if pob is None or len(pob) == 0:
    aviso(f"No hay población DANE en {rel(C.RAW_DANE)}/: se omiten las variables de exposición.")
    aviso(f"Para incluirlas baja las proyecciones municipales de {C.URL_DANE_POBLACION} "
          "o crea datos/raw/dane/poblacion_manual.csv (cod_mpio,poblacion,poblacion_cabecera).")
    sys.exit(0)

pob.to_csv(POBLACION, index=False)
escribir_json(POBLACION_META, {"fuente": fuente, "anio": C.ANIO_POBLACION, "n": int(len(pob)),
                               "fecha_descarga": C.FECHA_DESCARGA_POBLACION})
info(f"Fuente: {fuente}")
ok(f"Población {C.ANIO_POBLACION} de {len(pob)} municipios -> {rel(POBLACION)}")
