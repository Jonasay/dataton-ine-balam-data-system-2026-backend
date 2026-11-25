from __future__ import annotations

import json
from typing import List
from fastapi import APIRouter, HTTPException, Query
import polars as pl

from src.core.config import PROCESSED_DATA_DIR
from src.schemas.analytics import (
    DescriptiveResponse,
    OutliersResponse,
    CorrelationsResponse,
    PcaResponse,
    ClustersResponse,
    CostOfLivingForecastItem,
    DemographicGrowthItem,
    VulnerabilityResponse,
)

router = APIRouter(
    prefix="/analisis",
    tags=["Ciencia de Datos y Análisis Estadístico"]
)

DATA_PROCESSED = PROCESSED_DATA_DIR
ANALYSIS_DIR = DATA_PROCESSED / "analisis"


# consultar estadisticas descriptivas completas
@router.get("/descriptivo", response_model=DescriptiveResponse, summary="Estadísticas descriptivas de indicadores")
def get_descriptive_statistics():
    path = ANALYSIS_DIR / "estadisticas_descriptivas.parquet"
    if not path.exists():
        raise HTTPException(status_code=503, detail="estadísticas descriptivas no calculadas; ejecute el pipeline")

    df = pl.read_parquet(path)
    return DescriptiveResponse(
        total_variables=len(df),
        estadisticas=df.to_dicts()
    )


# consultar valores atipicos territoriales identificados
@router.get("/outliers", response_model=OutliersResponse, summary="Detección de valores atípicos territoriales")
def get_territorial_outliers():
    from src.analysis.data_science import detect_indicator_outliers, INDICATORS_PATH
    if not INDICATORS_PATH.exists():
        raise HTTPException(status_code=503, detail="matriz de indicadores no encontrada")

    df_ind = pl.read_parquet(INDICATORS_PATH)
    outliers = detect_indicator_outliers(df_ind)
    return OutliersResponse(
        total_outliers=len(outliers),
        outliers=outliers
    )


# consultar matriz de correlaciones de pearson y spearman con valores p
@router.get("/correlaciones", response_model=CorrelationsResponse, summary="Matriz de correlaciones de Pearson y Spearman")
def get_correlation_matrix(
    only_significant: bool = Query(default=False, description="Filtrar unicamente correlaciones estadisticamente significativas (p < 0.05)"),
    min_abs_r: float = Query(default=0.0, ge=0.0, le=1.0, description="Filtrar por correlacion absoluta minima"),
    sort_by: str = Query(default="pvalue", pattern="^(pvalue|pearson|spearman)$", description="Criterio de ordenamiento"),
):
    path = ANALYSIS_DIR / "matriz_correlaciones.parquet"
    if not path.exists():
        raise HTTPException(status_code=503, detail="matriz de correlaciones no disponible; ejecute el pipeline")

    df = pl.read_parquet(path)

    if only_significant:
        df = df.filter(pl.col("pearson_significativo_05"))

    if min_abs_r > 0.0:
        df = df.filter(pl.col("pearson_r").abs() >= min_abs_r)

    if sort_by == "pearson":
        df = df.sort(pl.col("pearson_r").abs(), descending=True)
    elif sort_by == "spearman":
        df = df.sort(pl.col("spearman_rho").abs(), descending=True)
    else:
        df = df.sort("pearson_pvalue")

    return CorrelationsResponse(
        total_pares=len(df),
        pares=df.to_dicts()
    )


# consultar descomposicion en componentes principales pca
@router.get("/pca", response_model=PcaResponse, summary="Análisis de Componentes Principales (PCA)")
def get_pca_analysis():
    meta_path = ANALYSIS_DIR / "resumen_ciencia_datos.json"
    if not meta_path.exists():
        raise HTTPException(status_code=503, detail="metadatos de pca no encontrados")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    pca_data = meta.get("pca_meta")
    if not pca_data:
        raise HTTPException(status_code=503, detail="informacion de pca no disponible en resumen")

    return PcaResponse(
        varianza_explicada_pc1=pca_data["varianza_explicada_pc1"],
        varianza_explicada_pc2=pca_data["varianza_explicada_pc2"],
        varianza_explicada_pc3=pca_data["varianza_explicada_pc3"],
        varianza_acumulada_3_componentes=pca_data["varianza_acumulada_3_componentes"],
        cargas_componentes=pca_data["cargas_componentes"]
    )


