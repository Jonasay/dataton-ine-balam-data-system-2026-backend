from pathlib import Path
import polars as pl
from src.core.geo_master import get_all_departamentos, normalize_depto

DATA_PROCESSED = Path("data/processed")
INDICATORS_DIR = DATA_PROCESSED / "indicadores"
INDICATORS_DIR.mkdir(parents=True, exist_ok=True)


def load_department_population(year: int = 2024) -> pl.DataFrame:
    path = DATA_PROCESSED / "demografia" / "poblacion_proyectada_departamental.parquet"
    if not path.exists():
        raise FileNotFoundError(f"no se encontró el denominador demográfico en: {path}")
    
    df = pl.read_parquet(path)
    return df.filter(pl.col("anio") == year).select([
        "depto_codigo",
        "depto_nombre",
        "depto_iso",
        "region_id",
        "region_nombre",
        "poblacion_total",
    ])


def compute_vital_rates(year: int = 2024) -> pl.DataFrame:
    pop_df = load_department_population(year=year)
    
    # defunciones del año
    deaths_path = DATA_PROCESSED / "demografia" / "defunciones_2024.parquet"
    if deaths_path.exists():
        df_deaths = pl.read_parquet(deaths_path)
        # filtrar defunciones válidas por departamento de ocurrencia (1-22)
        deaths_counts = (
            df_deaths.filter(pl.col("depocu").is_between(1, 22))
            .group_by("depocu")
            .agg(pl.len().alias("defunciones_total"))
            .rename({"depocu": "depto_codigo"})
            .with_columns(pl.col("depto_codigo").cast(pl.Int32))
        )
    else:
        deaths_counts = pop_df.select([pl.col("depto_codigo"), pl.lit(0).alias("defunciones_total")])
        
    # nacimientos del año
    births_path = DATA_PROCESSED / "demografia" / "nacimientos_2025.parquet"
    if births_path.exists():
        df_births = pl.read_parquet(births_path)
        births_counts = (
            df_births.filter(pl.col("depocu").is_between(1, 22))
            .group_by("depocu")
            .agg(pl.len().alias("nacimientos_total"))
            .rename({"depocu": "depto_codigo"})
            .with_columns(pl.col("depto_codigo").cast(pl.Int32))
        )
    else:
        births_counts = pop_df.select([pl.col("depto_codigo"), pl.lit(0).alias("nacimientos_total")])
        
    # unir con poblacion
    results = (
        pop_df.join(deaths_counts, on="depto_codigo", how="left")
        .join(births_counts, on="depto_codigo", how="left")
        .with_columns([
            pl.col("defunciones_total").fill_null(0),
            pl.col("nacimientos_total").fill_null(0),
        ])
        .with_columns([
            (pl.col("defunciones_total") / pl.col("poblacion_total") * 1000.0).round(2).alias("tasa_mortalidad_por_1000"),
            (pl.col("nacimientos_total") / pl.col("poblacion_total") * 1000.0).round(2).alias("tasa_natalidad_por_1000"),
            (pl.col("nacimientos_total") - pl.col("defunciones_total")).alias("crecimiento_natural_absoluto"),
            ((pl.col("nacimientos_total") - pl.col("defunciones_total")) / pl.col("poblacion_total") * 1000.0).round(2).alias("tasa_crecimiento_natural_por_1000"),
        ])
    )
    return results


def compute_security_rates(year: int = 2024) -> pl.DataFrame:
    pop_df = load_department_population(year=year)
    necropsies_path = DATA_PROCESSED / "seguridad" / "necropsias_inacif_2024.parquet"
    
    if not necropsies_path.exists():
        return pop_df.select(["depto_codigo"]).with_columns([
            pl.lit(0).alias("necropsias_total"),
            pl.lit(0.0).alias("tasa_necropsias_por_100k"),
        ])
        
    df_necropsies = pl.read_parquet(necropsies_path)
    
    # conteo por departamento normalizado
    necropsies_counts = (
        df_necropsies.filter(pl.col("depto_codigo_norm").is_not_null())
        .with_columns(pl.col("depto_codigo_norm").cast(pl.Int32).alias("depto_codigo"))
        .group_by("depto_codigo")
        .agg([
            pl.len().alias("necropsias_total"),
        ])
    )
    
    results = (
        pop_df.join(necropsies_counts, on="depto_codigo", how="left")
        .with_columns([
            pl.col("necropsias_total").fill_null(0),
        ])
        .with_columns([
            (pl.col("necropsias_total") / pl.col("poblacion_total") * 100_000.0).round(2).alias("tasa_necropsias_por_100k"),
        ])
    )
    return results.select(["depto_codigo", "necropsias_total", "tasa_necropsias_por_100k"])


