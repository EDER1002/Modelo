"""
Paso 01 · Catálogo USGS ComCat (opcional: validación cruzada del SGC).

- Si ya hay CSV en datos/raw/usgs/, solo los normaliza.
- Si no, los descarga año por año de la API FDSN pública del USGS con la misma caja (BBOX) y fechas.
- Si no hay internet o la API no responde, avisa y sigue (el USGS no es obligatorio).

Salida: datos/interim/catalogo_usgs.csv (mismas columnas que el catálogo SGC unificado)
"""
import sys

import numpy as np
import pandas as pd

from utils import C, CAT_USGS, asegurar_carpetas, aviso, info, ok, rel, titulo

titulo("01 · Catálogo USGS (validación cruzada, opcional)")
asegurar_carpetas()
solo_usgs = "--solo-usgs" in sys.argv

archivos = sorted(C.RAW_USGS.glob("*.csv"))
if not archivos:
    import requests
    ini, fin = pd.Timestamp(C.FECHA_INICIO), pd.Timestamp(C.FECHA_FIN)
    info(f"Descargando de {C.URL_USGS_API} ({ini.year}–{fin.year}) …")
    for anio in range(ini.year, fin.year + 1):
        params = dict(format="csv", starttime=max(ini, pd.Timestamp(f"{anio}-01-01")).date().isoformat(),
                      endtime=min(fin + pd.Timedelta(days=1), pd.Timestamp(f"{anio + 1}-01-01")).date().isoformat(),
                      minlatitude=C.BBOX["lat_min"], maxlatitude=C.BBOX["lat_max"],
                      minlongitude=C.BBOX["lon_min"], maxlongitude=C.BBOX["lon_max"], orderby="time-asc")
        try:
            r = requests.get(C.URL_USGS_API, params=params, timeout=90)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            aviso(f"No pude descargar el USGS ({e.__class__.__name__}: {str(e)[:120]}).")
            aviso("Sigue sin USGS: es opcional. Para usarlo, guarda el CSV a mano en datos/raw/usgs/ (ver README §2.2).")
            sys.exit(1 if solo_usgs else 0)
        destino = C.RAW_USGS / f"usgs_{anio}.csv"
        destino.write_text(r.text, encoding="utf-8")
        info(f"{anio}: {max(0, r.text.count(chr(10)) - 1)} eventos")
    archivos = sorted(C.RAW_USGS.glob("*.csv"))

partes = [pd.read_csv(f) for f in archivos]
u = pd.concat([p for p in partes if len(p)], ignore_index=True) if partes else pd.DataFrame()
if u.empty:
    aviso("Los CSV del USGS están vacíos.")
    sys.exit(1 if solo_usgs else 0)

out = pd.DataFrame({
    "id_evento": "USGS-" + u["id"].astype(str),
    "fecha_utc": pd.to_datetime(u["time"], utc=True).dt.tz_localize(None),
    "lat": u["latitude"], "lon": u["longitude"], "prof_km": u["depth"],
    "mag": u["mag"], "mag_tipo": u["magType"].astype(str).str.upper().str.startswith("MW").map(
        {True: "Mw", False: "ML"}),
    "mag_tipo_original": u["magType"], "fases": u.get("nst"), "rms_s": u.get("rms"),
    "gap_grados": u.get("gap"), "err_lat_km": u.get("horizontalError"),
    "err_lon_km": u.get("horizontalError"), "err_prof_km": u.get("depthError"),
    "region": u.get("place"), "estado": u.get("status"),
})
out["revisado"] = out["estado"].astype(str).str.lower().eq("reviewed")
b = C.BBOX
out = out.dropna(subset=["fecha_utc", "lat", "lon", "mag", "prof_km"])
out = out[out.lat.between(b["lat_min"], b["lat_max"]) & out.lon.between(b["lon_min"], b["lon_max"])]
out = out.drop_duplicates("id_evento").sort_values("fecha_utc")
eh = out[["err_lat_km", "err_lon_km"]].max(axis=1)
out["mala_localizacion"] = ((out["gap_grados"] > C.GAP_MAX)
                            | ((out["rms_s"] > C.RMS_MAX_S) & (out["mag"] < C.RMS_EXENTO_DESDE_M))
                            | (eh > C.ERROR_H_MAX_KM) | (out["err_prof_km"] > C.ERROR_PROF_MAX_KM)).fillna(False)
out["archivo"] = "USGS ComCat"
out["formato"] = "USGS FDSN csv"
out.to_csv(CAT_USGS, index=False)
ok(f"{len(out):,} eventos USGS -> {rel(CAT_USGS)} (M {np.nanmin(out.mag):.1f}–{np.nanmax(out.mag):.1f})")
