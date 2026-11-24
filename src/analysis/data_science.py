from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
import json
import numpy as np
import pandas as pd
import polars as pl
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

DATA_PROCESSED = Path("data/processed")
INDICATORS_PATH = DATA_PROCESSED / "indicadores" / "indicadores_consolidados_departamentales_2024.parquet"
ANALYSIS_DIR = DATA_PROCESSED / "analisis"
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


def compute_descriptive_summary(df_indicators: pl.DataFrame) -> pl.DataFrame:
    # calculo de estadisticas descriptivas completas por variable
    pdf = df_indicators.to_pandas()
    numeric_cols = [
        col for col in pdf.columns 
        if col not in ["depto_codigo", "depto_nombre", "depto_iso", "region_id", "region_nombre"]
        and pd.api.types.is_numeric_dtype(pdf[col])
    ]
    
    summary_records = []
    for col in numeric_cols:
        series = pdf[col].dropna()
        n_obs = len(series)
        if n_obs == 0:
            continue
            
        mean_val = float(series.mean())
        std_val = float(series.std(ddof=1))
        median_val = float(series.median())
        q25 = float(series.quantile(0.25))
        q75 = float(series.quantile(0.75))
        iqr = q75 - q25
        min_val = float(series.min())
        max_val = float(series.max())
        skew_val = float(series.skew())
        cv = (std_val / mean_val * 100.0) if mean_val != 0 else 0.0
        
        summary_records.append({
            "variable": col,
            "n_observaciones": n_obs,
            "media": round(mean_val, 3),
            "desviacion_estandar": round(std_val, 3),
            "mediana": round(median_val, 3),
            "q25": round(q25, 3),
            "q75": round(q75, 3),
            "rango_intercuartil": round(iqr, 3),
            "minimo": round(min_val, 3),
            "maximo": round(max_val, 3),
            "asimetria_skewness": round(skew_val, 3),
            "coeficiente_variacion_pct": round(cv, 2)
        })
        
    summary_df = pl.DataFrame(summary_records)
    summary_df.write_parquet(ANALYSIS_DIR / "estadisticas_descriptivas.parquet")
    return summary_df


def detect_indicator_outliers(df_indicators: pl.DataFrame) -> List[Dict[str, Any]]:
    # deteccion de valores atipicos territoriales usando z-score y rango intercuartil
    pdf = df_indicators.to_pandas()
    key_metrics = [
        "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "tasa_retorno_migratorio_por_10k",
        "tasa_matricula_superior_por_10k",
        "razon_dependencia_demografica",
        "tasa_natalidad_por_1000",
        "inflacion_regional_interanual",
    ]
    
    outliers_list = []
    for col in key_metrics:
        if col not in pdf.columns:
            continue
            
        series = pdf[col]
        mean_val = series.mean()
        std_val = series.std(ddof=1)
        q25 = series.quantile(0.25)
        q75 = series.quantile(0.75)
        iqr = q75 - q25
        lower_iqr = q25 - 1.5 * iqr
        upper_iqr = q75 + 1.5 * iqr
        
        for _, row in pdf.iterrows():
            val = row[col]
            z_score = (val - mean_val) / std_val if std_val > 0 else 0.0
            is_z_outlier = abs(z_score) >= 2.0
            is_iqr_outlier = val < lower_iqr or val > upper_iqr
            
            if is_z_outlier or is_iqr_outlier:
                outliers_list.append({
                    "variable": col,
                    "depto_codigo": int(row["depto_codigo"]),
                    "depto_nombre": str(row["depto_nombre"]),
                    "valor": round(float(val), 2),
                    "media_nacional": round(float(mean_val), 2),
                    "z_score": round(float(z_score), 2),
                    "metodo_deteccion": "Z-score e IQR" if (is_z_outlier and is_iqr_outlier) else ("Z-score" if is_z_outlier else "IQR"),
                })
                
    return outliers_list


