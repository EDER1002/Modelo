"""
Paso 00 · Territorio: los 87 municipios de Santander (DANE, MGN 2018).

Entrada : datos/raw/dane/  -> el shapefile oficial MGN2018_MPIO_POLITICO (.shp) si lo pusiste,
          o el GeoJSON del MGN 2018 incluido (co_2018_MGN_MPIO_POLITICO.geojson).
Salida  : datos/processed/municipios_santander.geojson (+ .csv sin geometría)
          datos/processed/santander_contorno.geojson
"""
import sys

import geopandas as gpd
import pandas as pd

from utils import (C, CONTORNO, CRS_COLOMBIA, MUNICIPIOS, asegurar_carpetas, aviso, escribir_json,
                   info, nombre_propio, ok, rel, titulo)

titulo("00 · Territorio: municipios de Santander (DANE MGN 2018)")
asegurar_carpetas()

candidatos = sorted(C.RAW_DANE.glob("*.shp")) + sorted(C.RAW_DANE.glob("*.geojson")) + \
    sorted(C.RAW_DANE.glob("*.json"))
candidatos = [p for p in candidatos if "MPIO" in p.name.upper()] or candidatos
if not candidatos:
    sys.exit(f"✗ No hay límites municipales en {rel(C.RAW_DANE)}. Pon el GeoJSON o el .shp del MGN 2018.")
ruta = candidatos[0]
info(f"Leyendo {rel(ruta)}")
g = gpd.read_file(ruta)
cols = {c.upper(): c for c in g.columns}


def col(*nombres):
    for n in nombres:
        if n in cols:
            return cols[n]
    return None


c_depto = col("DPTO_CCDGO", "COD_DPTO", "DPTO")
c_mpio = col("MPIO_CCNCT", "MPIO_CDPMP", "COD_MPIO", "DPTOMPIO")
c_mpio3 = col("MPIO_CCDGO")
c_nombre = col("MPIO_CNMBR", "NOMBRE_MPI", "MPIO_NOMBR", "NOMBRE")
c_area = col("MPIO_NAREA", "AREA_KM2")
if c_mpio is None and c_depto and c_mpio3:
    g["_cod"] = g[c_depto].astype(str).str.zfill(2) + g[c_mpio3].astype(str).str.zfill(3)
    c_mpio = "_cod"
if c_mpio is None or c_nombre is None:
    sys.exit(f"✗ No reconozco las columnas de código/nombre de municipio en {ruta.name}: {list(g.columns)}")

g["cod_mpio"] = g[c_mpio].astype(str).str.zfill(5)
g = g[g["cod_mpio"].str.startswith(C.COD_DEPTO)].copy()
if g.crs is None:
    g = g.set_crs("EPSG:4326")
g = g.to_crs("EPSG:4326")
g["geometry"] = g.geometry.make_valid()
g = g.dissolve(by="cod_mpio", as_index=False, aggfunc="first")   # por si un municipio viene en varias filas

g["municipio_oficial"] = g[c_nombre].astype(str).str.strip()
g["municipio"] = g["municipio_oficial"].map(nombre_propio)
g_m = g.to_crs(CRS_COLOMBIA)
g["area_km2_calculada"] = (g_m.geometry.area / 1e6).round(2)
g["area_km2"] = pd.to_numeric(g[c_area], errors="coerce").round(2) if c_area else g["area_km2_calculada"]
g["area_km2"] = g["area_km2"].fillna(g["area_km2_calculada"])

# Punto representativo (siempre cae dentro del polígono) -> centro del vecindario de 30 km
rep = g_m.geometry.representative_point().to_crs("EPSG:4326")
cen = g_m.geometry.centroid.to_crs("EPSG:4326")
g["lat"], g["lon"] = rep.y.round(5), rep.x.round(5)
g["lat_centroide"], g["lon_centroide"] = cen.y.round(5), cen.x.round(5)
g["zona_foco"] = g["cod_mpio"].isin(C.ZONA_FOCO.keys())

g = g[["cod_mpio", "municipio", "municipio_oficial", "area_km2", "area_km2_calculada", "lat", "lon",
       "lat_centroide", "lon_centroide", "zona_foco", "geometry"]].sort_values("cod_mpio")

n = len(g)
(ok if n == 87 else aviso)(f"{n} municipios de {C.NOMBRE_DEPTO} (se esperaban 87)")
faltan_foco = set(C.ZONA_FOCO) - set(g["cod_mpio"])
if faltan_foco:
    aviso(f"Códigos de ZONA_FOCO que no aparecen en el MGN: {sorted(faltan_foco)}")
info("Zona foco: " + ", ".join(g.loc[g.zona_foco, "municipio"]))
dif = (g["area_km2_calculada"] / g["area_km2"] - 1).abs()
info(f"Área oficial vs. calculada: diferencia mediana {dif.median():.1%} (el GeoJSON está simplificado)")

g.to_file(MUNICIPIOS, driver="GeoJSON")
g.drop(columns="geometry").to_csv(MUNICIPIOS.with_suffix(".csv"), index=False)
contorno = g[["geometry"]].dissolve()
contorno.to_file(CONTORNO, driver="GeoJSON")
escribir_json(C.INTERIM / "territorio_meta.json", {
    "archivo": ruta.name, "n_municipios": n, "crs_areas": CRS_COLOMBIA,
    "area_total_km2": float(g["area_km2"].sum()),
})
ok(f"Guardado {rel(MUNICIPIOS)}  (área total {g['area_km2'].sum():,.0f} km²)")
