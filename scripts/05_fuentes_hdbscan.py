"""
Paso 05 · NIVEL 1 · Fuentes sísmicas con HDBSCAN (una fila = un sismo).

Agrupa los sismos por densidad usando SOLO su posición (x, y en km y profundidad en km; las tres en
la misma unidad, así la distancia es física). HDBSCAN no necesita que le digas cuántos grupos hay y
deja aparte la sismicidad difusa (ruido). Se compara con K-Means y DBSCAN.

Se ajusta con el periodo de VARIABLES (sin mirar el periodo objetivo); los demás sismos se asignan a
la fuente de sus vecinos más cercanos.

Salidas: datos/interim/catalogo_con_fuente.csv, datos/interim/nido_centro.json,
         salidas/fuentes_sismicas.csv, salidas/comparacion_fuentes.csv, salidas/fig_fuentes_sismicas.png
"""
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, HDBSCAN, KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.neighbors import KNeighborsClassifier, NearestNeighbors

from utils import (CAT_FUENTES, COLOR_TIPO_FUENTE, CONTORNO, NIDO_JSON, C, TINTA, TINTA_2, TINTA_SUAVE,
                   asegurar_carpetas, aviso, cargar_catalogo, cargar_municipios, en_periodo, escribir_json,
                   estilo_figuras, filtrar_calidad, fuente_desde_args, haversine_km, info, ok,
                   periodos_efectivos, proyectar_km, rel, titulo)

titulo("05 · Nivel 1 · Fuentes sísmicas con HDBSCAN (una fila = un sismo)")
asegurar_carpetas()
fuente = fuente_desde_args()
cat_todo = cargar_catalogo(fuente)
per = periodos_efectivos(cat_todo)
cat = filtrar_calidad(cat_todo)
x, y = proyectar_km(cat["lat"], cat["lon"])
cat["x_km"], cat["y_km"] = x, y
X_todo = cat[["x_km", "y_km", "prof_km"]].to_numpy()

ajuste = en_periodo(cat, per["variables"])
info(f"Catálogo {fuente.upper()}: {len(cat):,} sismos bien localizados; ajuste con el periodo de variables "
     f"{per['variables'][0]} a {per['variables'][1]}: {len(ajuste):,} sismos")
rng = np.random.default_rng(C.SEMILLA)
if len(ajuste) > C.HDBSCAN_MAX_EVENTOS:
    ajuste = ajuste.loc[rng.choice(ajuste.index, C.HDBSCAN_MAX_EVENTOS, replace=False)]
    info(f"Muestra de {C.HDBSCAN_MAX_EVENTOS:,} para ajustar (el resto se asigna por vecinos)")
Xa = ajuste[["x_km", "y_km", "prof_km"]].to_numpy()
min_cluster = max(50, int(C.HDBSCAN_MIN_FRAC * len(Xa)))

# ----------------------------------------------------------------------------
# HDBSCAN
# ----------------------------------------------------------------------------
hdb = HDBSCAN(min_cluster_size=min_cluster, min_samples=C.HDBSCAN_MIN_SAMPLES, copy=True).fit(Xa)
lab_a = hdb.labels_
info(f"HDBSCAN (min_cluster_size={min_cluster}, min_samples={C.HDBSCAN_MIN_SAMPLES}): "
     f"{lab_a.max() + 1} fuentes, {np.mean(lab_a == -1):.1%} difusa")

# Asignar TODOS los sismos (los de la muestra conservan su etiqueta)
knn = KNeighborsClassifier(n_neighbors=15, weights="distance").fit(Xa, lab_a)
cat["fuente_id"] = knn.predict(X_todo)
cat.loc[ajuste.index, "fuente_id"] = lab_a
cat["asignacion"] = "vecinos más cercanos"
cat.loc[ajuste.index, "asignacion"] = "ajuste HDBSCAN"
cat["prob_fuente"] = np.nan
cat.loc[ajuste.index, "prob_fuente"] = hdb.probabilities_