def compute_correlation_analysis(df_indicators: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
    # calculo de correlaciones bivariadas de pearson y spearman con significancia
    pdf = df_indicators.to_pandas()
    target_cols = [
        "tasa_natalidad_por_1000",
        "tasa_mortalidad_por_1000",
        "razon_dependencia_demografica",
        "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "tasa_retorno_migratorio_por_10k",
        "pct_retornados_menores",
        "tasa_matricula_superior_por_10k",
        "pct_mujeres_superior",
        "inflacion_regional_interanual",
    ]
    
    records_pairwise = []
    n = len(target_cols)
    
    for i in range(n):
        for j in range(i + 1, n):
            c1, c2 = target_cols[i], target_cols[j]
            s1 = pdf[c1].dropna()
            s2 = pdf[c2].dropna()
            
            common_idx = s1.index.intersection(s2.index)
            if len(common_idx) < 3:
                continue
                
            p_val, p_pvalue = stats.pearsonr(s1.loc[common_idx], s2.loc[common_idx])
            s_val, s_pvalue = stats.spearmanr(s1.loc[common_idx], s2.loc[common_idx])
            
            # clasificacion de fuerza de asociacion
            abs_p = abs(p_val)
            if abs_p >= 0.7:
                strength = "Muy Fuerte"
            elif abs_p >= 0.5:
                strength = "Moderada a Fuerte"
            elif abs_p >= 0.3:
                strength = "Débil a Moderada"
            else:
                strength = "Nula o Muy Débil"
                
            records_pairwise.append({
                "variable_1": c1,
                "variable_2": c2,
                "pearson_r": round(float(p_val), 4),
                "pearson_pvalue": round(float(p_pvalue), 4),
                "pearson_significativo_05": bool(p_pvalue < 0.05),
                "pearson_significativo_01": bool(p_pvalue < 0.01),
                "spearman_rho": round(float(s_val), 4),
                "spearman_pvalue": round(float(s_pvalue), 4),
                "spearman_significativo_05": bool(s_pvalue < 0.05),
                "fuerza_asociacion": strength,
            })
            
    df_corrs = pl.DataFrame(records_pairwise).sort("pearson_pvalue")
    df_corrs.write_parquet(ANALYSIS_DIR / "matriz_correlaciones.parquet")
    return df_corrs


def perform_pca_and_clustering(df_indicators: pl.DataFrame, n_clusters: int = 4) -> Tuple[pl.DataFrame, Dict[str, Any]]:
    # reduccion dimensional con componentes principales y agrupamiento con k-means
    pdf = df_indicators.to_pandas().copy()
    features = [
        "tasa_natalidad_por_1000",
        "tasa_mortalidad_por_1000",
        "razon_dependencia_demografica",
        "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "tasa_retorno_migratorio_por_10k",
        "tasa_matricula_superior_por_10k",
        "inflacion_regional_interanual",
    ]
    
    x_matrix = pdf[features].values
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_matrix)
    
    # 1. componentes principales
    pca = PCA(n_components=3, random_state=42)
    x_pca = pca.fit_transform(x_scaled)
    
    pdf["pca_1"] = np.round(x_pca[:, 0], 3)
    pdf["pca_2"] = np.round(x_pca[:, 1], 3)
    pdf["pca_3"] = np.round(x_pca[:, 2], 3)
    
    loadings_dict = {}
    for idx, feat in enumerate(features):
        loadings_dict[feat] = {
            "PC1": round(float(pca.components_[0, idx]), 3),
            "PC2": round(float(pca.components_[1, idx]), 3),
            "PC3": round(float(pca.components_[2, idx]), 3),
        }
        
    pca_meta = {
        "varianza_explicada_pc1": round(float(pca.explained_variance_ratio_[0]), 4),
        "varianza_explicada_pc2": round(float(pca.explained_variance_ratio_[1]), 4),
        "varianza_explicada_pc3": round(float(pca.explained_variance_ratio_[2]), 4),
        "varianza_acumulada_3_componentes": round(float(sum(pca.explained_variance_ratio_)), 4),
        "cargas_componentes": loadings_dict,
    }
    
    # 2. agrupamiento espacial con k-means
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=15)
    clusters = kmeans.fit_predict(x_scaled)
    pdf["cluster_id"] = clusters
    
    # etiquetado interpretativo de los conglomerados
    cluster_labels = {
        0: "Hub Metropolitano y Central",
        1: "Altiplano Rural y Sobrecarga Demográfica",
        2: "Cinturón Agrícola de Alta Expulsión Migratoria",
        3: "Corredor Logístico Costero y Siniestralidad Vial",
    }
    
    # reasignar etiquetas segun promedios caracteristicos
    cluster_profiles = {}
    for c in range(n_clusters):
        c_subset = pdf[pdf["cluster_id"] == c]
        cluster_profiles[c] = {
            "n_departamentos": len(c_subset),
            "departamentos": c_subset["depto_nombre"].tolist(),
            "media_retorno_migratorio": round(float(c_subset["tasa_retorno_migratorio_por_10k"].mean()), 2),
            "media_necropsias": round(float(c_subset["tasa_necropsias_por_100k"].mean()), 2),
            "media_victimas_viales": round(float(c_subset["tasa_victimas_viales_por_100k"].mean()), 2),
            "media_matricula_superior": round(float(c_subset["tasa_matricula_superior_por_10k"].mean()), 2),
            "media_dependencia": round(float(c_subset["razon_dependencia_demografica"].mean()), 2),
            "media_inflacion": round(float(c_subset["inflacion_regional_interanual"].mean()), 2),
        }
        
    pdf["cluster_nombre"] = [cluster_labels.get(c, f"Cluster {c}") for c in clusters]
    
    out_cols = [
        "depto_codigo", "depto_nombre", "depto_iso", "region_nombre",
        "cluster_id", "cluster_nombre", "pca_1", "pca_2", "pca_3",
        "tasa_retorno_migratorio_por_10k", "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k", "tasa_matricula_superior_por_10k",
        "razon_dependencia_demografica", "inflacion_regional_interanual"
    ]
    df_clustered = pl.DataFrame(pdf[out_cols])
    df_clustered.write_parquet(ANALYSIS_DIR / "clusters_departamentales.parquet")
    
    clustering_meta = {
        "pca": pca_meta,
        "clusters": cluster_profiles,
    }
    return df_clustered, clustering_meta


