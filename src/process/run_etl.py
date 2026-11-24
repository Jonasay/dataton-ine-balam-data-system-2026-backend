from __future__ import annotations

import sys
import time
from pathlib import Path
import polars as pl

from src.core.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.core.geo_master import normalize_depto
from src.process.etl_pipeline import (
    process_basic_basket,
    process_cpi_indicators,
    process_general_microdata,
    process_higher_education,
    process_population_projections,
)


def run_full_etl():
    start_time = time.time()
    results = []

    # 1. proyecciones de poblacion (base fundamental de denominadores)
    try:
        print("\n[1/7] procesando proyecciones de poblacion 2015-2030...")
        path_granular, path_department = process_population_projections()
        results.append(("demografía: población granular", path_granular))
        results.append(("demografía: población departamental", path_department))
    except Exception as e:
        print(f"error en proyecciones: {e}")

    # 2. economia: canasta basica alimentaria y ampliada (cba/ca)
    try:
        print("\n[2/7] procesando canasta basica urbana y rural...")
        path_basket = process_basic_basket()
        results.append(("economía: canasta básica mensual", path_basket))
    except Exception as e:
        print(f"error en cba: {e}")

    # 3. economia: indicadores ipc (regiones, poder adquisitivo, divisiones)
    try:
        print("\n[3/7] procesando indicadores del ipc...")
        path_region, path_purchasing, path_divisions = process_cpi_indicators()
        results.append(("economía: ipc regiones", path_region))
        results.append(("economía: poder adquisitivo", path_purchasing))
        results.append(("economía: ipc divisiones gasto", path_divisions))
    except Exception as e:
        print(f"error en ipc: {e}")

    # 4. demografia: vitales defunciones y nacimientos
    try:
        print("\n[4/7] procesando estadisticas vitales (defunciones y nacimientos)...")
        # defunciones 2024
        file_deaths = RAW_DATA_DIR / "estadisticas-vitales-defunciones" / "bd-defunciones-2024-da.xlsx"
        if file_deaths.exists():
            out_deaths = PROCESSED_DATA_DIR / "demografia" / "defunciones_2024.parquet"
            path_deaths = process_general_microdata(file_deaths, out_deaths, "Defunciones 2024")
            results.append(("demografía: defunciones 2024", path_deaths))
            
        # nacimientos 2025
        file_births = RAW_DATA_DIR / "estadisticas-vitales-nacimientos" / "nacimientos_2025.xlsx"
        if file_births.exists():
            out_births = PROCESSED_DATA_DIR / "demografia" / "nacimientos_2025.parquet"
            path_births = process_general_microdata(file_births, out_births, "Nacimientos 2025")
            results.append(("demografía: nacimientos 2025", path_births))
    except Exception as e:
        print(f"error en vitales: {e}")

    # 5. seguridad: necropsias medico-legales inacif
    try:
        print("\n[5/7] procesando seguridad y necropsias inacif...")
        file_inacif = RAW_DATA_DIR / "hechos-delictivos-servicio-medico-necropsias-inacif" / "base-de-datos-necropsias-inacif-2024.xlsx"
        if file_inacif.exists():
            out_inacif = PROCESSED_DATA_DIR / "seguridad" / "necropsias_inacif_2024.parquet"
            path_inacif = process_general_microdata(file_inacif, out_inacif, "Necropsias INACIF 2024")
            results.append(("seguridad: necropsias inacif 2024", path_inacif))
    except Exception as e:
        print(f"error en inacif: {e}")

    # 6. movilidad: siniestralidad vial (fallecidos y lesionados)
    try:
        print("\n[6/7] procesando movilidad y victimas viales...")
        file_traffic = RAW_DATA_DIR / "accidentes-de-transito-fallecidos-y-lesionados" / "base-de-datos-fallecidos-y-lesionados-pnc-2024.xlsx"
        if file_traffic.exists():
            out_traffic = PROCESSED_DATA_DIR / "movilidad" / "accidentes_fallecidos_lesionados_2024.parquet"
            path_traffic = process_general_microdata(file_traffic, out_traffic, "Siniestralidad Vial 2024")
            results.append(("movilidad: fallecidos y lesionados 2024", path_traffic))
    except Exception as e:
        print(f"error en siniestralidad: {e}")

    # 7. migracion: retornados 2024 y 2023
    try:
        print("\n[7/7] procesando migracion de retorno...")
        file_return24 = RAW_DATA_DIR / "retornados-ano-2024vv" / "bd_retornados_ano_2024.xlsx"
        if file_return24.exists():
            out_return24 = PROCESSED_DATA_DIR / "migracion" / "retornados_2024.parquet"
            path_return24 = process_general_microdata(file_return24, out_return24, "Retornados 2024")
            results.append(("migración: retornados 2024", path_return24))
            
        file_return23_usa = RAW_DATA_DIR / "retornados" / "retornados_usa_aereo.csv"
        if file_return23_usa.exists():
            out_return23 = PROCESSED_DATA_DIR / "migracion" / "retornados_usa_aereo_2023.parquet"
            df_usa = pl.read_csv(str(file_return23_usa), ignore_errors=True)
            # normalizar columnas
            cols = [c.strip().lower().replace(" ", "_") for c in df_usa.columns]
            df_usa = df_usa.rename(dict(zip(df_usa.columns, cols)))
            
            # normalizar departamento
            dept_candidates = [c for c in df_usa.columns if "depto" in c or "departamento" in c]
            if dept_candidates:
                dept_col = dept_candidates[0]
                dept_parsed = [normalize_depto(v) for v in df_usa[dept_col].to_list()]
                df_usa = df_usa.with_columns([
                    pl.Series("depto_codigo_norm", [p["codigo"] if p else None for p in dept_parsed], dtype=pl.Int32),
                    pl.Series("depto_nombre_norm", [p["nombre"] if p else None for p in dept_parsed], dtype=pl.Utf8),
                    pl.Series("region_id_norm", [p["region_id"] if p else None for p in dept_parsed], dtype=pl.Int32),
                ])
            out_return23.parent.mkdir(parents=True, exist_ok=True)
            df_usa.write_parquet(str(out_return23), compression="zstd")
            print(f"✓ retornados usa 2023 guardados en: {out_return23} ({df_usa.shape[0]} filas)")
            results.append(("migración: retornados usa aéreo 2023", out_return23))
    except Exception as e:
        print(f"error en migracion: {e}")

    # 8. educacion: matriculados educacion superior 2025
    try:
        print("\n[8/8] procesando educacion superior...")
        path_edu = process_higher_education()
        if path_edu.exists():
            results.append(("educación: matriculados superior 2025", path_edu))
    except Exception as e:
        print(f"error en educacion: {e}")

    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"resumen etl completado en {elapsed:.2f} segundos")
    print("=" * 70)
    for title, path in results:
        df_tmp = pl.read_parquet(str(path))
        size_bytes = path.stat().st_size
        print(f"  • {title:38s}: {df_tmp.shape[0]:>9,d} filas | {df_tmp.shape[1]:>3d} cols | {size_bytes:>11,d} bytes")
    print("=" * 70)


if __name__ == "__main__":
    run_full_etl()