# ----------------------------------------------------------------------------
# Describir y nombrar las fuentes
# ----------------------------------------------------------------------------
mun = cargar_municipios()
ref = C.NIDO_REFERENCIA
desc = []
base = cat.loc[ajuste.index]
for k in sorted(set(lab_a) - {-1}):
    g = base[base["fuente_id"] == k]
    lat, lon, z = g["lat"].median(), g["lon"].median(), g["prof_km"].median()
    d_nido = float(haversine_km(lat, lon, ref["lat"], ref["lon"]))
    if d_nido <= C.RADIO_NIDO_KM and 110 <= z <= 190:
        tipo = "Nido de Bucaramanga"
    elif z < C.PROF_INTERMEDIA_KM:
        tipo = "Cortical"
    else:
        tipo = "Intermedia"
    i_cerca = int(np.argmin(haversine_km(lat, lon, mun["lat"].to_numpy(), mun["lon"].to_numpy())))
    desc.append(dict(fuente_id=int(k), tipo=tipo, n_sismos=len(g), lat=round(lat, 3), lon=round(lon, 3),
                     prof_mediana_km=round(z, 1), prof_p10_km=round(g["prof_km"].quantile(0.1), 1),
                     prof_p90_km=round(g["prof_km"].quantile(0.9), 1),
                     radio_p90_km=round(float(np.quantile(np.hypot(g["x_km"] - g["x_km"].median(),
                                                                   g["y_km"] - g["y_km"].median()), 0.9)), 1),
                     mag_max=g["mag"].max(), n_m4=int((g["mag"] >= C.MAG_FUERTE).sum()),
                     dist_nido_ref_km=round(d_nido, 1), municipio_cercano=mun["municipio"].iat[i_cerca]))
desc = pd.DataFrame(desc).sort_values("n_sismos", ascending=False).reset_index(drop=True)
desc["codigo"] = [f"F{i + 1}" for i in range(len(desc))]
desc["fuente"] = desc["codigo"] + " · " + desc["tipo"] + " (" + desc["municipio_cercano"] + ")"
desc["frac_sismos"] = (desc["n_sismos"] / len(base)).round(4)
n_ruido = int((base["fuente_id"] == -1).sum())

nombre = dict(zip(desc["fuente_id"], desc["fuente"]))
tipo = dict(zip(desc["fuente_id"], desc["tipo"]))
codigo = dict(zip(desc["fuente_id"], desc["codigo"]))
cat["fuente"] = cat["fuente_id"].map(nombre).fillna("Difusa (ruido)")
cat["fuente_tipo"] = cat["fuente_id"].map(tipo).fillna("Difusa (ruido)")
cat["fuente_codigo"] = cat["fuente_id"].map(codigo).fillna("F0")
base = cat.loc[ajuste.index]

# Centro del Nido: mediana de los sismos de las fuentes tipo Nido (si no aparece, la referencia)
nido = base[base["fuente_tipo"] == "Nido de Bucaramanga"]
if len(nido):
    centro = dict(lat=round(float(nido["lat"].median()), 4), lon=round(float(nido["lon"].median()), 4),
                  prof_km=round(float(nido["prof_km"].median()), 1), n_sismos=int(len(nido)),
                  origen="HDBSCAN (mediana de los sismos de la fuente Nido)")
else:
    centro = dict(**ref, n_sismos=0, origen="Referencia Prieto et al. (2012): HDBSCAN no aisló el Nido")
    aviso("HDBSCAN no encontró una fuente tipo Nido; se usa el centro de referencia.")
centro["dist_a_referencia_km"] = round(float(haversine_km(centro["lat"], centro["lon"], ref["lat"], ref["lon"])), 1)
escribir_json(NIDO_JSON, centro)

# ----------------------------------------------------------------------------
# Comparación HDBSCAN vs K-Means vs DBSCAN (misma muestra de evaluación)
# ----------------------------------------------------------------------------
k_hdb = max(2, int(lab_a.max() + 1))
km = KMeans(n_clusters=k_hdb, n_init=10, random_state=C.SEMILLA).fit(Xa)
nn = NearestNeighbors(n_neighbors=C.HDBSCAN_MIN_SAMPLES).fit(Xa)
kdist = np.sort(nn.kneighbors(Xa)[0][:, -1])
# codo de la curva k-distancia (punto más lejos de la recta entre extremos)
idx = np.linspace(0, 1, len(kdist))
kd = (kdist - kdist[0]) / (kdist[-1] - kdist[0])
eps = float(kdist[np.argmax(idx - kd)])
db = DBSCAN(eps=eps, min_samples=C.HDBSCAN_MIN_SAMPLES).fit(Xa)

