# Dataton INE 2026 - Balam Data Systems (Backend)

Servicio backend desarrollado con Python 3.12 y FastAPI para consultar el catalogo de datos abiertos (CKAN) del Instituto Nacional de Estadistica (INE) de Guatemala, ejecutar pipelines ETL hacia formato Parquet, calcular indicadores socioeconomicos departamentales y municipales, generar visualizaciones 2D/3D y responder consultas ciudadanas en lenguaje natural mediante un motor seguro Text-to-JSON.

## Tecnologias y Herramientas

* **Backend y API:** Python 3.12, FastAPI, Uvicorn, Pydantic v2, python-dotenv, SlowAPI (`rate limiting`), Cachetools (`TTLCache`).
* **Motor de Busqueda con IA (Text-to-JSON):** Google GenAI SDK (`google-genai`) con `gemini-2.5-flash` y salidas estructuradas (`response_schema`).
* **Documentacion API:** Scalar (`scalar-fastapi`) disponible en `/docs`.
* **Consumo de Datos INE:** Requests sobre la API CKAN v3 (`package_search`, `package_show`, `group_list`, `datastore_search`, `datastore_search_sql`) con registro en `manifest.jsonl`.
* **Procesamiento y Ciencia de Datos:** Polars, DuckDB, FastExcel, PyArrow, Pandas, NumPy, SciPy, Scikit-Learn (PCA, K-Means).
* **Geoespacial y Visualizacion 2D/3D:** GeoPandas, Shapely, Pyogrio, PyProj, Folium, MapClassify, Plotly, Deck.gl, Trimesh y Blender en modo consola.
* **Infraestructura y Pruebas:** Docker, Docker Compose, Pytest, HTTPX.
* **Entorno de Desarrollo:** Antigravity IDE, con apoyo de Gemini y Claude para arquitectura, revision de codigo y pruebas.

## Estructura del Proyecto

```text
dataton-ine-balam-data-system-2026-backend/
├── main.py                                  # Punto de entrada FastAPI, CORS, Rate Limiter y /docs
├── Dockerfile                               # Imagen Python 3.12 con soporte geoespacial y Blender
├── docker-compose.yml                       # Ejecucion unificada leyendo variables desde .env
├── .dockerignore                            # Exclusiones del contexto de Docker
├── .env.example                             # Plantilla de variables de entorno (sin datos quemados)
├── requirements.txt                         # Dependencias del proyecto
├── scripts/
│   ├── run_etl_indicators.py                # Descarga de fuentes INE, ETL Parquet y calculo de indicadores
│   ├── run_data_science.py                  # Pipeline estadistico (PCA, clusters, proyecciones y cache visual)
│   └── blender_render_guatemala.py          # Renderizado 3D en modo consola con Blender
├── src/
│   ├── core/
│   │   ├── config.py                        # Variables base del servidor, rutas y cliente INE
│   │   ├── ai_config.py                     # Configuracion validada del modulo IA (SecretStr, TTL, rate limit)
│   │   └── geo_master.py                    # Catalogo oficial de departamentos, regiones y GeoJSON
│   ├── schemas/
│   │   ├── ai_search.py                     # Contratos de entrada, enrutamiento estructurado y salida publica IA
│   │   ├── ine.py                           # Esquemas para consultas CKAN
│   │   ├── process.py                       # Esquemas de conversion Parquet y mapas
│   │   ├── indicators.py                    # Esquemas de indicadores departamentales, municipales y fichas
│   │   ├── analytics.py                     # Esquemas de correlaciones, PCA, clusters y vulnerabilidad
│   │   └── visualizations.py                # Esquemas del catalogo visual
│   ├── repositories/
│   │   └── statistics_repository.py         # Acceso en solo lectura (Polars scan_parquet) para el buscador IA
│   ├── services/
│   │   ├── query_cache.py                   # Cache en memoria con TTL y normalizacion de texto
│   │   ├── gemini_client.py                 # Cliente Google GenAI (gemini-2.5-flash, temperature=0.0)
│   │   └── ai_search_service.py             # Orquestacion del buscador IA y filtros de privacidad
│   ├── ingestion/
│   │   └── ine.py                           # Cliente CKAN INE y descargas auditadas
│   ├── process/
│   │   ├── etl_pipeline.py                  # Limpieza y normalizacion hacia Parquet
│   │   ├── run_etl.py                       # Ejecutor consolidado del ETL
│   │   ├── process.py                       # Utilidades Excel/Parquet y mapas 2D
│   │   └── relief_3d.py                     # Mapas 3D en Deck.gl y mallas Trimesh
│   ├── analysis/
│   │   ├── indicators.py                    # Calculo de tasas departamentales y municipales
│   │   ├── data_science.py                  # Estadistica descriptiva, correlaciones, PCA, K-Means e IVST
│   │   └── visualizations.py                # Generacion de graficas Plotly 2D/3D y cache
│   └── api/
│       └── v1/
│           ├── router.py                    # Enrutador principal (/api/v1)
│           └── endpoints/
│               ├── ai_search_router.py      # POST /api/v1/busqueda-ia
│               ├── ine_router.py            # Rutas de consulta y descarga CKAN INE
│               ├── process_router.py        # Rutas de conversion y mapas base
│               ├── indicators_router.py     # Rutas de indicadores y fichas metodologicas
│               ├── analytics_router.py      # Rutas de ciencia de datos y vulnerabilidad
│               └── visualizations_router.py # Rutas de graficas interactivas, mapas 3D y Blender
└── test/
    ├── test_ai_search.py                    # Pruebas unitarias y de seguridad del buscador IA
    ├── test_ine.py                          # Pruebas unitarias del modulo INE
    ├── test_process.py                      # Pruebas unitarias de procesamiento
    └── test_visualizations.py               # Pruebas unitarias del modulo de visualizaciones
```

