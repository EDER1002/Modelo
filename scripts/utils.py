"""
Utilidades compartidas por los scripts del pipeline.

Cada script hace `from utils import *`-like imports explícitos de aquí. Este módulo agrega la raíz
del proyecto al path para poder leer `config.py` aunque el script se corra desde `scripts/`.
"""
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import config as C  # noqa: E402

R_TIERRA_KM = 6371.0088
CRS_COLOMBIA = "EPSG:9377"          # MAGNA-SIRGAS 2018 / Origen-Nacional (metros, áreas oficiales)

# Archivos intermedios que comparten los scripts
CAT_SGC = C.INTERIM / "catalogo_sgc_unificado.csv"
CAT_USGS = C.INTERIM / "catalogo_usgs.csv"
ARCHIVOS_SGC = C.INTERIM / "archivos_sgc.csv"
CAT_FUENTES = C.INTERIM / "catalogo_con_fuente.csv"
NIDO_JSON = C.INTERIM / "nido_centro.json"
HISTORICO = C.INTERIM / "sismicidad_historica.csv"
HISTORICO_META = C.INTERIM / "sismicidad_historica_meta.json"
POBLACION = C.INTERIM / "poblacion_municipios.csv"
POBLACION_META = C.INTERIM / "poblacion_meta.json"
MUNICIPIOS = C.PROCESSED / "municipios_santander.geojson"
CONTORNO = C.PROCESSED / "santander_contorno.geojson"
DATASET = C.PROCESSED / "dataset_municipios.csv"
DATASET_GEO = C.PROCESSED / "municipios_variables.geojson"
DICCIONARIO_CSV = C.DOCS / "diccionario_datos.csv"


# ----------------------------------------------------------------------------
# Mensajes en consola
# ----------------------------------------------------------------------------
def titulo(txt):
    print(f"\n{'=' * 72}\n{txt}\n{'=' * 72}", flush=True)


def info(txt):
    print(f"  · {txt}", flush=True)


def ok(txt):
    print(f"  ✓ {txt}", flush=True)


def aviso(txt):
    print(f"  ⚠ {txt}", flush=True)


def asegurar_carpetas():
    for p in (C.INTERIM, C.PROCESSED, C.SALIDAS, C.DOCS, C.RAW_SGC, C.RAW_USGS):
        p.mkdir(parents=True, exist_ok=True)


def escribir(ruta, texto):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


def rel(ruta):
    """Ruta relativa a la raíz del proyecto, para mostrar en reportes."""
    try:
        return Path(ruta).resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(ruta)


def tabla_md(df, index=False, floatfmt=".3g"):
    if df is None or len(df) == 0:
        return "_(sin datos)_"
    from tabulate import tabulate
    df = df.reset_index() if index else df.copy()
    celdas, alineacion = {}, []
    for c in df.columns:                      # formato por columna: los enteros no salen como 2020.0
        s = df[c]
        ff = floatfmt.get(c, ".3g") if isinstance(floatfmt, dict) else floatfmt
        if pd.api.types.is_bool_dtype(s):
            celdas[c] = s.map(lambda v: "sí" if v else "no")
            alineacion.append("left")
        elif pd.api.types.is_integer_dtype(s):
            celdas[c] = s.map(lambda v: "" if pd.isna(v) else f"{int(v)}")
            alineacion.append("right")
        elif pd.api.types.is_float_dtype(s):
            celdas[c] = s.map(lambda v: "" if pd.isna(v) else format(v, ff))
            alineacion.append("right")
        else:
            celdas[c] = s.map(lambda v: "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))
            alineacion.append("left")
    return tabulate(pd.DataFrame(celdas).values.tolist(), headers=[str(c) for c in df.columns],
                    tablefmt="pipe", disable_numparse=True, colalign=alineacion)


# ----------------------------------------------------------------------------
# Texto
# ----------------------------------------------------------------------------
def normalizar(txt):
    """Mayúsculas, sin tildes y con espacios simples (para reconocer columnas por su nombre)."""
    if txt is None or (isinstance(txt, float) and np.isnan(txt)):
        return ""
    s = unicodedata.normalize("NFKD", str(txt))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


_MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "e"}