# consultar conglomerados socioeconomicos territoriales k-means
@router.get("/clusters", response_model=ClustersResponse, summary="Conglomerados socioeconómicos (K-Means)")
def get_clusters_analysis():
    meta_path = ANALYSIS_DIR / "resumen_ciencia_datos.json"
    if not meta_path.exists():
        raise HTTPException(status_code=503, detail="resumen de clusters no encontrado")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    raw_clusters = meta.get("clusters_meta", {})
    profiles = []
    for c_id, profile in raw_clusters.items():
        cid_int = int(c_id)
        cluster_names = {
            0: "Hub Metropolitano y Central",
            1: "Altiplano Rural y Sobrecarga Demográfica",
            2: "Cinturón Agrícola de Alta Expulsión Migratoria",
            3: "Corredor Logístico Costero y Siniestralidad Vial",
        }
        profiles.append({
            "cluster_id": cid_int,
            "cluster_nombre": cluster_names.get(cid_int, f"Cluster {cid_int}"),
            "n_departamentos": profile["n_departamentos"],
            "departamentos": profile["departamentos"],
            "media_retorno_migratorio": profile["media_retorno_migratorio"],
            "media_necropsias": profile["media_necropsias"],
            "media_victimas_viales": profile["media_victimas_viales"],
            "media_matricula_superior": profile["media_matricula_superior"],
            "media_dependencia": profile["media_dependencia"],
            "media_inflacion": profile["media_inflacion"],
        })

    return ClustersResponse(
        total_clusters=len(profiles),
        clusters=profiles
    )


# proyecciones y tendencias del costo de vida de la canasta basica
@router.get("/proyecciones/costo-vida", response_model=List[CostOfLivingForecastItem], summary="Modelos de proyección de Canasta Básica (CBA)")
def get_cost_of_living_forecasts():
    path = ANALYSIS_DIR / "proyecciones_costo_vida.parquet"
    if not path.exists():
        raise HTTPException(status_code=503, detail="modelos de costo de vida no encontrados")

    df = pl.read_parquet(path)
    return df.to_dicts()


# proyecciones demograficas y tasas de crecimiento geometrico departamental
@router.get("/proyecciones/demograficas", response_model=List[DemographicGrowthItem], summary="Proyecciones de crecimiento demográfico 2024-2030")
def get_demographic_forecasts():
    path = ANALYSIS_DIR / "proyecciones_demograficas.parquet"
    if not path.exists():
        raise HTTPException(status_code=503, detail="proyecciones demograficas no disponibles")

    df = pl.read_parquet(path)
    return df.to_dicts()


# indice exploratorio de vulnerabilidad socioeconomica territorial ivst
@router.get("/vulnerabilidad", response_model=VulnerabilityResponse, summary="Índice de Vulnerabilidad Socioeconómica Territorial (IVST)")
def get_territorial_vulnerability_index():
    from src.analysis.data_science import compute_territorial_vulnerability_df

    vuln_path = ANALYSIS_DIR / "vulnerabilidad_departamental.parquet"
    if vuln_path.exists():
        vuln_df = pl.read_parquet(vuln_path)
    else:
        ind_path = DATA_PROCESSED / "indicadores" / "indicadores_consolidados_departamentales_2024.parquet"
        if not ind_path.exists():
            raise HTTPException(status_code=503, detail="indicadores base no disponibles")
        vuln_df = compute_territorial_vulnerability_df()

    records = vuln_df.to_dicts()
    return VulnerabilityResponse(
        total_departamentos=len(records),
        metodo="Sintesis normalizada Min-Max de sobrecarga demografica, deficit universitario, inflacion y retorno migratorio",
        indicadores=records
    )
