from __future__ import annotations

import sys
import time
from pathlib import Path

# asegurar raiz del repositorio en sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.analysis.data_science import (
    run_full_data_science_pipeline,
    compute_descriptive_summary,
    compute_correlation_analysis,
    perform_pca_and_clustering,
    forecast_cost_of_living,
    forecast_demographic_trends,
)
import polars as pl


def run_analysis_pipeline() -> None:
    start_time = time.time()
    print("=" * 70)
    print("iniciando ejecucion del pipeline de ciencia de datos y estadistica")
    print("=" * 70)

    summary_results = run_full_data_science_pipeline()

    # cargar y mostrar hallazgos de correlaciones significativas
    corrs_path = Path("data/processed/analisis/matriz_correlaciones.parquet")
    if corrs_path.exists():
        df_corrs = pl.read_parquet(corrs_path).filter(pl.col("pearson_significativo_05"))
        print("\n" + "=" * 70)
        print("principales correlaciones estadisticamente significativas (p < 0.05):")
        print("=" * 70)
        display_corrs = df_corrs.select([
            "variable_1", "variable_2", "pearson_r", "pearson_pvalue", "fuerza_asociacion"
        ]).head(10)
        print(display_corrs)

    # mostrar resumen de conglomerados territoriales
    clusters_path = Path("data/processed/analisis/clusters_departamentales.parquet")
    if clusters_path.exists():
        df_clusters = pl.read_parquet(clusters_path)
        print("\n" + "=" * 70)
        print("distribucion de departamentos por conglomerado socioeconomico:")
        print("=" * 70)
        for cluster_id in sorted(df_clusters["cluster_id"].unique()):
            deptos = df_clusters.filter(pl.col("cluster_id") == cluster_id)["depto_nombre"].to_list()
            cluster_name = df_clusters.filter(pl.col("cluster_id") == cluster_id)["cluster_nombre"][0]
            print(f"  • {cluster_name} (n={len(deptos)}): {', '.join(deptos)}")

    # mostrar proyecciones de costo de vida
    cost_path = Path("data/processed/analisis/proyecciones_costo_vida.parquet")
    if cost_path.exists():
        df_cost = pl.read_parquet(cost_path)
        print("\n" + "=" * 70)
        print("modelado predictivo de costo mensual de la canasta basica alimentaria (cba):")
        print("=" * 70)
        print(df_cost.select([
            "dominio", "costo_actual_percapita", "tendencia_mensual_gtq",
            "proyeccion_tasa_anual_pct", "proyeccion_12_meses_gtq", "coeficiente_determinacion_r2"
        ]))

    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"pipeline cientifico completado exitosamente en {elapsed:.2f} segundos")
    print("=" * 70)


if __name__ == "__main__":
    run_analysis_pipeline()