def nombre_propio(txt):
    """'EL CARMEN DE CHUCURÍ' -> 'El Carmen de Chucurí'."""
    palabras = str(txt).strip().lower().split()
    out = []
    for i, p in enumerate(palabras):
        out.append(p if (i > 0 and p in _MINUSCULAS) else p[:1].upper() + p[1:])
    return " ".join(out)


# ----------------------------------------------------------------------------
# Lectura de tablas (Excel viejo/nuevo, HTML disfrazado de .xls, CSV)
# ----------------------------------------------------------------------------
def leer_tabla(ruta):
    """
    Devuelve {nombre_hoja: DataFrame sin encabezado (header=None)}.

    - .xlsx/.xls: primero `python-calamine`, que no falla con el ValueError de openpyxl
      "Colors must be aRGB hex values" que tienen los Excel exportados por el SGC.
    - .xls que en realidad es HTML (frecuente en exportaciones web antiguas): `pandas.read_html`.
    - .csv/.txt/.tsv: detecta separador y codificación.
    """
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    errores = []
    if ext in (".xlsx", ".xlsm", ".xls"):
        for engine in ("calamine", None):
            try:
                hojas = pd.read_excel(ruta, header=None, sheet_name=None, engine=engine)
                return {str(k): v for k, v in hojas.items()}
            except Exception as e:  # noqa: BLE001
                errores.append(f"read_excel({engine or 'por defecto'}): {e}")
        try:
            tablas = pd.read_html(ruta, header=None)
            return {f"html_{i}": t for i, t in enumerate(tablas)}
        except Exception as e:  # noqa: BLE001
            errores.append(f"read_html: {e}")
    elif ext in (".csv", ".txt", ".tsv"):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(ruta, header=None, sep=None, engine="python", encoding=enc,
                                 dtype=str, skip_blank_lines=False)
                return {"csv": df}
            except Exception as e:  # noqa: BLE001
                errores.append(f"read_csv({enc}): {e}")
    else:
        return {}
    raise ValueError(f"No pude leer {ruta.name}:\n    " + "\n    ".join(errores))


def fecha_creacion_xlsx(ruta):
    """Fecha de creación guardada por el portal dentro del .xlsx (docProps/core.xml), si existe."""
    try:
        with zipfile.ZipFile(ruta) as z:
            xml = z.read("docProps/core.xml").decode("utf-8", "ignore")
        m = re.search(r"<dcterms:created[^>]*>([^<]+)</dcterms:created>", xml)
        return m.group(1) if m else None
    except Exception:  # noqa: BLE001
        return None


def a_numero(s):
    """Convierte una columna a número aceptando coma decimal."""
    if s.dtype == object:
        s = s.astype(str).str.strip().str.replace(",", ".", regex=False)
        s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan, "-": np.nan})
    return pd.to_numeric(s, errors="coerce")


# ----------------------------------------------------------------------------
# Geografía
# ----------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia sobre la esfera (km). Acepta escalares o arreglos con broadcasting."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * R_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def matriz_distancias_km(lat_a, lon_a, lat_b, lon_b):
    """Matriz (len(a) x len(b)) de distancias epicentrales en km."""
    lat_a = np.asarray(lat_a, float)[:, None]
    lon_a = np.asarray(lon_a, float)[:, None]
    lat_b = np.asarray(lat_b, float)[None, :]
    lon_b = np.asarray(lon_b, float)[None, :]
    return haversine_km(lat_a, lon_a, lat_b, lon_b)


def proyectar_km(lat, lon):
    """Coordenadas planas en km (azimutal equidistante centrada en Santander)."""
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326",
                             "+proj=aeqd +lat_0=6.9 +lon_0=-73.4 +units=km +ellps=WGS84",
                             always_xy=True)
    x, y = t.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.asarray(x), np.asarray(y)


# ----------------------------------------------------------------------------
# Sismología
# ----------------------------------------------------------------------------
DM = 0.1  # resolución de magnitud del catálogo


