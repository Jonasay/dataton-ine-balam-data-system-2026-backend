# Tecnologías y Licencias Open Source — Backend

Este documento detalla la pila tecnológica del backend de **Balam Data Systems**, las versiones fijadas en [`requirements.txt`](../requirements.txt), su función dentro de los distintos módulos del sistema y el estatus de sus licencias Open Source.

---

## Índice

1. [Resumen del Ecosistema Tecnológico](#1-resumen-del-ecosistema-tecnológico)
2. [Framework Web, Servidores y Validación](#2-framework-web-servidores-y-validación)
3. [Ingeniería de Datos y Procesamiento ETL](#3-ingeniería-de-datos-y-procesamiento-etl)
4. [Ciencia de Datos, Estadística y Econometría](#4-ciencia-de-datos-estadística-y-econometría)
5. [Cartografía Geoespacial y Visualización 2D / 3D](#5-cartografía-geoespacial-y-visualización-2d--3d)
6. [Cliente HTTP, Configuración y Pruebas](#6-cliente-http-configuración-y-pruebas)
7. [Infraestructura, Contenedores y Motor Blender](#7-infraestructura-contenedores-y-motor-blender)
8. [Entorno de Desarrollo e Inteligencia Artificial](#8-entorno-de-desarrollo-e-inteligencia-artificial)
9. [Compatibilidad de Licencias Open Source](#9-compatibilidad-de-licencias-open-source)

---

## 1. Resumen del Ecosistema Tecnológico

El backend está desarrollado íntegramente sobre software libre y Open Source bajo **Python 3.12**, con procesamiento tabular en memoria sobre **Apache Parquet** (sin requerir motor de base de datos SQL externo en producción). Todas las bibliotecas centrales utilizan licencias permisivas (**MIT**, **BSD-2-Clause**, **BSD-3-Clause**, **Apache-2.0**, **ISC**), y el motor externo de renderizado **Blender** se ejecuta como proceso CLI aislado bajo licencia **GPL-2.0-or-later**.

---

## 2. Framework Web, Servidores y Validación

| Tecnología | Versión | Propósito en el proyecto | Licencia Open Source |
| :--- | :--- | :--- | :--- |
| **FastAPI** | `0.165.0` | Framework REST asíncrono/síncrono con generación OpenAPI 3.1 y enrutadores modulares por dominio | MIT |
| **Starlette** | `1.10.0` | Capa ASGI subyacente para respuestas HTTP, `FileResponse`, `HTMLResponse` y middleware CORS | BSD-3-Clause |
| **Uvicorn** | `0.54.0` | Servidor ASGI de alto rendimiento para ejecución en desarrollo y producción | BSD-3-Clause |
| **uvloop** | `0.23.0` | Bucle de eventos optimizado en sistemas Unix/Linux para concurrencia HTTP | MIT / Apache-2.0 |
| **Pydantic / pydantic-core** | `2.14.4` / `2.50.5` | Definición y validación estricta de esquemas de respuesta y cuerpos de petición JSON | MIT |
| **Scalar FastAPI** | `1.11.0` | Interfaz gráfica interactiva de documentación API disponible en `/docs` | MIT |
| **FastAPI CLI** | `0.0.34` | Utilidad de línea de comandos (`fastapi dev`) para desarrollo local | MIT |

---

## 3. Ingeniería de Datos y Procesamiento ETL

| Tecnología | Versión | Propósito en el proyecto | Licencia Open Source |
| :--- | :--- | :--- | :--- |
| **Polars** | `2.1.0` | Motor columnar principal de ETL, consolidación de indicadores y agregaciones de alto rendimiento sobre Parquet | MIT |
| **DuckDB** | `2.0.1` | Consultas analíticas en memoria directamente sobre archivos `.parquet` para cruces geoespaciales | MIT |
| **PyArrow** | `26.0.1` | Serialización columnar Apache Parquet y compresión ZSTD/Snappy | Apache-2.0 |
| **fastexcel** | `0.21.0` | Lectura rápida (basada en Rust/calamine) de hojas de cálculo Excel `.xlsx`/`.xls` publicadas por el INE | MIT |
| **XlsxWriter** | `3.3.4` | Soporte auxiliar para escritura y manipulación tabular Excel | BSD-2-Clause |
| **Pandas** | `3.1.1` | Manipulación tabular en interoperabilidad con GeoPandas, SciPy y Scikit-learn | BSD-3-Clause |
| **NumPy** | `2.5.5` | Cómputo numérico matricial, normalización Min-Max y transformaciones estadísticas | BSD-3-Clause |

---

## 4. Ciencia de Datos, Estadística y Econometría

| Tecnología | Versión | Propósito en el proyecto | Licencia Open Source |
| :--- | :--- | :--- | :--- |
| **SciPy** | `1.18.1` | Correlaciones de Pearson y Spearman, valores $p$ de dos colas y regresión lineal MCO para Canasta Básica | BSD-3-Clause |
| **scikit-learn** | `1.9.1` | Estandarización (`StandardScaler`), Análisis de Componentes Principales (`PCA`) y agrupamiento `KMeans` | BSD-3-Clause |
| **Statsmodels** | `0.15.0` | Soporte econométrico y validación estadística de modelos lineales | BSD-3-Clause |

---

## 5. Cartografía Geoespacial y Visualización 2D / 3D

| Tecnología | Versión | Propósito en el proyecto | Licencia Open Source |
| :--- | :--- | :--- | :--- |
| **GeoPandas** | `1.2.0` | Carga de límites departamentales GeoJSON/Shapefile, reproyección CRS a WGS84 y unión con datos Parquet | BSD-3-Clause |
| **Shapely** | `2.2.0` | Operaciones geométricas poligonales utilizadas en cartografía y extrusión tridimensional de departamentos | BSD-3-Clause |
| **Pyogrio** | `0.13.0` | Motor de E/S vectorizado GDAL/OGR para lectura rápida de capas GeoJSON | MIT |
| **Pyproj** | `3.8.0` | Transformación y proyección métrica/geográfica de coordenadas | MIT |
| **Folium** | `1.0.0` | Generación de mapas coropléticos interactivos Leaflet exportables a HTML multicapa | MIT |
| **mapclassify** | `2.11.0` | Clasificación cuantitativa de coropletas mediante quiebres naturales (Natural Breaks) | BSD-3-Clause |
| **Plotly** | `7.1.0` | Gráficas interactivas 2D/3D (trayectorias animadas, radar, heatmaps, boxplots, sunburst y mapas coropléticos) | MIT |
| **Trimesh** | `5.2.2` | Extrusión volumétrica 3D de polígonos departamentales y exportación a `.GLB`, `.STL`, `.OBJ` y packs `.ZIP` | MIT |
| **mapbox-earcut** | `2.1.0` | Triangulación poligonal rápida para mallas 3D válidas orientadas a impresión y Blender | ISC |
| **Pillow** | `13.0.0` | Procesamiento de imágenes y validación auxiliar de activos gráficos | MIT-CMU |
| **Deck.gl (CDN en HTML)** | `8.9.x` | Renderizado WebGL en navegador del relieve volumétrico 3D interactivo generado por `src/process/relief_3d.py` | MIT |

---

## 6. Cliente HTTP, Configuración y Pruebas

| Tecnología | Versión | Propósito en el proyecto | Licencia Open Source |
| :--- | :--- | :--- | :--- |
| **Requests** | `2.34.2` | Consumo de la API CKAN del INE (`datos.ine.gob.gt`) y descargas binarias en streaming con reintentos | Apache-2.0 |
| **HTTPX** | `0.28.1` | Cliente HTTP empleado internamente por `TestClient` de FastAPI/Starlette durante las pruebas | BSD-3-Clause |
| **python-dotenv** | `1.2.4` | Carga de variables de entorno desde el archivo `.env` localizado en `BACKEND_ROOT` | BSD-3-Clause |
| **pytest** | `9.2.0` | Framework de pruebas unitarias e integración para rutas, ingesta, ETL y visualizaciones | MIT |

---

## 7. Infraestructura, Contenedores y Motor Blender

| Componente | Versión / Base | Propósito en el proyecto | Licencia Open Source |
| :--- | :--- | :--- | :--- |
| **Python Runtime** | `3.12` (`python:3.12-slim-bookworm`) | Entorno de ejecución oficial en desarrollo y contenedor Docker | PSF License |
| **Blender Headless** | Empaquetado Debian Bookworm / CLI | Renderizado fotorrealista por lotes de escenas `.glb` hacia imágenes `.png` vía `scripts/blender_render_guatemala.py` | GPL-2.0-or-later (invocado como subproceso externo) |
| **Docker / Docker Compose** | Compose V2 | Empaquetado reproducible de la API, volúmenes persistentes `data/` y servicio auxiliar de Blender | Apache-2.0 |

---

## 8. Entorno de Desarrollo e Inteligencia Artificial

El desarrollo del backend contó con herramientas de ingeniería asistida por inteligencia artificial, separadas de las dependencias Open Source empaquetadas en el entorno de ejecución:

| Herramienta / Agente | Rol en el proyecto | Alcance y buenas prácticas | Naturaleza / Licencia |
| :--- | :--- | :--- | :--- |
| **Antigravity** | Entorno de desarrollo integrado (IDE) agéntico | Utilizado para el diseño de arquitectura, implementación de endpoints, depuración, ejecución de pruebas `pytest` y mantenimiento de documentación | Herramienta propietaria de desarrollo (Google Deepmind); no se distribuye en el runtime |
| **Gemini** | Agente de inteligencia artificial | Empleado como agente de IA durante el ciclo de desarrollo para análisis de datos CKAN, refactorización, generación de pruebas y soporte técnico | Modelo y servicio propietario de Google; cualquier clave `GEMINI_API_KEY` se gestiona exclusivamente en `.env` local (nunca quemada en el código) |

---

## 9. Compatibilidad de Licencias Open Source

- Todas las dependencias en tiempo de ejecución importadas dentro de `src/` utilizan licencias Open Source permisivas (**MIT**, **BSD-2-Clause**, **BSD-3-Clause**, **Apache-2.0**, **ISC** y **PSF**).
- **Blender** no se enlaza como biblioteca dentro del código Python de la API: se ejecuta mediante `subprocess` con un script independiente (`scripts/blender_render_guatemala.py`) que interactúa a través de archivos temporales `.glb` y `.png`, manteniendo separación de procesos y total compatibilidad de distribución.
- Las fuentes de datos geográficos base provienen del repositorio abierto **geoBoundaries** (CC-BY 4.0) y las estadísticas oficiales del portal público de Datos Abiertos del **INE Guatemala**.
