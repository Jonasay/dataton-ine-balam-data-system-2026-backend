from __future__ import annotations

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
import polars as pl

from src.core.config import PROCESSED_DATA_DIR
from src.core.geo_master import normalize_department
from src.schemas.indicators import (
    DepartmentIndicatorsResponse,
    MunicipalIndicatorsResponse,
    MethodologyCatalogResponse,
)

router = APIRouter(
    prefix="/indicadores",
    tags=["Indicadores Socioeconómicos - Sistema Oficial"]
)

DATA_PROCESSED = PROCESSED_DATA_DIR
INDICATORS_DIR = DATA_PROCESSED / "indicadores"
DEPT_FILE = INDICATORS_DIR / "indicadores_consolidados_departamentales_2024.parquet"
MUP_FILE = INDICATORS_DIR / "indicadores_consolidados_municipales_2024.parquet"


# catalogo formal de las fichas metodologicas
METHODOLOGY_CARDS: List[Dict[str, Any]] = [
    {
        "id_indicador": "TBN",
        "nombre": "Tasa Bruta de Natalidad",
        "dominio": "Demografía",
        "objetivo": "Cuantificar la frecuencia relativa de nacimientos vivos ocurridos respecto a la población total.",
        "formula": "(Nacimientos Registrados / Población Proyectada Total) * 1,000",
        "variables_requeridas": ["nacimientos_total", "poblacion_total"],
        "fuente": "INE - Estadísticas Vitales de Nacimientos 2025 y Proyecciones de Población 2015-2030",
        "unidad_medida": "Nacidos vivos por cada 1,000 habitantes",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Refleja el dinamismo reproductivo y demanda inmediata en servicios materno-infantiles.",
        "limitaciones": "Inscripciones extemporáneas en RENAP y concentración de partos en cabeceras departamentales."
    },
    {
        "id_indicador": "TBM",
        "nombre": "Tasa Bruta de Mortalidad",
        "dominio": "Demografía",
        "objetivo": "Estimar el volumen general de defunciones por todas las causas en una población.",
        "formula": "(Defunciones Totales / Población Proyectada Total) * 1,000",
        "variables_requeridas": ["defunciones_total", "poblacion_total"],
        "fuente": "INE - Estadísticas Vitales de Defunciones 2024 y Proyecciones 2015-2030",
        "unidad_medida": "Defunciones por cada 1,000 habitantes",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Impacto global de la mortalidad general sobre la estructura poblacional.",
        "limitaciones": "No estandarizada por edad; departamentos jóvenes tienen tasas brutas más bajas."
    },
    {
        "id_indicador": "TCN",
        "nombre": "Tasa de Crecimiento Natural de la Población",
        "dominio": "Demografía",
        "objetivo": "Medir el ritmo neto anual de expansión vegetativa de la población.",
        "formula": "TBN - TBM = ((Nacimientos - Defunciones) / Población Total) * 1,000",
        "variables_requeridas": ["nacimientos_total", "defunciones_total", "poblacion_total"],
        "fuente": "INE - Estadísticas Vitales 2024-2025 y Proyecciones 2015-2030",
        "unidad_medida": "Saldo vegetativo por cada 1,000 habitantes",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Dinamismo biológico de reemplazo generacional y presión sobre empleo futuro.",
        "limitaciones": "No incluye el saldo neto de emigración internacional."
    },
    {
        "id_indicador": "RDD",
        "nombre": "Razón de Dependencia Demográfica",
        "dominio": "Demografía",
        "objetivo": "Medir la carga económica de dependientes (<15 y >=65 años) sobre la población productiva (15-64).",
        "formula": "((Población <15 + Población >=65) / Población 15-64) * 100",
        "variables_requeridas": ["pob_menor_15", "pob_65_mas", "pob_15_64"],
        "fuente": "INE - Estimaciones y Proyecciones de Población por Sexo y Edad (2015-2030)",
        "unidad_medida": "Porcentaje (%)",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Evalúa la presencia o agotamiento del bono demográfico.",
        "limitaciones": "Asume inactividad estricta en menores de 15 años sin reflejar trabajo infantil informal."
    },
    {
        "id_indicador": "NECROPSIAS",
        "nombre": "Tasa de Necropsias Médico-Legales INACIF",
        "dominio": "Seguridad y Violencia",
        "objetivo": "Cuantificar la incidencia de muertes de causa externa o violentas sujetas a peritaje forense.",
        "formula": "(Total Necropsias INACIF / Población Total) * 100,000",
        "variables_requeridas": ["necropsias_total", "poblacion_total"],
        "fuente": "INACIF / INE - Base de Datos de Necropsias del Servicio Médico Forense 2024",
        "unidad_medida": "Necropsias por cada 100,000 habitantes",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Indicador proxy verificable de violencia letal, criminalidad y muertes sospechosas.",
        "limitaciones": "Incluye muertes viales, asfixias y envenenamientos además de homicidios con arma."
    },
    {
        "id_indicador": "VICTIMAS_VIALES",
        "nombre": "Tasa de Víctimas por Siniestralidad Vial PNC",
        "dominio": "Movilidad y Transporte",
        "objetivo": "Medir el riesgo sobre la vida y salud derivado del tránsito vehicular terrestre.",
        "formula": "((Fallecidos Viales + Lesionados Viales) / Población Total) * 100,000",
        "variables_requeridas": ["fallecidos_viales_total", "lesionados_viales_total", "poblacion_total"],
        "fuente": "PNC / Departamento de Tránsito / INE - Base de Siniestralidad Vial 2024",
        "unidad_medida": "Víctimas por cada 100,000 habitantes",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Evalúa la peligrosidad de la red vial, densidad vehicular y velocidad.",
        "limitaciones": "Solo recoge casos donde intervino la PNC o PMT; excluye colisiones menores privadas."
    },
    {
        "id_indicador": "MORTALIDAD_VIAL",
        "nombre": "Tasa de Mortalidad por Accidentes de Tránsito PNC",
        "dominio": "Movilidad y Transporte",
        "objetivo": "Cuantificar la letalidad directa in situ de los siniestros viales.",
        "formula": "(Fallecidos Viales Registrados / Población Total) * 100,000",
        "variables_requeridas": ["fallecidos_viales_total", "poblacion_total"],
        "fuente": "PNC / INE - Siniestralidad Vial 2024",
        "unidad_medida": "Fallecidos por cada 100,000 habitantes",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Severidad letal de los corredores viales y autopistas troncales.",
        "limitaciones": "Registra fallecidos en el lugar del hecho; excluye decesos hospitalarios tardíos."
    },
    {
        "id_indicador": "RETORNO_MIGRATORIO",
        "nombre": "Tasa de Retorno Migratorio",
        "dominio": "Migración",
        "objetivo": "Estimar la intensidad de intercepción y deportación de connacionales devueltos por país emisor.",
        "formula": "(Total Retornados Aéreos y Terrestres / Población Total) * 10,000",
        "variables_requeridas": ["retornados_total", "poblacion_total"],
        "fuente": "Instituto Guatemalteco de Migración (IGM) / INE - Retornados Año 2024",
        "unidad_medida": "Personas retornadas por cada 10,000 habitantes",
        "nivel_agregacion": "Departamental",
        "periodicidad": "Anual",
        "interpretacion": "Proxy de la presión expulsora de migración irregular forzada por falta de oportunidades.",
        "limitaciones": "Solo mide capturas y deportaciones oficiales, no el flujo migratorio exitoso."
    },
    {
        "id_indicador": "NINEZ_MIGRANTE",
        "nombre": "Proporción de Niñez y Adolescencia Retornada",
        "dominio": "Migración",
        "objetivo": "Medir la vulnerabilidad etaria en el flujo migratorio forzado.",
        "formula": "(Retornados Menores de 18 Años / Total Retornados) * 100",
        "variables_requeridas": ["retornados_menores", "retornados_total"],
        "fuente": "IGM / INE - Microdatos Retornados 2024",
        "unidad_medida": "Porcentaje (%)",
        "nivel_agregacion": "Departamental",
        "periodicidad": "Anual",
        "interpretacion": "Indica migración de grupos familiares y menores no acompañados hacia el norte.",
        "limitaciones": "Depende de la veracidad y verificación de edad por autoridades migratorias emisoras."
    },
    {
        "id_indicador": "MATRICULA_SUPERIOR",
        "nombre": "Tasa de Matrícula en Educación Superior",
        "dominio": "Educación",
        "objetivo": "Evaluar la absorción y cobertura de educación universitaria en la población.",
        "formula": "(Total Matriculados Universitarios / Población Total) * 10,000",
        "variables_requeridas": ["matriculados_superior_total", "poblacion_total"],
        "fuente": "INE - Educación Superior: Matriculados 2025 (408,975 microdatos)",
        "unidad_medida": "Estudiantes matriculados por cada 10,000 habitantes",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Acceso a formación de capital humano calificado y movilidad social.",
        "limitaciones": "Registra la sede universitaria donde estudia el alumno, no necesariamente su origen permanente."
    },
    {
        "id_indicador": "PARIDAD_GENERO_UNIVERSITARIA",
        "nombre": "Proporción de Mujeres en Educación Superior",
        "dominio": "Educación",
        "objetivo": "Evaluar la equidad de género en las aulas universitarias.",
        "formula": "(Mujeres Matriculadas / Total Matriculados Universitarios) * 100",
        "variables_requeridas": ["mujeres_matriculadas_superior", "matriculados_superior_total"],
        "fuente": "INE - Matriculados Educación Superior 2025",
        "unidad_medida": "Porcentaje (%)",
        "nivel_agregacion": "Departamental y Municipal",
        "periodicidad": "Anual",
        "interpretacion": "Avance de equidad de género e inclusión educativa de mujeres en la educación terciaria.",
        "limitaciones": "No desagrega por campo disciplinar ni discrimina licenciaturas de carreras técnicas."
    },
    {
        "id_indicador": "INFLACION_REGIONAL",
        "nombre": "Variación Interanual del IPC por Región",
        "dominio": "Economía",
        "objetivo": "Monitorear el ritmo de incremento de los precios al consumidor en las 8 regiones del país.",
        "formula": "((IPC_actual - IPC_hace_12_meses) / IPC_hace_12_meses) * 100",
        "variables_requeridas": ["indice_ipc_regional", "variacion_interanual_pct"],
        "fuente": "INE - Índice de Precios al Consumidor (IPC), Base Diciembre 2023",
        "unidad_medida": "Porcentaje de variación (%)",
        "nivel_agregacion": "Regional SEGEPLAN (8 Regiones)",
        "periodicidad": "Mensual",
        "interpretacion": "Asimetría territorial del costo de vida y encarecimiento de bienes esenciales.",
        "limitaciones": "No desagrega índices de precios independientes para cada municipio rural."
    },
    {
        "id_indicador": "BRECHA_CBA",
        "nombre": "Brecha Urbano-Rural de la Canasta Básica Alimentaria",
        "dominio": "Economía",
        "objetivo": "Cuantificar el sobrecosto de subsistencia alimentaria entre área urbana y rural.",
        "formula": "CBA Urbana Per Cápita - CBA Rural Per Cápita",
        "variables_requeridas": ["costo_mensual_percapita", "dominio"],
        "fuente": "INE - Costos de la Canasta Básica Alimentaria Urbana y Rural 2024",
        "unidad_medida": "Quetzales mensuales por persona (GTQ)",
        "nivel_agregacion": "Dominios Nacionales Urbano y Rural",
        "periodicidad": "Mensual",
        "interpretacion": "Disparidad en costo calórico de vida y presión hacia cinturones informales urbanos.",
        "limitaciones": "Las canastas ponderan dietas distintas entre zonas rurales y urbanas."
    }
]