def forecast_cost_of_living() -> pl.DataFrame:
    # modelado predictivo y proyeccion lineal del costo de canasta basica
    basket_path = DATA_PROCESSED / "economia" / "canasta_basica_mensual.parquet"
    if not basket_path.exists():
        return pl.DataFrame()
        
    df_basket = pl.read_parquet(basket_path).filter(pl.col("tipo_canasta") == "CBA").to_pandas()
    
    # ordenar cronologicamente por mes continuo
    df_basket["mes_continuo"] = (df_basket["anio"] - 2024) * 12 + df_basket["mes"]
    
    forecast_results = []
    for domain in ["Urbana", "Rural"]:
        domain_data = df_basket[df_basket["dominio"] == domain].sort_values("mes_continuo")
        if len(domain_data) < 3:
            continue
            
        x = domain_data["mes_continuo"].values
        y = domain_data["costo_mensual_percapita"].values
        
        # regresion lineal por minimos cuadrados ordinarios
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        r_squared = r_value ** 2
        
        last_t = x[-1]
        last_val = y[-1]
        
        # proyecciones a 3, 6 y 12 meses
        proj_3m = intercept + slope * (last_t + 3)
        proj_6m = intercept + slope * (last_t + 6)
        proj_12m = intercept + slope * (last_t + 12)
        
        monthly_growth_gtq = slope
        monthly_growth_pct = (slope / last_val) * 100.0 if last_val > 0 else 0.0
        annual_growth_pct = monthly_growth_pct * 12.0
        
        forecast_results.append({
            "dominio": domain,
            "costo_actual_percapita": round(float(last_val), 2),
            "tendencia_mensual_gtq": round(float(monthly_growth_gtq), 3),
            "crecimiento_mensual_pct": round(float(monthly_growth_pct), 3),
            "proyeccion_tasa_anual_pct": round(float(annual_growth_pct), 2),
            "coeficiente_determinacion_r2": round(float(r_squared), 4),
            "error_estandar_modelo": round(float(std_err), 4),
            "proyeccion_3_meses_gtq": round(float(proj_3m), 2),
            "proyeccion_6_meses_gtq": round(float(proj_6m), 2),
            "proyeccion_12_meses_gtq": round(float(proj_12m), 2),
        })
        
    forecast_df = pl.DataFrame(forecast_results)
    forecast_df.write_parquet(ANALYSIS_DIR / "proyecciones_costo_vida.parquet")
    return forecast_df


def forecast_demographic_trends() -> pl.DataFrame:
    # proyeccion demografica y calculo de tasa de crecimiento geometrico por departamento
    pop_path = DATA_PROCESSED / "demografia" / "poblacion_proyectada_departamental.parquet"
    if not pop_path.exists():
        return pl.DataFrame()
        
    df_pop = pl.read_parquet(pop_path).to_pandas()
    
    # filtrar anios horizonte 2024 y 2030
    p2024 = df_pop[df_pop["anio"] == 2024].set_index("depto_codigo")
    p2030 = df_pop[df_pop["anio"] == 2030].set_index("depto_codigo")
    
    records = []
    for code, row24 in p2024.iterrows():
        if code not in p2030.index:
            continue
        row30 = p2030.loc[code]
        
        pop24 = float(row24["poblacion_total"])
        pop30 = float(row30["poblacion_total"])
        
        # crecimiento absoluto y tasa de crecimiento geometrico anualizada r = (P_t / P_0)^(1/t) - 1
        growth_abs = pop30 - pop24
        growth_pct_total = (growth_abs / pop24) * 100.0
        annual_growth_rate = ((pop30 / pop24) ** (1.0 / 6.0) - 1.0) * 100.0
        
        records.append({
            "depto_codigo": int(code),
            "depto_nombre": str(row24["depto_nombre"]),
            "region_nombre": str(row24["region_nombre"]),
            "poblacion_2024": int(pop24),
            "poblacion_2030": int(pop30),
            "crecimiento_absoluto_2024_2030": int(growth_abs),
            "crecimiento_porcentual_total": round(growth_pct_total, 2),
            "tasa_anual_crecimiento_geometrico_pct": round(annual_growth_rate, 2),
        })
        
    df_demo_growth = pl.DataFrame(records).sort("tasa_anual_crecimiento_geometrico_pct", descending=True)
    df_demo_growth.write_parquet(ANALYSIS_DIR / "proyecciones_demograficas.parquet")
    return df_demo_growth


