# Guía de Errores Frecuentes y Soluciones — Backend

Este documento reúne los problemas comunes que pueden surgir al instalar dependencias, generar los datos procesados, levantar el servidor FastAPI o desplegar mediante Docker en el backend, junto con su causa raíz y solución verificada.

---

## Índice

1. [Errores al instalar dependencias o crear el entorno virtual](#1-errores-al-instalar-dependencias-o-crear-el-entorno-virtual)
2. [Error `503` al consultar `/indicadores/*` o `/analisis/*`](#2-error-503-al-consultar-indicadores-o-analisis)
3. [Error `ModuleNotFoundError: No module named 'main'` al ejecutar `pytest`](#3-error-modulenotfounderror-no-module-named-main-al-ejecutar-pytest)
4. [Fallos en Docker Compose por variables de `.env` vacías](#4-fallos-en-docker-compose-por-variables-de-env-vacías)
5. [Error al iniciar el servidor: puerto `8000` en uso](#5-error-al-iniciar-el-servidor-puerto-8000-en-uso)
6. [Timeouts o errores `502` al consultar `/api/v1/ine/*` desde CKAN](#6-timeouts-o-errores-502-al-consultar-apiv1ine-desde-ckan)
7. [Fallos al generar renders PNG con Blender](#7-fallos-al-generar-renders-png-con-blender)
8. [Error al cargar capa geográfica `departamentos_gt.geojson`](#8-error-al-cargar-capa-geográfica-departamentos_gtgeojson)

---

## 1. Errores al instalar dependencias o crear el entorno virtual

- **Síntoma**: errores al compilar ruedas de `polars`, `pyarrow`, `pyogrio` o `trimesh`, o paquetes no encontrados al importar.
- **Causa**: versión de Python distinta a **3.12** (ej. Python 3.13/3.14 del sistema operativo) o activación incorrecta del entorno `.venv`.
- **Solución**:
  1. Crea el entorno virtual explícitamente con Python 3.12:
     ```bash
     python3.12 -m venv .venv
     source .venv/bin/activate
     ```
     O con `uv`:
     ```bash
     uv venv .venv --python 3.12
     source .venv/bin/activate
     uv pip install -r requirements.txt
     ```
  2. Verifica con `python --version` que muestre `Python 3.12.x` antes de iniciar FastAPI.

---

## 2. Error `503` al consultar `/indicadores/*` o `/analisis/*`

- **Síntoma**: el servidor responde HTTP `503` con mensajes como `"matriz departamental de indicadores no encontrada; ejecute el pipeline"` o `"estadísticas descriptivas no calculadas"`.
- **Causa**: los archivos `.parquet` de las capas Silver y Gold en `data/processed/` aún no han sido generados (el directorio `data/` está excluido del repositorio Git).
- **Solución**:
  Ejecuta ambos scripts de pipeline desde la raíz del backend con el entorno virtual activo:
  ```bash
  python scripts/run_etl_indicators.py
  python scripts/run_data_science.py
  ```
  Esto descargará las fuentes oficiales faltantes en `data/raw/`, generará las tablas Parquet consolidadas y dejará lista la caché analítica y visual.

---

## 3. Error `ModuleNotFoundError: No module named 'main'` al ejecutar `pytest`

- **Síntoma**: al correr `.venv/bin/pytest` sin variables adicionales, la fase de recolección falla indicando que no encuentra el módulo `main`.
- **Causa**: `pytest` busca módulos raíz en `sys.path`; si no se incluye el directorio actual del proyecto, los archivos dentro de `test/` no resuelven `from main import app`.
- **Solución**:
  Ejecuta siempre desde la raíz del repositorio exportando `PYTHONPATH=.`:
  ```bash
  PYTHONPATH=. .venv/bin/pytest -v
  ```
  En Windows (PowerShell):
  ```powershell
  $env:PYTHONPATH="."; .\.venv\Scripts\pytest -v
  ```

---

## 4. Fallos en Docker Compose por variables de `.env` vacías

- **Síntoma**: al ejecutar `docker compose up`, Compose rechaza la sintaxis `invalid port specification: ":"` o el contenedor de Uvicorn falla con `--port` sin argumento.
- **Causa**: el archivo `.env.example` contiene las claves vacías (`PORT=`), y `docker-compose.yml` interpola `${PORT}:${PORT}` y requiere `.env`.
- **Solución**:
  Edita el archivo `.env` en la raíz del backend asegurando como mínimo:
  ```env
  PORT=8000
  BASE_PATH_INE=https://datos.ine.gob.gt/api/3/action
  INE_REQUEST_TIMEOUT=60
  INE_DOWNLOAD_TIMEOUT=300
  RAW_DATA_PATH=data/raw
  PROCESSED_DATA_PATH=data/processed
  USER_AGENT=datathon-ine-2026 (equipo: balam-data-systems)
  GEMINI_API_KEY=<TU_GEMINI_API_KEY>
  ```
  > Nota: reemplaza `<TU_GEMINI_API_KEY>` únicamente en tu archivo local `.env` (ignorado por Git) y nunca quemes claves reales en `.env.example` ni en el código fuente.

---

## 5. Error al iniciar el servidor: puerto `8000` en uso

- **Síntoma**: `ERROR: [Errno 98] Address already in use` o fallo de enlace en Docker para el puerto `8000`.
- **Causa**: ya existe otra instancia de `fastapi`, `uvicorn` o un contenedor Docker ocupando el puerto `8000`.
- **Solución**:
  1. Verifica qué proceso usa el puerto en Linux:
     ```bash
     ss -tlnp | grep 8000
     ```
  2. Detén el proceso previo o cambia `PORT=8080` en `.env` (y actualiza `VITE_API_PROXY_TARGET=http://localhost:8080` en el `.env` del frontend si ejecutas desarrollo local).

---

## 6. Timeouts o errores `502` al consultar `/api/v1/ine/*` desde CKAN

- **Síntoma**: respuestas lentas o HTTP `502` (`ReadTimeout` o error de conexión hacia `datos.ine.gob.gt`) al buscar conjuntos o previsualizar recursos remotos no cacheados.
- **Causa**: el portal externo CKAN del INE puede presentar latencia elevada o caídas temporales. Además, algunos archivos del catálogo INE no están indexados en el módulo CKAN Datastore (por eso `datastore/consulta` responde `404`).
- **Solución**:
  - Usa los conjuntos ya descargados en caché (estado "En disco"), que evitan nuevas solicitudes remotas y se procesan localmente desde `data/raw/` y `data/processed/`.
  - Aumenta `INE_REQUEST_TIMEOUT` o `INE_DOWNLOAD_TIMEOUT` en `.env` si cuentas con conexión lenta.
  - Si un recurso no está indexado en Datastore CKAN, utiliza **Ver gráficas** (`/proceso/dataset/{slug}/analizar`) o **Vista previa** (`/ine/{slug}/vista-previa`), los cuales leen directamente el archivo XLSX/CSV descargado.

---

## 7. Fallos al generar renders PNG con Blender

- **Síntoma**: error `500` indicando que el ejecutable `blender` no se encuentra o faltan librerías de renderizado (`libGL.so.1` / entorno headless), o tiempo de espera prolongado al generar un render nuevo.
- **Causa**: en ejecución local fuera de Docker es necesario tener Blender instalado en el `PATH` del sistema operativo, además de librerías gráficas del sistema en Linux sin servidor X.
- **Solución**:
  - **En local**: instala Blender (`sudo apt install blender` en Debian/Ubuntu) o utiliza el servicio de Docker incluido (`docker compose up -d --build` o `docker compose -f docker-compose.blender.yml run --rm blender ...`), donde `Dockerfile` ya instala Blender y las dependencias `libgl1`, `libxi6`, `libxrender1`.
  - **Modelos 3D sin Blender**: la exportación y descarga de archivos `.STL`, `.OBJ`, `.GLB` y `.ZIP` se realiza íntegramente en Python con **Trimesh** y **mapbox-earcut**, por lo que funciona incluso sin tener Blender instalado.

---

## 8. Error al cargar capa geográfica `departamentos_gt.geojson`

- **Síntoma**: error `404` o fallo en mapas 2D/3D si falta `data/raw/geo/departamentos_gt.geojson`.
- **Causa**: la primera ejecución offline sin conexión a GitHub/geoBoundaries no pudo descargar automáticamente el archivo GeoJSON base.
- **Solución**:
  Con conexión a internet, ejecuta:
  ```bash
  python -c "from src.core.geo_master import ensure_guatemala_geojson; print(ensure_guatemala_geojson())"
  ```
  El sistema descargará, normalizará los códigos `01`–`22` y guardará la capa en `data/raw/geo/departamentos_gt.geojson`.