ev = rng.choice(len(Xa), min(6000, len(Xa)), replace=False)
prof_a = Xa[:, 2]


def mezcla_profundidad(lab):
    """Promedio ponderado de la fracción minoritaria (superficial < 30 km vs. intermedia ≥ 70 km) en cada grupo.
    0 = cada grupo tiene sismos de una sola profundidad; 0.5 = revuelve superficiales con profundos."""
    tot, acc = 0, 0.0
    for k in set(lab) - {-1}:
        z = prof_a[lab == k]
        s, d = np.sum(z < C.PROF_SUPERFICIAL_KM), np.sum(z >= C.PROF_INTERMEDIA_KM)
        if s + d:
            acc += min(s, d)
            tot += s + d
    return acc / tot if tot else np.nan


def metricas(nombre_m, lab, nota):
    m = lab[ev] != -1
    n_g = len(set(lab) - {-1})
    ok_m = n_g >= 2 and len(set(lab[ev][m])) >= 2
    return dict(
        metodo=nombre_m, n_fuentes=n_g, pct_difusa=round(float(np.mean(lab == -1)) * 100, 1),
        silueta=round(silhouette_score(Xa[ev][m], lab[ev][m]), 3) if ok_m else np.nan,
        davies_bouldin=round(davies_bouldin_score(Xa[ev][m], lab[ev][m]), 3) if ok_m else np.nan,
        calinski_harabasz=round(calinski_harabasz_score(Xa[ev][m], lab[ev][m]), 0) if ok_m else np.nan,
        mezcla_profundidad=round(mezcla_profundidad(lab), 3), parametros=nota)


comp = pd.DataFrame([
    metricas("HDBSCAN", lab_a, f"min_cluster_size={min_cluster}, min_samples={C.HDBSCAN_MIN_SAMPLES}"),
    metricas("K-Means", km.labels_, f"k={k_hdb} (el mismo número de fuentes que HDBSCAN)"),
    metricas("DBSCAN", db.labels_, f"eps={eps:.1f} km (codo k-distancia), min_samples={C.HDBSCAN_MIN_SAMPLES}"),
])
comp.to_csv(C.SALIDAS / "comparacion_fuentes.csv", index=False)
desc[["codigo", "fuente", "tipo", "n_sismos", "frac_sismos", "lat", "lon", "prof_mediana_km", "prof_p10_km",
      "prof_p90_km", "radio_p90_km", "mag_max", "n_m4", "dist_nido_ref_km", "municipio_cercano"]].to_csv(
    C.SALIDAS / "fuentes_sismicas.csv", index=False)
cat[["id_evento", "fuente_id", "fuente_codigo", "fuente", "fuente_tipo", "prob_fuente", "asignacion"]].to_csv(
    CAT_FUENTES, index=False)
escribir_json(C.INTERIM / "fuentes_meta.json", dict(
    fuente_catalogo=fuente, periodo_ajuste=per["variables"], n_ajuste=int(len(Xa)), min_cluster_size=min_cluster,
    min_samples=C.HDBSCAN_MIN_SAMPLES, n_fuentes=int(len(desc)), n_difusa=n_ruido, eps_dbscan=eps))

print()
print(comp.to_string(index=False))
print()
for _, r in desc.iterrows():
    info(f"{r['fuente']}: {r['n_sismos']:,} sismos, prof. mediana {r['prof_mediana_km']} km, M máx {r['mag_max']}")
info(f"Difusa (ruido): {n_ruido:,} sismos ({n_ruido / len(base):.1%})")
info(f"Centro del Nido: {centro['lat']}, {centro['lon']}, {centro['prof_km']} km "
     f"({centro['dist_a_referencia_km']} km de la referencia)")

