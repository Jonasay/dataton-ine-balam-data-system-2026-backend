from __future__ import annotations

import math
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import polars as pl

from src.core.config import PROCESSED_DATA_DIR

# mapeo de conjuntos nucleo con visualizaciones oficiales preconstruidas
CURATED_DATASET_VISUALIZATIONS: Dict[str, List[Dict[str, str]]] = {
    "proyecciones-de-poblacion-2015-2030": [
        {"titulo": "Trayectoria Demográfica 3D (2015–2030)", "endpoint": "/api/v1/visualizaciones/3d/trayectoria-demografica"},
        {"titulo": "Crecimiento Demográfico Departamental", "endpoint": "/api/v1/visualizaciones/tendencias/crecimiento-demografico"},
        {"titulo": "Estructura Etaria por Departamento", "endpoint": "/api/v1/visualizaciones/barras/estructura-demografica"},
    ],
    "costos-de-la-cba-urbana-y-rural": [
        {"titulo": "Evolución y Pronóstico de Canasta Básica", "endpoint": "/api/v1/visualizaciones/tendencias/costo-vida"},
        {"titulo": "Trayectoria 3D CBA Urbana vs Rural", "endpoint": "/api/v1/visualizaciones/3d/trayectoria-costo-vida"},
    ],
    "indicadores-ipc-base-diciembre-2023-100-0": [
        {"titulo": "Tendencias del IPC por Región", "endpoint": "/api/v1/visualizaciones/tendencias/ipc?vista=regiones"},
        {"titulo": "IPC por Divisiones de Gasto", "endpoint": "/api/v1/visualizaciones/tendencias/ipc?vista=divisiones"},
        {"titulo": "Pérdida del Poder Adquisitivo", "endpoint": "/api/v1/visualizaciones/tendencias/ipc?vista=poder_adquisitivo"},
    ],
    "estadisticas-vitales-defunciones": [
        {"titulo": "Tasa Bruta de Mortalidad por Departamento", "endpoint": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_mortalidad_por_1000"},
        {"titulo": "Ranking Municipal de Mortalidad", "endpoint": "/api/v1/visualizaciones/barras/ranking-municipal?indicador=tasa_mortalidad_por_1000"},
    ],
    "estadisticas-vitales-nacimientos": [
        {"titulo": "Tasa Bruta de Natalidad por Departamento", "endpoint": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_natalidad_por_1000"},
        {"titulo": "Ranking Municipal de Natalidad", "endpoint": "/api/v1/visualizaciones/barras/ranking-municipal?indicador=tasa_natalidad_por_1000"},
    ],
    "hechos-delictivos-servicio-medico-necropsias-inacif": [
        {"titulo": "Tasa de Necropsias INACIF Departamental", "endpoint": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_necropsias_por_100k"},
        {"titulo": "Puntos Críticos Municipales INACIF", "endpoint": "/api/v1/visualizaciones/barras/ranking-municipal?indicador=tasa_necropsias_por_100k"},
    ],
    "accidentes-de-transito-fallecidos-y-lesionados": [
        {"titulo": "Tasa de Víctimas Viales PNC", "endpoint": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_victimas_viales_por_100k"},
        {"titulo": "Distribución de Víctimas Viales", "endpoint": "/api/v1/visualizaciones/pastel/distribucion?tipo=victimas_viales"},
    ],
    "educacion-superior-matriculados": [
        {"titulo": "Matrícula Universitaria por 10k Hab.", "endpoint": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_matricula_superior_por_10k"},
        {"titulo": "Paridad de Género Universitaria", "endpoint": "/api/v1/visualizaciones/pastel/distribucion?tipo=educacion_genero"},
    ],
    "retornados-ano-2024vv": [
        {"titulo": "Tasa de Retorno Migratorio por 10k Hab.", "endpoint": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_retorno_migratorio_por_10k"},
        {"titulo": "Composición de Retornados", "endpoint": "/api/v1/visualizaciones/barras/composicion-retornados"},
        {"titulo": "Proporción de Niñez Retornada", "endpoint": "/api/v1/visualizaciones/pastel/distribucion?tipo=retornados_edad"},
    ],
    "retornados": [
        {"titulo": "Tasa de Retorno Migratorio por 10k Hab.", "endpoint": "/api/v1/visualizaciones/barras/ranking-departamental?indicador=tasa_retorno_migratorio_por_10k"},
        {"titulo": "Composición de Retornados", "endpoint": "/api/v1/visualizaciones/barras/composicion-retornados"},
    ],
}

_IDENTIFIER_PATTERN = re.compile(r"(^_id$|id$|_id$|^cod_|^codigo_|^num_corre|^mupio$|^depto$|^depocu$|^depreg$)")
_TEMPORAL_PATTERN = re.compile(r"(anio|año|year|fecha|periodo|mes|semestre|trimestre)")


def _sanitize_value(value: Any) -> Any:
    """Convertir valores no compatibles con json estandar a tipos nativos seguros."""
    if value is None:
        return None
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        val = float(value)
        return round(val, 4) if math.isfinite(val) else None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _sanitize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalizar filas para serializacion json estricta."""
    return [{str(k): _sanitize_value(v) for k, v in row.items()} for row in rows]


def _clean_column_names(raw_names: List[Any]) -> List[str]:
    """Limpiar nombres de columnas eliminando saltos de linea y duplicados."""
    seen: Dict[str, int] = {}
    cleaned: List[str] = []
    for idx, raw in enumerate(raw_names):
        text = re.sub(r"\s+", " ", str(raw or "").strip())
        if not text or text.startswith("__UNNAMED__"):
            text = f"columna_{idx + 1}"
        count = seen.get(text, 0) + 1
        seen[text] = count
        cleaned.append(text if count == 1 else f"{text}_{count}")
    return cleaned


def _detect_header_row(raw_df: pl.DataFrame) -> int:
    """Detectar fila real de encabezados en hojas de calculo del ine con banners iniciales."""
    max_scan = min(15, raw_df.height)
    if max_scan == 0:
        return 0

    row_scores: List[Tuple[int, int]] = []
    for r_idx in range(max_scan):
        row_vals = raw_df.row(r_idx)
        non_empty = [
            str(v).strip()
            for v in row_vals
            if v is not None and str(v).strip() != ""
        ]
        # penalizar filas puramente numericas porque suelen ser datos y no encabezados
        text_like = sum(1 for v in non_empty if not re.fullmatch(r"-?\d+(\.\d+)?", v))
        row_scores.append((r_idx, len(non_empty) + text_like))

    best_score = max(score for _, score in row_scores)
    if best_score == 0:
        return 0

    threshold = max(2, int(best_score * 0.7))
    for r_idx, score in row_scores:
        if score >= threshold:
            return r_idx
    return 0


def _coerce_numeric_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Convertir columnas de texto puramente numericas a enteros o flotantes."""
    updates: List[pl.Expr] = []
    for col_name in df.columns:
        dtype = df.schema[col_name]
        if dtype not in (pl.Utf8, pl.String):
            continue
        series = df[col_name].drop_nulls().str.strip_chars()
        non_empty = series.filter(series != "")
        if len(non_empty) == 0:
            continue

        # intentar conversion a entero o flotante solo si al menos 85% son numericos validos
        cleaned_str = pl.col(col_name).cast(pl.Utf8).str.strip_chars().str.replace_all(",", "")
        int_parsed = non_empty.str.replace_all(",", "").cast(pl.Int64, strict=False)
        if int_parsed.null_count() <= len(non_empty) * 0.15:
            updates.append(
                pl.when(pl.col(col_name).cast(pl.Utf8).str.strip_chars() == "")
                .then(None)
                .otherwise(cleaned_str.cast(pl.Int64, strict=False))
                .alias(col_name)
            )
            continue

        float_parsed = non_empty.str.replace_all(",", "").cast(pl.Float64, strict=False)
        if float_parsed.null_count() <= len(non_empty) * 0.15:
            updates.append(
                pl.when(pl.col(col_name).cast(pl.Utf8).str.strip_chars() == "")
                .then(None)
                .otherwise(cleaned_str.cast(pl.Float64, strict=False))
                .alias(col_name)
            )

    return df.with_columns(updates) if updates else df


def _read_excel_clean(local_path: Path, hoja_id: int = 1) -> Tuple[pl.DataFrame, List[str], int]:
    """Leer libro excel con deteccion automatica de encabezados y devolver dataframe limpio."""
    import fastexcel

    wb = fastexcel.read_excel(str(local_path))
    sheet_names = list(wb.sheet_names)
    if not sheet_names:
        raise ValueError("el archivo excel no contiene hojas legibles")

    active_sheet = max(1, min(hoja_id, len(sheet_names)))
    raw_df = wb.load_sheet(active_sheet - 1, header_row=None).to_polars()
    if raw_df.height == 0:
        return raw_df, sheet_names, active_sheet

    header_idx = _detect_header_row(raw_df)
    header_vals = list(raw_df.row(header_idx))
    clean_cols = _clean_column_names(header_vals)

    data_df = raw_df.slice(header_idx + 1)
    data_df = data_df.rename(dict(zip(data_df.columns, clean_cols)))

    # descartar filas completamente vacias
    non_empty_expr = pl.any_horizontal([
        pl.col(c).is_not_null() & (pl.col(c).cast(pl.Utf8).str.strip_chars() != "")
        for c in data_df.columns
    ])
    data_df = data_df.filter(non_empty_expr)
    data_df = _coerce_numeric_columns(data_df)
    return data_df, sheet_names, active_sheet


def _read_csv_clean(local_path: Path) -> pl.DataFrame:
    """Leer csv detectando separador coma o punto y coma y limpiando columnas."""
    sample_text = local_path.read_bytes()[:4096].decode("utf-8", errors="ignore")
    first_line = sample_text.splitlines()[0] if sample_text else ""
    separator = ";" if first_line.count(";") > first_line.count(",") else ","

    try:
        df = pl.read_csv(str(local_path), separator=separator, ignore_errors=True, encoding="utf8-lossy")
    except Exception:
        df = pl.read_csv(str(local_path), separator=separator, ignore_errors=True)

    clean_cols = _clean_column_names(df.columns)
    df = df.rename(dict(zip(df.columns, clean_cols)))
    return _coerce_numeric_columns(df)


def load_or_process_dataset_parquet(
    local_path: Path,
    slug: str,
    hoja_id: int = 1,
    processed_dir: Path = PROCESSED_DATA_DIR,
    regenerar: bool = False,
) -> Dict[str, Any]:
    """Cargar parquet procesado en cache o transformar el archivo crudo y guardarlo en disco."""
    ext = local_path.suffix.lower()
    target_dir = processed_dir / "datasets" / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    if ext in {".xlsx", ".xls"}:
        import fastexcel
        wb = fastexcel.read_excel(str(local_path))
        sheet_names = list(wb.sheet_names)
        active_sheet = max(1, min(hoja_id, len(sheet_names))) if sheet_names else 1
        parquet_path = target_dir / f"{local_path.stem}_hoja{active_sheet}.parquet"
    else:
        sheet_names = []
        active_sheet = 1
        parquet_path = target_dir / f"{local_path.stem}.parquet"

    cache_valid = (
        not regenerar
        and parquet_path.exists()
        and parquet_path.stat().st_size > 0
        and parquet_path.stat().st_mtime >= local_path.stat().st_mtime
    )

    if cache_valid:
        df = pl.read_parquet(str(parquet_path))
        return {
            "df": df,
            "parquet_path": parquet_path,
            "rel_parquet": str(parquet_path.relative_to(processed_dir)),
            "hojas": sheet_names,
            "hoja_actual": active_sheet if sheet_names else None,
            "ya_estaba_procesado": True,
        }

    if ext in {".xlsx", ".xls"}:
        df, sheet_names, active_sheet = _read_excel_clean(local_path, hoja_id=hoja_id)
    elif ext == ".csv":
        df = _read_csv_clean(local_path)
    elif ext == ".parquet":
        df = pl.read_parquet(str(local_path))
    elif ext == ".zip":
        with zipfile.ZipFile(local_path, "r") as zf:
            tabular_names = [n for n in zf.namelist() if n.lower().endswith((".csv", ".xlsx", ".xls"))]
            if not tabular_names:
                raise ValueError("el archivo zip no contiene tablas csv o excel compatibles")
            inner_name = tabular_names[0]
            extracted_path = target_dir / Path(inner_name).name
            extracted_path.write_bytes(zf.read(inner_name))
            if extracted_path.suffix.lower() == ".csv":
                df = _read_csv_clean(extracted_path)
            else:
                df, sheet_names, active_sheet = _read_excel_clean(extracted_path, hoja_id=hoja_id)
    else:
        raise ValueError(f"formato de recurso no soportado para procesamiento automatico: {ext}")

    df.write_parquet(str(parquet_path), compression="zstd")
    return {
        "df": df,
        "parquet_path": parquet_path,
        "rel_parquet": str(parquet_path.relative_to(processed_dir)),
        "hojas": sheet_names,
        "hoja_actual": active_sheet if sheet_names else None,
        "ya_estaba_procesado": False,
    }


def _classify_columns(df: pl.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    """Clasificar columnas en numericas, categoricas graficables y temporales."""
    numeric_cols: List[str] = []
    categorical_cols: List[str] = []
    temporal_cols: List[str] = []

    for col in df.columns:
        dtype = df.schema[col]
        col_lower = col.lower()
        n_unique = df[col].drop_nulls().n_unique()

        if _TEMPORAL_PATTERN.search(col_lower) and 2 <= n_unique <= 60:
            temporal_cols.append(col)

        if dtype.is_numeric():
            if not _IDENTIFIER_PATTERN.search(col_lower):
                numeric_cols.append(col)
        elif dtype in (pl.Utf8, pl.String, pl.Categorical):
            if 2 <= n_unique <= 40:
                categorical_cols.append(col)

    # priorizar columnas categoricas con cardinalidad ideal (2 a 22 valores)
    categorical_cols.sort(
        key=lambda c: (
            0 if any(k in c.lower() for k in ("depto", "departamento", "region", "tipo", "estado", "licencia", "sexo", "area")) else 1,
            abs(df[c].drop_nulls().n_unique() - 8),
        )
    )
    return numeric_cols, categorical_cols, temporal_cols


def _aggregate_series(
    df: pl.DataFrame,
    group_col: str,
    metric_col: Optional[str] = None,
    limit: int = 12,
) -> Tuple[List[Dict[str, Any]], str]:
    """Agrupar dataframe por categoria devolviendo conteos o sumatoria de metrica numerica."""
    cleaned = df.filter(
        pl.col(group_col).is_not_null() & (pl.col(group_col).cast(pl.Utf8).str.strip_chars() != "")
    )
    if metric_col and metric_col in df.columns and df.schema[metric_col].is_numeric():
        agg_df = (
            cleaned.group_by(group_col)
            .agg(pl.col(metric_col).sum().alias("valor"))
            .sort("valor", descending=True)
            .head(limit)
        )
        metric_label = metric_col
    else:
        agg_df = (
            cleaned.group_by(group_col)
            .agg(pl.len().alias("valor"))
            .sort("valor", descending=True)
            .head(limit)
        )
        metric_label = "Registros"

    total_sum = sum(float(r["valor"] or 0.0) for r in agg_df.to_dicts()) or 1.0
    points = [
        {
            "etiqueta": str(row[group_col]),
            "valor": round(float(row["valor"] or 0.0), 2),
            "porcentaje": round((float(row["valor"] or 0.0) / total_sum) * 100.0, 1),
        }
        for row in agg_df.to_dicts()
    ]
    return points, metric_label


def build_dataset_analysis_payload(
    df: pl.DataFrame,
    slug: str,
    resource: Dict[str, Any],
    rel_parquet: str,
    hojas: List[str],
    hoja_actual: Optional[int],
    ya_estaba_descargado: bool,
    ya_estaba_procesado: bool,
    agrupar_por: Optional[str] = None,
    columna_valor: Optional[str] = None,
    limite_muestra: int = 25,
) -> Dict[str, Any]:
    """Construir resumen estadistico, tabla procesada y graficas automaticas de un recurso."""
    numeric_cols, categorical_cols, temporal_cols = _classify_columns(df)
    active_group = agrupar_por if agrupar_por in df.columns else (categorical_cols[0] if categorical_cols else None)
    active_metric = columna_valor if columna_valor and columna_valor in df.columns and df.schema[columna_valor].is_numeric() else None

    # estadisticas descriptivas de las columnas numericas principales
    numeric_stats: List[Dict[str, Any]] = []
    for col in numeric_cols[:8]:
        ser = df[col].drop_nulls()
        if len(ser) == 0:
            continue
        numeric_stats.append({
            "columna": col,
            "conteo": int(len(ser)),
            "minimo": _sanitize_value(float(ser.min())),
            "maximo": _sanitize_value(float(ser.max())),
            "promedio": _sanitize_value(float(ser.mean())),
            "mediana": _sanitize_value(float(ser.median())),
            "suma": _sanitize_value(float(ser.sum())),
        })

    # generar graficas descriptivas adaptadas a la estructura del conjunto
    charts: List[Dict[str, Any]] = []

    if active_group:
        pts, metric_label = _aggregate_series(df, active_group, active_metric, limit=12)
        if pts:
            charts.append({
                "id": "distribucion_principal",
                "titulo": f"{metric_label} por {active_group}",
                "subtitulo": f"Principales categorías ordenadas ({len(pts)} mostradas)",
                "tipo": "bar",
                "eje_x": active_group,
                "eje_y": metric_label,
                "datos": pts,
            })

    # segunda grafica proporcional (dona) sobre otra variable categorica o participacion porcentual
    secondary_group = next((c for c in categorical_cols if c != active_group), None)
    if secondary_group:
        pts_sec, sec_label = _aggregate_series(df, secondary_group, active_metric, limit=8)
        if pts_sec:
            charts.append({
                "id": "composicion_secundaria",
                "titulo": f"Composición por {secondary_group}",
                "subtitulo": f"Participación porcentual sobre {sec_label}",
                "tipo": "donut",
                "eje_x": secondary_group,
                "eje_y": sec_label,
                "datos": pts_sec,
            })
    elif active_group and charts:
        charts.append({
            "id": "proporcion_principal",
            "titulo": f"Participación proporcional ({active_group})",
            "subtitulo": "Porcentaje relativo respecto al total mostrado",
            "tipo": "donut",
            "eje_x": active_group,
            "eje_y": charts[0]["eje_y"],
            "datos": charts[0]["datos"][:7],
        })

    # tercera grafica: serie temporal si existe columna de tiempo o comparativo de medias numericas
    temp_col = next((c for c in temporal_cols if c != active_group), None)
    if temp_col:
        temp_df = (
            df.filter(pl.col(temp_col).is_not_null())
            .group_by(temp_col)
            .agg(
                pl.col(active_metric).sum().alias("valor") if active_metric else pl.len().alias("valor")
            )
            .sort(temp_col)
            .head(24)
        )
        t_total = sum(float(r["valor"] or 0.0) for r in temp_df.to_dicts()) or 1.0
        t_pts = [
            {
                "etiqueta": str(r[temp_col]),
                "valor": round(float(r["valor"] or 0.0), 2),
                "porcentaje": round((float(r["valor"] or 0.0) / t_total) * 100.0, 1),
            }
            for r in temp_df.to_dicts()
        ]
        if len(t_pts) >= 2:
            charts.append({
                "id": "tendencia_temporal",
                "titulo": f"Evolución por {temp_col}",
                "subtitulo": f"Serie ordenada por {temp_col}",
                "tipo": "line",
                "eje_x": temp_col,
                "eje_y": active_metric or "Registros",
                "datos": t_pts,
            })
    elif len(numeric_stats) >= 2:
        stat_pts = [
            {
                "etiqueta": item["columna"],
                "valor": round(float(item["promedio"] or 0.0), 2),
                "porcentaje": 0.0,
            }
            for item in numeric_stats[:8]
        ]
        max_stat = max((p["valor"] for p in stat_pts), default=1.0) or 1.0
        for p in stat_pts:
            p["porcentaje"] = round((p["valor"] / max_stat) * 100.0, 1)
        charts.append({
            "id": "comparativo_numerico",
            "titulo": "Promedio por variable numérica",
            "subtitulo": "Comparación de magnitudes promedio detectadas",
            "tipo": "bar",
            "eje_x": "Variable",
            "eje_y": "Promedio",
            "datos": stat_pts,
        })

    # completitud global de celdas no nulas
    total_cells = max(df.height * max(df.width, 1), 1)
    null_cells = sum(df[col].null_count() for col in df.columns)
    completeness = round(((total_cells - null_cells) / total_cells) * 100.0, 1)

    sample_rows = _sanitize_rows(df.head(limite_muestra).to_dicts())

    return {
        "dataset": slug,
        "recurso_id": resource.get("id", ""),
        "nombre_recurso": resource.get("nombre") or resource.get("id", ""),
        "formato": resource.get("formato") or "",
        "ya_estaba_descargado": ya_estaba_descargado,
        "ya_estaba_procesado": ya_estaba_procesado,
        "ruta_parquet": rel_parquet,
        "hojas": hojas,
        "hoja_actual": hoja_actual,
        "total_filas": int(df.height),
        "total_columnas": int(df.width),
        "completitud_pct": completeness,
        "columnas": df.columns,
        "columnas_numericas": numeric_cols,
        "columnas_categoricas": categorical_cols,
        "agrupado_por": active_group,
        "metrica_activa": active_metric,
        "estadisticas_numericas": numeric_stats,
        "graficas": charts,
        "visualizaciones_curadas": CURATED_DATASET_VISUALIZATIONS.get(slug, []),
        "filas_muestra": sample_rows,
    }


def render_dataset_chart_html(chart: Dict[str, Any], dataset_title: str) -> str:
    """Generar pagina html interactiva con plotly para una grafica especifica del conjunto."""
    import plotly.graph_objects as go

    labels = [pt["etiqueta"] for pt in chart.get("datos", [])]
    values = [pt["valor"] for pt in chart.get("datos", [])]
    chart_type = chart.get("tipo", "bar")

    fig = go.Figure()
    if chart_type == "donut":
        fig.add_trace(go.Pie(labels=labels, values=values, hole=0.48, textinfo="label+percent"))
    elif chart_type == "line":
        fig.add_trace(go.Scatter(
            x=labels, y=values, mode="lines+markers",
            line=dict(color="#0068c8", width=3),
            marker=dict(size=8, color="#004080"),
        ))
    else:
        fig.add_trace(go.Bar(
            x=values[::-1], y=labels[::-1], orientation="h",
            marker=dict(color="#0068c8"),
        ))

    fig.update_layout(
        title=f"<b>{chart.get('titulo', 'Gráfica')}</b><br><span style='font-size:12px;color:#5a7188;'>{dataset_title}</span>",
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f7fbff",
        font=dict(family="Public Sans, Inter, sans-serif", color="#173a5e"),
        margin=dict(l=40, r=30, t=75, b=45),
        height=540,
    )
    return fig.to_html(full_html=True, include_plotlyjs="cdn")