def mc_maxima_curvatura(mag, correccion=0.2):
    """Magnitud de completitud: moda del histograma (máxima curvatura) + corrección (Wiemer y Wyss, 2000)."""
    m = np.round(np.asarray(mag, float)[~np.isnan(mag)] / DM) * DM
    if len(m) == 0:
        return np.nan
    valores, conteos = np.unique(np.round(m, 1), return_counts=True)
    return float(np.round(valores[np.argmax(conteos)] + correccion, 1))


def mc_homogeneo(df, min_eventos=50):
    """Mc por año y Mc homogéneo (el peor año) para que los conteos no dependan de la mejora de la red."""
    por_anio = {}
    for anio, g in df.groupby(df["fecha_utc"].dt.year):
        if len(g) >= min_eventos:
            por_anio[int(anio)] = mc_maxima_curvatura(g["mag"].to_numpy())
    if not por_anio:
        return mc_maxima_curvatura(df["mag"].to_numpy()), por_anio
    return float(max(por_anio.values())), por_anio


def valor_b(mag, mc):
    """Valor b por máxima verosimilitud (Aki, 1965; corrección de Utsu por bins de 0.1)."""
    m = np.asarray(mag, float)
    m = m[m >= mc - 1e-9]
    if len(m) < 2:
        return np.nan
    den = m.mean() - (mc - DM / 2)
    return float(np.log10(np.e) / den) if den > 0 else np.nan


def energia_joules(mag):
    """Energía sísmica liberada, log10 E = 1.5 M + 4.8 (Gutenberg-Richter, E en julios)."""
    return 10 ** (1.5 * np.asarray(mag, float) + 4.8)