# ----------------------------------------------------------------------------
# Figura: planta + perfil de profundidad
# ----------------------------------------------------------------------------
plt = estilo_figuras()
import geopandas as gpd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

contorno = gpd.read_file(CONTORNO)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 6.6), gridspec_kw=dict(width_ratios=[1, 1.25]))
orden = ["Difusa (ruido)", "Intermedia", "Cortical", "Nido de Bucaramanga"]
for t in orden:
    g = base[base["fuente_tipo"] == t]
    if g.empty:
        continue
    kw = dict(s=1.2 if t == "Difusa (ruido)" else 1.6, c=COLOR_TIPO_FUENTE[t], linewidths=0,
              alpha=0.35 if t == "Difusa (ruido)" else 0.5, rasterized=True)
    a1.scatter(g["lon"], g["lat"], **kw)
    a2.scatter(g["lon"], g["prof_km"], **kw)
mun.boundary.plot(ax=a1, color="#d4d2ca", linewidth=0.35)
contorno.boundary.plot(ax=a1, color=TINTA_2, linewidth=0.9)
puestas = {a1: [], a2: []}
for _, r in desc.iterrows():
    for ax, yy, tol_y in ((a1, r["lat"], 0.06), (a2, r["prof_mediana_km"], 9)):
        # si otra etiqueta ya está muy cerca, esta se corre hacia abajo para que no se tapen
        n_cerca = sum(abs(r["lon"] - px) < 0.12 and abs(yy - py) < tol_y for px, py in puestas[ax])
        puestas[ax].append((r["lon"], yy))
        ax.annotate(r["codigo"], (r["lon"], yy), xytext=(0, -13 * n_cerca),
                    textcoords="offset points", fontsize=8.5, fontweight="bold", color=TINTA, ha="center",
                    va="center", bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.85))
a1.plot(centro["lon"], centro["lat"], marker="*", ms=13, mfc="white", mec=TINTA, mew=1.0, zorder=5)
a2.plot(centro["lon"], centro["prof_km"], marker="*", ms=13, mfc="white", mec=TINTA, mew=1.0, zorder=5)
b = mun.total_bounds
a1.set_xlim(b[0] - 0.15, b[2] + 0.15)
a1.set_ylim(b[1] - 0.15, b[3] + 0.15)
a1.set_aspect("equal")
a1.set_xlabel("Longitud (°)")
a1.set_ylabel("Latitud (°)")
a1.set_title("Planta", loc="left")
a2.set_xlim(b[0] - 0.15, b[2] + 0.15)
a2.invert_yaxis()
a2.set_xlabel("Longitud (°)")
a2.set_ylabel("Profundidad (km)")
a2.set_title("Perfil oeste–este", loc="left")
conteo = base["fuente_tipo"].value_counts()
h = [Line2D([], [], ls="", marker="o", ms=7, mfc=COLOR_TIPO_FUENTE[t], mec="none",
            label=f"{t} · {conteo.get(t, 0):,} sismos") for t in orden[::-1] if conteo.get(t, 0)]
h.append(Line2D([], [], ls="", marker="*", ms=11, mfc="white", mec=TINTA, label="Centro del Nido (HDBSCAN)"))
a2.legend(handles=h, loc="lower left", fontsize=8.5)
fig.suptitle(f"Nivel 1 · {len(desc)} fuentes sísmicas encontradas por HDBSCAN "
             f"({per['variables'][0][:7]} a {per['variables'][1][:7]}, {len(base):,} sismos)",
             x=0.01, ha="left", fontsize=13, fontweight="bold", color=TINTA)
fig.text(0.01, 0.005, "Fuente: SGC – Red Sismológica Nacional de Colombia. F1…Fn = fuentes ordenadas por número de "
         "sismos (detalle en salidas/fuentes_sismicas.csv).", fontsize=8, color=TINTA_SUAVE)
fig.tight_layout(rect=(0, 0.02, 1, 0.95))
fig.savefig(C.SALIDAS / "fig_fuentes_sismicas.png")
plt.close(fig)
ok(f"Guardado {rel(C.SALIDAS / 'fig_fuentes_sismicas.png')}, fuentes_sismicas.csv, comparacion_fuentes.csv")
