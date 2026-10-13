"""
Paso 07 · NIVEL 2 · Clasificación de los municipios con K-Means (una fila = un municipio).

1. Prepara las variables de modelo del diccionario (log1p donde corresponde + estandarización z).
2. Compara 6 enfoques: K-Means, Ward, mezcla gaussiana, PCA + K-Means (k = K_MIN…K_MAX), DBSCAN y HDBSCAN,
   con silueta, Davies-Bouldin, Calinski-Harabasz y estabilidad bootstrap (ARI).
3. Modelo final: K-Means con el k de mejor silueta dentro de K_SELECCION y grupos de >= 3 municipios.
4. Ordena los grupos con un índice de amenaza/riesgo relativo -> niveles (Bajo … Muy alto).
5. Interpreta (perfiles, importancia η²), valida contra el periodo objetivo y compara la zona foco con el resto.
6. Mapa interactivo (folium), figuras y reporte.

Salidas en salidas/: mapa_riesgo_santander.html, reporte_modelo.md, municipios_clasificados.csv,
comparacion_modelos.csv, perfiles_grupos.csv, importancia_variables.csv, validacion_temporal.csv, fig_*.png
"""
import json
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import DBSCAN, HDBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from utils import (CAT_FUENTES, COLOR_TIPO_FUENTE, CONTORNO, DATASET, DICCIONARIO_CSV, EJE, NIDO_JSON,
                   NOMBRES_NIVELES, RAMPA_NIVELES, C, GRIS_NEUTRO, TINTA, TINTA_2, TINTA_SUAVE, asegurar_carpetas,
                   aviso, cargar_catalogo, cargar_municipios, en_periodo, escribir, estilo_figuras, filtrar_calidad,
                   info, leer_json, ok, rel, tabla_md, titulo)

warnings.filterwarnings("ignore", category=FutureWarning)
titulo("07 · Nivel 2 · K-Means por municipio (una fila = un municipio)")
asegurar_carpetas()
S = C.SALIDAS

ds = pd.read_csv(DATASET, dtype={"cod_mpio": str})
dic = pd.read_csv(DICCIONARIO_CSV)
per = leer_json(C.INTERIM / "periodos.json", {})
vars_m = [v for v in dic.loc[dic["uso"] == "modelo", "variable"] if v in ds.columns]
trans = dict(zip(dic["variable"], dic["transformacion"]))
comp_indice = dict(zip(dic["variable"], dic["componente_indice"].fillna("")))
desc_var = dict(zip(dic["variable"], dic["descripcion"]))
info(f"{len(ds)} municipios × {len(vars_m)} variables de modelo")

Xt = ds[vars_m].astype(float).copy()
for v in vars_m:
    if trans.get(v) == "log1p":
        Xt[v] = np.log1p(Xt[v].clip(lower=0))
Xt = Xt.fillna(Xt.median())
Xz = StandardScaler().fit_transform(Xt)
n = len(Xz)
rng = np.random.default_rng(C.SEMILLA)
pca_full = PCA(n_components=0.90, random_state=C.SEMILLA).fit(Xz)
Xp = pca_full.transform(Xz)
info(f"PCA: {pca_full.n_components_} componentes explican el {pca_full.explained_variance_ratio_.sum():.0%} de la varianza")


# ----------------------------------------------------------------------------
# Métodos
# ----------------------------------------------------------------------------
def ajustar(metodo, k, X):
    if metodo == "K-Means":
        m = KMeans(n_clusters=k, n_init=50, random_state=C.SEMILLA).fit(X)
        return m.labels_, m
    if metodo == "Ward":
        return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(X), None
    if metodo == "Mezcla gaussiana":
        m = GaussianMixture(n_components=k, covariance_type="diag", n_init=5, random_state=C.SEMILLA,
                            reg_covar=1e-3).fit(X)
        return m.predict(X), m
    if metodo == "PCA + K-Means":
        Z = PCA(n_components=pca_full.n_components_, random_state=C.SEMILLA).fit_transform(X)
        m = KMeans(n_clusters=k, n_init=50, random_state=C.SEMILLA).fit(Z)
        return m.labels_, m
    raise ValueError(metodo)


def asignar(X_fit, lab_fit, X_all):
    """Asigna cada municipio al centroide más cercano de los grupos del remuestreo (para Ward / GMM / PCA)."""
    cents = np.array([X_fit[lab_fit == g].mean(axis=0) for g in np.unique(lab_fit)])
    return np.argmin(((X_all[:, None, :] - cents[None]) ** 2).sum(-1), axis=1)


def estabilidad(metodo, k, lab_ref):
    aris = []
    for _ in range(C.N_BOOTSTRAP):
        idx = np.unique(rng.choice(n, n, replace=True))
        if len(idx) <= k + 1:
            continue
        Xb = Xz[idx]
        if metodo == "K-Means":
            m = KMeans(n_clusters=k, n_init=10, random_state=int(rng.integers(1e9))).fit(Xb)
            lab = m.predict(Xz)
        elif metodo == "PCA + K-Means":
            p = PCA(n_components=pca_full.n_components_).fit(Xb)
            m = KMeans(n_clusters=k, n_init=10, random_state=int(rng.integers(1e9))).fit(p.transform(Xb))
            lab = m.predict(p.transform(Xz))
        elif metodo == "Mezcla gaussiana":
            m = GaussianMixture(n_components=k, covariance_type="diag", n_init=2, reg_covar=1e-3,
                                random_state=int(rng.integers(1e9))).fit(Xb)
            lab = m.predict(Xz)
        else:
            lab = asignar(Xb, AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Xb), Xz)
        aris.append(adjusted_rand_score(lab_ref, lab))
    return float(np.mean(aris)), float(np.std(aris))


