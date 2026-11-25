# Arquitectura del Sistema y Especificación de Endpoints — Backend

Este documento describe la arquitectura de software, la organización del lago de datos, la topología de servidores y el catálogo completo de **todos los endpoints** expuestos por el backend bajo `/api/v1` y rutas raíz de servicio.

---

## Índice

1. [Arquitectura de Software por Capas](#1-arquitectura-de-software-por-capas)
2. [Arquitectura del Lago de Datos (Medallón)](#2-arquitectura-del-lago-de-datos-medallón)
3. [Topología de Servidores y Contenedores](#3-topología-de-servidores-y-contenedores)
4. [Catálogo Completo de Endpoints REST](#4-catálogo-completo-de-endpoints-rest)
   - [4.1 Salud y Documentación del Servicio](#41-salud-y-documentación-del-servicio)
   - [4.2 Catálogo INE y Datastore CKAN (`/api/v1/ine`)](#42-catálogo-ine-y-datastore-ckan-apiv1ine)
   - [4.3 Procesamiento, Análisis de Conjuntos y Mapas (`/api/v1/proceso`)](#43-procesamiento-análisis-de-conjuntos-y-mapas-apiv1proceso)
   - [4.4 Indicadores Socioeconómicos (`/api/v1/indicadores`)](#44-indicadores-socioeconómicos-apiv1indicadores)
   - [4.5 Ciencia de Datos y Análisis Estadístico (`/api/v1/analisis`)](#45-ciencia-de-datos-y-análisis-estadístico-apiv1analisis)
   - [4.6 Visualizaciones Interactivas, 3D y Blender (`/api/v1/visualizaciones`)](#46-visualizaciones-interactivas-3d-y-blender-apiv1visualizaciones)

---

## 1. Arquitectura de Software por Capas

El proyecto emplea una arquitectura modular desacoplada basada en **FastAPI**:

1. **Capa de Entrada HTTP (`main.py` y `src/api/v1/router.py`)**:
   - Configura CORS, documentación Scalar en `/docs`, salud en `/health` y redirige `/` al visor completo `/api/v1/visualizaciones/stack-completo`.
   - Agrupa los cinco enrutadores temáticos bajo el prefijo versionado `/api/v1` (manteniendo también compatibilidad directa en raíz con `include_in_schema=False`).
2. **Capa de Contratos y Validación (`src/schemas/`)**:
   - Define modelos **Pydantic v2** para parámetros de cuerpo JSON y respuestas tipadas en `ine.py`, `process.py`, `indicators.py`, `analytics.py` y `visualizations.py`.
3. **Capa de Enrutadores (`src/api/v1/endpoints/`)**:
   - `ine_router.py`: consultas CKAN con caché TTL en memoria (`180s`), verificación de caché local antes de descargar y saneamiento estricto JSON.
   - `process_router.py`: inspección de libros Excel, conversión a Parquet, agregaciones sin SQL, análisis integral de cualquier conjunto INE (`/dataset/{slug}/analizar`), mapas y exportación 3D ad-hoc.
   - `indicators_router.py`: consultas filtrables y ordenables de indicadores departamentales, municipales y catálogo de 18 fichas metodológicas.
   - `analytics_router.py`: exposición en milisegundos de resultados descriptivos, outliers, correlaciones, PCA, K-Means, proyecciones e índice IVST.
   - `visualizations_router.py`: 22 endpoints especializados que devuelven HTML interactivo o especificaciones JSON Plotly, mapas Deck.gl, mallas 3D (`GLB`/`STL`/`OBJ`/`ZIP`) y renders Blender PNG.
4. **Capa de Núcleo y Dominio (`src/core/`, `src/ingestion/`, `src/process/`, `src/analysis/`)**:
   - Lógica reutilizable separada de los controladores HTTP: normalización geopolítica (`geo_master.py`), resolución unificada de rutas desde `BACKEND_ROOT` (`config.py`), motor ETL (`etl_pipeline.py`), analítica estadística (`data_science.py`), auto-exploración de datasets (`dataset_explorer.py`), cartografía 2D (`process.py`) y modelado 3D (`relief_3d.py`).

---

## 2. Arquitectura del Lago de Datos (Medallón)

El sistema prescinde de motores RDBMS pesados apoyándose en almacenamiento columnar local en `data/`:

```text
datos.ine.gob.gt (CKAN API v3)
       |
       | Streaming HTTP + SHA-256 + manifest.jsonl
       v
[CAPA BRONCE: data/raw/]
  - Archivos XLSX, CSV, ZIP por conjunto
  - geo/departamentos_gt.geojson (geoBoundaries normalizado con códigos 01-22)
       |
       | Limpieza de encabezados, despivoteo y tipado (Polars + fastexcel)
       v
[CAPA SILVER: data/processed/]
  - demografia/  : población edad/sexo (1,158,720 filas), población depto, defunciones, nacimientos
  - economia/    : canasta_basica_mensual, ipc_regiones, ipc_poder_adquisitivo, ipc_divisiones_gasto
  - seguridad/   : necropsias_inacif_2024
  - movilidad/   : accidentes_fallecidos_lesionados_2024
  - educacion/   : matriculados_educacion_superior_2025
  - migracion/   : retornados_2024, retornados_usa_aereo_2023
  - datasets/    : Parquets cacheados por conjunto explorado dinámicamente
       |
       | Cruces demográficos y modelado multivariado (Polars, SciPy, Scikit-learn)
       v
[CAPA GOLD: data/processed/indicadores/ y data/processed/analisis/]
  - indicadores_consolidados_departamentales_2024.parquet (22 deptos x 39 vars)
  - indicadores_consolidados_municipales_2024.parquet     (340 munis x 24 vars)
  - estadisticas_descriptivas.parquet, matriz_correlaciones.parquet, clusters_departamentales.parquet
  - proyecciones_costo_vida.parquet, proyecciones_demograficas.parquet, vulnerabilidad_departamental.parquet
  - resumen_ciencia_datos.json + caché en visualizaciones/charts/, mapas/, modelos_3d/, renders_blender/
```

---

## 3. Topología de Servidores y Contenedores

### Modo Desarrollo Local

```text
Navegador (:5173) ---> Vite Dev Server (/api -> proxy localhost:8000) ---> Uvicorn/FastAPI (:8000)
                                                                                 |
                                                                                 +--> datos.ine.gob.gt (CKAN)
                                                                                 +--> data/processed/*.parquet
                                                                                 +--> blender CLI (opcional)
```

### Modo Contenedores Docker

- **Servicio principal (`docker-compose.yml` -> `api`)**: basado en `python:3.12-slim-bookworm` con `blender` y librerías OpenGL (`libgl1`, `libxi6`, `libxrender1`) preinstaladas. Monta `./data:/app/data` como volumen persistente y expone `${PORT}:${PORT}` con `healthcheck` sobre `/health`.
- **Servicio auxiliar (`docker-compose.blender.yml` -> `blender`)**: imagen ligera `debian:bookworm-slim` con Blender para ejecutar `scripts/blender_render_guatemala.py` bajo demanda si se requiere generar renders aislados fuera del servicio principal.

---

## 4. Catálogo Completo de Endpoints REST

### 4.1 Salud y Documentación del Servicio

| Método | Ruta | Descripción | Respuesta |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Redirección al portal unificado de visualizaciones | `307` hacia `/api/v1/visualizaciones/stack-completo` |
| `GET` | `/docs` | Documentación interactiva Scalar API Reference | `text/html` |
| `GET` | `/openapi.json` | Especificación OpenAPI 3.1 completa | `application/json` |
| `GET` | `/health` | Verificación de estado y versión del servicio | `{"status": "ok", "service": ..., "version": "1.1.0"}` |

---

### 4.2 Catálogo INE y Datastore CKAN (`/api/v1/ine`)

| Método | Ruta | Parámetros clave | Función |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/ine/conjuntos` | `consulta`, `grupo`, `filas` (1-1000), `inicio` | Busca conjuntos en el catálogo CKAN del INE con caché TTL en memoria y precarga de recursos. |
| `GET` | `/api/v1/ine/grupos` | — | Lista los grupos temáticos oficiales de CKAN (`total`, `grupos`). |
| `GET` | `/api/v1/ine/{slug}/recursos` | `slug` (path) | Obtiene recursos de un conjunto enriquecidos con verificación local (`descargado_local`, `tamano_bytes`, `parquet_disponible`). |
| `GET` | `/api/v1/ine/{slug}/vista-previa` | `recurso_id`, `hoja_id`, `limite` | Previsualiza filas usando archivo local en caché, Datastore CKAN o descarga única automática. |
| `GET` | `/api/v1/ine/{slug}/descargar/{resource_id}` | `forzar` (bool) | Descarga un recurso con escritura atómica `.part` y registro en `manifest.jsonl`, reutilizando copia en disco si no cambió. |
| `GET` | `/api/v1/ine/{slug}/verificar-cambio/{resource_id}` | `slug`, `resource_id` | Compara `last_modified` remoto contra el historial del manifiesto local. |
| `GET` | `/api/v1/ine/datastore/consulta` | `recurso_id`, `limite`, `desplazamiento`, `consulta` | Consulta filas de recursos indexados en CKAN Datastore. |
| `POST` | `/api/v1/ine/datastore/consulta` | JSON (`DatastoreSearchBody`) | Equivalente POST con soporte de filtros por columna y ordenamiento. |
| `GET` | `/api/v1/ine/datastore/consulta-sql` | `sql` | Ejecuta una consulta SQL directa sobre CKAN Datastore. |
| `POST` | `/api/v1/ine/datastore/consulta-sql` | JSON (`SqlQueryBody`) | Equivalente POST enviando la sentencia SQL en cuerpo JSON. |

---

### 4.3 Procesamiento, Análisis de Conjuntos y Mapas (`/api/v1/proceso`)

| Método | Ruta | Parámetros clave | Función |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/proceso/indicadores-mapa` | — | Lista indicadores departamentales disponibles en `data/processed/` para mapear y exportar en 3D. |
| `GET` | `/api/v1/proceso/dataset/{slug}/analizar` | `recurso_id`, `hoja_id`, `agrupar_por`, `columna_valor`, `forzar_descarga`, `regenerar`, `limite_muestra` | Verifica descarga local sin duplicar, convierte Excel/CSV/ZIP a Parquet, calcula estadísticas numéricas, gráficas automáticas, enlaces curados y muestra tabular. |
| `GET` | `/api/v1/proceso/dataset/{slug}/grafica` | `recurso_id`, `hoja_id`, `agrupar_por`, `columna_valor`, `indice_grafica` | Devuelve una página HTML interactiva con Plotly para la gráfica indicada del conjunto analizado. |
| `GET` | `/api/v1/proceso/hojas-excel` | `ruta_excel` o `slug`, `limite`, `hoja_id` | Inspecciona nombres de hojas de cálculo Excel y muestra primeras filas. |
| `POST` | `/api/v1/proceso/convertir` | JSON (`ExcelToParquetRequest`) | Convierte una hoja Excel de `data/raw` a formato Apache Parquet con compresión `zstd` o `snappy`. |
| `GET` | `/api/v1/proceso/resumen` | `ruta_parquet`, `agrupar_por`, `columna_filtro`, `valor_filtro`, `limite` | Agrupa y cuenta registros de cualquier Parquet procesado sin escribir SQL manual. |
| `POST` | `/api/v1/proceso/resumen` | JSON (`ParquetAggregateRequest`) | Versión POST con cuerpo JSON para agregación de Parquet. |
| `GET` | `/api/v1/proceso/mapa-html` | `ruta_parquet`, `ruta_geo`, `columna_codigo_geo`, `columna_codigo_parquet`, `columna_valor`, `esquema_color`, `capa_base`, `descargar` | Construye mapa coroplético interactivo Folium con panel lateral KPI de Guatemala. |
| `GET` | `/api/v1/proceso/mapa-plotly` | `ruta_parquet`, `columna_valor`, `formato` (`html`/`json`), `descargar` | Genera mapa coroplético Plotly Express en HTML con barra lateral o especificación JSON serializable. |
| `GET` | `/api/v1/proceso/mapa-3d-relieve` | `ruta_parquet`, `columna_valor`, `estilo_color`, `altura_max_m`, `descargar` | Genera mapa interactivo 3D extruido en Deck.gl WebGL. |
| `GET` | `/api/v1/proceso/modelo-3d-impresion` | `ruta_parquet`, `columna_valor`, `formato` (`glb`/`stl`/`zip`/`obj`), `estilo_color`, `ancho_mm`, `altura_max_mm`, `grosor_base_mm`, `forma_base` | Genera y descarga maqueta 3D de Guatemala con relieve por valor estadístico. |
| `GET` | `/api/v1/proceso/render-3d-blender` | `ruta_parquet`, `columna_valor`, `estilo_color`, `grosor_base_mm`, `ancho_px`, `alto_px`, `descargar`, `regenerar` | Renderiza el relieve 3D de Guatemala mediante Blender headless a imagen PNG. |

---

### 4.4 Indicadores Socioeconómicos (`/api/v1/indicadores`)

| Método | Ruta | Parámetros clave | Función |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/indicadores/departamentales` | `region_id` (1-8), `sort_by`, `order` (`asc`/`desc`), `limit`, `offset` | Devuelve la matriz de los 22 departamentos × 39 variables socioeconómicas (`DepartmentIndicatorsResponse`). |
| `GET` | `/api/v1/indicadores/departamentales/{codigo_o_nombre}` | `codigo_o_nombre` (`1`, `GT-GU`, `Petén`, etc.) | Ficha individual enriquecida con pertenencia a conglomerado K-Means y coordenadas `pca_1`/`pca_2`. |
| `GET` | `/api/v1/indicadores/municipales` | `depto_codigo` (1-22), `sort_by`, `order`, `limit` (máx. 340), `offset` | Consulta paginada de los 340 municipios con sus 24 variables analíticas. |
| `GET` | `/api/v1/indicadores/municipales/{muni_code}` | `muni_code` (ej. `0101`, `0901`) | Devuelve los indicadores del municipio identificado por código oficial INE de 4 dígitos. |
| `GET` | `/api/v1/indicadores/fichas-metodologicas` | `dominio` (filtro parcial opcional) | Retorna las 18 fichas metodológicas formales (objetivo, fórmula, variables, fuente, unidad, interpretación y limitaciones). |

---

### 4.5 Ciencia de Datos y Análisis Estadístico (`/api/v1/analisis`)

| Método | Ruta | Parámetros clave | Función |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analisis/descriptivo` | — | Estadísticas descriptivas de 34 variables (media, desv. estándar, mediana, Q25, Q75, IQR, mín, máx, asimetría y CV %). |
| `GET` | `/api/v1/analisis/outliers` | — | Detección de valores atípicos departamentales mediante umbrales $\|Z\| \ge 2.0$ e $1.5 \times \text{IQR}$. |
| `GET` | `/api/v1/analisis/correlaciones` | `only_significant` (bool), `min_abs_r` (0-1), `sort_by` (`pvalue`/`pearson`/`spearman`) | Matriz bivariada de 55 pares con coeficientes Pearson $r$, Spearman $\rho$, valores $p$ y fuerza asociativa. |
| `GET` | `/api/v1/analisis/pca` | — | Varianza explicada de PC1, PC2 y PC3 (80% acumulada) y matriz de cargas factoriales. |
| `GET` | `/api/v1/analisis/clusters` | — | Perfiles de los 4 conglomerados territoriales K-Means con departamentos miembros y promedios. |
| `GET` | `/api/v1/analisis/proyecciones/costo-vida` | — | Regresión lineal MCO de Canasta Básica Alimentaria (Urbana y Rural) con $R^2$ y pronóstico a 3, 6 y 12 meses. |
| `GET` | `/api/v1/analisis/proyecciones/demograficas` | — | Crecimiento absoluto y tasa geométrica anualizada 2024–2030 para los 22 departamentos. |
| `GET` | `/api/v1/analisis/vulnerabilidad` | — | Ranking departamental del Índice de Vulnerabilidad Socioeconómica Territorial (IVST, escala 0–100). |

---

### 4.6 Visualizaciones Interactivas, 3D y Blender (`/api/v1/visualizaciones`)

| Método | Ruta | Parámetros clave | Función |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/visualizaciones/catalogo` | — | Catálogo maestro de las 20 visualizaciones e indicadores disponibles. |
| `GET` | `/api/v1/visualizaciones/3d/trayectoria-demografica` | `color_por`, `formato` (`html`/`json`), `regenerar` | Gráfica 3D animada (2015–2030) de dependencia, masculinidad y % población < 15 años. |
| `GET` | `/api/v1/visualizaciones/3d/clusters-pca` | `formato`, `regenerar` | Espacio ortogonal 3D (PC1, PC2, PC3) con centroides K-Means y tamaño por IVST. |
| `GET` | `/api/v1/visualizaciones/3d/riesgo-multidimensional` | `eje_x`, `eje_y`, `eje_z`, `color_por`, `tamano_por`, `formato` | Cubo 3D personalizable de indicadores departamentales. |
| `GET` | `/api/v1/visualizaciones/3d/trayectoria-costo-vida` | `formato`, `regenerar` | Trayectoria 3D animada mensual de CBA Urbana vs Rural y brecha monetaria. |
| `GET` | `/api/v1/visualizaciones/barras/ranking-departamental` | `indicador`, `top_n`, `orden`, `orientacion`, `color_por`, `formato` | Barras comparativas por departamento con línea de promedio nacional. |
| `GET` | `/api/v1/visualizaciones/barras/ranking-municipal` | `indicador`, `depto_codigo`, `top_n`, `formato` | Barras a escala municipal sobre los 340 municipios. |
| `GET` | `/api/v1/visualizaciones/barras/estructura-demografica` | `formato`, `regenerar` | Barras apiladas al 100% de grupos etarios (<15, 15–64, 65+). |
| `GET` | `/api/v1/visualizaciones/barras/composicion-retornados` | `top_n`, `formato`, `regenerar` | Barras agrupadas de menores, adultos y mujeres retornadas. |
| `GET` | `/api/v1/visualizaciones/pastel/distribucion` | `tipo` (`clusters`, `retornados_edad`, `retornados_genero`, `educacion_genero`, `victimas_viales`, `estructura_etaria`, `jerarquia_territorial`), `depto_codigo`, `metrica`, `formato` | Gráficas de pastel, dona y sunburst jerárquico Región -> Clúster -> Departamento. |
| `GET` | `/api/v1/visualizaciones/tendencias/costo-vida` | `formato`, `regenerar` | Serie observada de CBA urbana/rural y proyección MCO a 12 meses. |
| `GET` | `/api/v1/visualizaciones/tendencias/ipc` | `vista` (`regiones`/`divisiones`/`poder_adquisitivo`), `formato` | Evolución mensual del IPC regional, 13 divisiones CCIF o pérdida del poder adquisitivo del quetzal. |
| `GET` | `/api/v1/visualizaciones/tendencias/crecimiento-demografico` | `top_n`, `formato`, `regenerar` | Curvas de expansión poblacional proyectada 2015–2030. |
| `GET` | `/api/v1/visualizaciones/correlaciones/heatmap` | `metodo` (`pearson`/`spearman`), `formato` | Mapa de calor anotado de correlaciones bivariadas. |
| `GET` | `/api/v1/visualizaciones/outliers/boxplot` | `formato`, `regenerar` | Diagramas de caja estandarizados Z-score destacando valores atípicos. |
| `GET` | `/api/v1/visualizaciones/perfil/radar` | `depto_codigo`, `comparar_con`, `formato` | Perfil radar normalizado 0–100 comparando un departamento frente a otro o a la media nacional. |
| `GET` | `/api/v1/visualizaciones/mapa/2d-folium` | `indicador`, `esquema_color`, `capa_base`, `descargar`, `regenerar` | Mapa coroplético Folium conectado directamente al indicador departamental. |
| `GET` | `/api/v1/visualizaciones/mapa/2d-plotly` | `indicador`, `formato` (`html`/`json`), `descargar`, `regenerar` | Mapa coroplético Plotly 2D con panel de KPIs nacionales y ranking. |
| `GET` | `/api/v1/visualizaciones/mapa/3d-relieve` | `indicador`, `estilo_color`, `altura_max_m`, `descargar`, `regenerar` | Relieve 3D volumétrico en Deck.gl con controles de perspectiva y rotación 360. |
| `GET` | `/api/v1/visualizaciones/mapa/modelo-3d` | `indicador`, `formato` (`glb`/`stl`/`zip`/`obj`), `estilo_color`, `ancho_mm`, `altura_max_mm`, `grosor_base_mm`, `forma_base`, `regenerar` | Exportación binaria/Wavefront de modelos 3D físicos del indicador indicado. |
| `GET` | `/api/v1/visualizaciones/mapa/render-blender` | `indicador`, `estilo_color` (`multicolor`/`negro`/`azul`), `grosor_base_mm`, `ancho_px`, `alto_px`, `descargar`, `regenerar` | Imagen PNG renderizada con Blender headless para el indicador seleccionado. |
| `GET` | `/api/v1/visualizaciones/stack-completo` | — | Visor HTML integrado del stack visual completo servido directamente desde el backend. |