# consultar matriz de indicadores consolidados departamentales con filtros
@router.get("/departamentales", response_model=DepartmentIndicatorsResponse, summary="Obtener indicadores consolidados departamentales")
def get_department_indicators(
    region_id: Optional[int] = Query(default=None, ge=1, le=8, description="Filtrar por region socioeconomica (1-8)"),
    sort_by: Optional[str] = Query(default=None, description="Columna numerica para ordenar resultados"),
    order: str = Query(default="desc", pattern="^(asc|desc)$", description="Direccion de ordenamiento"),
    limit: int = Query(default=50, ge=1, le=100, description="Cantidad maxima de registros"),
    offset: int = Query(default=0, ge=0, description="Desplazamiento inicial"),
):
    if not DEPT_FILE.exists():
        raise HTTPException(status_code=503, detail="matriz departamental de indicadores no encontrada; ejecute el pipeline")

    df = pl.read_parquet(DEPT_FILE)
    
    if region_id is not None:
        df = df.filter(pl.col("region_id") == region_id)
        
    if sort_by is not None:
        if sort_by not in df.columns:
            raise HTTPException(status_code=400, detail=f"columna de ordenamiento invalida: '{sort_by}'")
        descending = (order.lower() == "desc")
        df = df.sort(sort_by, descending=descending)
    else:
        df = df.sort("depto_codigo")
        
    total_count = len(df)
    page_df = df.slice(offset, limit)
    
    return DepartmentIndicatorsResponse(
        total_departamentos=total_count,
        anio=2024,
        datos=page_df.to_dicts()
    )