def metricas(lab):
    m = lab != -1
    grupos = np.unique(lab[m])
    r = dict(n_grupos=len(grupos), pct_sin_grupo=round(100 * float(np.mean(~m)), 1),
             tam_min=int(min(np.sum(lab == g) for g in grupos)) if len(grupos) else 0)
    if len(grupos) >= 2 and m.sum() > len(grupos):
        r.update(silueta=silhouette_score(Xz[m], lab[m]), davies_bouldin=davies_bouldin_score(Xz[m], lab[m]),
                 calinski_harabasz=calinski_harabasz_score(Xz[m], lab[m]))
    else:
        r.update(silueta=np.nan, davies_bouldin=np.nan, calinski_harabasz=np.nan)
    return r


filas, etiquetas = [], {}
for metodo in ("K-Means", "Ward", "Mezcla gaussiana", "PCA + K-Means"):
    for k in range(C.K_MIN, C.K_MAX + 1):
        lab, _ = ajustar(metodo, k, Xz)
        r = dict(metodo=metodo, parametro=f"k={k}", k=k, **metricas(lab))
        r["ari_media"], r["ari_sd"] = estabilidad(metodo, k, lab)
        filas.append(r)
        etiquetas[(metodo, k)] = lab
kd = np.sort(NearestNeighbors(n_neighbors=4).fit(Xz).kneighbors(Xz)[0][:, -1])
for q in (0.5, 0.6, 0.7, 0.8, 0.9):
    eps = float(np.quantile(kd, q))
    lab = DBSCAN(eps=eps, min_samples=4).fit_predict(Xz)
    filas.append(dict(metodo="DBSCAN", parametro=f"eps={eps:.2f} (p{int(q * 100)} 4-distancia), min_samples=4",
                      k=np.nan, ari_media=np.nan, ari_sd=np.nan, **metricas(lab)))
for mcs in (3, 4, 5, 6, 8):
    lab = HDBSCAN(min_cluster_size=mcs, copy=True).fit_predict(Xz)
    filas.append(dict(metodo="HDBSCAN", parametro=f"min_cluster_size={mcs}", k=np.nan, ari_media=np.nan,
                      ari_sd=np.nan, **metricas(lab)))
comp = pd.DataFrame(filas)
for c in ("silueta", "davies_bouldin", "ari_media", "ari_sd"):
    comp[c] = comp[c].round(3)
comp["calinski_harabasz"] = comp["calinski_harabasz"].round(1)
comp.to_csv(S / "comparacion_modelos.csv", index=False)

# ----------------------------------------------------------------------------
# Selección: K-Means, k en K_SELECCION, grupos >= 3 municipios, mejor silueta
# ----------------------------------------------------------------------------
cand = comp[(comp["metodo"] == "K-Means") & comp["k"].between(*C.K_SELECCION) & (comp["tam_min"] >= 3)]
if cand.empty:
    cand = comp[(comp["metodo"] == "K-Means") & comp["k"].between(*C.K_SELECCION)]
    aviso("Ningún k deja grupos de >= 3 municipios; se relaja esa condición.")
fila_final = cand.sort_values(["silueta", "ari_media"], ascending=False).iloc[0]
k = int(fila_final["k"])
modelo = KMeans(n_clusters=k, n_init=200, random_state=C.SEMILLA).fit(Xz)
grupo = modelo.labels_
mejor_global = comp.dropna(subset=["silueta"]).query("pct_sin_grupo == 0 and n_grupos >= 3").sort_values(
    "silueta", ascending=False).iloc[0]
info(f"Modelo final: K-Means k={k} · silueta {fila_final['silueta']:.3f} · "
     f"estabilidad ARI {fila_final['ari_media']:.2f} ± {fila_final['ari_sd']:.2f}")

# ----------------------------------------------------------------------------
# Índice de amenaza/riesgo relativo -> nombres de los niveles
# ----------------------------------------------------------------------------
Zdf = pd.DataFrame(Xz, columns=vars_m)
componentes = {}
for v in vars_m:
    c = comp_indice.get(v, "")
    if c:
        componentes.setdefault(c, []).append(v)
suma = pd.Series(0.0, index=Zdf.index)
for c, vs in componentes.items():
    puntaje = Zdf[vs].mean(axis=1)
    suma += -puntaje if c == "distancia" else puntaje
indice_bruto = suma / max(1, len(componentes))
ds["indice_riesgo"] = (100 * (indice_bruto - indice_bruto.min()) / (indice_bruto.max() - indice_bruto.min())).round(1)
ds["grupo"] = grupo
orden_g = ds.groupby("grupo")["indice_riesgo"].mean().sort_values().index.tolist()
nombres = NOMBRES_NIVELES.get(k, [f"Nivel {i + 1}" for i in range(k)])
colores = RAMPA_NIVELES.get(k, RAMPA_NIVELES[5][:k])
nivel_de = {g: nombres[i] for i, g in enumerate(orden_g)}
ds["nivel_ord"] = ds["grupo"].map({g: i + 1 for i, g in enumerate(orden_g)})
ds["nivel"] = ds["grupo"].map(nivel_de)
ds["grupo"] = ds["nivel_ord"]                       # grupos numerados de menor a mayor amenaza
color_nivel = dict(zip(nombres, colores))
ds["color"] = ds["nivel"].map(color_nivel)
# Contraste: el nivel cuyo índice medio está más cerca del índice del municipio. Si difiere en >= 2 niveles del
# grupo de K-Means, el municipio tiene un perfil mixto y se reporta aparte (no se fuerza el resultado del modelo).
medias_idx = ds.groupby("nivel_ord")["indice_riesgo"].mean()
ds["nivel_segun_indice"] = ds["indice_riesgo"].map(
    lambda v: nombres[int(np.argmin(np.abs(medias_idx.to_numpy() - v)))])
ds["dif_niveles"] = ds["nivel_segun_indice"].map({nv: i + 1 for i, nv in enumerate(nombres)}) - ds["nivel_ord"]
discrepantes = ds[ds["dif_niveles"].abs() >= 2].sort_values("dif_niveles", ascending=False)

