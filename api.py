"""
API REST del modelo de riesgo sísmico de Santander (FastAPI).

Sirve el modelo ya entrenado (modelo/modelo_kmeans.json) y sus resultados (salidas/) para que una aplicación
web, un dashboard o cualquier cliente HTTP los consuma. No re-entrena nada: para actualizar con datos nuevos se
corre `python run_all.py` y se reinicia la API.

Arrancar:
    pip install -r requirements-api.txt        # solo fastapi, uvicorn, pandas y numpy
    python api.py                              # http://localhost:8000  (o: uvicorn api:app --reload)

Documentación interactiva (probar cada endpoint desde el navegador):
    http://localhost:8000/docs
Contrato de la API con ejemplos: API.md
"""
import json
import os
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from usar_modelo import ModeloSismico, _norm

RAIZ = Path(__file__).resolve().parent
SALIDAS = RAIZ / "salidas"
modelo = ModeloSismico(RAIZ)
NIVELES = modelo.niveles                                   # de menor a mayor amenaza
COLORES = modelo.modelo["colores_niveles"]


def _leer(nombre, **kw):
    ruta = SALIDAS / nombre
    return pd.read_csv(ruta, **kw) if ruta.exists() else pd.DataFrame()


def _registros(df):
    """DataFrame -> lista de dicts JSON (NaN -> null)."""
    return json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))


TABLA = modelo.tabla().copy()
TABLA["nivel_orden"] = TABLA["nivel"].map({n: i + 1 for i, n in enumerate(NIVELES)})
TABLA["color"] = TABLA["nivel"].map(COLORES)
TABLA["zona_foco"] = TABLA["zona_foco"].astype(str).str.lower() == "true"
_mun = pd.read_csv(RAIZ / "datos" / "processed" / "municipios_santander.csv", dtype={"cod_mpio": str})
TABLA = TABLA.merge(_mun[["cod_mpio", "lat", "lon", "area_km2"]], on="cod_mpio", how="left")
FUENTES = _leer("fuentes_sismicas.csv")
SISMOS = _leer("sismos_relevantes.csv", dtype={"cod_mpio": str}, parse_dates=["fecha_utc"])
VALIDACION = _leer("validacion_temporal.csv")
COMPARACION = _leer("comparacion_modelos.csv")
IMPORTANCIA = _leer("importancia_variables.csv")
GEOJSON = json.loads((SALIDAS / "municipios_niveles.geojson").read_text(encoding="utf-8")) \
    if (SALIDAS / "municipios_niveles.geojson").exists() else None
CLAVE = ["tasa_sismos_r30", "tasa_m3_r30", "tasa_fuertes_r30", "mag_max_r30", "log_energia_anual_r30",
         "log_flujo_energia_hipo", "prof_mediana_r30", "frac_superficiales_r30", "dist_nido_km",
         "indice_riesgo", "obj_tasa_fuertes_futura_r50"]
CLAVE = [c for c in CLAVE if c in TABLA.columns]
RESUMEN_COLS = ["cod_mpio", "municipio", "nivel", "nivel_orden", "color", "indice_riesgo", "zona_foco", "lat", "lon"]