## Variables de Entorno (`.env`)

El sistema lee toda su configuracion desde el archivo `.env` sin valores fijos de conexion o credenciales en el codigo.

1. Copia `.env.example` a `.env`:

   * **Linux / macOS:**
     ```bash
     cp .env.example .env
     ```
   * **Windows (PowerShell):**
     ```powershell
     Copy-Item .env.example .env
     ```
   * **Windows (CMD):**
     ```cmd
     copy .env.example .env
     ```

2. Configura las variables en `.env`:

   ```env
   PORT=
   BASE_PATH_INE=
   INE_REQUEST_TIMEOUT=
   INE_DOWNLOAD_TIMEOUT=
   RAW_DATA_PATH=
   PROCESSED_DATA_PATH=
   USER_AGENT=
   GEMINI_API_KEY=
   GEMINI_MODEL=
   AI_SEARCH_CACHE_TTL_SECONDS=
   AI_SEARCH_CACHE_MAXSIZE=
   AI_SEARCH_RATE_LIMIT=
   ```

| Variable | Uso |
| :--- | :--- |
| `PORT` | Puerto TCP donde escucha Uvicorn y que expone Docker Compose. |
| `BASE_PATH_INE` | URL base de la API CKAN v3 del INE. |
| `INE_REQUEST_TIMEOUT` | Tiempo limite en segundos para consultas de metadatos a CKAN. |
| `INE_DOWNLOAD_TIMEOUT` | Tiempo limite en segundos para descargas de archivos crudos. |
| `RAW_DATA_PATH` | Ruta relativa para archivos descargados y capas geograficas (`data/raw`). |
| `PROCESSED_DATA_PATH` | Ruta relativa para tablas Parquet, analisis y cache visual (`data/processed`). |
| `USER_AGENT` | Cabecera `User-Agent` enviada en las peticiones HTTP hacia el INE. |
| `GEMINI_API_KEY` | Clave de API de Google Gemini requerida para el endpoint `/api/v1/busqueda-ia`. |
| `GEMINI_MODEL` | Modelo de Gemini a utilizar (si se deja vacio usa `gemini-2.5-flash`). |
| `AI_SEARCH_CACHE_TTL_SECONDS` | Tiempo de vida en segundos para las respuestas en cache del buscador IA (por defecto `300`). |
| `AI_SEARCH_CACHE_MAXSIZE` | Cantidad maxima de consultas almacenadas en memoria (por defecto `256`). |
| `AI_SEARCH_RATE_LIMIT` | Limite de peticiones por IP para el buscador IA (por defecto `15/minute`). |

## Modulo de Busqueda Inteligente con IA (`POST /api/v1/busqueda-ia`)

Este modulo permite a ciudadanos y analistas realizar preguntas en lenguaje natural sobre las estadisticas oficiales procesadas en el sistema, traduciendo la pregunta a un plan de consulta estructurado (**Text-to-JSON**) sin exponer la base de datos al modelo externo.

### Flujo de Funcionamiento

1. **Validacion y Sanitizacion (`AISearchRequest`):** Limpia caracteres de control y espacios multiples, exigiendo una longitud entre `3` y `300` caracteres y rechazando campos adicionales (`422 Unprocessable Entity`).
2. **Control de Tasa por IP (`SlowAPI`):** Limita el volumen de consultas por direccion IP (ej. `15/minute`), devolviendo `429 Too Many Requests` ante uso excesivo.
3. **Filtro de Privacidad por Diseno:** Antes de llamar al modelo, verifica que la consulta no solicite datos personales (DPI/CUI, NIT, pasaporte, direcciones particulares o nombres de individuos). Si detecta una solicitud personal, bloquea la consulta y devuelve un aviso neutro con `datos: []`.
4. **Cache en Memoria (`AIQueryCache`):** Normaliza la pregunta a minusculas sin espacios redundantes. Si ya fue consultada dentro de la ventana TTL, responde de inmediato desde memoria sin consumir cuota de Gemini.
5. **Enrutamiento Estructurado (`GeminiRoutingClient`):** Envia unicamente el texto de la consulta a `gemini-2.5-flash` con `temperature=0.0` y `response_schema=AISearchRoutingPlan`. El modelo nunca recibe los datos del INE ni genera SQL o codigo Python; solo selecciona valores dentro de listas cerradas (`Literal[...]`) que corresponden a las 13 tablas agregadas reales del sistema.
6. **Guardrail de Dominio:** Si la pregunta trata temas ajenos al portal (deportes, clima, politica, noticias o indicadores no publicados), responde con un mensaje informativo indicando los temas disponibles y `datos: []`.
7. **Consulta en Solo Lectura (`StatisticsRepository`):** Ejecuta el plan con `polars.scan_parquet(...)` aplicando filtros parametrizados y limite de filas, renombra las columnas a etiquetas legibles sin filtrar rutas internas `.parquet` y adjunta en `visualizacion_url` la ruta de grafica o mapa interactivo relacionada.