# ----------------------------------------------------------------------------
# Interpretación: perfiles e importancia (η²)
# ----------------------------------------------------------------------------
Zdf["nivel"] = ds["nivel"]
perfil_z = Zdf.groupby("nivel")[vars_m].mean().reindex(nombres)
perfil = ds.groupby("nivel")[vars_m + ["indice_riesgo", "obj_tasa_fuertes_futura_r50"]].mean().reindex(nombres)
perfil.insert(0, "n_municipios", ds.groupby("nivel").size().reindex(nombres))
perfil.round(3).to_csv(S / "perfiles_grupos.csv")
eta = {}
for v in vars_m:
    tot = ((Zdf[v] - Zdf[v].mean()) ** 2).sum()
    entre = sum(len(g) * (g[v].mean() - Zdf[v].mean()) ** 2 for _, g in Zdf.groupby("nivel"))
    eta[v] = entre / tot if tot > 0 else 0
imp = pd.Series(eta).sort_values(ascending=False).rename("eta2").reset_index().rename(columns={"index": "variable"})
imp["descripcion"] = imp["variable"].map(desc_var)
imp.round(3).to_csv(S / "importancia_variables.csv", index=False)

# ----------------------------------------------------------------------------
# Validación temporal (periodo objetivo, que no entró al modelo)
# ----------------------------------------------------------------------------
val = ds.groupby("nivel").agg(municipios=("municipio", "size"),
                              objetivo_media=("obj_tasa_fuertes_futura_r50", "mean"),
                              objetivo_mediana=("obj_tasa_fuertes_futura_r50", "median"),
                              futura_r30_media=("obj_tasa_futura_r30", "mean"),
                              futura_r30_mediana=("obj_tasa_futura_r30", "median")).reindex(nombres)
val.round(3).to_csv(S / "validacion_temporal.csv")
rho_niv, p_niv = stats.spearmanr(ds["nivel_ord"], ds["obj_tasa_fuertes_futura_r50"])
rho_ind, p_ind = stats.spearmanr(ds["indice_riesgo"], ds["obj_tasa_fuertes_futura_r50"])
rho_r30, p_r30 = stats.spearmanr(ds["nivel_ord"], ds["obj_tasa_futura_r30"])
rho_base, _ = stats.spearmanr(ds["tasa_fuertes_r30"], ds["obj_tasa_fuertes_futura_r50"])
kw = stats.kruskal(*[g["obj_tasa_fuertes_futura_r50"].to_numpy() for _, g in ds.groupby("nivel")])
monotona = bool(np.all(np.diff(val["objetivo_media"].to_numpy()) >= 0))
info(f"Validación: Spearman(nivel, objetivo) = {rho_niv:.2f} (p={p_niv:.1e}); Kruskal-Wallis p={kw.pvalue:.1e}; "
     f"{'crece' if monotona else 'NO crece'} de forma monótona con el nivel")

# ----------------------------------------------------------------------------
# Zona foco vs resto
# ----------------------------------------------------------------------------
clave = [v for v in ("tasa_sismos_r30", "tasa_m3_r30", "tasa_fuertes_r30", "mag_max_r30", "log_energia_anual_r30",
                     "prof_mediana_r30", "frac_superficiales_r30", "tasa_superficiales_r30", "dist_nido_km",
                     "frac_nido_r30", "poblacion", "densidad_poblacion", "hist_int_max_r100") if v in ds.columns]
clave += ["indice_riesgo", "obj_tasa_fuertes_futura_r50"]
foco = ds["zona_foco"].astype(str).str.lower().isin(["true", "1"])
zf = []
for v in clave:
    a, b = ds.loc[foco, v], ds.loc[~foco, v]
    p = stats.mannwhitneyu(a, b).pvalue if a.nunique() > 1 or b.nunique() > 1 else np.nan
    zf.append(dict(variable=v, zona_foco_media=a.mean(), resto_media=b.mean(), razon=a.mean() / b.mean()
                   if b.mean() else np.nan, p_mann_whitney=p))
zf = pd.DataFrame(zf)
foco_tab = ds.loc[foco, ["municipio", "nivel", "indice_riesgo", "tasa_sismos_r30", "tasa_fuertes_r30",
                         "dist_nido_km", "obj_tasa_fuertes_futura_r50"]].sort_values("indice_riesgo", ascending=False)
dist_niv = pd.crosstab(ds["nivel"], foco.map({True: "Zona foco", False: "Resto"})).reindex(nombres).fillna(0).astype(int)

# ----------------------------------------------------------------------------
# Tabla final por municipio
# ----------------------------------------------------------------------------
salida_cols = ["cod_mpio", "municipio", "zona_foco", "grupo", "nivel", "indice_riesgo", "nivel_segun_indice"] + vars_m + \
              ["obj_tasa_fuertes_futura_r50", "obj_tasa_futura_r30"]
ds.sort_values(["nivel_ord", "indice_riesgo"], ascending=False)[salida_cols].to_csv(
    S / "municipios_clasificados.csv", index=False)

# ----------------------------------------------------------------------------
# Figuras
# ----------------------------------------------------------------------------
plt = estilo_figuras()
import geopandas as gpd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

SERIES = {"K-Means": "#2a78d6", "Ward": "#eb6834", "Mezcla gaussiana": "#1baf7a", "PCA + K-Means": "#eda100"}

