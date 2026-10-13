"""
Configuración central del proyecto: Riesgo sísmico de Santander (Hackathon, categoría Medio).

Todos los scripts leen sus parámetros de aquí. Si cambias la zona, las fechas o los radios,
vuelve a correr `python run_all.py` y todo se regenera.
"""
from pathlib import Path

# ----------------------------------------------------------------------------
# Rutas
# ----------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "datos"
RAW = DATOS / "raw"
RAW_SGC = RAW / "sgc"                    # exports del catálogo SGC (los pones tú)
RAW_USGS = RAW / "usgs"                  # se llena con 01_descargar_usgs.py
RAW_DANE = RAW / "dane"                  # MGN 2018 (incluido) + proyecciones de población (opcional)
RAW_HISTORICO = RAW / "sgc_historico"    # sismicidad_historica.xls (incluido)
INTERIM = DATOS / "interim"
PROCESSED = DATOS / "processed"
SALIDAS = RAIZ / "salidas"
DOCS = RAIZ / "docs"

# ----------------------------------------------------------------------------
# Zona de estudio
# ----------------------------------------------------------------------------
COD_DEPTO = "68"                         # Santander (código DANE)
NOMBRE_DEPTO = "Santander"

# Caja de descarga: Santander (lat 5.71–8.15, lon −74.53 a −72.48) + ~50 km de margen,
# para que los municipios de borde también "vean" los sismos cercanos.
BBOX = dict(lat_min=5.2, lat_max=8.7, lon_min=-75.0, lon_max=-72.0)

# Zona foco que se compara contra el resto de Santander:
# Área Metropolitana de Bucaramanga + Mesa de Los Santos (encima del Nido Sísmico).
ZONA_FOCO = {
    "68001": "Bucaramanga",
    "68276": "Floridablanca",
    "68307": "Girón",
    "68547": "Piedecuesta",
    "68418": "Los Santos",
}

# ----------------------------------------------------------------------------
# Periodos
# ----------------------------------------------------------------------------
# Tema de referencia del reto: últimos 20 años -> 20 años completos.
FECHA_INICIO = "2006-01-01"
FECHA_FIN = "2025-12-31"

# Validación temporal: las variables se calculan con 2006–2020 y la variable objetivo
# con 2021–2025. Así la variable objetivo NO se calcula a partir de las variables de
# entrada (son observaciones distintas) y además sirve para mostrar capacidad de anticipar.
PERIODO_VARIABLES = ("2006-01-01", "2020-12-31")
PERIODO_OBJETIVO = ("2021-01-01", "2025-12-31")
# Si los exports de datos/raw/sgc/ no cubren esos periodos (p. ej. solo 2020-03 a 2025-03), el pipeline
# parte el rango que SÍ hay: el último 40 % del tiempo es el objetivo y lo anterior las variables
# (siguen sin solaparse). Cuando metas los Excel 2006–2025, vuelve solo a los periodos de arriba.
# Los periodos usados quedan escritos en el reporte. Pon False para obligar los de arriba.
AJUSTAR_PERIODOS_A_DATOS = True
FRACCION_OBJETIVO = 0.4

# ----------------------------------------------------------------------------
# Metadatos de origen (LLENAR: la rúbrica exige fecha de descarga y filtros)
# ----------------------------------------------------------------------------
FECHA_DESCARGA_SGC = "2026-10-13"  # Csg_2020…Csg_2024.xlsx (fecha de creación que trae cada .xlsx)
FECHA_DESCARGA_HISTORICO = None    # fecha en que bajaste sismicidad_historica.xls
FECHA_DESCARGA_POBLACION = None    # fecha en que bajaste el Excel de población DANE

URL_SGC_CATALOGO = "http://bdrsnc.sgc.gov.co/paginas1/catalogo/"
URL_SGC_HISTORICO = "https://sish.sgc.gov.co/visor/"
URL_USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
URL_DANE_MGN = "https://geoportal.dane.gov.co/servicios/descarga-y-metadatos/descarga-mgn-marco-geoestadistico-nacional/"
URL_DANE_MGN_ESPEJO = "https://github.com/caticoa3/colombia_mapa"
URL_DANE_POBLACION = "https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion"
ANIO_POBLACION = 2020              # año de población que se usa (último del periodo de variables)

