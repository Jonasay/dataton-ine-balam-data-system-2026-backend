from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DepartmentIndicatorItem(BaseModel):
    depto_codigo: int
    depto_nombre: str
    depto_iso: str
    region_id: int
    region_nombre: str
    poblacion_total: int
    defunciones_total: int
    nacimientos_total: int
    tasa_mortalidad_por_1000: float
    tasa_natalidad_por_1000: float
    crecimiento_natural_absoluto: int
    tasa_crecimiento_natural_por_1000: float
    indice_masculinidad: float
    razon_dependencia_demografica: float
    pct_poblacion_menor_15: float
    pct_poblacion_15_64: float
    pct_poblacion_65_mas: float
    necropsias_total: int
    tasa_necropsias_por_100k: float
    victimas_viales_total: int
    fallecidos_viales_total: int
    lesionados_viales_total: int
    tasa_victimas_viales_por_100k: float
    tasa_mortalidad_vial_por_100k: float
    retornados_total: int
    retornados_hombres: int
    retornados_mujeres: int
    retornados_menores: int
    tasa_retorno_migratorio_por_10k: float
    pct_retornados_menores: float
    pct_retornadas_mujeres: float
    matriculados_superior_total: int
    tasa_matricula_superior_por_10k: float
    pct_mujeres_superior: float
    indice_ipc_regional: float
    inflacion_regional_interanual: float
    perdida_poder_adquisitivo_quetzal: float
    brecha_urbano_rural_cba_gtq: float
    brecha_urbano_rural_cba_pct: float


class DepartmentIndicatorsResponse(BaseModel):
    total_departamentos: int
    anio: int
    datos: List[DepartmentIndicatorItem]


class MunicipalIndicatorItem(BaseModel):
    depto_codigo: int
    depto_nombre: str
    depto_iso: str
    region_id: int
    region_nombre: str
    mupio_codigo_str: str
    poblacion_total: int
    defunciones_total: int
    nacimientos_total: int
    necropsias_total: int
    victimas_viales_total: int
    fallecidos_viales_total: int
    lesionados_viales_total: int
    matriculados_superior_total: int
    mujeres_matriculadas_superior: int
    tasa_mortalidad_por_1000: float
    tasa_natalidad_por_1000: float
    crecimiento_natural_absoluto: int
    tasa_crecimiento_natural_por_1000: float
    tasa_necropsias_por_100k: float
    tasa_victimas_viales_por_100k: float
    tasa_mortalidad_vial_por_100k: float
    tasa_matricula_superior_por_10k: float
    pct_mujeres_superior: float


class MunicipalIndicatorsResponse(BaseModel):
    total_municipios: int
    offset: int
    limit: int
    anio: int
    datos: List[MunicipalIndicatorItem]


class IndicatorMethodologyCard(BaseModel):
    id_indicador: str
    nombre: str
    dominio: str
    objetivo: str
    formula: str
    variables_requeridas: List[str]
    fuente: str
    unidad_medida: str
    nivel_agregacion: str
    periodicidad: str
    interpretacion: str
    limitaciones: str


class MethodologyCatalogResponse(BaseModel):
    total_fichas: int
    fichas: List[IndicatorMethodologyCard]
