"""
Ejecuta todo el pipeline en orden:  python run_all.py

Opciones:
  --usgs        además normaliza/descarga el catálogo USGS (validación cruzada)
  --solo-usgs   PRUEBA sin catálogo SGC: construye todo con USGS (no sirve como entrega final)
"""
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
S = R / "scripts"
a = set(sys.argv[1:])
solo_usgs = "--solo-usgs" in a

pasos = [["00_preparar_territorio.py"]]
if "--usgs" in a or solo_usgs:
    pasos.append(["01_descargar_usgs.py"])
if not solo_usgs:
    pasos.append(["02_unificar_sgc.py"])
fuente = ["--fuente", "usgs"] if solo_usgs else []
pasos += [["03_sismicidad_historica.py"], ["04_poblacion_dane.py"],
          ["05_fuentes_hdbscan.py", *fuente],          # Nivel 1: fuentes sísmicas (por sismo)
          ["06_construir_variables.py", *fuente],      # variables por municipio
          ["07_modelo_clustering.py"]]                 # Nivel 2: K-Means por municipio

for p in pasos:
    r = subprocess.run([sys.executable, str(S / p[0]), *p[1:]], cwd=R)
    if r.returncode != 0:
        sys.exit(f"\n✗ Falló {p[0]}. Corrige lo indicado arriba y vuelve a correr.")
print("\n✓ Pipeline completo. Abre salidas/mapa_riesgo_santander.html y salidas/reporte_modelo.md")