### Ejemplo de Uso

**Peticion (`POST /api/v1/busqueda-ia`):**
```json
{
  "consulta": "¿Cuáles son los 3 departamentos con mayor índice de vulnerabilidad territorial?"
}
```

**Respuesta (`200 OK`):**
```json
{
  "mensaje": "Se muestran los departamentos con mayor índice de vulnerabilidad territorial.",
  "datos": [
    {
      "posicion": 1,
      "departamento": "Huehuetenango",
      "region": "Noroccidente",
      "indice_vulnerabilidad_territorial": 90.56,
      "nivel_vulnerabilidad": "Crítica"
    },
    {
      "posicion": 2,
      "departamento": "Quiché",
      "region": "Noroccidente",
      "indice_vulnerabilidad_territorial": 85.9,
      "nivel_vulnerabilidad": "Crítica"
    },
    {
      "posicion": 3,
      "departamento": "San Marcos",
      "region": "Suroccidente",
      "indice_vulnerabilidad_territorial": 85.01,
      "nivel_vulnerabilidad": "Crítica"
    }
  ],
  "visualizacion_url": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=indice_vulnerabilidad_ivst&top_n=3&orden=desc"
}
```

### Codigos de Respuesta del Buscador IA

* `200 OK`: Consulta resuelta (incluye tambien respuestas controladas cuando no hay coincidencias, temas fuera de dominio o bloqueo de privacidad, devolviendo `datos: []`).
* `422 Unprocessable Entity`: Consulta vacia, menor a 3 caracteres, mayor a 300 caracteres o JSON con propiedades no permitidas.
* `429 Too Many Requests`: Limite de consultas por minuto superado desde la misma IP.
* `503 Service Unavailable`: Falta configurar `GEMINI_API_KEY` o fallo temporal de comunicacion con el proveedor externo (sin exponer trazas internas).

## Ejecucion con Docker Compose

Con Docker activo y el archivo `.env` configurado en la raiz del proyecto, ejecuta:

```bash
docker compose up --build
```

Al iniciar por primera vez, el contenedor ejecuta automaticamente:
1. `python scripts/run_etl_indicators.py` (descarga fuentes faltantes, genera Parquets y calcula indicadores).
2. `python scripts/run_data_science.py` (ejecuta PCA, conglomerados, proyecciones y cache de mapas/graficas).
3. `uvicorn main:app --host 0.0.0.0 --port ${PORT}`.

Para correr en segundo plano:
```bash
docker compose up -d --build
```

Comandos utiles:
* Ver registros: `docker compose logs -f api`
* Ejecutar pruebas dentro del contenedor: `docker compose exec api pytest -v`
* Detener servicios: `docker compose down`

## Instalacion Local en Desarrollo

```bash
git clone <URL_DEL_REPOSITORIO>
cd dataton-ine-balam-data-system-2026-backend
git checkout develop
```

Crear entorno virtual e instalar dependencias:

* **Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  ```
* **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  ```

Generar datos procesados (primera vez) y levantar el servidor:
```bash
python scripts/run_etl_indicators.py
python scripts/run_data_science.py
uvicorn main:app --reload --port <PORT>
```

## Rutas Principales y Documentacion

* **Scalar UI (Documentacion interactiva):** `http://localhost:<PORT>/docs`
* **Portal Visual Integrado:** `http://localhost:<PORT>/api/v1/visualizaciones/stack-completo`
* **Estado de Salud:** `http://localhost:<PORT>/health`
* **Busqueda con IA:** `POST http://localhost:<PORT>/api/v1/busqueda-ia`
* **Indicadores Oficiales:** `/api/v1/indicadores/departamentales`, `/api/v1/indicadores/municipales`, `/api/v1/indicadores/metodologia`
* **Ciencia de Datos:** `/api/v1/analisis/descriptivo`, `/api/v1/analisis/correlaciones`, `/api/v1/analisis/pca`, `/api/v1/analisis/clusters`, `/api/v1/analisis/vulnerabilidad`
* **Catalogo INE (CKAN):** `/api/v1/ine/conjuntos`, `/api/v1/ine/grupos`, `/api/v1/ine/{slug}/vista-previa`

## Pruebas Unitarias

Para ejecutar todas las pruebas unitarias (`test_ai_search.py`, `test_ine.py`, `test_process.py` y `test_visualizations.py`):

```bash
pytest -v
```