# ----------------------------------------------------------------------------
# Catálogo y periodos
# ----------------------------------------------------------------------------
def fuente_desde_args(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--fuente", choices=["sgc", "usgs"], default="sgc")
    return p.parse_args(argv).fuente


def cargar_catalogo(fuente="sgc"):
    ruta = CAT_SGC if fuente == "sgc" else CAT_USGS
    if not ruta.exists():
        paso = "02_unificar_sgc.py" if fuente == "sgc" else "01_descargar_usgs.py"
        sys.exit(f"✗ Falta {rel(ruta)}. Corre primero scripts/{paso}.")
    df = pd.read_csv(ruta, parse_dates=["fecha_utc"], low_memory=False)
    if df.empty:
        sys.exit(f"✗ {rel(ruta)} está vacío.")
    return df


def filtrar_calidad(df):
    """Excluye sismos mal localizados (y, si se pide, los no revisados). La calidad es FILTRO, no variable."""
    m = pd.Series(True, index=df.index)
    if C.EXCLUIR_ATIPICOS and "mala_localizacion" in df:
        m &= ~df["mala_localizacion"].fillna(False).astype(bool)
    if C.SOLO_REVISADOS and "revisado" in df:
        m &= df["revisado"].fillna(False).astype(bool)
    return df[m].copy()


def limites(periodo):
    ini = pd.Timestamp(periodo[0])
    fin = pd.Timestamp(periodo[1]) + pd.Timedelta(days=1)   # fin inclusivo
    return ini, fin


def en_periodo(df, periodo):
    ini, fin = limites(periodo)
    return df[(df["fecha_utc"] >= ini) & (df["fecha_utc"] < fin)].copy()


def anios_periodo(periodo):
    ini, fin = limites(periodo)
    return (fin - ini).days / 365.25


def cobertura(df, periodo):
    """Fracción del periodo que cubren los datos (entre la primera y la última fecha del catálogo)."""
    ini, fin = limites(periodo)
    if df.empty:
        return 0.0
    a = max(ini, df["fecha_utc"].min())
    b = min(fin, df["fecha_utc"].max())
    return max(0.0, (b - a).days) / max(1, (fin - ini).days)


def periodos_efectivos(df):
    """
    Periodos de variables y de objetivo que realmente se usan.

    Si los datos cubren (>= 90 %) los periodos de config.py, se usan tal cual. Si no (p. ej. solo hay
    exports 2020–2025) y AJUSTAR_PERIODOS_A_DATOS = True, se parte el rango disponible: el último
    FRACCION_OBJETIVO del tiempo es el objetivo y lo anterior son las variables (corte al inicio de mes).
    Así basta con meter más Excel en datos/raw/sgc/ y volver a correr: no hay que tocar el código.
    """
    pv, po = tuple(C.PERIODO_VARIABLES), tuple(C.PERIODO_OBJETIVO)
    cub_v, cub_o = cobertura(df, pv), cobertura(df, po)
    res = dict(variables=pv, objetivo=po, ajustado=False, cobertura_config=(round(cub_v, 3), round(cub_o, 3)))
    if (cub_v >= 0.9 and cub_o >= 0.9) or not getattr(C, "AJUSTAR_PERIODOS_A_DATOS", True):
        return res
    d0 = df["fecha_utc"].min().normalize()
    d1 = df["fecha_utc"].max().normalize()
    corte = d0 + (d1 - d0) * (1 - getattr(C, "FRACCION_OBJETIVO", 0.4))
    corte = (corte + pd.Timedelta(days=15)).to_period("M").to_timestamp()   # inicio de mes más cercano
    res.update(variables=(d0.date().isoformat(), (corte - pd.Timedelta(days=1)).date().isoformat()),
               objetivo=(corte.date().isoformat(), d1.date().isoformat()), ajustado=True)
    return res


def leer_json(ruta, defecto=None):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return defecto


def escribir_json(ruta, obj):
    escribir(ruta, json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cargar_municipios():
    import geopandas as gpd
    if not MUNICIPIOS.exists():
        sys.exit(f"✗ Falta {rel(MUNICIPIOS)}. Corre primero scripts/00_preparar_territorio.py.")
    g = gpd.read_file(MUNICIPIOS)
    g["cod_mpio"] = g["cod_mpio"].astype(str).str.zfill(5)
    return g


# ----------------------------------------------------------------------------
# Paleta (validada con el validador de daltonismo; ver docs)
# ----------------------------------------------------------------------------
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_SUAVE = "#898781"
REJILLA = "#e1e0d9"
EJE = "#c3c2b7"
FONDO = "#fcfcfb"
GRIS_NEUTRO = "#f0efec"

# Tipos de fuente sísmica (categórico, 3 colores validados "todos contra todos" + gris para difusa)
COLOR_TIPO_FUENTE = {
    "Nido de Bucaramanga": "#2a78d6",
    "Cortical": "#eb6834",
    "Intermedia": "#1baf7a",
    "Difusa (ruido)": "#b9b7b0",
}

# Niveles de amenaza/riesgo relativo: rampa ordinal de un solo tono (azul), validada
RAMPA_NIVELES = {
    2: ["#86b6ef", "#1c5cab"],
    3: ["#86b6ef", "#2a78d6", "#0d366b"],
    4: ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
    5: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"],
}
NOMBRES_NIVELES = {
    2: ["Bajo", "Alto"],
    3: ["Bajo", "Medio", "Alto"],
    4: ["Bajo", "Medio", "Alto", "Muy alto"],
    5: ["Muy bajo", "Bajo", "Medio", "Alto", "Muy alto"],
}


def estilo_figuras():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO,
        "axes.edgecolor": EJE, "axes.linewidth": 0.8, "axes.labelcolor": TINTA_2,
        "axes.titlecolor": TINTA, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.labelsize": 10, "xtick.color": TINTA_SUAVE, "ytick.color": TINTA_SUAVE,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.grid": True, "grid.color": REJILLA,
        "grid.linewidth": 0.6, "grid.linestyle": "-", "axes.spines.top": False,
        "axes.spines.right": False, "legend.frameon": False, "legend.fontsize": 9,
        "font.family": "sans-serif", "text.color": TINTA, "figure.dpi": 110, "savefig.dpi": 160,
        "savefig.bbox": "tight",
    })
    return plt
