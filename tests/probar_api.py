"""
Prueba rápida de la API sin levantar el servidor:  python tests/probar_api.py
(necesita fastapi y httpx: pip install -r requirements.txt)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from api import NIVELES, app  # noqa: E402

c = TestClient(app)


def ok(ruta, **kw):
    r = c.get(ruta, **kw)
    assert r.status_code == 200, (ruta, r.status_code, r.text[:300])
    return r.json()


assert ok("/salud")["estado"] == "ok"
m = ok("/modelo")
assert m["k"] == len(NIVELES) and m["n_variables"] >= 15
assert sum(m["municipios_por_nivel"].values()) == 87
assert len(ok("/municipios")) == 87
assert all(x["nivel"] == "Muy alto" for x in ok("/municipios", params={"nivel": "muy alto"}))
assert len(ok("/municipios", params={"zona_foco": True})) == 5
f = ok("/municipios/giron")
assert f["municipio"] == "Girón" and f["nivel"] in NIVELES and f["color"].startswith("#")
assert ok("/municipios/68001")["municipio"] == "Bucaramanga"
assert c.get("/municipios/Gotham").status_code == 404
assert len(ok("/comparar", params={"municipios": "Bucaramanga,Girón"})["municipios"]) == 2
assert len(ok("/niveles")) == len(NIVELES)
assert ok("/zona-foco")["comparacion"]
g = ok("/geojson")
assert g["type"] == "FeatureCollection" and len(g["features"]) == 87
assert ok("/fuentes")
s = ok("/sismos", params={"mag_min": 4, "periodo": "objetivo"})
assert s["total"] > 0 and all(x["mag"] >= 4 for x in s["sismos"])
assert ok("/variables") and ok("/validacion")["por_nivel"] and ok("/comparacion-modelos")["comparacion"]
assert c.get("/mapa").status_code == 200 and c.get("/salidas/fig_mapa_niveles.png").status_code == 200

# /clasificar reproduce el nivel de un municipio existente
completo = {x["municipio"]: x for x in ok("/municipios", params={"completo": True})}
fila = {v: completo["Girón"][v] for v in m["variables"]}
r = c.post("/clasificar", json={"filas": [fila, {"tasa_sismos_r30": 0.5}]})
assert r.status_code == 200, r.text
res = r.json()["resultados"]
assert res[0]["nivel"] == completo["Girón"]["nivel"] and res[1]["nivel"] in NIVELES

print("✓ API OK: 17 endpoints respondieron como se esperaba")