# obtener el perfil de indicadores de un departamento especifico
@router.get("/departamentales/{codigo_o_nombre}", summary="Obtener indicadores de un departamento especifico")
def get_single_department_indicators(codigo_o_nombre: str):
    if not DEPT_FILE.exists():
        raise HTTPException(status_code=503, detail="matriz departamental de indicadores no encontrada")

    norm_geo = normalize_department(codigo_o_nombre)
    if not norm_geo:
        raise HTTPException(status_code=404, detail=f"departamento '{codigo_o_nombre}' no encontrado en maestro geopolitico")

    code = norm_geo["codigo"]
    df = pl.read_parquet(DEPT_FILE).filter(pl.col("depto_codigo") == code)
    if len(df) == 0:
        raise HTTPException(status_code=404, detail=f"indicadores no disponibles para departamento {code}")

    dept_data = df.to_dicts()[0]

    # cruzar con cluster si existe
    cluster_file = DATA_PROCESSED / "analisis" / "clusters_departamentales.parquet"
    if cluster_file.exists():
        cdf = pl.read_parquet(cluster_file).filter(pl.col("depto_codigo") == code)
        if len(cdf) > 0:
            crow = cdf.to_dicts()[0]
            dept_data["cluster_id"] = crow.get("cluster_id")
            dept_data["cluster_nombre"] = crow.get("cluster_nombre")
            dept_data["pca_1"] = crow.get("pca_1")
            dept_data["pca_2"] = crow.get("pca_2")

    return dept_data


