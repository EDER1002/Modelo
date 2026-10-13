# Sirve la API del modelo ya entrenado: docker build -t sismos-api . && docker run -p 8000:8000 sismos-api
FROM python:3.12-slim
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY api.py usar_modelo.py ./
COPY modelo/ modelo/
COPY salidas/ salidas/
COPY docs/diccionario_datos.csv docs/
COPY datos/processed/municipios_santander.csv datos/processed/
ENV PORT=8000
EXPOSE 8000
CMD ["python", "api.py"]