app = FastAPI(
    title="API · Riesgo sísmico relativo de Santander",
    version="1.0.0",
    description=(
        "Clasificación no supervisada (HDBSCAN para fuentes sísmicas + K-Means por municipio) de los 87 municipios "
        "de Santander con el catálogo sísmico del Servicio Geológico Colombiano. "
        f"Modelo: K-Means k={modelo.modelo['k']} sobre {len(modelo.variables)} variables · variables "
        f"{modelo.modelo['periodo_variables'][0]} a {modelo.modelo['periodo_variables'][1]} · validación "
        f"{modelo.modelo['periodo_objetivo'][0]} a {modelo.modelo['periodo_objetivo'][1]}. "
        "Todas las respuestas son JSON salvo /mapa (HTML) y /salidas/* (archivos)."),
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/salidas", StaticFiles(directory=SALIDAS), name="salidas")


def _municipio_o_404(id_municipio):
    try:
        return modelo.consultar(id_municipio)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------- general
@app.get("/", tags=["general"], summary="Bienvenida y lista de endpoints")
def raiz():
    return {
        "api": app.title, "version": app.version, "documentacion": "/docs",
        "endpoints": {
            "/modelo": "resumen, métricas y validación del modelo",
            "/niveles": "los niveles con su color y sus municipios",
            "/municipios": "los 87 municipios (filtros: nivel, zona_foco)",
            "/municipios/{nombre_o_codigo}": "ficha completa de un municipio",
            "/comparar?municipios=A,B": "comparación lado a lado",
            "/zona-foco": "AMB + Los Santos vs resto de Santander",
            "/geojson": "polígonos con nivel y color para pintar el mapa",
            "/fuentes": "fuentes sísmicas encontradas por HDBSCAN",
            "/sismos": "sismos M >= 3 (filtros: mag_min, periodo, fuente_tipo, municipio)",
            "/variables": "diccionario de datos",
            "/validacion": "validación temporal por nivel",
            "/comparacion-modelos": "métricas de los 6 métodos comparados",
            "/clasificar (POST)": "clasifica filas nuevas con las variables del modelo",
            "/mapa": "mapa interactivo HTML (para un iframe)",
            "/salidas/{archivo}": "figuras PNG, reporte y CSV",
        },
    }


@app.get("/salud", tags=["general"], summary="Estado de la API")
def salud():
    return {"estado": "ok", "municipios": len(TABLA), "modelo_generado": modelo.modelo["generado"]}


@app.get("/modelo", tags=["modelo"], summary="Resumen y métricas del modelo")
def info_modelo():
    m = modelo.modelo
    return {
        "algoritmo": "K-Means (nivel 2, por municipio) sobre fuentes HDBSCAN (nivel 1, por sismo)",
        "k": m["k"], "niveles": NIVELES, "colores": COLORES,
        "variables": m["variables"], "n_variables": len(m["variables"]),
        "catalogo": m["catalogo"], "periodo_variables": m["periodo_variables"],
        "periodo_objetivo": m["periodo_objetivo"], "periodos_ajustados_a_datos": m["periodos_ajustados_a_datos"],
        "magnitud_completitud": m["mc"], "radio_influencia_km": m["radio_influencia_km"],
        "metricas": {"silueta": m["silueta"], "estabilidad_bootstrap_ari": m["estabilidad_ari"],
                     "spearman_nivel_vs_objetivo": m["spearman_validacion"]},
        "municipios_por_nivel": TABLA["nivel"].value_counts().reindex(NIVELES).fillna(0).astype(int).to_dict(),
        "generado": m["generado"],
        "fuentes_de_datos": "ver docs/metadatos_origen.md (URL, fecha de descarga y filtros de cada fuente)",
    }


# ---------------------------------------------------------------------------- municipios
@app.get("/niveles", tags=["municipios"], summary="Niveles de amenaza/riesgo relativo con sus municipios")
def niveles():
    out = []
    for i, n in enumerate(NIVELES):
        t = TABLA[TABLA["nivel"] == n].sort_values("indice_riesgo", ascending=False)
        out.append({"nivel": n, "orden": i + 1, "color": COLORES[n], "n_municipios": len(t),
                    "indice_medio": round(float(t["indice_riesgo"].mean()), 1) if len(t) else None,
                    "municipios": t["municipio"].tolist()})
    return out[::-1]


@app.get("/municipios", tags=["municipios"], summary="Lista de municipios con su nivel")
def municipios(
    nivel: str | None = Query(None, description=f"Uno de: {', '.join(NIVELES)}"),
    zona_foco: bool | None = Query(None, description="true = solo AMB + Los Santos"),
    completo: bool = Query(False, description="true = incluir todas las variables del modelo"),
):
    t = TABLA
    if nivel is not None:
        n = {_norm(x): x for x in NIVELES}.get(_norm(nivel))
        if n is None:
            raise HTTPException(400, f"Nivel '{nivel}' no existe. Niveles: {', '.join(NIVELES)}")
        t = t[t["nivel"] == n]
    if zona_foco is not None:
        t = t[t["zona_foco"] == zona_foco]
    cols = RESUMEN_COLS + (modelo.variables + ["obj_tasa_fuertes_futura_r50", "nivel_segun_indice"] if completo else
                           [c for c in CLAVE if c not in RESUMEN_COLS])
    return _registros(t.sort_values(["nivel_orden", "indice_riesgo"], ascending=False)[cols])


@app.get("/municipios/{nombre_o_codigo}", tags=["municipios"], summary="Ficha de un municipio")
def ficha(nombre_o_codigo: str):
    r = _municipio_o_404(nombre_o_codigo)
    fila = TABLA[TABLA["cod_mpio"] == r["cod_mpio"]].iloc[0]
    r.update(color=COLORES[r["nivel"]], lat=float(fila["lat"]), lon=float(fila["lon"]),
             area_km2=float(fila["area_km2"]),
             perfil_mixto=bool(r.get("nivel_segun_indice") and r["nivel_segun_indice"] != r["nivel"]))
    if len(SISMOS):
        s = SISMOS[SISMOS["cod_mpio"] == r["cod_mpio"]]
        r["sismos_m3_con_epicentro_en_el_municipio"] = int(len(s))
    return r


@app.get("/comparar", tags=["municipios"], summary="Compara municipios lado a lado")
def comparar(municipios: str = Query(..., description="Nombres o códigos separados por coma, p. ej. Bucaramanga,Girón")):
    ids = [x.strip() for x in municipios.split(",") if x.strip()]
    if len(ids) < 2:
        raise HTTPException(400, "Indica al menos 2 municipios separados por coma.")
    filas = [_municipio_o_404(i) for i in ids]
    return {
        "municipios": [{"municipio": f["municipio"], "cod_mpio": f["cod_mpio"], "nivel": f["nivel"],
                        "color": COLORES[f["nivel"]], "indice_riesgo": f["indice_riesgo"]} for f in filas],
        "variables": {v: {f["municipio"]: f["variables"][v] for f in filas} for v in modelo.variables},
        "descripcion_variables": {v: modelo._desc.get(v, "") for v in modelo.variables},
    }


@app.get("/zona-foco", tags=["municipios"], summary="Zona foco (AMB + Los Santos) vs resto de Santander")
def zona_foco():
    foco, resto = TABLA[TABLA["zona_foco"]], TABLA[~TABLA["zona_foco"]]
    comp = [{"variable": v, "descripcion": modelo._desc.get(v, ""),
             "zona_foco_media": round(float(foco[v].mean()), 4), "resto_media": round(float(resto[v].mean()), 4)}
            for v in CLAVE]
    return {
        "zona_foco": _registros(foco.sort_values("indice_riesgo", ascending=False)[RESUMEN_COLS]),
        "distribucion_niveles": {
            "zona_foco": foco["nivel"].value_counts().reindex(NIVELES).fillna(0).astype(int).to_dict(),
            "resto": resto["nivel"].value_counts().reindex(NIVELES).fillna(0).astype(int).to_dict()},
        "comparacion": comp,
    }


@app.get("/geojson", tags=["mapa"], summary="GeoJSON de los 87 municipios con nivel, color e índice")
def geojson():
    if GEOJSON is None:
        raise HTTPException(503, "Falta salidas/municipios_niveles.geojson: corre python run_all.py")
    return GEOJSON


@app.get("/mapa", tags=["mapa"], summary="Mapa interactivo (HTML, para abrir o poner en un iframe)",
         response_class=HTMLResponse)
def mapa():
    return FileResponse(SALIDAS / "mapa_riesgo_santander.html", media_type="text/html")


# ---------------------------------------------------------------------------- sismicidad
@app.get("/fuentes", tags=["sismicidad"], summary="Fuentes sísmicas encontradas por HDBSCAN (nivel 1)")
def fuentes():
    return _registros(FUENTES)


@app.get("/sismos", tags=["sismicidad"], summary="Sismos M ≥ 3 bien localizados (catálogo SGC)")
def sismos(
    mag_min: float = Query(4.0, ge=3.0, le=9.0, description="Magnitud mínima (≥ 3)"),
    periodo: Literal["variables", "objetivo", "todos"] = Query("todos"),
    fuente_tipo: str | None = Query(None, description="Nido de Bucaramanga, Cortical, Intermedia o Difusa (ruido)"),
    municipio: str | None = Query(None, description="Nombre o código: sismos con epicentro en ese municipio"),
    limite: int = Query(2000, ge=1, le=20000),
):
    if SISMOS.empty:
        raise HTTPException(503, "Falta salidas/sismos_relevantes.csv: corre python run_all.py")
    s = SISMOS[SISMOS["mag"] >= mag_min]
    if periodo != "todos":
        s = s[s["periodo"] == periodo]
    if fuente_tipo:
        s = s[s["fuente_tipo"].map(_norm) == _norm(fuente_tipo)]
    if municipio:
        s = s[s["cod_mpio"] == _municipio_o_404(municipio)["cod_mpio"]]
    s = s.sort_values("fecha_utc", ascending=False).head(limite)
    return {"total": int(len(s)), "sismos": _registros(s)}


# ---------------------------------------------------------------------------- modelo y datos
@app.get("/variables", tags=["modelo"], summary="Diccionario de datos")
def variables():
    d = modelo.diccionario.drop(columns=[c for c in ("mín", "mediana", "máx") if c in modelo.diccionario], errors="ignore")
    return _registros(d)


@app.get("/validacion", tags=["modelo"], summary="Validación temporal por nivel (periodo objetivo)")
def validacion():
    return {"periodo_objetivo": modelo.modelo["periodo_objetivo"],
            "spearman_nivel_vs_objetivo": modelo.modelo["spearman_validacion"],
            "descripcion": "Sismos M ≥ 4 por año a ≤ 50 km en un periodo POSTERIOR al usado para entrenar.",
            "por_nivel": _registros(VALIDACION)}


@app.get("/comparacion-modelos", tags=["modelo"], summary="Métricas de los métodos comparados")
def comparacion_modelos():
    return {"comparacion": _registros(COMPARACION), "importancia_variables": _registros(IMPORTANCIA)}


class FilasEntrada(BaseModel):
    filas: list[dict[str, float | None]] = Field(
        ..., description="Cada fila con las variables del modelo (ver GET /modelo → variables), en sus unidades "
                         "originales. Las que falten se rellenan con la mediana de Santander.")


@app.post("/clasificar", tags=["modelo"], summary="Clasifica filas nuevas (escenarios o datos recalculados)")
def clasificar(entrada: FilasEntrada):
    if not entrada.filas:
        raise HTTPException(400, "Envía al menos una fila.")
    df = pd.DataFrame(entrada.filas)
    faltantes = [v for v in modelo.variables if v not in df.columns]
    for v in faltantes:
        df[v] = np.nan
    out = modelo.clasificar(df)
    return {"variables_rellenadas_con_mediana": faltantes,
            "resultados": [{"nivel": n, "color": COLORES[n], "distancia_centroide": float(d)}
                           for n, d in zip(out["nivel_modelo"], out["distancia_centroide"])]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