def compute_yearly_demographic_trajectory() -> pl.DataFrame:
    # calcular evolucion anual de estructura demografica y dependencia 2015-2030
    granular_path = DATA_PROCESSED / "demografia" / "poblacion_proyectada_edad_sexo.parquet"
    if not granular_path.exists():
        return pl.DataFrame()

    df_granular = pl.read_parquet(granular_path)
    sex_pivot = (
        df_granular.filter(pl.col("sexo_id").is_in([1, 2]))
        .group_by(["anio", "depto_codigo", "depto_nombre", "region_nombre", "sexo_id"])
        .agg(pl.col("poblacion").sum())
        .pivot(on="sexo_id", index=["anio", "depto_codigo", "depto_nombre", "region_nombre"], values="poblacion")
        .rename({"1": "hombres", "2": "mujeres"})
        .with_columns((pl.col("hombres") / pl.col("mujeres") * 100.0).round(2).alias("indice_masculinidad"))
    )

    age_groups = (
        df_granular.filter(pl.col("sexo_id") == 0)
        .group_by(["anio", "depto_codigo"])
        .agg([
            pl.col("poblacion").sum().alias("poblacion_total"),
            pl.col("poblacion").filter(pl.col("edad") < 15).sum().alias("pob_menor_15"),
            pl.col("poblacion").filter((pl.col("edad") >= 15) & (pl.col("edad") < 65)).sum().alias("pob_15_64"),
            pl.col("poblacion").filter(pl.col("edad") >= 65).sum().alias("pob_65_mas"),
        ])
        .with_columns([
            ((pl.col("pob_menor_15") + pl.col("pob_65_mas")) / pl.col("pob_15_64") * 100.0).round(2).alias("razon_dependencia_demografica"),
            (pl.col("pob_menor_15") / pl.col("poblacion_total") * 100.0).round(2).alias("pct_poblacion_menor_15"),
            (pl.col("pob_15_64") / pl.col("poblacion_total") * 100.0).round(2).alias("pct_poblacion_15_64"),
            (pl.col("pob_65_mas") / pl.col("poblacion_total") * 100.0).round(2).alias("pct_poblacion_65_mas"),
        ])
    )

    traj_df = sex_pivot.join(age_groups, on=["anio", "depto_codigo"]).sort(["anio", "depto_codigo"])
    traj_df.write_parquet(ANALYSIS_DIR / "trayectoria_demografica_anual.parquet")
    return traj_df