# 1) Selección de modelos: silueta y estabilidad vs k
fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
for ax, met, tit in ((axes[0], "silueta", "Silueta (más alto = grupos más separados)"),
                     (axes[1], "ari_media", "Estabilidad bootstrap, ARI (más alto = más estable)")):
    finales = []
    for m_, col in SERIES.items():
        d = comp[comp["metodo"] == m_]
        ax.plot(d["k"], d[met], color=col, lw=2, marker="o", ms=5, label=m_)
        finales.append([d[met].iloc[-1], m_, d["k"].iloc[-1]])
    # etiquetas directas al final de cada línea, separadas para que no se tapen
    sep = 0.045 * (comp[met].max() - comp[met].min())
    finales.sort()
    for i_ in range(1, len(finales)):
        finales[i_][0] = max(finales[i_][0], finales[i_ - 1][0] + sep)
    for y_, m_, x_ in finales:
        ax.annotate(m_, (x_, y_), xytext=(8, 0), textcoords="offset points", fontsize=8.5, color=TINTA_2,
                    va="center")
    ax.axvspan(C.K_SELECCION[0] - 0.4, C.K_SELECCION[1] + 0.4, color=GRIS_NEUTRO, zorder=0)
    ax.plot(k, fila_final[met], marker="o", ms=13, mfc="none", mec=TINTA, mew=1.5, zorder=5)
    ax.set_title(tit, loc="left", fontsize=11)
    ax.set_xlabel("Número de grupos (k)")
    ax.set_xlim(C.K_MIN - 0.5, C.K_MAX + 1.6)
axes[0].legend(loc="upper right", fontsize=8)
axes[0].annotate(f"Elegido: K-Means k={k}", (k, fila_final["silueta"]), xytext=(10, 14), textcoords="offset points",
                 fontsize=9, fontweight="bold", color=TINTA)