def compute_traffic_rates(year: int = 2024) -> pl.DataFrame:
    pop_df = load_department_population(year=year)
    traffic_path = DATA_PROCESSED / "movilidad" / "accidentes_fallecidos_lesionados_2024.parquet"
    
    if not traffic_path.exists():
        return pop_df.select(["depto_codigo"]).with_columns([
            pl.lit(0).alias("victimas_viales_total"),
            pl.lit(0.0).alias("tasa_victimas_viales_por_100k"),
        ])
        
    df_traffic = pl.read_parquet(traffic_path)
    
    traffic_counts = (
        df_traffic.filter(pl.col("depto_codigo_norm").is_not_null())
        .with_columns(pl.col("depto_codigo_norm").cast(pl.Int32).alias("depto_codigo"))
        .group_by("depto_codigo")
        .agg([
            pl.len().alias("victimas_viales_total"),
            (pl.col("fall_les") == 1).sum().alias("fallecidos_viales_total"),
            (pl.col("fall_les") == 2).sum().alias("lesionados_viales_total"),
        ])
    )
    
    results = (
        pop_df.join(traffic_counts, on="depto_codigo", how="left")
        .with_columns([
            pl.col("victimas_viales_total").fill_null(0),
            pl.col("fallecidos_viales_total").fill_null(0),
            pl.col("lesionados_viales_total").fill_null(0),
        ])
        .with_columns([
            (pl.col("victimas_viales_total") / pl.col("poblacion_total") * 100_000.0).round(2).alias("tasa_victimas_viales_por_100k"),
            (pl.col("fallecidos_viales_total") / pl.col("poblacion_total") * 100_000.0).round(2).alias("tasa_mortalidad_vial_por_100k"),
        ])
    )
    return results.select(["depto_codigo", "victimas_viales_total", "fallecidos_viales_total", "lesionados_viales_total", "tasa_victimas_viales_por_100k", "tasa_mortalidad_vial_por_100k"])


def compute_migration_rates(year: int = 2024) -> pl.DataFrame:
    pop_df = load_department_population(year=year)
    migration_path = DATA_PROCESSED / "migracion" / "retornados_2024.parquet"
    
    if not migration_path.exists():
        return pop_df.select(["depto_codigo"]).with_columns([
            pl.lit(0).alias("retornados_total"),
            pl.lit(0.0).alias("tasa_retornados_por_10k"),
        ])
        
    df_migration = pl.read_parquet(migration_path)
    
    migration_counts = (
        df_migration.filter(pl.col("depto_codigo_norm").is_not_null())
        .with_columns(pl.col("depto_codigo_norm").cast(pl.Int32).alias("depto_codigo"))
        .group_by("depto_codigo")
        .agg([
            pl.len().alias("retornados_total"),
            (pl.col("sexo") == 1).sum().alias("retornados_hombres"),
            (pl.col("sexo") == 2).sum().alias("retornados_mujeres"),
            (pl.col("grupo_etario") == 1).sum().alias("retornados_menores"),
        ])
    )
    
    results = (
        pop_df.join(migration_counts, on="depto_codigo", how="left")
        .with_columns([
            pl.col("retornados_total").fill_null(0),
            pl.col("retornados_hombres").fill_null(0),
            pl.col("retornados_mujeres").fill_null(0),
            pl.col("retornados_menores").fill_null(0),
        ])
        .with_columns([
            (pl.col("retornados_total") / pl.col("poblacion_total") * 10_000.0).round(2).alias("tasa_retorno_migratorio_por_10k"),
            (pl.col("retornados_menores") / pl.col("retornados_total") * 100.0).round(2).fill_null(0.0).alias("pct_retornados_menores"),
        ])
    )
    return results.select(["depto_codigo", "retornados_total", "retornados_hombres", "retornados_mujeres", "retornados_menores", "tasa_retorno_migratorio_por_10k", "pct_retornados_menores"])


def compute_consolidated_department_dataset(year: int = 2024) -> pl.DataFrame:
    vitals = compute_vital_rates(year=year)
    security = compute_security_rates(year=year)
    traffic = compute_traffic_rates(year=year)
    migration = compute_migration_rates(year=year)
    
    # cruce relacional completo
    gold_df = (
        vitals.join(security, on="depto_codigo", how="inner")
        .join(traffic, on="depto_codigo", how="inner")
        .join(migration, on="depto_codigo", how="inner")
    )
    
    # guardar en repositorio gold de indicadores
    out_file = INDICATORS_DIR / f"indicadores_consolidados_departamentales_{year}.parquet"
    gold_df.write_parquet(out_file)
    print(f"✓ matriz consolidada de indicadores {year} guardada en: {out_file} ({len(gold_df)} departamentos, {len(gold_df.columns)} variables)")
    return gold_df


# alias compatibles
load_poblacion_departamental = load_department_population
compute_consolidated_departmental_dataset = compute_consolidated_department_dataset


if __name__ == "__main__":
    df_indicators = compute_consolidated_department_dataset(year=2024)
    print("\nresumen de indicadores calculados (primeros 5 departamentos):")
    cols_to_display = [
        "depto_codigo", "depto_nombre", "poblacion_total",
        "tasa_natalidad_por_1000", "tasa_mortalidad_por_1000",
        "tasa_necropsias_por_100k", "tasa_victimas_viales_por_100k",
        "tasa_retorno_migratorio_por_10k"
    ]
    print(df_indicators.select(cols_to_display).head(5))