def compute_territorial_vulnerability_df(df_indicators: Optional[pl.DataFrame] = None) -> pl.DataFrame:
    # calcular indice de vulnerabilidad socioeconomica territorial ivst normalizado min-max
    if df_indicators is None:
        if not INDICATORS_PATH.exists():
            raise FileNotFoundError(f"no se encontro el dataset consolidado en: {INDICATORS_PATH}")
        df_indicators = pl.read_parquet(INDICATORS_PATH)

    pdf = df_indicators.to_pandas().copy()
    clust_path = ANALYSIS_DIR / "clusters_departamentales.parquet"
    c_df = pl.read_parquet(clust_path).to_pandas() if clust_path.exists() else None

    def min_max_norm(series: pd.Series) -> pd.Series:
        s_min, s_max = series.min(), series.max()
        return (series - s_min) / (s_max - s_min) if s_max > s_min else series * 0.0

    norm_dep = min_max_norm(pdf["razon_dependencia_demografica"])
    norm_mig = min_max_norm(pdf["tasa_retorno_migratorio_por_10k"])
    norm_inf = min_max_norm(pdf["inflacion_regional_interanual"])
    norm_edu_deficit = 1.0 - min_max_norm(pdf["tasa_matricula_superior_por_10k"])

    # ponderacion multidimensional equilibrada
    ivst_raw = (0.30 * norm_dep + 0.30 * norm_mig + 0.25 * norm_edu_deficit + 0.15 * norm_inf) * 100.0
    pdf["indice_vulnerabilidad_ivst"] = np.round(ivst_raw, 2)

    def classify_level(score: float) -> str:
        if score >= 65.0:
            return "Crítica"
        elif score >= 50.0:
            return "Alta"
        elif score >= 35.0:
            return "Moderada"
        return "Baja"

    pdf["nivel_vulnerabilidad"] = [classify_level(float(s)) for s in pdf["indice_vulnerabilidad_ivst"]]
    pdf = pdf.sort_values("indice_vulnerabilidad_ivst", ascending=False).reset_index(drop=True)
    pdf["ranking"] = pdf.index + 1

    cluster_names = []
    for _, row in pdf.iterrows():
        c_name = "No clasificado"
        if c_df is not None:
            match = c_df[c_df["depto_codigo"] == row["depto_codigo"]]
            if len(match) > 0:
                c_name = str(match["cluster_nombre"].values[0])
        cluster_names.append(c_name)
    pdf["cluster_nombre"] = cluster_names

    out_cols = [
        "ranking",
        "depto_codigo",
        "depto_nombre",
        "depto_iso",
        "region_nombre",
        "indice_vulnerabilidad_ivst",
        "nivel_vulnerabilidad",
        "cluster_nombre",
        "tasa_retorno_migratorio_por_10k",
        "razon_dependencia_demografica",
        "tasa_matricula_superior_por_10k",
        "inflacion_regional_interanual",
    ]
    vuln_df = pl.DataFrame(pdf[out_cols])
    vuln_df.write_parquet(ANALYSIS_DIR / "vulnerabilidad_departamental.parquet")
    return vuln_df


def run_full_data_science_pipeline() -> Dict[str, Any]:
    # ejecucion integral del pipeline cientifico y estadistico
    if not INDICATORS_PATH.exists():
        raise FileNotFoundError(f"no se encontro el dataset consolidado en: {INDICATORS_PATH}")
        
    df_indicators = pl.read_parquet(INDICATORS_PATH)
    
    # 1. analisis descriptivo
    desc_df = compute_descriptive_summary(df_indicators)
    outliers = detect_indicator_outliers(df_indicators)
    
    # 2. analisis de correlaciones
    corrs_df = compute_correlation_analysis(df_indicators)
    
    # 3. pca y agrupamiento
    clusters_df, cluster_meta = perform_pca_and_clustering(df_indicators, n_clusters=4)
    
    # 4. modelos predictivos, trayectoria anual y vulnerabilidad ivst
    cba_forecast = forecast_cost_of_living()
    demo_forecast = forecast_demographic_trends()
    compute_yearly_demographic_trajectory()
    vuln_df = compute_territorial_vulnerability_df(df_indicators)
    
    # 5. consolidacion de resumen
    summary_report = {
        "status": "completado exitosamente",
        "n_departamentos": len(df_indicators),
        "n_variables_descriptivas": len(desc_df),
        "n_pares_correlacion": len(corrs_df),
        "n_outliers_identificados": len(outliers),
        "pca_meta": cluster_meta["pca"],
        "clusters_meta": cluster_meta["clusters"],
        "proyecciones_costo_vida": cba_forecast.to_dicts(),
        "top_crecimiento_demografico": demo_forecast.head(5).to_dicts(),
        "top_vulnerabilidad_ivst": vuln_df.head(5).to_dicts(),
    }
    
    with open(ANALYSIS_DIR / "resumen_ciencia_datos.json", "w", encoding="utf-8") as handle:
        json.dump(summary_report, handle, indent=2, ensure_ascii=False)
        
    print(f"✓ pipeline de ciencia de datos completado exitosamente.")
    print(f"  • estadísticas descriptivas : {len(desc_df)} variables analizadas")
    print(f"  • matriz correlaciones      : {len(corrs_df)} pares calculados")
    print(f"  • pca y conglomerados       : 3 componentes ({cluster_meta['pca']['varianza_acumulada_3_componentes']*100:.1f}% varianza) y 4 clusters")
    print(f"  • proyecciones y tendencias : costo de vida y demografía 2024-2030 exportadas")
    print(f"  • directorio de salida      : {ANALYSIS_DIR}")
    return summary_report


if __name__ == "__main__":
    run_full_data_science_pipeline()