fig.suptitle("Nivel 2 · Comparación de modelos por municipio (zona gris = k permitido)", x=0.01, ha="left",
             fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(S / "fig_seleccion_modelos.png")
plt.close(fig)

# 2) Perfiles de los grupos (z medio por variable), divergente azul–gris–rojo
cmap = LinearSegmentedColormap.from_list("div", ["#184f95", "#6da7ec", GRIS_NEUTRO, "#ec835a", "#d03b3b"])
orden_v = imp["variable"].tolist()
fig, ax = plt.subplots(figsize=(13, 1.2 + 0.62 * k))
im = ax.imshow(perfil_z[orden_v].to_numpy(), cmap=cmap, vmin=-2, vmax=2, aspect="auto")
ax.set_yticks(range(k), [f"{nv} ({int(perfil.loc[nv, 'n_municipios'])})" for nv in nombres])
ax.set_xticks(range(len(orden_v)), orden_v, rotation=50, ha="right", fontsize=8.5)
ax.grid(False)
for s_ in ax.spines.values():
    s_.set_visible(False)
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
cb.set_label("Media del grupo (z)", fontsize=9)
cb.outline.set_visible(False)
ax.set_title("Perfil de cada nivel: media estandarizada de cada variable (variables ordenadas por importancia η²)",
             loc="left", fontsize=11)
fig.tight_layout()
fig.savefig(S / "fig_perfiles_grupos.png")
plt.close(fig)

# 3) Importancia de variables (η²)
fig, ax = plt.subplots(figsize=(9, 0.32 * len(imp) + 1.2))
yy = np.arange(len(imp))[::-1]
ax.barh(yy, imp["eta2"], color="#2a78d6", height=0.62)
ax.set_yticks(yy, imp["variable"], fontsize=8.5)
for i_ in range(min(5, len(imp))):
    ax.annotate(f"{imp['eta2'].iat[i_]:.2f}", (imp["eta2"].iat[i_], yy[i_]), xytext=(4, 0),
                textcoords="offset points", va="center", fontsize=8.5, color=TINTA_2)
ax.set_xlim(0, 1.05)
ax.set_xlabel("η² (fracción de la varianza explicada por los grupos)")
ax.grid(axis="y", visible=False)
ax.set_title("¿Qué variables separan los niveles?", loc="left")
fig.tight_layout()
fig.savefig(S / "fig_importancia_variables.png")
plt.close(fig)

# 4) Validación temporal
fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
for ax, col, tit, logy in ((axes[0], "obj_tasa_fuertes_futura_r50",
                            f"Sismos M ≥ {C.MAG_FUERTE:g} por año a ≤ {C.RADIO_OBJETIVO_KM} km (periodo objetivo)", False),
                           (axes[1], "obj_tasa_futura_r30",
                            f"Sismos M ≥ Mc por año a ≤ {C.RADIO_INFLUENCIA_KM} km (periodo objetivo)", True)):
    for i_, nv in enumerate(nombres):
        v = ds.loc[ds["nivel"] == nv, col].to_numpy()
        jit = rng.uniform(-0.18, 0.18, len(v))
        ax.scatter(np.full(len(v), i_) + jit, (v + 0.1) if logy else v, s=26, color=color_nivel[nv],
                   edgecolor="white", linewidth=0.8, zorder=3)
        med = np.median(v)
        ax.plot([i_ - 0.3, i_ + 0.3], [(med + 0.1) if logy else med] * 2, color=TINTA, lw=2, zorder=4)
    ax.set_xticks(range(k), nombres)
    ax.set_title(tit, loc="left", fontsize=10.5)
    ax.grid(axis="x", visible=False)
    if logy:
        ax.set_yscale("log")
        ax.set_ylabel("sismos/año (escala log, +0.1)")
    else:
        ax.set_ylabel("sismos/año")
fig.suptitle(f"Validación temporal: los niveles se calcularon con {per.get('variables', ['', ''])[0][:7]} a "
             f"{per.get('variables', ['', ''])[1][:7]}; los puntos son {per.get('objetivo', ['', ''])[0][:7]} a "
             f"{per.get('objetivo', ['', ''])[1][:7]} (raya = mediana)", x=0.01, ha="left", fontsize=11.5,
             fontweight="bold")
fig.tight_layout()
fig.savefig(S / "fig_validacion_temporal.png")
plt.close(fig)

# 5) Mapa estático de niveles
mun = cargar_municipios()
g = mun[["cod_mpio", "geometry"]].merge(ds, on="cod_mpio")
contorno = gpd.read_file(CONTORNO)
nido = leer_json(NIDO_JSON, C.NIDO_REFERENCIA)
fig, ax = plt.subplots(figsize=(8.5, 9))
g.plot(ax=ax, color=g["color"], edgecolor="white", linewidth=0.6)
g[foco].boundary.plot(ax=ax, color=TINTA, linewidth=1.6)
contorno.boundary.plot(ax=ax, color=TINTA_2, linewidth=0.8)
ax.plot(nido["lon"], nido["lat"], marker="*", ms=14, mfc="white", mec=TINTA, mew=1)
for _, r in g[foco].iterrows():
    ax.annotate(r["municipio"], (r["lon"], r["lat"]), fontsize=7.5, ha="center", color=TINTA,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
ax.set_axis_off()
h = [Patch(fc=color_nivel[nv], ec="none", label=f"{nv} ({int((ds['nivel'] == nv).sum())})") for nv in nombres[::-1]]
h += [Line2D([], [], color=TINTA, lw=1.6, label="Zona foco (AMB + Los Santos)"),
      Line2D([], [], ls="", marker="*", ms=12, mfc="white", mec=TINTA, label="Centro del Nido")]
ax.legend(handles=h, loc="lower left", title="Nivel de amenaza/riesgo relativo", title_fontsize=9, fontsize=8.5)
ax.set_title(f"Santander · {k} niveles de amenaza sísmica relativa por municipio (K-Means)", loc="left", fontsize=12)
fig.savefig(S / "fig_mapa_niveles.png")
plt.close(fig)

# 6) PCA 2D de los municipios
p2 = PCA(n_components=2, random_state=C.SEMILLA).fit(Xz)
P = p2.transform(Xz)
fig, ax = plt.subplots(figsize=(8, 6))
for nv in nombres:
    m_ = (ds["nivel"] == nv).to_numpy()
    ax.scatter(P[m_, 0], P[m_, 1], s=40, color=color_nivel[nv], edgecolor="white", linewidth=0.8, label=nv, zorder=3)
for i_ in np.where(foco.to_numpy())[0]:
    ax.annotate(ds["municipio"].iat[i_], (P[i_, 0], P[i_, 1]), xytext=(5, 4), textcoords="offset points",
                fontsize=8, color=TINTA_2)
ax.set_xlabel(f"Componente 1 ({p2.explained_variance_ratio_[0]:.0%} de la varianza)")
ax.set_ylabel(f"Componente 2 ({p2.explained_variance_ratio_[1]:.0%})")
ax.legend(title="Nivel", fontsize=8.5, title_fontsize=9)
ax.set_title("Municipios en el plano de las dos primeras componentes", loc="left")
fig.tight_layout()
fig.savefig(S / "fig_pca_grupos.png")
plt.close(fig)

# ----------------------------------------------------------------------------
# Mapa interactivo (folium)
# ----------------------------------------------------------------------------
import folium  # noqa: E402

cen = contorno.geometry.iloc[0].centroid
mapa = folium.Map(location=[cen.y, cen.x], zoom_start=8, tiles="OpenStreetMap", control_scale=True)
campos = [("municipio", "Municipio"), ("nivel", "Nivel"), ("indice_riesgo", "Índice (0–100)"),
          ("sacudida_pct", "Energía sísmica que llega (% del municipio más sacudido)"),
          ("tasa_sismos_r30", "Sismos/año a ≤ 30 km (M ≥ Mc)"), ("tasa_fuertes_r30", "Sismos M ≥ 4/año a ≤ 30 km"),
          ("mag_max_r30", "Magnitud máx. a ≤ 30 km"), ("prof_mediana_r30", "Profundidad mediana (km)"),
          ("dist_nido_km", "Distancia al Nido (km)"),
          ("obj_tasa_fuertes_futura_r50", "Validación: M ≥ 4/año a ≤ 50 km después")]
if "log_flujo_energia_hipo" in g:
    g["sacudida_pct"] = (100 * 10 ** (g["log_flujo_energia_hipo"] - g["log_flujo_energia_hipo"].max())).round(0)
else:
    campos = [c for c in campos if c[0] != "sacudida_pct"]
gj = g[["cod_mpio", "geometry", "color", "zona_foco"] + [c for c, _ in campos]].copy()
for c in ("tasa_sismos_r30", "tasa_fuertes_r30", "dist_nido_km", "obj_tasa_fuertes_futura_r50", "prof_mediana_r30"):
    gj[c] = gj[c].round(1)
gj["zona_foco"] = gj["zona_foco"].astype(str)
folium.GeoJson(
    json.loads(gj.to_json()), name="Niveles de amenaza/riesgo relativo",
    style_function=lambda f: dict(fillColor=f["properties"]["color"], color="#ffffff", weight=0.8, fillOpacity=0.78),
    highlight_function=lambda f: dict(weight=2.5, color=TINTA, fillOpacity=0.9),
    tooltip=folium.GeoJsonTooltip(fields=[c for c, _ in campos], aliases=[a for _, a in campos], sticky=True),
).add_to(mapa)
folium.GeoJson(json.loads(gj[gj["zona_foco"].str.lower() == "true"][["geometry", "municipio"]].to_json()),
               name="Zona foco (AMB + Los Santos)",
               style_function=lambda f: dict(fill=False, color=TINTA, weight=3),
               tooltip=folium.GeoJsonTooltip(fields=["municipio"], aliases=["Zona foco"])).add_to(mapa)

cat = filtrar_calidad(cargar_catalogo(per.get("fuente", "sgc")))
if CAT_FUENTES.exists():
    cat = cat.merge(pd.read_csv(CAT_FUENTES)[["id_evento", "fuente", "fuente_tipo"]], on="id_evento", how="left")
fuertes = en_periodo(cat, per["variables"]) if per else cat
fuertes = fuertes[fuertes["mag"] >= C.MAG_FUERTE]
capa = folium.FeatureGroup(name=f"Sismos M ≥ {C.MAG_FUERTE:g} del periodo de variables ({len(fuertes)})", show=True)
for _, r in fuertes.iterrows():
    t = r.get("fuente_tipo") if isinstance(r.get("fuente_tipo"), str) else "Difusa (ruido)"
    folium.CircleMarker([r["lat"], r["lon"]], radius=2.5 + 3 * (r["mag"] - C.MAG_FUERTE), color="white", weight=0.8,
                        fill=True, fill_color=COLOR_TIPO_FUENTE.get(t, TINTA_SUAVE), fill_opacity=0.9,
                        tooltip=f"M {r['mag']:.1f} · {r['prof_km']:.0f} km · {r['fecha_utc']:%Y-%m-%d} · "
                                f"{r.get('fuente', '')}").add_to(capa)
capa.add_to(mapa)
fz = pd.read_csv(S / "fuentes_sismicas.csv") if (S / "fuentes_sismicas.csv").exists() else pd.DataFrame()
capa_f = folium.FeatureGroup(name="Fuentes sísmicas (HDBSCAN)", show=True)
for _, r in fz.iterrows():
    folium.Marker([r["lat"], r["lon"]], icon=folium.DivIcon(html=(
        f'<div style="font:600 11px system-ui,sans-serif;color:#0b0b0b;background:#fff;border:2px solid '
        f'{COLOR_TIPO_FUENTE.get(r["tipo"], TINTA_SUAVE)};border-radius:10px;padding:1px 5px;'
        f'transform:translate(-50%,-50%);white-space:nowrap">{r["codigo"]}</div>')),
        tooltip=f"{r['fuente']} · {r['n_sismos']:,} sismos · prof. mediana {r['prof_mediana_km']} km · "
                f"M máx {r['mag_max']}").add_to(capa_f)
capa_f.add_to(mapa)
folium.Marker([nido["lat"], nido["lon"]], tooltip=f"Centro del Nido de Bucaramanga · {nido.get('prof_km', 150)} km",
              icon=folium.Icon(color="black", icon="star")).add_to(mapa)

leyenda_niv = "".join(f'<div><span style="display:inline-block;width:14px;height:14px;background:{color_nivel[nv]};'
                      f'border-radius:3px;margin-right:6px;vertical-align:-2px"></span>{nv} '
                      f'<span style="color:#52514e">({int((ds["nivel"] == nv).sum())})</span></div>'
                      for nv in nombres[::-1])
leyenda_f = "".join(f'<div><span style="display:inline-block;width:10px;height:10px;background:{c};border-radius:50%;'
                    f'margin-right:6px"></span>{t}</div>' for t, c in COLOR_TIPO_FUENTE.items() if t != "Difusa (ruido)")
caja = f"""
<div style="position:fixed;bottom:24px;left:12px;z-index:9999;background:#fcfcfb;padding:10px 12px;border-radius:8px;
 box-shadow:0 1px 4px rgba(0,0,0,.25);font:12px system-ui,-apple-system,'Segoe UI',sans-serif;color:#0b0b0b;max-width:260px">
 <div style="font-weight:700;margin-bottom:4px">Nivel de amenaza/riesgo relativo</div>{leyenda_niv}
 <div style="font-weight:700;margin:8px 0 4px">Sismos M ≥ {C.MAG_FUERTE:g} por tipo de fuente</div>{leyenda_f}
 <div style="color:#52514e;margin-top:6px">Borde negro grueso = zona foco · ★ = Nido</div>
</div>
<div style="position:fixed;top:12px;left:56px;z-index:9999;background:#fcfcfb;padding:8px 12px;border-radius:8px;
 box-shadow:0 1px 4px rgba(0,0,0,.25);font:12px system-ui,-apple-system,'Segoe UI',sans-serif;color:#0b0b0b;max-width:430px">
 <div style="font-weight:700;font-size:14px">Riesgo sísmico relativo · 87 municipios de Santander</div>
 <div style="color:#52514e">K-Means (k={k}) sobre {len(vars_m)} variables del catálogo SGC
 {per.get('variables', ['', ''])[0]} a {per.get('variables', ['', ''])[1]}; validado con
 {per.get('objetivo', ['', ''])[0]} a {per.get('objetivo', ['', ''])[1]}. Pasa el cursor sobre un municipio.</div>
</div>"""
mapa.get_root().html.add_child(folium.Element(caja))
folium.LayerControl(collapsed=False).add_to(mapa)
mapa.save(S / "mapa_riesgo_santander.html")

# ----------------------------------------------------------------------------
# Reporte
# ----------------------------------------------------------------------------
fz_cmp = pd.read_csv(S / "comparacion_fuentes.csv") if (S / "comparacion_fuentes.csv").exists() else pd.DataFrame()
fmeta = leer_json(C.INTERIM / "fuentes_meta.json", {})
mejor_por_metodo = (comp.dropna(subset=["silueta"]).sort_values("silueta", ascending=False)
                    .groupby("metodo", sort=False).head(1))
mejor_por_metodo = mejor_por_metodo[["metodo", "parametro", "n_grupos", "pct_sin_grupo", "tam_min", "silueta",
                                     "davies_bouldin", "calinski_harabasz", "ari_media"]]
km_tab = comp[comp["metodo"] == "K-Means"][["k", "silueta", "davies_bouldin", "calinski_harabasz", "tam_min",
                                            "ari_media", "ari_sd"]]
niveles_tab = pd.DataFrame([dict(
    Nivel=nv, Municipios=int((ds["nivel"] == nv).sum()),
    **{"Índice medio": ds.loc[ds["nivel"] == nv, "indice_riesgo"].mean(),
       "Sismos/año ≤30 km": ds.loc[ds["nivel"] == nv, "tasa_sismos_r30"].mean(),
       "M≥4/año ≤30 km": ds.loc[ds["nivel"] == nv, "tasa_fuertes_r30"].mean(),
       "M máx": ds.loc[ds["nivel"] == nv, "mag_max_r30"].mean(),
       "Prof. mediana (km)": ds.loc[ds["nivel"] == nv, "prof_mediana_r30"].mean(),
       "Dist. Nido (km)": ds.loc[ds["nivel"] == nv, "dist_nido_km"].mean()},
    Ejemplos=", ".join(ds[ds["nivel"] == nv].sort_values("indice_riesgo", ascending=False)["municipio"].head(6)))
    for nv in nombres[::-1]])
lista = ds.sort_values(["nivel_ord", "indice_riesgo"], ascending=False)[
    ["municipio", "nivel", "indice_riesgo", "tasa_sismos_r30", "tasa_fuertes_r30", "mag_max_r30",
     "prof_mediana_r30", "dist_nido_km", "obj_tasa_fuertes_futura_r50"]].rename(columns={
        "municipio": "Municipio", "nivel": "Nivel", "indice_riesgo": "Índice", "tasa_sismos_r30": "Sismos/año",
        "tasa_fuertes_r30": "M≥4/año", "mag_max_r30": "M máx", "prof_mediana_r30": "Prof. (km)",
        "dist_nido_km": "Dist. Nido (km)", "obj_tasa_fuertes_futura_r50": "Objetivo (M≥4/año ≤50 km)"})
lim_extra = []
if per.get("ajustado"):
    lim_extra.append(f"**Periodo corto.** Solo hay exports del SGC de {per['variables'][0]} a {per['objetivo'][1]}: las "
                     f"variables usan {per['variables'][0]} a {per['variables'][1]} y el objetivo "
                     f"{per['objetivo'][0]} a {per['objetivo'][1]}. Con los exports 2006–2025 el pipeline vuelve "
                     "solo a 2006–2020 / 2021–2025 (`config.py`).")
arch = pd.read_csv(C.INTERIM / "archivos_sgc.csv") if (C.INTERIM / "archivos_sgc.csv").exists() else pd.DataFrame()
if len(arch) and arch["departamento"].notna().any():
    lim_extra.append("**Consulta por departamento.** Los exports se pidieron con filtro *departamento = Santander*, así "
                     "que faltan los sismos que caen justo fuera del límite; los municipios de borde quedan algo "
                     "subestimados. La consulta por cuadrante (README §2.1) lo corrige.")
if not per.get("hay_historico"):
    lim_extra.append("**Sin sismicidad histórica.** Falta `datos/raw/sgc_historico/`; las 3 variables históricas no entraron.")
if not per.get("hay_poblacion"):
    lim_extra.append("**Sin población.** Falta la población DANE; el resultado es amenaza relativa sin exposición.")

top_imp = ", ".join(f"`{v}` ({e:.2f})" for v, e in imp[["variable", "eta2"]].head(5).itertuples(index=False))
escribir(S / "reporte_modelo.md", f"""# Riesgo sísmico relativo de los 87 municipios de Santander

Reporte generado por `scripts/07_modelo_clustering.py` (`python run_all.py` lo regenera desde cero).

## 1. Resumen

- **Datos:** catálogo sísmico del SGC (RSNC), {per.get('variables', ['?'])[0]} a {per.get('objetivo', ['', '?'])[1]};
  completitud Mc = {per.get('mc', float('nan')):.1f}; sismos mal localizados excluidos.
- **Nivel 1 · HDBSCAN (una fila = un sismo):** {fmeta.get('n_fuentes', '?')} fuentes sísmicas en
  {fmeta.get('n_ajuste', 0):,} sismos; el Nido de Bucaramanga sale solo, centrado en {nido['lat']}, {nido['lon']},
  {nido.get('prof_km', '?')} km.
- **Nivel 2 · K-Means (una fila = un municipio):** {len(vars_m)} variables → **{k} niveles** (silueta
  {fila_final['silueta']:.2f}, estabilidad bootstrap ARI {fila_final['ari_media']:.2f} ± {fila_final['ari_sd']:.2f}).
- **Validación temporal** (periodo objetivo {per.get('objetivo', ['?'])[0]} a {per.get('objetivo', ['', '?'])[1]}, que
  no entró al modelo): Spearman nivel vs. sismos M ≥ {C.MAG_FUERTE:g} futuros = **{rho_niv:.2f}** (p = {p_niv:.1e});
  la tasa media futura {'crece en cada nivel' if monotona else 'no crece de forma estrictamente monótona entre niveles'}.
- **Zona foco** (AMB + Los Santos): ver §7.

## 2. Datos y periodos

| | Desde | Hasta |
|---|---|---|
| Variables (entrada del modelo) | {per.get('variables', ['?', '?'])[0]} | {per.get('variables', ['?', '?'])[1]} |
| Objetivo (validación) | {per.get('objetivo', ['?', '?'])[0]} | {per.get('objetivo', ['?', '?'])[1]} |

Limpieza: `datos/interim/reporte_limpieza_sgc.md` · Variables: `datos/interim/reporte_variables.md` ·
Diccionario: `docs/diccionario_datos.md` · Origen: `docs/metadatos_origen.md`.

## 3. Nivel 1 · Fuentes sísmicas (HDBSCAN vs K-Means vs DBSCAN)

Entrada: x, y y profundidad de cada sismo, las tres en km. Silueta, Davies-Bouldin y Calinski-Harabasz sobre una
muestra de 6 000 sismos sin el ruido. `mezcla_profundidad` = fracción de sismos superficiales (< 30 km) mezclados
con intermedios (≥ 70 km) en el mismo grupo (0 = no los mezcla).

{tabla_md(fz_cmp, floatfmt='.3g')}

{tabla_md(fz[['codigo', 'tipo', 'n_sismos', 'prof_mediana_km', 'prof_p10_km', 'prof_p90_km', 'mag_max', 'n_m4', 'municipio_cercano']] if len(fz) else fz, floatfmt='.4g')}

![Fuentes sísmicas](fig_fuentes_sismicas.png)

## 4. Nivel 2 · Comparación de modelos por municipio

{len(vars_m)} variables (log1p en las muy sesgadas y estandarización z). PCA conserva {pca_full.n_components_}
componentes (90 % de la varianza). Mejor configuración de cada método:

{tabla_md(mejor_por_metodo, floatfmt='.3g')}

K-Means por número de grupos (estabilidad = ARI medio de {C.N_BOOTSTRAP} remuestreos bootstrap):

{tabla_md(km_tab, floatfmt='.3g')}

**Regla de selección:** K-Means, k entre {C.K_SELECCION[0]} y {C.K_SELECCION[1]} (interpretable), todos los grupos con
≥ 3 municipios y la mejor silueta → **k = {k}**. La mejor silueta de todos los métodos que clasifican a todos los
municipios fue {mejor_global['metodo']} ({mejor_global['parametro']}, silueta {mejor_global['silueta']:.3f}). Se
prefiere K-Means porque clasifica a todos los municipios (DBSCAN/HDBSCAN dejan municipios sin grupo), sus
centroides son perfiles interpretables y es estable bajo remuestreo. Tabla completa: `comparacion_modelos.csv`.

![Selección de modelos](fig_seleccion_modelos.png)

## 5. Niveles de amenaza/riesgo relativo

Los grupos los forma K-Means; un índice solo los **nombra**: promedio de componentes estandarizados
(+ actividad, + magnitud, + energía, + superficialidad{', + historia' if per.get('hay_historico') else ''}{', + exposición' if per.get('hay_poblacion') else ''}, − distancia a las fuentes), escalado 0–100.

{tabla_md(niveles_tab, floatfmt='.1f')}

Variables que más separan los niveles (η²): {top_imp}.

**Municipios con perfil mixto** (su índice los ubicaría a 2 o más niveles de su grupo K-Means). K-Means agrupa por
el perfil completo de {len(vars_m)} variables, la mayoría medidas a ≤ {C.RADIO_INFLUENCIA_KM} km; el índice pesa además
la sacudida con distancia hipocentral. Se reportan en vez de reasignarlos a mano:

{tabla_md(discrepantes[['municipio', 'nivel', 'nivel_segun_indice', 'indice_riesgo', 'dist_nido_km', 'tasa_sismos_r30', 'log_flujo_energia_hipo']].rename(columns={'municipio': 'Municipio', 'nivel': 'Nivel (K-Means)', 'nivel_segun_indice': 'Nivel según índice', 'indice_riesgo': 'Índice', 'dist_nido_km': 'Dist. Nido (km)', 'tasa_sismos_r30': 'Sismos/año ≤30 km', 'log_flujo_energia_hipo': 'log flujo energía'}) if 'log_flujo_energia_hipo' in ds else discrepantes[['municipio', 'nivel', 'nivel_segun_indice', 'indice_riesgo']], floatfmt='.2f') if len(discrepantes) else 'Ninguno.'}

![Perfiles](fig_perfiles_grupos.png)

![Importancia](fig_importancia_variables.png)

![Mapa de niveles](fig_mapa_niveles.png)

## 6. Validación temporal (sin fuga de información)

La variable objetivo `obj_tasa_fuertes_futura_r50` (sismos M ≥ {C.MAG_FUERTE:g} por año a ≤ {C.RADIO_OBJETIVO_KM} km) se
calcula con un periodo **posterior** y distinto al de las variables, y no entra al modelo.

{tabla_md(val.reset_index(), floatfmt='.2f')}

- Spearman(nivel, objetivo) = **{rho_niv:.2f}** (p = {p_niv:.1e}); Spearman(índice, objetivo) = {rho_ind:.2f} (p = {p_ind:.1e}).
- Spearman(nivel, sismos M ≥ Mc futuros a ≤ 30 km) = {rho_r30:.2f} (p = {p_r30:.1e}).
- Kruskal-Wallis entre niveles: H = {kw.statistic:.1f}, p = {kw.pvalue:.1e}.
- Referencia ingenua (persistencia: la tasa M ≥ 4 pasada predice la futura): Spearman = {rho_base:.2f}. El nivel resume
  {len(vars_m)} variables y alcanza {rho_niv:.2f}, es decir, los grupos anticipan dónde siguió la actividad fuerte.

![Validación temporal](fig_validacion_temporal.png)

## 7. Zona foco (AMB + Los Santos) vs resto de Santander

{tabla_md(foco_tab.rename(columns={'municipio': 'Municipio', 'nivel': 'Nivel', 'indice_riesgo': 'Índice'}), floatfmt='.1f')}

Distribución por nivel:

{tabla_md(dist_niv.reset_index())}

Comparación de medias (prueba de Mann-Whitney):

{tabla_md(zf, floatfmt='.3g')}

## 8. Clasificación de los {len(ds)} municipios

{tabla_md(lista, floatfmt='.1f')}

Mapa interactivo: `salidas/mapa_riesgo_santander.html` (ábrelo en el navegador).

## 9. Alcance y limitaciones

- **Amenaza vs riesgo.** Riesgo = amenaza × exposición × vulnerabilidad. La vulnerabilidad (tipo de construcción)
  no está en estas fuentes: el resultado es un **riesgo relativo** entre municipios, no pérdidas absolutas.
- **Profundidad.** Los sismos del Nido (~140 km) se sienten mucho menos que uno cortical de igual magnitud; por eso
  hay variables de superficialidad y distancia a fuentes corticales, y el índice suma la superficialidad aparte.
{chr(10).join('- ' + t for t in lim_extra)}
""")

print()
print(niveles_tab[["Nivel", "Municipios", "Índice medio", "Ejemplos"]].to_string(index=False))
print()
ok(f"Mapa -> {rel(S / 'mapa_riesgo_santander.html')}")
ok(f"Reporte -> {rel(S / 'reporte_modelo.md')} · figuras fig_*.png · tablas *.csv")
