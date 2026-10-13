"""
Consumir el modelo de riesgo sísmico de Santander SIN volver a entrenarlo.

Lee lo que deja `python run_all.py` (ya viene incluido en el repositorio):
  modelo/modelo_kmeans.json            escalador + centroides de K-Means (portable, sin pickles)
  salidas/municipios_clasificados.csv  nivel, índice y variables de los 87 municipios
  docs/diccionario_datos.csv           qué significa cada variable

Desde la terminal:
  python usar_modelo.py Bucaramanga              ficha de un municipio (acepta minúsculas y sin tildes)
  python usar_modelo.py 68001                    lo mismo con el código DANE
  python usar_modelo.py --lista                  los 87 municipios con su nivel
  python usar_modelo.py --nivel "Muy alto"       municipios de un nivel
  python usar_modelo.py --resumen                datos del modelo y su validación
  python usar_modelo.py --clasificar nuevos.csv  clasifica filas nuevas (mismas columnas que el modelo)
  python usar_modelo.py Girón --json             salida en JSON (para otra aplicación)

Desde Python:
  from usar_modelo import ModeloSismico
  m = ModeloSismico()
  m.consultar("Floridablanca")      # dict con nivel, índice, variables y rasgos principales
  m.tabla()                         # DataFrame con los 87 municipios
  m.tabla(nivel="Alto")             # solo un nivel
  m.clasificar(df)                  # DataFrame con las variables del modelo -> nivel de cada fila
"""
import argparse
import difflib
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent


def _norm(txt):
    s = unicodedata.normalize("NFKD", str(txt))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


class ModeloSismico:
    def __init__(self, raiz=RAIZ):
        raiz = Path(raiz)
        ruta_modelo = raiz / "modelo" / "modelo_kmeans.json"
        ruta_tabla = raiz / "salidas" / "municipios_clasificados.csv"
        for r in (ruta_modelo, ruta_tabla):
            if not r.exists():
                raise FileNotFoundError(f"Falta {r.relative_to(raiz)}. Corre primero: python run_all.py")
        self.modelo = json.loads(ruta_modelo.read_text(encoding="utf-8"))
        self.variables = self.modelo["variables"]
        self.niveles = self.modelo["niveles_ordenados"]
        self._tabla = pd.read_csv(ruta_tabla, dtype={"cod_mpio": str})
        ruta_dic = raiz / "docs" / "diccionario_datos.csv"
        self.diccionario = pd.read_csv(ruta_dic) if ruta_dic.exists() else pd.DataFrame(
            columns=["variable", "descripcion", "unidad"])
        self._desc = dict(zip(self.diccionario["variable"], self.diccionario["descripcion"]))
        self._unidad = dict(zip(self.diccionario["variable"], self.diccionario["unidad"]))
        self._centroides = np.asarray(self.modelo["centroides"], float)
        self._media = np.array([self.modelo["media"][v] for v in self.variables])
        self._escala = np.array([self.modelo["escala"][v] for v in self.variables])

    # ------------------------------------------------------------------ consultas
    def tabla(self, nivel=None):
        """Los 87 municipios ordenados de mayor a menor amenaza (o solo los de un nivel)."""
        t = self._tabla
        if nivel is not None:
            n = {_norm(x): x for x in self.niveles}.get(_norm(nivel))
            if n is None:
                raise ValueError(f"Nivel '{nivel}' no existe. Niveles: {', '.join(self.niveles)}")
            t = t[t["nivel"] == n]
        return t.reset_index(drop=True)

    def buscar(self, nombre_o_codigo):
        """Devuelve la fila del municipio (por nombre, sin importar tildes/mayúsculas, o por código DANE)."""
        q = str(nombre_o_codigo).strip()
        t = self._tabla
        if q.isdigit():
            fila = t[t["cod_mpio"] == q.zfill(5)]
        else:
            nombres = t["municipio"].map(_norm)
            fila = t[nombres == _norm(q)]
            if fila.empty:
                fila = t[nombres.str.startswith(_norm(q))]
        if len(fila) != 1:
            sug = difflib.get_close_matches(_norm(q), t["municipio"].map(_norm).tolist(), n=4, cutoff=0.6)
            sug = [t.loc[t["municipio"].map(_norm) == s, "municipio"].iat[0] for s in sug]
            if len(fila) > 1:
                sug = fila["municipio"].tolist()
            raise ValueError(f"No encontré un único municipio para '{q}'." +
                             (f" ¿Quisiste decir: {', '.join(sug)}?" if sug else ""))
        return fila.iloc[0]

    def consultar(self, nombre_o_codigo, n_rasgos=5):
        """Ficha de un municipio: nivel, índice, variables y los rasgos que más lo distinguen."""
        f = self.buscar(nombre_o_codigo)
        x = np.array([self._transformar(v, f[v]) for v in self.variables])
        z = (x - self._media) / self._escala
        orden = np.argsort(-np.abs(z))[:n_rasgos]
        rasgos = [dict(variable=self.variables[i], valor=float(f[self.variables[i]]), z=round(float(z[i]), 2),
                       lectura=("muy por encima" if z[i] > 1 else "por encima" if z[i] > 0 else
                                "muy por debajo" if z[i] < -1 else "por debajo") + " de la media de Santander",
                       descripcion=self._desc.get(self.variables[i], "")) for i in orden]
        return dict(
            municipio=f["municipio"], cod_mpio=f["cod_mpio"], zona_foco=str(f["zona_foco"]).lower() == "true",
            nivel=f["nivel"], nivel_numero=self.niveles.index(f["nivel"]) + 1, de_niveles=len(self.niveles),
            nivel_segun_indice=f.get("nivel_segun_indice"), indice_riesgo=float(f["indice_riesgo"]),
            variables={v: float(f[v]) for v in self.variables},
            validacion={c: float(f[c]) for c in ("obj_tasa_fuertes_futura_r50", "obj_tasa_futura_r30") if c in f},
            rasgos_principales=rasgos,
        )

    # ------------------------------------------------------------------ clasificar datos nuevos
    def _transformar(self, v, valor):
        valor = float(valor) if pd.notna(valor) else self.modelo["medianas"][v]
        return np.log1p(max(valor, 0.0)) if self.modelo["transformacion"].get(v) == "log1p" else valor

    def clasificar(self, df):
        """
        Asigna un nivel a cada fila de `df`, que debe traer las columnas de `self.variables` en sus unidades
        originales (como en datos/processed/dataset_municipios.csv). Útil para recalcular con datos nuevos
        o para escenarios "¿qué pasaría si…?".
        """
        faltan = [v for v in self.variables if v not in df.columns]
        if faltan:
            raise ValueError(f"Faltan columnas: {faltan}")
        X = np.array([[self._transformar(v, r[v]) for v in self.variables] for _, r in df.iterrows()])
        Z = (X - self._media) / self._escala
        d = np.sqrt(((Z[:, None, :] - self._centroides[None]) ** 2).sum(-1))
        g = d.argmin(axis=1)
        out = df.copy()
        out["nivel_modelo"] = [self.modelo["nivel_por_centroide"][i] for i in g]
        out["distancia_centroide"] = d.min(axis=1).round(3)
        return out

    def resumen(self):
        m = self.modelo
        conteo = self._tabla["nivel"].value_counts().reindex(self.niveles[::-1]).fillna(0).astype(int)
        return (f"Modelo K-Means con k={m['k']} niveles sobre {len(self.variables)} variables por municipio\n"
                f"Catálogo {m['catalogo'].upper()} · variables {m['periodo_variables'][0]} a {m['periodo_variables'][1]}"
                f" · validación {m['periodo_objetivo'][0]} a {m['periodo_objetivo'][1]}\n"
                f"Silueta {m['silueta']:.3f} · estabilidad bootstrap (ARI) {m['estabilidad_ari']:.2f} · "
                f"Spearman nivel vs. sismos M≥4 futuros {m['spearman_validacion']:.2f}\n"
                f"Generado {m['generado']}\n\nMunicipios por nivel:\n" +
                "\n".join(f"  {n:<9} {c:>3}" for n, c in conteo.items()))