# ----------------------------------------------------------------------------
# Limpieza
# ----------------------------------------------------------------------------
MAG_VALIDA = (-1.0, 9.5)           # fuera de este rango = registro inválido
PROF_MAX_VALIDA_KM = 300.0         # el slab bajo Santander no pasa de ~200 km
# Calidad de localización: Fases, RMS, Gap y errores NO entran al modelo (describen la red de
# estaciones, no la amenaza); se usan para marcar sismos mal localizados (~10 % en 2024).
GAP_MAX = 270                      # brecha azimutal (°) mayor = epicentro mal restringido
RMS_MAX_S = 1.2                    # residuo medio (s)
RMS_EXENTO_DESDE_M = 3.0           # el criterio de RMS no se aplica a M >= 3: los sismos grandes los registran
                                   # estaciones lejanas y su RMS sube aunque estén bien localizados (en 2020–2025,
                                   # 33 % de los M >= 4 tenía RMS > 1.2 s con error de profundidad mediano de 4 km)
ERROR_H_MAX_KM = 10.0              # error horizontal (máx. de lat/long)
ERROR_PROF_MAX_KM = 10.0           # error de profundidad
FASES_MIN = 6                      # mínimo de fases usadas en la localización
EXCLUIR_ATIPICOS = True            # excluir atípicos al construir variables
SOLO_REVISADOS = False             # True = usar solo eventos con estado "revisado"
VENTANA_DUPLICADO_S = 3.0          # dos registros a <= 3 s y <= 10 km = mismo sismo
DIST_DUPLICADO_KM = 10.0

# ----------------------------------------------------------------------------
# Variables
# ----------------------------------------------------------------------------
RADIO_INFLUENCIA_KM = 30           # vecindario de cada municipio (centroide + 30 km)
RADIO_OBJETIVO_KM = 50             # radio para la variable objetivo
RADIO_HISTORICO_KM = 100           # radio para sismos históricos con daño
MAG_FUERTE = 4.0                   # umbral de sismo "fuerte" (sentido ampliamente)
PROF_SUPERFICIAL_KM = 30           # corteza superior: los más dañinos
PROF_INTERMEDIA_KM = 70            # desde aquí: sismicidad intermedia (Nido ~150 km)
MIN_EVENTOS_B = 50                 # mínimo de eventos para estimar el valor b
NIDO_REFERENCIA = dict(lat=6.8, lon=-73.1, prof_km=150.0)  # Prieto et al. (2012)

# ----------------------------------------------------------------------------
# Nivel 1 · Fuentes sísmicas con HDBSCAN (una fila = un sismo)
# ----------------------------------------------------------------------------
HDBSCAN_MAX_EVENTOS = 40000        # muestra para ajustar (el resto se asigna por vecino más cercano)
HDBSCAN_MIN_FRAC = 0.005           # tamaño mínimo de una fuente = 0.5 % de los sismos (mín. 50)
HDBSCAN_MIN_SAMPLES = 10           # robustez frente a sismos aislados
RADIO_NIDO_KM = 40                 # una fuente cuyo centro está a <= 40 km del Nido y ~110–190 km
                                   # de profundidad se etiqueta como "Nido"

# ----------------------------------------------------------------------------
# Nivel 2 · Modelo por municipio
# ----------------------------------------------------------------------------
SEMILLA = 42
K_MIN, K_MAX = 2, 8                # rango de grupos a evaluar
K_SELECCION = (3, 5)               # rango permitido para el modelo final (interpretable; máx. 5 niveles:
                                   # con 6 tonos de un mismo color dos niveles vecinos no se distinguen en el mapa)
N_BOOTSTRAP = 30                   # remuestreos para medir estabilidad de los grupos