# consultar indicadores municipales para los 340 municipios
@router.get("/municipales", response_model=MunicipalIndicatorsResponse, summary="Obtener indicadores consolidados municipales")
def get_municipal_indicators(
    depto_codigo: Optional[int] = Query(default=None, ge=1, le=22, description="Filtrar por codigo departamental (1-22)"),
    sort_by: Optional[str] = Query(default=None, description="Columna numerica para ordenar resultados"),
    order: str = Query(default="desc", pattern="^(asc|desc)$", description="Direccion de ordenamiento"),
    limit: int = Query(default=50, ge=1, le=340, description="Cantidad maxima de municipios por pagina"),
    offset: int = Query(default=0, ge=0, description="Desplazamiento inicial de paginacion"),
):
    if not MUP_FILE.exists():
        raise HTTPException(status_code=503, detail="matriz municipal de indicadores no encontrada; ejecute el pipeline")

    df = pl.read_parquet(MUP_FILE)

    if depto_codigo is not None:
        df = df.filter(pl.col("depto_codigo") == depto_codigo)

    if sort_by is not None:
        if sort_by not in df.columns:
            raise HTTPException(status_code=400, detail=f"columna de ordenamiento invalida: '{sort_by}'")
        descending = (order.lower() == "desc")
        df = df.sort(sort_by, descending=descending)
    else:
        df = df.sort(["depto_codigo", "mupio_codigo_str"])

    total_count = len(df)
    page_df = df.slice(offset, limit)

    return MunicipalIndicatorsResponse(
        total_municipios=total_count,
        offset=offset,
        limit=limit,
        anio=2024,
        datos=page_df.to_dicts()
    )


# obtener detalle municipal por codigo de cuatro digitos
@router.get("/municipales/{muni_code}", summary="Obtener indicadores de un municipio por codigo ine")
def get_single_municipal_indicators(muni_code: str):
    if not MUP_FILE.exists():
        raise HTTPException(status_code=503, detail="matriz municipal no encontrada")

    padded_code = muni_code.strip().zfill(4)
    df = pl.read_parquet(MUP_FILE).filter(pl.col("mupio_codigo_str") == padded_code)
    if len(df) == 0:
        raise HTTPException(status_code=404, detail=f"municipio con codigo '{muni_code}' no encontrado")

    return df.to_dicts()[0]


# catalogo formal de fichas metodologicas
@router.get("/fichas-metodologicas", response_model=MethodologyCatalogResponse, summary="Listar catálogo formal de fichas metodológicas")
def get_methodology_catalog(
    dominio: Optional[str] = Query(default=None, description="Filtrar por dominio tematico (Demografía, Seguridad, Movilidad, Migración, Educación, Economía)")
):
    cards = METHODOLOGY_CARDS
    if dominio is not None:
        term = dominio.strip().lower()
        cards = [c for c in cards if term in c["dominio"].lower()]

    return MethodologyCatalogResponse(
        total_fichas=len(cards),
        fichas=cards
    )