# ---------------------------------------------------------------------- terminal
def _imprimir_ficha(m, r):
    print(f"\n{r['municipio']} (DANE {r['cod_mpio']}){'  · zona foco AMB + Los Santos' if r['zona_foco'] else ''}")
    print(f"  Nivel de amenaza/riesgo relativo: {r['nivel'].upper()}  ({r['nivel_numero']} de {r['de_niveles']})")
    print(f"  Índice 0–100: {r['indice_riesgo']:.1f}", end="")
    if r.get("nivel_segun_indice") and r["nivel_segun_indice"] != r["nivel"]:
        print(f"  (por el índice solo estaría en '{r['nivel_segun_indice']}': perfil mixto, ver reporte §5)", end="")
    print("\n\n  Lo que más lo distingue:")
    for x in r["rasgos_principales"]:
        u = m._unidad.get(x["variable"], "")
        print(f"   - {x['descripcion'] or x['variable']}: {x['valor']:.3g} {u if u != '—' else ''} ({x['lectura']})")
    v = r["validacion"]
    if v:
        print(f"\n  Validación (periodo posterior, no usado para entrenar): "
              f"{v.get('obj_tasa_fuertes_futura_r50', float('nan')):.1f} sismos M≥4/año a ≤ 50 km")


def main(argv=None):
    p = argparse.ArgumentParser(description="Consulta el modelo de riesgo sísmico de Santander.")
    p.add_argument("municipio", nargs="?", help="nombre o código DANE del municipio")
    p.add_argument("--lista", action="store_true", help="todos los municipios con su nivel")
    p.add_argument("--nivel", help="municipios de un nivel (p. ej. 'Muy alto')")
    p.add_argument("--resumen", action="store_true", help="resumen del modelo")
    p.add_argument("--clasificar", metavar="CSV", help="clasifica un CSV con las variables del modelo")
    p.add_argument("--json", action="store_true", help="salida en JSON")
    a = p.parse_args(argv)
    m = ModeloSismico()
    try:
        if a.clasificar:
            out = m.clasificar(pd.read_csv(a.clasificar))
            destino = Path(a.clasificar).with_name(Path(a.clasificar).stem + "_clasificado.csv")
            out.to_csv(destino, index=False)
            print(out.to_json(orient="records", force_ascii=False) if a.json else
                  f"{len(out)} filas clasificadas -> {destino}")
        elif a.resumen:
            print(json.dumps(m.modelo, ensure_ascii=False, indent=2) if a.json else m.resumen())
        elif a.lista or a.nivel:
            t = m.tabla(a.nivel)[["cod_mpio", "municipio", "nivel", "indice_riesgo"]]
            print(t.to_json(orient="records", force_ascii=False) if a.json else t.to_string(index=False))
        elif a.municipio:
            r = m.consultar(a.municipio)
            print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else "", end="")
            if not a.json:
                _imprimir_ficha(m, r)
        else:
            p.print_help()
    except ValueError as e:
        sys.exit(f"✗ {e}")


if __name__ == "__main__":
    main()
