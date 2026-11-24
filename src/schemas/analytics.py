from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DescriptiveMetricItem(BaseModel):
    variable: str
    n_observaciones: int
    media: float
    desviacion_estandar: float
    mediana: float
    q25: float
    q75: float
    rango_intercuartil: float
    minimo: float
    maximo: float
    asimetria_skewness: float
    coeficiente_variacion_pct: float


class DescriptiveResponse(BaseModel):
    total_variables: int
    estadisticas: List[DescriptiveMetricItem]


class OutlierItem(BaseModel):
    variable: str
    depto_codigo: int
    depto_nombre: str
    valor: float
    media_nacional: float
    z_score: float
    metodo_deteccion: str


class OutliersResponse(BaseModel):
    total_outliers: int
    outliers: List[OutlierItem]


class CorrelationPairItem(BaseModel):
    variable_1: str
    variable_2: str
    pearson_r: float
    pearson_pvalue: float
    pearson_significativo_05: bool
    pearson_significativo_01: bool
    spearman_rho: float
    spearman_pvalue: float
    spearman_significativo_05: bool
    fuerza_asociacion: str


class CorrelationsResponse(BaseModel):
    total_pares: int
    pares: List[CorrelationPairItem]


class PcaComponentLoadings(BaseModel):
    PC1: float
    PC2: float
    PC3: float


class PcaResponse(BaseModel):
    varianza_explicada_pc1: float
    varianza_explicada_pc2: float
    varianza_explicada_pc3: float
    varianza_acumulada_3_componentes: float
    cargas_componentes: Dict[str, PcaComponentLoadings]


class ClusterProfileItem(BaseModel):
    cluster_id: int
    cluster_nombre: str
    n_departamentos: int
    departamentos: List[str]
    media_retorno_migratorio: float
    media_necropsias: float
    media_victimas_viales: float
    media_matricula_superior: float
    media_dependencia: float
    media_inflacion: float


class ClustersResponse(BaseModel):
    total_clusters: int
    clusters: List[ClusterProfileItem]


class CostOfLivingForecastItem(BaseModel):
    dominio: str
    costo_actual_percapita: float
    tendencia_mensual_gtq: float
    crecimiento_mensual_pct: float
    proyeccion_tasa_anual_pct: float
    coeficiente_determinacion_r2: float
    error_estandar_modelo: float
    proyeccion_3_meses_gtq: float
    proyeccion_6_meses_gtq: float
    proyeccion_12_meses_gtq: float


class DemographicGrowthItem(BaseModel):
    depto_codigo: int
    depto_nombre: str
    region_nombre: str
    poblacion_2024: int
    poblacion_2030: int
    crecimiento_absoluto_2024_2030: int
    crecimiento_porcentual_total: float
    tasa_anual_crecimiento_geometrico_pct: float


class VulnerabilityIndexItem(BaseModel):
    ranking: int
    depto_codigo: int
    depto_nombre: str
    region_nombre: str
    indice_vulnerabilidad_ivst: float
    nivel_vulnerabilidad: str
    cluster_nombre: str
    tasa_retorno_migratorio_por_10k: float
    razon_dependencia_demografica: float
    tasa_matricula_superior_por_10k: float
    inflacion_regional_interanual: float


class VulnerabilityResponse(BaseModel):
    total_departamentos: int
    metodo: str
    indicadores: List[VulnerabilityIndexItem]
