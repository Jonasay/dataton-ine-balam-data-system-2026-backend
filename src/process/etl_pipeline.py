from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import polars as pl

from src.core.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.core.geo_master import (
    DEPARTAMENTOS_INE,
    REGIONES_SOCIOECONOMICAS,
    normalize_depto,
    strip_accents,
)

# mapeo estandarizado de nombres de meses en espanol a numero entero (1..12)
MONTH_NAMES_MAP: Dict[str, int] = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}
MESES_MAP = MONTH_NAMES_MAP


def normalize_month(value: Any) -> Optional[int]:
    """convertir representacion de mes (texto o numero) a entero de 1 a 12."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = int(value)
        return v if 1 <= v <= 12 else None
    cleaned = strip_accents(str(value))
    return MONTH_NAMES_MAP.get(cleaned)


def process_population_projections(
    raw_file: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Tuple[Path, Path]:
    """procesar proyecciones demograficas oficiales 2015-2030 del ine."""
    if raw_file is None:
        raw_file = RAW_DATA_DIR / "proyecciones-de-poblacion-2015-2030" / "estimaciones-y-proyecciones-de-la-poblacion-total-por-municipio-segun-sexo-y-edad.-2015-2030.xlsx"
    if output_dir is None:
        output_dir = PROCESSED_DATA_DIR / "demografia"
        
    output_dir.mkdir(parents=True, exist_ok=True)
    if not raw_file.exists():
        raise FileNotFoundError(f"no existe el archivo de proyecciones: {raw_file}")

    print(f"leyendo proyecciones demograficas desde: {raw_file}...")
    df_raw = pl.read_excel(str(raw_file))

    # identificar columnas de anios (2015..2030)
    year_cols = [c for c in df_raw.columns if re.match(r"^20\d\d$", str(c))]
    id_cols = [c for c in df_raw.columns if c not in year_cols]

    # convertir a formato largo (melt / unpivot)
    df_long = df_raw.unpivot(
        on=year_cols,
        index=id_cols,
        variable_name="anio_str",
        value_name="poblacion",
    )

    # normalizar tipos y nombres de columnas
    df_clean = df_long.with_columns([
        pl.col("DEPTO").cast(pl.Utf8).str.strip_chars().alias("depto_codigo_str"),
        pl.col("MUPIO").cast(pl.Utf8).str.strip_chars().alias("mupio_codigo_str"),
        pl.col("SEXO").cast(pl.Int32).alias("sexo_id"),
        pl.col("EDAD").cast(pl.Int32).alias("edad"),
        pl.col("anio_str").cast(pl.Int32).alias("anio"),
        pl.col("poblacion").cast(pl.Int64).alias("poblacion"),
    ])

    df_clean = df_clean.with_columns(
        pl.col("depto_codigo_str").cast(pl.Int32).alias("depto_codigo")
    )

    # enriquecer con catalogo de departamentos
    departments_meta = []
    for code, dept in DEPARTAMENTOS_INE.items():
        departments_meta.append({
            "depto_codigo": code,
            "depto_nombre": dept["nombre"],
            "depto_iso": dept["iso"],
            "region_id": dept["region_id"],
            "region_nombre": dept["region_nombre"],
        })
    df_departments = pl.DataFrame(departments_meta)
    df_clean = df_clean.join(df_departments, on="depto_codigo", how="left")

    # reordenar columnas para la tabla granular
    cols_order = [
        "anio", "depto_codigo", "depto_nombre", "depto_iso", "region_id", "region_nombre",
        "mupio_codigo_str", "sexo_id", "edad", "poblacion",
    ]
    df_granular = df_clean.select(cols_order)
    path_granular = output_dir / "poblacion_proyectada_edad_sexo.parquet"
    df_granular.write_parquet(str(path_granular), compression="zstd")
    print(f"✓ poblacion granular guardada en: {path_granular} ({df_granular.shape[0]} filas)")

    # tabla agregada departamental filtrando sexo=0 (ambos sexos)
    df_department = (
        df_clean.filter(pl.col("sexo_id") == 0)
        .group_by(["anio", "depto_codigo", "depto_nombre", "depto_iso", "region_id", "region_nombre"])
        .agg(pl.col("poblacion").sum().alias("poblacion_total"))
        .sort(["anio", "depto_codigo"])
    )
    path_department = output_dir / "poblacion_proyectada_departamental.parquet"
    df_department.write_parquet(str(path_department), compression="zstd")
    print(f"✓ poblacion departamental guardada en: {path_department} ({df_department.shape[0]} filas)")

    return path_granular, path_department


def process_basic_basket(
    raw_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """procesar series de canasta basica alimentaria (cba) y canasta ampliada (ca)."""
    if raw_dir is None:
        raw_dir = RAW_DATA_DIR / "costos-de-la-cba-urbana-y-rural"
    if output_dir is None:
        output_dir = PROCESSED_DATA_DIR / "economia"
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    files_map = [
        ("costo-cba-percapita_u.xlsx", "Urbana", "CBA"),
        ("costo-cba-percapita_r.xlsx", "Rural", "CBA"),
        ("costo-campliada-urbana-2.xlsx", "Urbana", "CA"),
        ("costo-campliada-rural-2-1.xlsx", "Rural", "CA"),
    ]

    frames = []
    for filename, domain, basket_type in files_map:
        filepath = raw_dir / filename
        if not filepath.exists():
            print(f"aviso: archivo {filepath} no encontrado, omitiendo...")
            continue
            
        df = pl.read_excel(str(filepath))
        
        # detectar columnas temporales y numericas
        cols = df.columns
        year_col = next(c for c in cols if "año" in c.lower())
        month_col = next(c for c in cols if "mes" in c.lower())
        daily_col = next(c for c in cols if "diario" in c.lower())
        monthly_col = next(c for c in cols if "mensual" in c.lower())

        df_norm = df.select([
            pl.col(year_col).cast(pl.Int32).alias("anio"),
            pl.col(month_col).cast(pl.Utf8).alias("mes_nombre"),
            pl.col(daily_col).cast(pl.Float64).alias("costo_diario_percapita"),
            pl.col(monthly_col).cast(pl.Float64).alias("costo_mensual_percapita"),
        ]).with_columns([
            pl.lit(domain).alias("dominio"),
            pl.lit(basket_type).alias("tipo_canasta"),
        ])
        
        # mapear mes a numero entero
        month_ints = [normalize_month(m) for m in df_norm["mes_nombre"].to_list()]
        df_norm = df_norm.with_columns(pl.Series("mes", month_ints, dtype=pl.Int32))
        frames.append(df_norm)

    if not frames:
        raise RuntimeError("no se encontraron archivos de canasta basica para procesar.")

    df_combined = pl.concat(frames).sort(["tipo_canasta", "dominio", "anio", "mes"])

    # calcular variaciones intermensuales e interanuales
    df_combined = df_combined.with_columns([
        (
            (pl.col("costo_mensual_percapita") - pl.col("costo_mensual_percapita").shift(1).over(["tipo_canasta", "dominio"]))
            / pl.col("costo_mensual_percapita").shift(1).over(["tipo_canasta", "dominio"])
            * 100.0
        ).round(2).alias("variacion_intermensual_pct"),
        (
            (pl.col("costo_mensual_percapita") - pl.col("costo_mensual_percapita").shift(12).over(["tipo_canasta", "dominio"]))
            / pl.col("costo_mensual_percapita").shift(12).over(["tipo_canasta", "dominio"])
            * 100.0
        ).round(2).alias("variacion_interanual_pct"),
    ])

    out_file = output_dir / "canasta_basica_mensual.parquet"
    df_combined.write_parquet(str(out_file), compression="zstd")
    print(f"✓ canasta basica consolidada guardada en: {out_file} ({df_combined.shape[0]} filas)")
    return out_file


def process_cpi_indicators(
    raw_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Tuple[Path, Path, Path]:
    """procesar indicadores del ipc (base diciembre 2023 = 100)."""
    if raw_dir is None:
        raw_dir = RAW_DATA_DIR / "indicadores-ipc-base-diciembre-2023-100-0"
    if output_dir is None:
        output_dir = PROCESSED_DATA_DIR / "economia"
        
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. ipc por region
    region_file = raw_dir / "ipc_reg_b23_es24.xlsx"
    variation_file = raw_dir / "ipc_varinreg_b23_es24.xlsx"
    
    df_reg = pl.read_excel(str(region_file))
    df_var = pl.read_excel(str(variation_file))
    
    region_cols = [c for c in df_reg.columns if "regi" in c.lower() or "rep" in c.lower()]
    df_reg_long = df_reg.unpivot(on=region_cols, index=["Año", "Mes"], variable_name="region_nombre_raw", value_name="indice_ipc")
    df_var_long = df_var.unpivot(on=region_cols, index=["Año", "Mes"], variable_name="region_nombre_raw", value_name="variacion_interanual_pct")
    
    df_ipc_region = df_reg_long.join(df_var_long, on=["Año", "Mes", "region_nombre_raw"])
    
    # limpiar region y asociar identificador numerico
    def clean_region_id(name: str) -> Tuple[int, str]:
        s = strip_accents(name)
        if "REP" in s:
            return 0, "República"
        m = re.search(r"REGION\s+([IVX]+)", s)
        if m:
            roman = m.group(1)
            romans = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
            rid = romans.get(roman, 99)
            rname = REGIONES_SOCIOECONOMICAS.get(rid, {}).get("nombre", f"Región {roman}")
            return rid, f"Región {roman} ({rname})"
        return 99, name

    parsed_regions = [clean_region_id(r) for r in df_ipc_region["region_nombre_raw"].to_list()]
    df_ipc_region = df_ipc_region.with_columns([
        pl.col("Año").cast(pl.Int32).alias("anio"),
        pl.Series("mes", [normalize_month(m) for m in df_ipc_region["Mes"].to_list()], dtype=pl.Int32),
        pl.Series("region_id", [p[0] for p in parsed_regions], dtype=pl.Int32),
        pl.Series("region_nombre", [p[1] for p in parsed_regions], dtype=pl.Utf8),
        pl.col("indice_ipc").cast(pl.Float64),
        pl.col("variacion_interanual_pct").cast(pl.Float64),
    ]).select(["anio", "mes", "region_id", "region_nombre", "indice_ipc", "variacion_interanual_pct"]).sort(["anio", "mes", "region_id"])

    out_region = output_dir / "ipc_regiones.parquet"
    df_ipc_region.write_parquet(str(out_region), compression="zstd")
    print(f"✓ ipc regiones guardado en: {out_region}")

    # 2. poder adquisitivo del quetzal
    purchasing_file = raw_dir / "ipc_perypod_b23_es24.xlsx"
    df_purchasing = pl.read_excel(str(purchasing_file))
    df_purchasing_clean = df_purchasing.select([
        pl.col("Año").cast(pl.Int32).alias("anio"),
        pl.Series("mes", [normalize_month(m) for m in df_purchasing["Mes"].to_list()], dtype=pl.Int32),
        pl.col("Número índice").cast(pl.Float64).alias("indice_ipc_nacional"),
        pl.col("Poder adquisitivo").cast(pl.Float64).alias("poder_adquisitivo_quetzal"),
        pl.col(df_purchasing.columns[-1]).cast(pl.Float64).alias("perdida_poder_adquisitivo"),
    ]).sort(["anio", "mes"])
    out_purchasing = output_dir / "ipc_poder_adquisitivo.parquet"
    df_purchasing_clean.write_parquet(str(out_purchasing), compression="zstd")
    print(f"✓ poder adquisitivo guardado en: {out_purchasing}")

    # 3. ipc por divisiones de gasto
    divisions_file = raw_dir / "ipc_divga_b23_es24.xlsx"
    divisions_variation_file = raw_dir / "ipc_varintdivga_b23_es24.xlsx"
    df_div = pl.read_excel(str(divisions_file))
    df_div_var = pl.read_excel(str(divisions_variation_file))
    
    division_cols = [c for c in df_div.columns if c not in ["Año", "Mes"]]
    df_div_long = df_div.unpivot(on=division_cols, index=["Año", "Mes"], variable_name="division_gasto", value_name="indice_ipc")
    df_div_var_long = df_div_var.unpivot(on=division_cols, index=["Año", "Mes"], variable_name="division_gasto", value_name="variacion_interanual_pct")
    
    df_ipc_divisions = df_div_long.join(df_div_var_long, on=["Año", "Mes", "division_gasto"]).select([
        pl.col("Año").cast(pl.Int32).alias("anio"),
        pl.Series("mes", [normalize_month(m) for m in df_div_long["Mes"].to_list()], dtype=pl.Int32),
        pl.col("division_gasto").cast(pl.Utf8),
        pl.col("indice_ipc").cast(pl.Float64),
        pl.col("variacion_interanual_pct").cast(pl.Float64),
    ]).sort(["anio", "mes", "division_gasto"])
    
    out_divisions = output_dir / "ipc_divisiones_gasto.parquet"
    df_ipc_divisions.write_parquet(str(out_divisions), compression="zstd")
    print(f"✓ ipc divisiones guardado en: {out_divisions}")

    return out_region, out_purchasing, out_divisions


def process_general_microdata(
    input_file: Path,
    output_parquet: Path,
    topic: str,
) -> Path:
    """procesador generico de microdatos institucionales."""
    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    print(f"procesando microdatos de {topic} desde: {input_file.name}...")
    
    df = pl.read_excel(str(input_file))
    cols = df.columns
    cols_clean = [c.strip().lower().replace(" ", "_") for c in cols]
    df = df.rename(dict(zip(cols, cols_clean)))

    # localizar columna departamental
    dept_candidates = [c for c in df.columns if any(k in c for k in ["depto", "departamento"])]
    if dept_candidates:
        dept_col = dept_candidates[0]
        # mapear codigos y nombres oficiales
        parsed_departments = []
        for val in df[dept_col].to_list():
            record = normalize_depto(val)
            if record:
                parsed_departments.append((record["codigo"], record["nombre"], record["iso"], record["region_id"], record["region_nombre"]))
            else:
                parsed_departments.append((None, None, None, None, None))
                
        df = df.with_columns([
            pl.Series("depto_codigo_norm", [p[0] for p in parsed_departments], dtype=pl.Int32),
            pl.Series("depto_nombre_norm", [p[1] for p in parsed_departments], dtype=pl.Utf8),
            pl.Series("depto_iso_norm", [p[2] for p in parsed_departments], dtype=pl.Utf8),
            pl.Series("region_id_norm", [p[3] for p in parsed_departments], dtype=pl.Int32),
            pl.Series("region_nombre_norm", [p[4] for p in parsed_departments], dtype=pl.Utf8),
        ])

    df.write_parquet(str(output_parquet), compression="zstd")
    print(f"✓ microdatos de {topic} guardados en: {output_parquet} ({df.shape[0]} filas, {df.shape[1]} columnas)")
    return output_parquet


def process_higher_education(
    raw_file: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """procesar matriculados de educacion superior."""
    if raw_file is None:
        raw_file = RAW_DATA_DIR / "educacion-superior-matriculados" / "matriculados_educacion_superior-2025.xlsx"
    if output_dir is None:
        output_dir = PROCESSED_DATA_DIR / "educacion"
        
    output_dir.mkdir(parents=True, exist_ok=True)
    if not raw_file.exists():
        print(f"aviso: archivo de educacion superior no encontrado en {raw_file}")
        return output_dir / "matriculados_educacion_superior_2025.parquet"

    print(f"procesando educacion superior desde: {raw_file.name}...")
    import fastexcel
    excel = fastexcel.read_excel(str(raw_file))
    df = excel.load_sheet(0).to_polars()
    
    # normalizar columnas a minusculas
    clean_cols = [c.strip().lower() for c in df.columns]
    df = df.rename(dict(zip(df.columns, clean_cols)))
    
    # normalizar departamento
    if "depto" in df.columns:
        parsed_departments = []
        for val in df["depto"].to_list():
            record = normalize_depto(val)
            if record:
                parsed_departments.append((record["codigo"], record["nombre"], record["iso"], record["region_id"], record["region_nombre"]))
            else:
                parsed_departments.append((None, None, None, None, None))
                
        df = df.with_columns([
            pl.Series("depto_codigo_norm", [p[0] for p in parsed_departments], dtype=pl.Int32),
            pl.Series("depto_nombre_norm", [p[1] for p in parsed_departments], dtype=pl.Utf8),
            pl.Series("depto_iso_norm", [p[2] for p in parsed_departments], dtype=pl.Utf8),
            pl.Series("region_id_norm", [p[3] for p in parsed_departments], dtype=pl.Int32),
            pl.Series("region_nombre_norm", [p[4] for p in parsed_departments], dtype=pl.Utf8),
        ])
        
    out_file = output_dir / "matriculados_educacion_superior_2025.parquet"
    df.write_parquet(str(out_file), compression="zstd")
    print(f"✓ matriculados educacion superior guardados en: {out_file} ({df.shape[0]} filas)")
    return out_file


# alias compatibles
process_proyecciones_poblacion = process_population_projections
process_canasta_basica = process_basic_basket
process_indicadores_ipc = process_cpi_indicators
process_microdata_general = process_general_microdata
