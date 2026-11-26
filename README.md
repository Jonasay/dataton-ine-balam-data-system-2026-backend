# Balam Data Systems — Backend API (Datatón INE Guatemala 2026)

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?style=flat-square)](#5-requisitos-previos-para-backend)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.165.0-009688.svg?style=flat-square)](./docs/TECNOLOGIAS.md)
[![Apache Parquet](https://img.shields.io/badge/Formato-Apache_Parquet-4B8BBE.svg?style=flat-square)](./docs/ARQUITECTURA_Y_ENDPOINTS.md)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat-square)](#65-despliegue-con-docker-y-docker-compose)

API REST y motor de ingeniería, analítica estadística y visualización geoespacial para el **SISTEMA DE ANÁLISIS SOCIOECONÓMICO, DEMOGRÁFICO Y VULNERABILIDAD TERRITORIAL DE GUATEMALA**, construido sobre los datos abiertos oficiales del **Instituto Nacional de Estadística (INE)**.

---

## Tabla de Contenidos

1. [Índice de Documentación Especializada](#1-índice-de-documentación-especializada)
2. [Descripción del Proyecto](#2-descripción-del-proyecto)
3. [Arquitectura Resumida y Flujo de Datos](#3-arquitectura-resumida-y-flujo-de-datos)
4. [Estructura del Proyecto](#4-estructura-del-proyecto)
5. [Requisitos Previos para Backend](#5-requisitos-previos-para-backend)
6. [Instalación y Levantamiento Paso a Paso](#6-instalación-y-levantamiento-paso-a-paso)
7. [Variables de Entorno](#7-variables-de-entorno)
8. [Documentación Interactiva y Pruebas Automatizadas](#8-documentación-interactiva-y-pruebas-automatizadas)
9. [Integración con el Frontend](#9-integración-con-el-frontend)

---

## 1. Índice de Documentación Especializada

Para mantener esta guía enfocada en el levantamiento y operación general del servicio, las especificaciones extendidas se encuentran organizadas en los siguientes documentos:

| Documento | Alcance | Enlace |
| :--- | :--- | :--- |
| **Tecnologías y Licencias Open Source** | Listado completo de paquetes Python, versiones fijadas, propósito en el sistema, herramientas del sistema, entorno Antigravity / Gemini y licencias. | [docs/TECNOLOGIAS.md](./docs/TECNOLOGIAS.md) |
| **Arquitectura y Especificación de Endpoints** | Diseño por capas, arquitectura Medallón (Bronce/Silver/Gold), infraestructura de servidores y detalle completo de todos los endpoints registrados en OpenAPI (bajo `/api/v1` y `/health`). | [docs/ARQUITECTURA_Y_ENDPOINTS.md](./docs/ARQUITECTURA_Y_ENDPOINTS.md) |
| **Guía de Errores y Soluciones** | Diagnóstico y resolución de errores frecuentes al configurar entorno, pipelines de datos, CKAN remoto, Blender (Opcional) y contenedores Docker. | [docs/ERRORES_Y_SOLUCIONES.md](./docs/ERRORES_Y_SOLUCIONES.md) |

---

## 2. Descripción del Proyecto

**Balam Data Systems — Backend** el equipo centralizo la ingesta, limpieza, modelado estadístico y exposición vía REST de registros administrativos, proyecciones demográficas y series económicas del INE de Guatemala.

### Propósito principal

Proveer un servidor desacoplado de alto rendimiento capaz de consultar microdatos en formato columnar **Apache Parquet** en milisegundos, ejecutar modelos multivariados de ciencia de datos, renderizar cartografía 2D/3D y servir directamente los datos al frontend institucional y a herramientas externas.

### Problemas que resuelve

- **Ingesta resiliente desde CKAN INE**: descarga controlada desde `datos.ine.gob.gt` con validación de integridad SHA-256, detección de cambios remotos y manifiesto de auditoría (`data/raw/manifest.jsonl`) para evitar descargas duplicadas.
- **Estandarización geoespacial oficial**: normalización fonética y numérica de los 22 departamentos (códigos `01`–`22`, ISO 3166-2 `GT-XX`), los 340 municipios y las 8 regiones SEGEPLAN.
- **Construcción de indicadores con denominadores reales**: cálculo de 39 indicadores departamentales y 24 indicadores municipales cruzando eventos vitales, INACIF, PNC, IGM, IPC, CBA y educación superior contra proyecciones oficiales de población 2015–2030.
- **Analítica inferencial y vulnerabilidad territorial**: estadísticas descriptivas, detección de atípicos (`Z-score` / `IQR`), matriz de correlaciones (Pearson/Spearman), Componentes Principales (PCA), conglomerados K-Means, proyecciones MCO de Canasta Básica y cálculo del Índice de Vulnerabilidad Socioeconómica Territorial (IVST).
- **Visualizaciones 2D/3D y exportación física**: generación de gráficas Plotly HTML/JSON, mapas coropléticos Folium/Plotly, relieves volumétricos Deck.gl, mallas 3D descargables (`.STL`, `.OBJ`, `.GLB`) y renderizados en Blender headless (`.PNG`).

---

## 3. Arquitectura Resumida y Flujo de Datos

El backend sigue una arquitectura modular por dominios sobre **FastAPI** combinada con almacenamiento columnar **Medallón (Bronce, Silver y Gold)** en disco local:

```text
+-----------------------------------------------------------------------------+
|                    CLIENTES CONSUMIDORES (Frontend React)                   |
+--------------------------------------+--------------------------------------+
                                       | HTTP / JSON / HTML / GLB / STL / PNG
                                       v
+-----------------------------------------------------------------------------+
|                     CAPA DE SERVICIOS FASTAPI (main.py)                     |
|  - /api/v1/ine/*             (Catálogo CKAN INE, caché local y Datastore)   |
|  - /api/v1/proceso/*         (Conversión Parquet, análisis dataset y mapas) |
|  - /api/v1/indicadores/*     (Matrices departamentales, municipales y fichas)|
|  - /api/v1/analisis/*        (Descriptivo, outliers, PCA, K-Means, IVST)    |
|  - /api/v1/visualizaciones/* (20+ vistas 2D/3D, Deck.gl, modelos y Blender) |
+--------------------------------------+--------------------------------------+
                                       | Polars / DuckDB / GeoPandas / Trimesh
                                       v
+-----------------------------------------------------------------------------+
|                   ALMACENAMIENTO MEDALLÓN LOCAL (data/)                     |
|  - Bronce (data/raw/)      : XLSX/CSV/ZIP crudos + GeoJSON + manifest.jsonl |
|  - Silver (data/processed/): Tablas normalizadas por dominio (Parquet ZSTD) |
|  - Gold   (indicadores/ & analisis/): Matrices consolidadas y modelos JSON  |
+-----------------------------------------------------------------------------+
```

Para la especificación completa de arquitectura, flujo de servidores y referencia detallada de cada endpoint, consulta [docs/ARQUITECTURA_Y_ENDPOINTS.md](./docs/ARQUITECTURA_Y_ENDPOINTS.md).

---

## 4. Estructura del Proyecto

**Es importante resaltar que el renderizado en Blender es opcional y que se ofrece alternativas para la visualización 3D y descargas en otro formato sin la necesidad de usar esta herramienta**

```text
dataton-ine-balam-data-system-2026-backend/
├── main.py                                    # Punto de entrada FastAPI, CORS, Scalar y enrutadores
├── requirements.txt                           # Dependencias fijadas para Python 3.12
├── .env.example                               # Plantilla de variables de entorno
├── Dockerfile                                 # Imagen Python 3.12 + Blender headless
├── docker-compose.yml                         # Orquestación del servicio API y volumen de datos
├── Dockerfile.blender                         # Imagen aislada para renderizado Blender
├── docker-compose.blender.yml                 # Servicio auxiliar de renderizado 3D bajo demanda
├── docs/                                      # Documentación modular del backend
│   ├── TECNOLOGIAS.md                         # Stack tecnológico y licencias Open Source
│   ├── ARQUITECTURA_Y_ENDPOINTS.md            # Arquitectura y catálogo completo de endpoints
│   ├── EQUIPO.md                              # Equipo de desarrollo y roles
│   └── ERRORES_Y_SOLUCIONES.md                # Resolución de fallos comunes al levantar el sistema
├── scripts/
│   ├── run_etl_indicators.py                  # Descarga crudos, ejecuta ETL e indicadores 2024 o los mas recientes
│   ├── run_data_science.py                    # Ejecuta análisis estadístico y preconstruye caché visual
│   └── blender_render_guatemala.py            # Script ejecutado por Blender para iluminación PNG
├── src/
│   ├── core/
│   │   ├── config.py                          # Resolución de rutas respecto a BACKEND_ROOT y .env
│   │   └── geo_master.py                      # Catálogo oficial de 22 departamentos, regiones y GeoJSON
│   ├── ingestion/
│   │   └── ine.py                             # Cliente CKAN INE, descarga atómica, manifest y Datastore
│   ├── process/
│   │   ├── etl_pipeline.py                    # Limpieza y despivoteo multi-dominio hacia Parquet
│   │   ├── run_etl.py                         # Orquestador de generación de tablas Silver
│   │   ├── process.py                         # Procesamiento Excel/Parquet, DuckDB, Folium y Plotly
│   │   └── relief_3d.py                       # Escenas 3D Trimesh, Deck.gl WebGL y puente Blender
│   ├── analysis/
│   │   ├── indicators.py                      # Cálculo de matrices Gold departamental y municipal
│   │   ├── data_science.py                    # Descriptivo, outliers, correlaciones, PCA, clusters, IVST
│   │   ├── dataset_explorer.py                # Auto-conversión Parquet y gráficas para cualquier recurso INE
│   │   └── visualizations.py                  # Generadores Plotly 2D/3D y caché visual en disco
│   ├── schemas/                               # Contratos de entrada/salida en Pydantic v2
│   │   ├── ine.py
│   │   ├── process.py
│   │   ├── indicators.py
│   │   ├── analytics.py
│   │   └── visualizations.py
│   └── api/
│       └── v1/
│           ├── router.py                      # Enrutador maestro /api/v1
│           └── endpoints/
│               ├── ine_router.py              # Endpoints CKAN /api/v1/ine/*
│               ├── process_router.py          # Endpoints procesamiento /api/v1/proceso/*
│               ├── indicators_router.py       # Endpoints indicadores /api/v1/indicadores/*
│               ├── analytics_router.py        # Endpoints ciencia de datos /api/v1/analisis/*
│               └── visualizations_router.py   # Endpoints visuales 2D/3D /api/v1/visualizaciones/*
├── test/                                      # Suite automatizada en pytest
│   ├── test_ine.py
│   ├── test_process.py
│   ├── test_visualizations.py
│   └── test_api_analytics_indicators.py
└── data/                                      # Lago de datos local (creado en ejecución; ignorado en git)
    ├── raw/                                   # Fuentes originales descargadas y geo/departamentos_gt.geojson
    └── processed/                             # Tablas Parquet, mapas HTML, modelos 3D y renders
```

---

## 5. Requisitos Previos para Backend

- **Python**: versión **3.12** (requerido por las dependencias binarias fijadas en `requirements.txt`).
- **Git**: para clonar el repositorio.
- **Gestor de paquetes Python**: `pip` o [`uv`](https://github.com/astral-sh/uv).
- **Opcional para renders PNG en local**: **Blender** (`blender` disponible en el `PATH` del sistema), o bien Docker Engine + Docker Compose para ejecutar el entorno contenedorizado donde Blender ya viene preinstalado.

---

## 6. Instalación y Levantamiento Paso a Paso

### 6.1. Clonar el repositorio y preparar entorno

```bash
git clone https://github.com/Jonasay/dataton-ine-balam-data-system-2026-backend.git
cd dataton-ine-balam-data-system-2026-backend
```

#### Opción recomendada con entorno virtual estándar (`venv`)

En Linux / macOS:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

En Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### Alternativa rápida con `uv`

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 6.2. Configurar variables de entorno

Copia la plantilla `.env.example` y asigna los valores de configuración (especialmente `PORT` si usarás Docker Compose):

```bash
cp .env.example .env
```

Configuración base recomendada en `.env`:

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

> Nota de seguridad: la variable `GEMINI_API_KEY` debe completarse únicamente en el archivo local `.env` (ignorado por Git). Nunca guardes ni subas claves reales a `.env.example`, código fuente ni repositorios remotos. Si ejecutas localmente con Python/Uvicorn, `src/core/config.py` provee valores por defecto seguros para el resto de variables; para Docker Compose es obligatorio definir `PORT=8000` en `.env`.

### 6.3. Generar el lago de datos analítico (ETL, Indicadores y Ciencia de Datos)

Si la carpeta `data/processed/` aún no ha sido generada en tu máquina, ejecuta los dos scripts de pipeline en orden antes o al levantar la API (necesario para que `/indicadores/*`, `/analisis/*` y `/visualizaciones/*` cuenten con los archivos Parquet calculados):

```bash
python scripts/run_etl_indicators.py
python scripts/run_data_science.py
```

Qué ejecutan estos scripts:
1. `run_etl_indicators.py`: verifica los archivos requeridos en `data/raw/` (descargando desde CKAN los faltantes y asegurando `data/raw/geo/departamentos_gt.geojson`), compila las tablas normalizadas en `data/processed/` y construye las matrices departamental (39 variables) y municipal (24 variables).
2. `run_data_science.py`: calcula estadísticas descriptivas, matriz de correlaciones, componentes principales PCA, clusters K-Means, proyecciones CBA/demográficas, índice IVST y preconstruye la caché de visualizaciones.

### 6.4. Levantar el servidor de desarrollo

Con el entorno virtual activado y escuchando en el puerto **8000** (puerto esperado por el proxy del frontend):

```bash
fastapi dev main.py --port 8000
```

O directamente con Uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Una vez iniciado, verifica el estado de salud en:
- Health Check: `http://localhost:8000/health`
- Documentación interactiva Scalar: `http://localhost:8000/docs`
- Esquema OpenAPI 3.1 JSON: `http://localhost:8000/openapi.json`

### 6.5. Despliegue con Docker y Docker Compose

El `Dockerfile` construye la imagen con Python 3.12, dependencias compiladas y Blender headless incluido, y al arrancar ejecuta automáticamente `run_etl_indicators.py`, `run_data_science.py` y `uvicorn`:

1. Asegúrate de tener `.env` configurado con `PORT=8000`.
2. Construye e inicia el contenedor:

```bash
docker compose up -d --build
```

3. Verifica logs y estado del servicio:

```bash
docker compose logs -f api
```

Para ejecutar renderizados 3D con Blender de forma aislada mediante contenedor auxiliar **(Opcional)**:

```bash
docker compose -f docker-compose.blender.yml run --rm blender \
  --input data/processed/modelos_3d/modelo_3d_indice_vulnerabilidad_ivst_multicolor.glb \
  --output data/processed/renders_blender/render_guatemala.png
```

---

## 7. Variables de Entorno

Definidas en `src/core/config.py` y declaradas en `.env.example`. Todas las rutas relativas se resuelven automáticamente respecto a `BACKEND_ROOT`.

| Variable | Descripción | Obligatoria | Valor por defecto en `config.py` |
| :--- | :--- | :--- | :--- |
| `PORT` | Puerto HTTP donde escucha FastAPI/Uvicorn y mapeo de puertos Docker | Sí en Docker / No en local | `8000` |
| `BASE_PATH_INE` | URL base de la API Action v3 CKAN del INE Guatemala | No | `https://datos.ine.gob.gt/api/3/action` |
| `INE_REQUEST_TIMEOUT` | Tiempo máximo de espera (segundos) para consultas de catálogo/Datastore | No | `60` |
| `INE_DOWNLOAD_TIMEOUT` | Tiempo máximo (segundos) para descarga de archivos XLSX/CSV/ZIP en streaming | No | `300` |
| `RAW_DATA_PATH` | Ruta para almacenamiento Bronce (crudos, GeoJSON y `manifest.jsonl`) | No | `data/raw` |
| `PROCESSED_DATA_PATH` | Ruta para almacenamiento Silver/Gold (Parquet, mapas y modelos 3D) | No | `data/processed` |
| `USER_AGENT` | Cabecera HTTP enviada al portal institucional del INE | No | `datathon-ine-2026 (equipo: balam-data-systems)` |
| `GEMINI_API_KEY` | Clave de API para integraciones con Gemini (definir solo en `.env` local; nunca quemar en código o ejemplos) | No | `""` (vacía por defecto) |

---

## 8. Documentación Interactiva y Pruebas Automatizadas

- **Scalar API Explorer**: `http://localhost:8000/docs` permite inspeccionar modelos Pydantic v2 y probar peticiones directamente desde el navegador.
- **Suite de pruebas (`pytest`)**: ejecuta todas las pruebas unitarias y de integración (`test/test_ine.py`, `test/test_process.py`, `test/test_visualizations.py`, `test/test_api_analytics_indicators.py`) desde la raíz del repositorio indicando `PYTHONPATH=.`:

```bash
PYTHONPATH=. .venv/bin/pytest -v
```

---

## 9. Integración con el Frontend

El frontend en React/Vite (`dataton-ine-balam-data-system-2026-frontend`) consume esta API a través de `/api/v1/*`:
- En desarrollo local, Vite redirige `/api` hacia `http://localhost:8000`.
- En producción Docker, Nginx realiza proxy inverso de `/api/` hacia `http://api:8000/api/`.
- CORS está habilitado en `main.py` para permitir integraciones directas cuando se configura `VITE_API_BASE_URL`.
- Se recomienda usar el puerto 8000 para el backend, asi el despliegue del frontend no se ve comprometido.
