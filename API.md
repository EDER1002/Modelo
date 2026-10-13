# API del modelo · Riesgo sísmico relativo de Santander

API REST (FastAPI) que sirve el modelo **ya entrenado** y sus resultados. Responde JSON y permite CORS desde
cualquier origen, así que un frontend (React, Vue, HTML + JS, Streamlit, Power BI…) la consume directo.

## 1. Arrancar

```bash
cd Modelo
python -m venv .venv && source .venv/bin/activate     # fish: activate.fish · Windows: .venv\Scripts\activate
pip install -r requirements-api.txt                    # solo fastapi, uvicorn, pandas y numpy
python api.py                                          # -> http://localhost:8000
```

- Documentación interactiva para probar cada endpoint: **http://localhost:8000/docs**
- Puerto: variable de entorno `PORT` (por defecto 8000). Ej.: `PORT=9000 python api.py`
- Con recarga automática al editar: `uvicorn api:app --reload`
- Con Docker: `docker build -t sismos-api . && docker run -p 8000:8000 sismos-api`

La API **no re-entrena**: lee `modelo/modelo_kmeans.json` y `salidas/`. Para actualizar con más datos del SGC:
`python run_all.py` (necesita `requirements.txt` completo) y reiniciar la API.

## 2. Endpoints

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/` | Bienvenida y lista de endpoints |
| GET | `/salud` | `{"estado": "ok", ...}` |
| GET | `/modelo` | Algoritmo, k, niveles, colores, variables, periodos, métricas (silueta, estabilidad, validación) |
| GET | `/niveles` | Niveles de mayor a menor con color, nº de municipios, índice medio y lista de municipios |
| GET | `/municipios` | Los 87 municipios. Filtros: `?nivel=Muy alto`, `?zona_foco=true`, `?completo=true` (todas las variables) |
| GET | `/municipios/{nombre_o_codigo}` | Ficha: nivel, color, índice, variables, rasgos principales, validación, lat/lon. Acepta `bucaramanga`, `Girón`, `giron` o `68001` |
| GET | `/comparar?municipios=Bucaramanga,Girón,Socorro` | Comparación lado a lado de todas las variables |
| GET | `/zona-foco` | AMB + Los Santos vs resto: municipios, niveles y medias de variables clave |
| GET | `/geojson` | FeatureCollection de los 87 municipios con `nivel`, `color`, `indice_riesgo` y variables (para pintar el mapa) |
| GET | `/mapa` | Mapa interactivo HTML (sirve para un `<iframe>`) |
| GET | `/fuentes` | Fuentes sísmicas de HDBSCAN (código, tipo, centro, profundidad, nº de sismos, M máx) |
| GET | `/sismos` | Sismos M ≥ 3. Filtros: `mag_min` (def. 4), `periodo` (`variables`/`objetivo`/`todos`), `fuente_tipo`, `municipio`, `limite` |
| GET | `/variables` | Diccionario de datos (variable, descripción, unidad, fuente, uso, justificación) |
| GET | `/validacion` | Validación temporal por nivel |
| GET | `/comparacion-modelos` | Métricas de los métodos comparados e importancia de variables (η²) |
| POST | `/clasificar` | Clasifica filas nuevas con el modelo (escenarios "¿qué pasaría si…?") |
| GET | `/salidas/{archivo}` | Archivos generados: `fig_mapa_niveles.png`, `reporte_modelo.md`, `municipios_clasificados.csv`, … |

Niveles (de menor a mayor): `Muy bajo`, `Bajo`, `Medio`, `Alto`, `Muy alto`. Cada respuesta trae el `color` hex
del nivel para que el frontend use la misma paleta que el mapa y las figuras.

Errores: `404` si el municipio no existe (el mensaje sugiere nombres parecidos), `400` si un filtro es inválido.

## 3. Ejemplos de respuesta

`GET /municipios/girón`
```json
{
  "municipio": "Girón", "cod_mpio": "68307", "zona_foco": true,
  "nivel": "Muy alto", "nivel_numero": 5, "de_niveles": 5, "color": "#0d366b",
  "indice_riesgo": 79.3, "perfil_mixto": false,
  "variables": {"tasa_sismos_r30": 865.38, "tasa_fuertes_r30": 24.4, "dist_nido_km": 32.0, "...": "..."},
  "validacion": {"obj_tasa_fuertes_futura_r50": 34.9, "obj_tasa_futura_r30": 1407.2},
  "rasgos_principales": [{"variable": "tasa_fuertes_r30", "valor": 24.4, "z": 1.6,
                          "lectura": "muy por encima de la media de Santander", "descripcion": "..."}],
  "lat": 7.03, "lon": -73.21, "area_km2": 475.1
}
```
(valores ilustrativos: consulta `/docs` para la respuesta real)

`POST /clasificar`
```json
{"filas": [{"tasa_sismos_r30": 900, "tasa_fuertes_r30": 20, "dist_nido_km": 25}]}
```
→ las variables que no envíes se rellenan con la mediana de Santander:
```json
{"variables_rellenadas_con_mediana": ["tasa_m3_r30", "..."],
 "resultados": [{"nivel": "Muy alto", "color": "#0d366b", "distancia_centroide": 3.21}]}
```

## 4. Consumirla desde el frontend

JavaScript (fetch):
```js
const API = "http://localhost:8000";

// Pintar el mapa con Leaflet
const geo = await fetch(`${API}/geojson`).then(r => r.json());
L.geoJSON(geo, {
  style: f => ({ fillColor: f.properties.color, color: "#fff", weight: 1, fillOpacity: 0.8 }),
  onEachFeature: (f, layer) => layer.bindTooltip(`${f.properties.municipio}: ${f.properties.nivel}`)
}).addTo(map);

// Ficha de un municipio
const ficha = await fetch(`${API}/municipios/${encodeURIComponent("Bucaramanga")}`).then(r => r.json());
console.log(ficha.nivel, ficha.indice_riesgo);

// Ranking para una tabla o gráfico
const lista = await fetch(`${API}/municipios`).then(r => r.json());
```

Python (requests):
```python
import requests
API = "http://localhost:8000"
print(requests.get(f"{API}/municipios/Floridablanca").json()["nivel"])
print(requests.get(f"{API}/sismos", params={"mag_min": 4.5, "periodo": "objetivo"}).json()["total"])
```

Sin servidor (mismo modelo, desde Python): `from usar_modelo import ModeloSismico` (ver README §0.3).

## 5. Qué hay detrás

- **Nivel 1 · HDBSCAN** (una fila = un sismo): agrupa los sismos por posición y profundidad y encuentra las fuentes
  sísmicas (Nido de Bucaramanga, intermedias, corticales) → `/fuentes`.
- **Nivel 2 · K-Means** (una fila = un municipio): clasifica los 87 municipios con las variables de
  `/variables` (uso = modelo) → `/municipios`, `/niveles`, `/geojson`.
- **Validación**: la variable objetivo se calcula con un periodo **posterior** que no entró al modelo → `/validacion`.
- Detalle completo: `salidas/reporte_modelo.md` y `README.md`.
