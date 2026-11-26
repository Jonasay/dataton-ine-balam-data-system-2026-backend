from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode

import numpy as np
import polars as pl

from src.core.config import PROCESSED_DATA_DIR
from src.core.human_labels import (
    HUMAN_READABLE_LABELS,
    INTEGER_METRIC_COLUMNS,
    format_metric_for_summary,
    humanize_label,
)
from src.schemas.ai_search import AISearchRoutingPlan, DatasetId, VisualizationKind

_MUNICIPAL_CODE_RE = re.compile(r"^\d{4}$")
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_UNSAFE_GROUP_COL_RE = re.compile(
    r"(id$|_id$|^cod|correl|nombre_persona|dpi|cui|nit|telefono|direccion)",
    re.IGNORECASE,
)

# Indicadores departamentales validados directamente compatibles con /api/v1/visualizaciones/...
_CHARTABLE_INDICATORS: frozenset[str] = frozenset(
    {
        "indice_vulnerabilidad_ivst",
        "tasa_retorno_migratorio_por_10k",
        "pct_retornados_menores",
        "pct_retornadas_mujeres",
        "retornados_total",
        "retornados_hombres",
        "retornados_mujeres",
        "retornados_menores",
        "tasa_necropsias_por_100k",
        "necropsias_total",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "victimas_viales_total",
        "fallecidos_viales_total",
        "lesionados_viales_total",
        "tasa_matricula_superior_por_10k",
        "pct_mujeres_superior",
        "matriculados_superior_total",
        "razon_dependencia_demografica",
        "indice_masculinidad",
        "tasa_natalidad_por_1000",
        "tasa_mortalidad_por_1000",
        "tasa_crecimiento_natural_por_1000",
        "nacimientos_total",
        "defunciones_total",
        "crecimiento_natural_absoluto",
        "inflacion_regional_interanual",
        "indice_ipc_regional",
        "perdida_poder_adquisitivo_quetzal",
        "brecha_urbano_rural_cba_gtq",
        "brecha_urbano_rural_cba_pct",
        "poblacion_total",
        "pct_poblacion_menor_15",
        "pct_poblacion_15_64",
        "pct_poblacion_65_mas",
    }
)

_ENRICHED_DEMOGRAPHIC_COLS: frozenset[str] = frozenset(
    {
        "hombres",
        "mujeres",
        "pob_menor_15",
        "pob_15_64",
        "pob_65_mas",
        "mujeres_matriculadas_superior",
    }
)

_UNIFIED_DEPT_DATASETS: frozenset[str] = frozenset(
    {
        "indicadores_departamentales",
        "vulnerabilidad_departamental",
        "clusters_departamentales",
        "proyecciones_demograficas",
    }
)

_MUNICIPAL_CHARTABLE_INDICATORS: frozenset[str] = frozenset(
    {
        "poblacion_total",
        "defunciones_total",
        "nacimientos_total",
        "crecimiento_natural_absoluto",
        "tasa_mortalidad_por_1000",
        "tasa_natalidad_por_1000",
        "tasa_crecimiento_natural_por_1000",
        "necropsias_total",
        "tasa_necropsias_por_100k",
        "victimas_viales_total",
        "fallecidos_viales_total",
        "lesionados_viales_total",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "matriculados_superior_total",
        "mujeres_matriculadas_superior",
        "tasa_matricula_superior_por_10k",
        "pct_mujeres_superior",
    }
)

_NON_NUMERIC_META_COLS: frozenset[str] = frozenset(
    {
        "ranking",
        "anio",
        "mes",
        "mes_nombre",
        "depto_codigo",
        "depto_nombre",
        "depto_iso",
        "region_id",
        "region_nombre",
        "mupio_codigo_str",
        "dominio",
        "tipo_canasta",
        "division_gasto",
        "cluster_id",
        "cluster_nombre",
        "nivel_vulnerabilidad",
        "variable",
        "variable_1",
        "variable_2",
        "pearson_r",
        "pearson_pvalue",
        "spearman_rho",
        "fuerza_asociacion",
    }
)

# Alias retrocompatible
PUBLIC_FIELD_LABELS: Dict[str, str] = HUMAN_READABLE_LABELS


def classify_pearson_strength(r_val: float) -> str:
    """Clasificar rigurosamente la magnitud de asociacion lineal de Pearson."""
    abs_r = abs(r_val)
    if abs_r < 0.15:
        return "nula"
    if abs_r < 0.35:
        return "débil"
    if abs_r < 0.60:
        return "moderada"
    return "fuerte"


@dataclass(frozen=True)
class DatasetSpec:
    """Metadatos internos de cada tabla estadistica agregada permitida."""

    relative_path: Tuple[str, ...]
    dimension_columns: Tuple[str, ...]
    default_metrics: Tuple[str, ...]
    default_sort: Optional[str] = None


@dataclass(frozen=True)
class DynamicDatasetInfo:
    """Metadatos verificados de conjuntos INE procesados localmente desde Explorar datos."""

    slug: str
    stem: str
    parquet_path: Path
    groupable_columns: Tuple[str, ...]


DATASET_REGISTRY: Dict[DatasetId, DatasetSpec] = {
    "indicadores_departamentales": DatasetSpec(
        relative_path=("indicadores", "indicadores_consolidados_departamentales_2024.parquet"),
        dimension_columns=("depto_nombre", "region_nombre"),
        default_metrics=(
            "poblacion_total",
            "tasa_retorno_migratorio_por_10k",
            "tasa_matricula_superior_por_10k",
            "tasa_necropsias_por_100k",
            "tasa_victimas_viales_por_100k",
        ),
        default_sort="poblacion_total",
    ),
    "indicadores_municipales": DatasetSpec(
        relative_path=("indicadores", "indicadores_consolidados_municipales_2024.parquet"),
        dimension_columns=("depto_nombre", "mupio_codigo_str"),
        default_metrics=(
            "poblacion_total",
            "tasa_necropsias_por_100k",
            "tasa_victimas_viales_por_100k",
            "tasa_matricula_superior_por_10k",
        ),
        default_sort="poblacion_total",
    ),
    "vulnerabilidad_departamental": DatasetSpec(
        relative_path=("analisis", "vulnerabilidad_departamental.parquet"),
        dimension_columns=("ranking", "depto_nombre", "region_nombre"),
        default_metrics=(
            "indice_vulnerabilidad_ivst",
            "nivel_vulnerabilidad",
            "cluster_nombre",
            "tasa_retorno_migratorio_por_10k",
            "razon_dependencia_demografica",
        ),
        default_sort="indice_vulnerabilidad_ivst",
    ),
    "clusters_departamentales": DatasetSpec(
        relative_path=("analisis", "clusters_departamentales.parquet"),
        dimension_columns=("depto_nombre", "region_nombre", "cluster_nombre"),
        default_metrics=(
            "tasa_retorno_migratorio_por_10k",
            "razon_dependencia_demografica",
            "tasa_matricula_superior_por_10k",
            "tasa_victimas_viales_por_100k",
        ),
        default_sort="tasa_retorno_migratorio_por_10k",
    ),
    "trayectoria_demografica": DatasetSpec(
        relative_path=("analisis", "trayectoria_demografica_anual.parquet"),
        dimension_columns=("anio", "depto_nombre", "region_nombre"),
        default_metrics=(
            "poblacion_total",
            "razon_dependencia_demografica",
            "indice_masculinidad",
        ),
        default_sort="anio",
    ),
    "proyecciones_demograficas": DatasetSpec(
        relative_path=("analisis", "proyecciones_demograficas.parquet"),
        dimension_columns=("depto_nombre", "region_nombre"),
        default_metrics=(
            "poblacion_2024",
            "poblacion_2030",
            "crecimiento_absoluto_2024_2030",
            "crecimiento_porcentual_total",
            "tasa_anual_crecimiento_geometrico_pct",
        ),
        default_sort="tasa_anual_crecimiento_geometrico_pct",
    ),
    "canasta_basica_mensual": DatasetSpec(
        relative_path=("economia", "canasta_basica_mensual.parquet"),
        dimension_columns=("anio", "mes", "mes_nombre", "dominio", "tipo_canasta"),
        default_metrics=(
            "costo_mensual_percapita",
            "costo_diario_percapita",
            "variacion_intermensual_pct",
            "variacion_interanual_pct",
        ),
        default_sort="anio",
    ),
    "proyecciones_costo_vida": DatasetSpec(
        relative_path=("analisis", "proyecciones_costo_vida.parquet"),
        dimension_columns=("dominio",),
        default_metrics=(
            "costo_actual_percapita",
            "proyeccion_3_meses_gtq",
            "proyeccion_6_meses_gtq",
            "proyeccion_12_meses_gtq",
            "proyeccion_tasa_anual_pct",
        ),
        default_sort="costo_actual_percapita",
    ),
    "ipc_regiones": DatasetSpec(
        relative_path=("economia", "ipc_regiones.parquet"),
        dimension_columns=("anio", "mes", "region_nombre"),
        default_metrics=("indice_ipc", "variacion_interanual_pct"),
        default_sort="anio",
    ),
    "ipc_divisiones_gasto": DatasetSpec(
        relative_path=("economia", "ipc_divisiones_gasto.parquet"),
        dimension_columns=("anio", "mes", "division_gasto"),
        default_metrics=("indice_ipc", "variacion_interanual_pct"),
        default_sort="variacion_interanual_pct",
    ),
    "ipc_poder_adquisitivo": DatasetSpec(
        relative_path=("economia", "ipc_poder_adquisitivo.parquet"),
        dimension_columns=("anio", "mes"),
        default_metrics=("indice_ipc_nacional", "poder_adquisitivo_quetzal", "perdida_poder_adquisitivo"),
        default_sort="anio",
    ),
    "estadisticas_descriptivas": DatasetSpec(
        relative_path=("analisis", "estadisticas_descriptivas.parquet"),
        dimension_columns=("variable",),
        default_metrics=("media", "mediana", "minimo", "maximo", "desviacion_estandar"),
        default_sort="media",
    ),
    "matriz_correlaciones": DatasetSpec(
        relative_path=("analisis", "matriz_correlaciones.parquet"),
        dimension_columns=("variable_1", "variable_2", "fuerza_asociacion"),
        default_metrics=("pearson_r", "pearson_pvalue", "spearman_rho"),
        default_sort="pearson_r",
    ),
}


class DatasetUnavailableError(RuntimeError):
    """Error interno cuando una fuente estadistica procesada no se encuentra disponible."""


class StatisticsRepository:
    """Repositorio de acceso exclusivamente en modo solo lectura sobre tablas estadisticas agregadas."""

    def __init__(self, base_dir: Path = PROCESSED_DATA_DIR, max_rows: int = 25) -> None:
        self._base_dir = Path(base_dir)
        self._max_rows = max_rows

    def _build_unified_departmental_lazy_frame(self) -> Tuple[pl.LazyFrame, set[str]]:
        """Unificar en memoria solo-lectura todos los indicadores departamentales (22 filas) para cruces limpios."""
        ind_path = self._base_dir / "indicadores" / "indicadores_consolidados_departamentales_2024.parquet"
        if not ind_path.exists() or not ind_path.is_file():
            raise DatasetUnavailableError("Archivo departamental consolidado no encontrado.")

        lf = pl.scan_parquet(str(ind_path))
        cols = set(lf.collect_schema().names())

        vuln_path = self._base_dir / "analisis" / "vulnerabilidad_departamental.parquet"
        if vuln_path.exists() and vuln_path.is_file():
            v_lf = pl.scan_parquet(str(vuln_path)).select(
                ["depto_codigo", "ranking", "indice_vulnerabilidad_ivst", "nivel_vulnerabilidad", "cluster_nombre"]
            )
            lf = lf.join(v_lf, on="depto_codigo", how="left")
            cols.update({"ranking", "indice_vulnerabilidad_ivst", "nivel_vulnerabilidad", "cluster_nombre"})

        clust_path = self._base_dir / "analisis" / "clusters_departamentales.parquet"
        if clust_path.exists() and clust_path.is_file():
            c_lf = pl.scan_parquet(str(clust_path)).select(["depto_codigo", "cluster_id"])
            lf = lf.join(c_lf, on="depto_codigo", how="left")
            cols.add("cluster_id")

        proy_path = self._base_dir / "analisis" / "proyecciones_demograficas.parquet"
        if proy_path.exists() and proy_path.is_file():
            p_cols = [
                "poblacion_2024",
                "poblacion_2030",
                "crecimiento_absoluto_2024_2030",
                "crecimiento_porcentual_total",
                "tasa_anual_crecimiento_geometrico_pct",
            ]
            p_lf = pl.scan_parquet(str(proy_path)).select(["depto_codigo", *p_cols])
            lf = lf.join(p_lf, on="depto_codigo", how="left")
            cols.update(p_cols)

        traj_path = self._base_dir / "analisis" / "trayectoria_demografica_anual.parquet"
        if traj_path.exists() and traj_path.is_file():
            t_cols = ["hombres", "mujeres", "pob_menor_15", "pob_15_64", "pob_65_mas"]
            t_lf = (
                pl.scan_parquet(str(traj_path))
                .filter(pl.col("anio") == 2024)
                .select(["depto_codigo", *t_cols])
            )
            lf = lf.join(t_lf, on="depto_codigo", how="left")
            cols.update(t_cols)

        muni_path = self._base_dir / "indicadores" / "indicadores_consolidados_municipales_2024.parquet"
        if muni_path.exists() and muni_path.is_file():
            m_schema = set(pl.scan_parquet(str(muni_path)).collect_schema().names())
            if "mujeres_matriculadas_superior" in m_schema:
                m_lf = (
                    pl.scan_parquet(str(muni_path))
                    .group_by("depto_codigo")
                    .agg(pl.col("mujeres_matriculadas_superior").sum().alias("mujeres_matriculadas_superior"))
                )
                lf = lf.join(m_lf, on="depto_codigo", how="left")
                cols.add("mujeres_matriculadas_superior")

        return lf, cols

    def list_dynamic_datasets(self) -> List[DynamicDatasetInfo]:
        """Descubrir de forma segura conjuntos INE ya convertidos a Parquet en data/processed/datasets/."""
        datasets_root = self._base_dir / "datasets"
        if not datasets_root.exists() or not datasets_root.is_dir():
            return []

        discovered: List[DynamicDatasetInfo] = []
        for slug_dir in sorted(datasets_root.iterdir()):
            if not slug_dir.is_dir() or not _SAFE_SEGMENT_RE.match(slug_dir.name):
                continue
            for pq_file in sorted(slug_dir.glob("*.parquet")):
                if not pq_file.is_file() or not _SAFE_SEGMENT_RE.match(pq_file.stem):
                    continue
                try:
                    schema = pl.scan_parquet(str(pq_file)).collect_schema()
                except Exception:
                    continue
                group_cols = tuple(
                    col_name
                    for col_name in schema.names()
                    if not _UNSAFE_GROUP_COL_RE.search(col_name)
                )
                if group_cols:
                    discovered.append(
                        DynamicDatasetInfo(
                            slug=slug_dir.name,
                            stem=pq_file.stem,
                            parquet_path=pq_file,
                            groupable_columns=group_cols[:20],
                        )
                    )
        return discovered

    def execute_dynamic_plan(self, plan: AISearchRoutingPlan) -> Tuple[List[Dict[str, Any]], Optional[str], int]:
        """Agregar en modo solo lectura un conjunto dinamico garantizando anonimizacion por conteos."""
        if not plan.conjunto_dinamico_slug:
            raise DatasetUnavailableError("Conjunto dinamico no especificado.")

        catalog = self.list_dynamic_datasets()
        candidates = [d for d in catalog if d.slug == plan.conjunto_dinamico_slug]
        if not candidates:
            raise DatasetUnavailableError("Conjunto dinamico no encontrado en catalogo procesado.")

        matched = candidates[0]
        if plan.conjunto_dinamico_archivo:
            exact = next((d for d in candidates if d.stem == plan.conjunto_dinamico_archivo), None)
            if exact is not None:
                matched = exact
            else:
                partial = next((d for d in candidates if plan.conjunto_dinamico_archivo in d.stem), None)
                if partial is not None:
                    matched = partial

        lazy_frame = pl.scan_parquet(str(matched.parquet_path))
        total_records = int(lazy_frame.select(pl.len()).collect().item())
        if total_records == 0:
            return [], None, 0

        group_col = self._pick_dynamic_group_column(matched.groupable_columns, plan.agrupar_por_dinamico)
        safe_limit = max(1, min(plan.limite, self._max_rows))
        descending = plan.direccion_orden == "desc"

        agg_df = (
            lazy_frame.filter(
                pl.col(group_col).is_not_null()
                & (pl.col(group_col).cast(pl.Utf8).str.strip_chars() != "")
            )
            .group_by(group_col)
            .agg(pl.len().alias("cantidad_registros"))
            .sort("cantidad_registros", descending=descending)
            .with_row_index(name="posicion", offset=1)
            .limit(safe_limit)
            .collect()
        )

        dim_label = humanize_label(group_col)
        rows: List[Dict[str, Any]] = []
        for raw in agg_df.to_dicts():
            cnt = int(raw["cantidad_registros"])
            rows.append(
                {
                    humanize_label("posicion"): int(raw["posicion"]),
                    dim_label: str(raw[group_col]),
                    humanize_label("cantidad_registros"): cnt,
                    humanize_label("porcentaje_pct"): round((cnt / total_records) * 100.0, 2),
                }
            )

        viz_query = urlencode(
            {
                "slug": matched.slug,
                "archivo": matched.stem,
                "agrupar_por": group_col,
            }
        )
        viz_url = f"/api/v1/busqueda-ia/visualizacion-dinamica?{viz_query}"
        return rows, viz_url, total_records

    def execute_bivariate_analysis(self, plan: AISearchRoutingPlan) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
        """Calcular con Polars correlacion de Pearson exclusivamente entre los indicadores pedidos y devolver los 22 departamentos."""
        lf, available_cols = self._build_unified_departmental_lazy_frame()
        df = lf.collect()

        numeric_candidates = [
            col
            for col in plan.columnas_metricas
            if col in available_cols and col not in _NON_NUMERIC_META_COLS and df.schema[col].is_numeric()
        ]
        if len(numeric_candidates) < 2:
            # Respaldo seguro si solo se envio 1 indicador junto a intencion de relacion
            fallback_pool = ["tasa_retorno_migratorio_por_10k", "pct_mujeres_superior", "tasa_natalidad_por_1000"]
            for fb in fallback_pool:
                if fb in available_cols and fb not in numeric_candidates:
                    numeric_candidates.append(fb)
                if len(numeric_candidates) >= 2:
                    break

        selected_metrics = numeric_candidates[:4]
        col_x = selected_metrics[0]
        other_metrics = selected_metrics[1:]

        # Ordenar los 22 departamentos por el primer indicador solicitado
        base_for_sort = df.drop("ranking") if "ranking" in df.columns else df
        sorted_df = base_for_sort.sort(
            col_x, descending=(plan.direccion_orden != "asc"), nulls_last=True
        ).with_row_index(name="ranking", offset=1)
        table_cols = ["ranking", "depto_nombre", "region_nombre", *selected_metrics]
        public_rows = self._to_public_records(sorted_df.select(table_cols).to_dicts())

        # Resumen de lideres por cada indicador solicitado
        leader_parts: List[str] = []
        for m_col in selected_metrics:
            top_row = df.sort(m_col, descending=True, nulls_last=True).row(0, named=True)
            val_fmt = format_metric_for_summary(m_col, top_row[m_col])
            leader_parts.append(f"{humanize_label(m_col)}: lidera {top_row['depto_nombre']} ({val_fmt})")

        # Calculo exacto de Pearson en Polars unicamente para los pares pedidos
        corr_parts: List[str] = []
        for col_y in other_metrics:
            r_raw = df.select(pl.corr(col_x, col_y)).item()
            r_val = float(r_raw) if r_raw is not None and math.isfinite(float(r_raw)) else 0.0
            strength = classify_pearson_strength(r_val)
            if abs(r_val) < 0.15:
                sense = ""
            elif r_val > 0:
                sense = " positiva"
            else:
                sense = " inversa"
            corr_parts.append(
                f"entre {humanize_label(col_x)} y {humanize_label(col_y)} la asociación es {strength}{sense} (r = {r_val:.2f})"
            )

        summary_msg = (
            f"Análisis de relación departamental: {'; '.join(corr_parts)}. "
            f"Líderes nacionales — {'; '.join(leader_parts)}. "
            "Nota metodológica: la asociación estadística observada no implica necesariamente causalidad."
        )

        viz_query = urlencode({"x": col_x, "y": other_metrics[0]})
        viz_url = f"/api/v1/busqueda-ia/visualizacion-dispersion?{viz_query}"
        return public_rows, viz_url, summary_msg

    def build_multi_query_summary(self, metrics: Sequence[str], direccion_orden: str = "desc") -> str:
        """Responder directamente cada sub-pregunta independiente citando region o departamento lider."""
        lf, available_cols = self._build_unified_departmental_lazy_frame()
        df = lf.collect()
        valid_metrics = [
            m for m in metrics if m in available_cols and m not in _NON_NUMERIC_META_COLS and df.schema[m].is_numeric()
        ]
        if not valid_metrics:
            return ""

        descending = direccion_orden != "asc"
        qual = "mayor" if descending else "menor"
        findings: List[str] = []
        for m_col in valid_metrics[:4]:
            top_row = df.sort(m_col, descending=descending, nulls_last=True).row(0, named=True)
            val_fmt = format_metric_for_summary(m_col, top_row[m_col])
            if m_col in {"inflacion_regional_interanual", "indice_ipc_regional"}:
                findings.append(
                    f"En {humanize_label(m_col)}, el {qual} registro corresponde a la región {top_row['region_nombre']} ({val_fmt})"
                )
            else:
                findings.append(
                    f"En {humanize_label(m_col)}, el {qual} registro corresponde al departamento de {top_row['depto_nombre']} ({val_fmt})"
                )

        return ". ".join(findings) + "."

    def build_bivariate_scatter_html(self, x_col: str, y_col: str) -> str:
        """Generar grafica de dispersion (scatter plot) interactiva con los 22 departamentos etiquetados."""
        import plotly.graph_objects as go

        lf, available_cols = self._build_unified_departmental_lazy_frame()
        if x_col not in available_cols or y_col not in available_cols:
            raise DatasetUnavailableError("Indicadores no disponibles para grafica de dispersion.")

        df = lf.collect()
        if not df.schema[x_col].is_numeric() or not df.schema[y_col].is_numeric():
            raise DatasetUnavailableError("Las columnas para dispersion deben ser numericas.")

        r_raw = df.select(pl.corr(x_col, y_col)).item()
        r_val = float(r_raw) if r_raw is not None and math.isfinite(float(r_raw)) else 0.0
        strength = classify_pearson_strength(r_val)

        x_label = humanize_label(x_col)
        y_label = humanize_label(y_col)

        vuln_palette = {
            "Crítica": "#ef4444",
            "Alta": "#f97316",
            "Moderada": "#eab308",
            "Baja": "#10b981",
        }

        fig = go.Figure()
        records = df.to_dicts()
        for vuln_level in ("Crítica", "Alta", "Moderada", "Baja"):
            group_rows = [r for r in records if r.get("nivel_vulnerabilidad") == vuln_level]
            if not group_rows:
                continue
            fig.add_trace(
                go.Scatter(
                    x=[r[x_col] for r in group_rows],
                    y=[r[y_col] for r in group_rows],
                    mode="markers+text",
                    name=vuln_level,
                    text=[r["depto_nombre"] for r in group_rows],
                    textposition="top center",
                    cliponaxis=False,
                    marker=dict(
                        size=12,
                        color=vuln_palette.get(vuln_level, "#0068c8"),
                        line=dict(width=1, color="#ffffff"),
                    ),
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        f"{x_label}: %{{x:,.2f}}<br>"
                        f"{y_label}: %{{y:,.2f}}<extra>{vuln_level}</extra>"
                    ),
                )
            )

        # Linea de tendencia lineal MCO (referencia visual sin implicar causalidad)
        xs = np.array([float(r[x_col]) for r in records if r[x_col] is not None and r[y_col] is not None], dtype=float)
        ys = np.array([float(r[y_col]) for r in records if r[x_col] is not None and r[y_col] is not None], dtype=float)
        if len(xs) >= 3 and float(np.std(xs)) > 1e-9:
            slope, intercept = np.polyfit(xs, ys, 1)
            x_line = np.linspace(float(xs.min()), float(xs.max()), 50)
            y_line = slope * x_line + intercept
            fig.add_trace(
                go.Scatter(
                    x=x_line.tolist(),
                    y=y_line.tolist(),
                    mode="lines",
                    name="Tendencia lineal",
                    line=dict(color="#64748b", width=2, dash="dash"),
                    hoverinfo="skip",
                )
            )

        x_pad = (float(xs.max()) - float(xs.min())) * 0.12 if len(xs) > 1 else 1.0
        y_pad = (float(ys.max()) - float(ys.min())) * 0.15 if len(ys) > 1 else 1.0

        fig.update_layout(
            title=(
                f"<b>Dispersión Departamental: {x_label} vs. {y_label}</b>"
                f"<br><span style='font-size:12px;color:#5a7188;'>"
                f"22 departamentos · Correlación de Pearson r = {r_val:.2f} (asociación {strength}; no implica causalidad)"
                f"</span>"
            ),
            xaxis=dict(title=x_label, range=[float(xs.min()) - x_pad, float(xs.max()) + x_pad]),
            yaxis=dict(title=y_label, range=[float(ys.min()) - y_pad * 0.6, float(ys.max()) + y_pad]),
            legend_title_text="Nivel de vulnerabilidad",
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f7fbff",
            font=dict(family="Public Sans, Inter, sans-serif", color="#173a5e"),
            margin=dict(l=65, r=60, t=90, b=60),
            height=620,
        )
        return fig.to_html(full_html=True, include_plotlyjs="cdn")

    def build_dynamic_chart_html(
        self,
        slug: str,
        archivo: str,
        agrupar_por: Optional[str] = None,
    ) -> str:
        """Construir grafica interactiva HTML en modo 100% local a partir de un conjunto dinamico."""
        from src.analysis.dataset_explorer import render_dataset_chart_html

        catalog = self.list_dynamic_datasets()
        matched = next((d for d in catalog if d.slug == slug and d.stem == archivo), None)
        if matched is None:
            matched = next((d for d in catalog if d.slug == slug), None)
        if matched is None:
            raise DatasetUnavailableError("Conjunto dinamico no disponible para graficar.")

        group_col = self._pick_dynamic_group_column(matched.groupable_columns, agrupar_por)
        lazy_frame = pl.scan_parquet(str(matched.parquet_path))
        total_records = int(lazy_frame.select(pl.len()).collect().item()) or 1

        agg_df = (
            lazy_frame.filter(
                pl.col(group_col).is_not_null()
                & (pl.col(group_col).cast(pl.Utf8).str.strip_chars() != "")
            )
            .group_by(group_col)
            .agg(pl.len().alias("valor"))
            .sort("valor", descending=True)
            .limit(12)
            .collect()
        )

        clean_group_title = humanize_label(group_col)
        points = [
            {
                "etiqueta": str(r[group_col]),
                "valor": float(r["valor"]),
                "porcentaje": round((float(r["valor"]) / total_records) * 100.0, 1),
            }
            for r in agg_df.to_dicts()
        ]
        chart_spec = {
            "id": "distribucion_ia",
            "titulo": f"Registros agregados por {clean_group_title} (Total: {total_records:,})",
            "subtitulo": matched.slug.replace("-", " ").title(),
            "tipo": "bar",
            "eje_x": clean_group_title,
            "eje_y": "Registros",
            "datos": points,
        }
        return render_dataset_chart_html(chart_spec, matched.slug.replace("-", " ").upper())

    @staticmethod
    def _pick_dynamic_group_column(
        groupable_columns: Tuple[str, ...],
        requested: Optional[str],
    ) -> str:
        if requested:
            exact = next((c for c in groupable_columns if c.lower() == requested.strip().lower()), None)
            if exact is not None:
                return exact
        preferred_keywords = ("depto", "departamento", "facultad", "carrera", "nivel", "sector", "sexo", "area", "área")
        for kw in preferred_keywords:
            candidate = next((c for c in groupable_columns if kw in c.lower()), None)
            if candidate is not None:
                return candidate
        return groupable_columns[0]

    def execute_plan(self, plan: AISearchRoutingPlan) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if plan.conjunto_datos is None or plan.conjunto_datos not in DATASET_REGISTRY:
            raise DatasetUnavailableError("Conjunto de datos no especificado en el plan.")

        spec = DATASET_REGISTRY[plan.conjunto_datos]
        if plan.conjunto_datos in _UNIFIED_DEPT_DATASETS:
            lazy_frame, available_columns = self._build_unified_departmental_lazy_frame()
        else:
            parquet_path = self._base_dir.joinpath(*spec.relative_path)
            if not parquet_path.exists() or not parquet_path.is_file():
                raise DatasetUnavailableError("Archivo fuente no encontrado en disco.")
            lazy_frame = pl.scan_parquet(str(parquet_path))
            available_columns = set(lazy_frame.collect_schema().names())

        is_muni_by_depto_only = (
            "mupio_codigo_str" in available_columns
            and bool(plan.codigos_departamento)
            and not plan.codigo_municipio
        )

        lazy_frame = self._apply_context_filters(
            lazy_frame,
            available_columns,
            plan,
            filter_depto_early=is_muni_by_depto_only,
        )
        lazy_frame, sort_col = self._apply_sorting(lazy_frame, available_columns, plan, spec)

        # Calcular posicion oficial antes de filtrar un departamento o municipio puntual
        if "depto_codigo" in available_columns and "anio" not in available_columns:
            if "ranking" in available_columns:
                lazy_frame = lazy_frame.drop("ranking")
            lazy_frame = lazy_frame.with_row_index(name="ranking", offset=1)
            available_columns.add("ranking")

        lazy_frame = self._apply_entity_filters(
            lazy_frame,
            available_columns,
            plan,
            skip_depto=is_muni_by_depto_only,
        )

        selected_cols = self._select_columns(available_columns, plan.columnas_metricas, spec, sort_col=sort_col)
        effective_limit = max(10, plan.limite) if plan.subtipo_consulta == "multi_consulta" else plan.limite
        safe_limit = max(1, min(effective_limit, self._max_rows))

        df_result = lazy_frame.select([pl.col(c) for c in selected_cols]).limit(safe_limit).collect()
        public_rows = self._to_public_records(df_result.to_dicts())
        vis_url = self._build_visualization_url(plan) if public_rows else None
        return public_rows, vis_url

    @staticmethod
    def _apply_context_filters(
        lazy_frame: pl.LazyFrame,
        available_columns: set[str],
        plan: AISearchRoutingPlan,
        *,
        filter_depto_early: bool = False,
    ) -> pl.LazyFrame:
        if filter_depto_early:
            valid_deptos = [d for d in plan.codigos_departamento if 1 <= d <= 22]
            if valid_deptos and "depto_codigo" in available_columns:
                lazy_frame = lazy_frame.filter(pl.col("depto_codigo").is_in(valid_deptos))

        if "anio" in available_columns:
            if plan.anio_inicio is not None and 2015 <= plan.anio_inicio <= 2030:
                lazy_frame = lazy_frame.filter(pl.col("anio") >= plan.anio_inicio)
            if plan.anio_fin is not None and 2015 <= plan.anio_fin <= 2030:
                lazy_frame = lazy_frame.filter(pl.col("anio") <= plan.anio_fin)

        if plan.mes is not None and 1 <= plan.mes <= 12 and "mes" in available_columns:
            lazy_frame = lazy_frame.filter(pl.col("mes") == plan.mes)

        if plan.dominio_area is not None and "dominio" in available_columns:
            lazy_frame = lazy_frame.filter(pl.col("dominio") == plan.dominio_area)

        if plan.tipo_canasta is not None and "tipo_canasta" in available_columns:
            lazy_frame = lazy_frame.filter(pl.col("tipo_canasta") == plan.tipo_canasta)

        return lazy_frame

    @staticmethod
    def _apply_entity_filters(
        lazy_frame: pl.LazyFrame,
        available_columns: set[str],
        plan: AISearchRoutingPlan,
        *,
        skip_depto: bool = False,
    ) -> pl.LazyFrame:
        if not skip_depto:
            valid_deptos = [d for d in plan.codigos_departamento if 1 <= d <= 22]
            if valid_deptos and "depto_codigo" in available_columns:
                lazy_frame = lazy_frame.filter(pl.col("depto_codigo").is_in(valid_deptos))

        if (
            plan.codigo_municipio
            and _MUNICIPAL_CODE_RE.match(plan.codigo_municipio.strip())
            and "mupio_codigo_str" in available_columns
        ):
            lazy_frame = lazy_frame.filter(pl.col("mupio_codigo_str") == plan.codigo_municipio.strip())

        if plan.region_id is not None and 0 <= plan.region_id <= 8 and "region_id" in available_columns:
            lazy_frame = lazy_frame.filter(pl.col("region_id") == plan.region_id)

        if plan.nivel_vulnerabilidad is not None and "nivel_vulnerabilidad" in available_columns:
            lazy_frame = lazy_frame.filter(pl.col("nivel_vulnerabilidad") == plan.nivel_vulnerabilidad)

        if "variable_1" in available_columns and "variable_2" in available_columns and plan.columnas_metricas:
            corr_targets = [
                c
                for c in plan.columnas_metricas
                if c not in {"pearson_r", "pearson_pvalue", "spearman_rho", "fuerza_asociacion", "variable_1", "variable_2"}
            ]
            if corr_targets:
                matched_corr = lazy_frame.filter(
                    pl.col("variable_1").is_in(corr_targets) | pl.col("variable_2").is_in(corr_targets)
                )
                if int(matched_corr.select(pl.len()).collect().item()) > 0:
                    lazy_frame = matched_corr

        return lazy_frame

    @staticmethod
    def _apply_sorting(
        lazy_frame: pl.LazyFrame,
        available_columns: set[str],
        plan: AISearchRoutingPlan,
        spec: DatasetSpec,
    ) -> Tuple[pl.LazyFrame, Optional[str]]:
        descending = plan.direccion_orden == "desc"
        sort_col: Optional[str] = None
        if plan.ordenar_por and plan.ordenar_por != "ranking" and plan.ordenar_por in available_columns:
            sort_col = plan.ordenar_por
        elif plan.columnas_metricas:
            for candidate in plan.columnas_metricas:
                if candidate != "ranking" and candidate not in {"nivel_vulnerabilidad", "cluster_nombre"} and candidate in available_columns:
                    sort_col = candidate
                    break
        if sort_col is None and spec.default_sort and spec.default_sort in available_columns:
            sort_col = spec.default_sort

        if sort_col is not None:
            lazy_frame = lazy_frame.sort(sort_col, descending=descending, nulls_last=True)
        return lazy_frame, sort_col

    @staticmethod
    def _select_columns(
        available_columns: set[str],
        requested_metrics: Sequence[str],
        spec: DatasetSpec,
        *,
        sort_col: Optional[str] = None,
    ) -> List[str]:
        ordered: List[str] = []
        if "ranking" in available_columns and "anio" not in available_columns:
            ordered.append("ranking")

        for dim in spec.dimension_columns:
            if dim in available_columns and dim not in ordered:
                ordered.append(dim)

        valid_requested = [m for m in requested_metrics if m in available_columns and m not in ordered]
        if valid_requested:
            ordered.extend(valid_requested)
            if sort_col and sort_col in available_columns and sort_col not in ordered and len(valid_requested) == 0:
                ordered.append(sort_col)
        elif sort_col and sort_col in available_columns and sort_col not in ordered:
            ordered.append(sort_col)
        else:
            for default_col in spec.default_metrics:
                if default_col in available_columns and default_col not in ordered:
                    ordered.append(default_col)

        return ordered

    @staticmethod
    def _to_public_records(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convertir registros internos a etiquetas legibles en espanol (cero snake_case y enteros exactos)."""
        sanitized: List[Dict[str, Any]] = []
        for row in raw_rows:
            clean_row: Dict[str, Any] = {}
            for key, val in row.items():
                public_key = humanize_label(key)
                if key in {"variable", "variable_1", "variable_2"} and isinstance(val, str):
                    clean_row[public_key] = humanize_label(val)
                elif val is None:
                    clean_row[public_key] = None
                elif key in INTEGER_METRIC_COLUMNS and isinstance(val, (int, float)):
                    clean_row[public_key] = int(round(float(val)))
                elif isinstance(val, float):
                    clean_row[public_key] = round(val, 4) if math.isfinite(val) else None
                else:
                    clean_row[public_key] = val
            sanitized.append(clean_row)
        return sanitized

    @staticmethod
    def _build_visualization_url(plan: AISearchRoutingPlan) -> Optional[str]:
        dataset_default_routes: Dict[DatasetId, str] = {
            "proyecciones_demograficas": "/api/v1/visualizaciones/tendencias/crecimiento-demografico",
            "trayectoria_demografica": "/api/v1/visualizaciones/3d/trayectoria-demografica",
            "canasta_basica_mensual": "/api/v1/visualizaciones/tendencias/costo-vida",
            "proyecciones_costo_vida": "/api/v1/visualizaciones/tendencias/costo-vida",
            "ipc_regiones": "/api/v1/visualizaciones/tendencias/ipc?vista=regiones",
            "ipc_divisiones_gasto": "/api/v1/visualizaciones/tendencias/ipc?vista=divisiones",
            "ipc_poder_adquisitivo": "/api/v1/visualizaciones/tendencias/ipc?vista=poder_adquisitivo",
            "clusters_departamentales": "/api/v1/visualizaciones/3d/clusters-pca",
            "matriz_correlaciones": "/api/v1/visualizaciones/correlaciones/heatmap",
            "estadisticas_descriptivas": "/api/v1/visualizaciones/outliers/boxplot",
        }
        if plan.conjunto_datos in dataset_default_routes:
            return dataset_default_routes[plan.conjunto_datos]

        kind: VisualizationKind = plan.visualizacion_sugerida
        if kind == "dispersion_bivariada" and len(plan.columnas_metricas) >= 2:
            q_sc = urlencode({"x": plan.columnas_metricas[0], "y": plan.columnas_metricas[1]})
            return f"/api/v1/busqueda-ia/visualizacion-dispersion?{q_sc}"

        if kind == "ninguna":
            if plan.conjunto_datos == "indicadores_municipales":
                kind = "ranking_municipal"
            elif plan.conjunto_datos in _UNIFIED_DEPT_DATASETS:
                kind = "ranking_departamental"
            else:
                return None

        if plan.conjunto_datos in _UNIFIED_DEPT_DATASETS:
            if "mujeres" in plan.columnas_metricas and "hombres" in plan.columnas_metricas:
                return "/api/v1/busqueda-ia/visualizacion-demografica?modo=sexo"
            demo_col = (
                plan.ordenar_por
                if plan.ordenar_por in _ENRICHED_DEMOGRAPHIC_COLS
                else next((m for m in plan.columnas_metricas if m in _ENRICHED_DEMOGRAPHIC_COLS), None)
            )
            if demo_col is not None and demo_col not in _CHARTABLE_INDICATORS:
                top_n_demo = 22 if plan.codigos_departamento else max(5, min(plan.limite, 22))
                q_demo = urlencode(
                    {
                        "modo": "ranking",
                        "columna": demo_col,
                        "orden": plan.direccion_orden,
                        "top_n": top_n_demo,
                    }
                )
                return f"/api/v1/busqueda-ia/visualizacion-demografica?{q_demo}"

        primary_metric: Optional[str] = (
            plan.ordenar_por if plan.ordenar_por in _CHARTABLE_INDICATORS else None
        )
        if primary_metric is None:
            primary_metric = next(
                (m for m in plan.columnas_metricas if m in _CHARTABLE_INDICATORS),
                None,
            )

        if kind == "ranking_departamental":
            ind = primary_metric or (
                "indice_vulnerabilidad_ivst"
                if plan.conjunto_datos == "vulnerabilidad_departamental"
                else "poblacion_total"
            )
            top_n = 22 if plan.codigos_departamento else max(5, min(plan.limite, 22))
            query = urlencode({"indicador": ind, "top_n": top_n, "orden": plan.direccion_orden})
            return f"/api/v1/visualizaciones/barras/ranking-departamental?{query}"

        if kind == "ranking_municipal":
            muni_ind = next(
                (m for m in plan.columnas_metricas if m in _MUNICIPAL_CHARTABLE_INDICATORS),
                None,
            )
            if muni_ind is None and plan.ordenar_por in _MUNICIPAL_CHARTABLE_INDICATORS:
                muni_ind = plan.ordenar_por
            muni_ind = muni_ind or "tasa_necropsias_por_100k"
            params: Dict[str, Any] = {"indicador": muni_ind, "top_n": max(5, min(plan.limite, 50))}
            if len(plan.codigos_departamento) == 1 and 1 <= plan.codigos_departamento[0] <= 22:
                params["depto_codigo"] = plan.codigos_departamento[0]
            return f"/api/v1/visualizaciones/barras/ranking-municipal?{urlencode(params)}"

        if kind == "mapa_3d_relieve":
            ind = primary_metric or "tasa_retorno_migratorio_por_10k"
            return f"/api/v1/visualizaciones/mapa/3d-relieve?{urlencode({'indicador': ind})}"

        if kind == "mapa_2d_plotly":
            ind = primary_metric or "indice_vulnerabilidad_ivst"
            return f"/api/v1/visualizaciones/mapa/2d-plotly?{urlencode({'indicador': ind})}"

        if kind == "mapa_2d_folium":
            ind = primary_metric or "tasa_retorno_migratorio_por_10k"
            return f"/api/v1/visualizaciones/mapa/2d-folium?{urlencode({'indicador': ind})}"

        static_routes: Dict[VisualizationKind, str] = {
            "tendencia_costo_vida": "/api/v1/visualizaciones/tendencias/costo-vida",
            "tendencia_ipc_regiones": "/api/v1/visualizaciones/tendencias/ipc?vista=regiones",
            "tendencia_ipc_divisiones": "/api/v1/visualizaciones/tendencias/ipc?vista=divisiones",
            "tendencia_poder_adquisitivo": "/api/v1/visualizaciones/tendencias/ipc?vista=poder_adquisitivo",
            "crecimiento_demografico": "/api/v1/visualizaciones/tendencias/crecimiento-demografico",
            "clusters_pca_3d": "/api/v1/visualizaciones/3d/clusters-pca",
            "trayectoria_demografica_3d": "/api/v1/visualizaciones/3d/trayectoria-demografica",
            "trayectoria_costo_vida_3d": "/api/v1/visualizaciones/3d/trayectoria-costo-vida",
            "heatmap_correlaciones": "/api/v1/visualizaciones/correlaciones/heatmap",
        }
        if kind in static_routes:
            return static_routes[kind]

        if kind == "radar_departamental":
            params_radar: Dict[str, Any] = {}
            if len(plan.codigos_departamento) >= 1 and 1 <= plan.codigos_departamento[0] <= 22:
                params_radar["depto_codigo"] = plan.codigos_departamento[0]
            if len(plan.codigos_departamento) >= 2 and 1 <= plan.codigos_departamento[1] <= 22:
                params_radar["comparar_con"] = plan.codigos_departamento[1]
            suffix = f"?{urlencode(params_radar)}" if params_radar else ""
            return f"/api/v1/visualizaciones/perfil/radar{suffix}"

        return None

    def build_demographic_chart_html(
        self,
        modo: str = "sexo",
        columna: str = "pob_menor_15",
        orden: str = "asc",
        top_n: int = 10,
    ) -> str:
        """Construir grafica interactiva HTML para desgloses demograficos por sexo, edad o matricula femenina."""
        import plotly.graph_objects as go

        lf, available_cols = self._build_unified_departmental_lazy_frame()
        df_2024 = lf.collect()
        if df_2024.height == 0:
            raise DatasetUnavailableError("Sin registros demograficos 2024.")

        fig = go.Figure()
        if modo == "sexo":
            sorted_df = df_2024.sort("poblacion_total", descending=False)
            deptos = sorted_df["depto_nombre"].to_list()
            mujeres = sorted_df["mujeres"].to_list()
            hombres = sorted_df["hombres"].to_list()
            fig.add_trace(
                go.Bar(
                    name="Mujeres",
                    y=deptos,
                    x=mujeres,
                    orientation="h",
                    marker=dict(color="#0068c8"),
                )
            )
            fig.add_trace(
                go.Bar(
                    name="Hombres",
                    y=deptos,
                    x=hombres,
                    orientation="h",
                    marker=dict(color="#5ca9ff"),
                )
            )
            fig.update_layout(
                barmode="group",
                title=(
                    "<b>Población de Mujeres vs. Hombres por Departamento (2024)</b>"
                    "<br><span style='font-size:12px;color:#5a7188;'>Proyecciones demográficas oficiales agregadas</span>"
                ),
                legend_title_text="Sexo",
                height=680,
                margin=dict(l=65, r=80, t=85, b=55),
            )
        else:
            safe_col = columna if columna in available_cols and columna in _ENRICHED_DEMOGRAPHIC_COLS else "pob_menor_15"
            safe_top = max(5, min(top_n, 22))
            descending = orden.lower() != "asc"
            sub = df_2024.sort(safe_col, descending=descending).head(safe_top)
            deptos = sub["depto_nombre"].to_list()[::-1]
            vals = [int(round(float(v or 0))) for v in sub[safe_col].to_list()[::-1]]
            max_val = max(vals) if vals else 1
            col_title = humanize_label(safe_col)
            sentido = "Mayor a menor" if descending else "Menor a mayor"
            dyn_height = max(420, 160 + safe_top * 24) if safe_top < 22 else 680

            fig.add_trace(
                go.Bar(
                    y=deptos,
                    x=vals,
                    orientation="h",
                    text=[f"{v:,}" for v in vals],
                    textposition="outside",
                    cliponaxis=False,
                    marker=dict(color="#0068c8"),
                )
            )
            fig.update_layout(
                title=(
                    f"<b>{col_title}</b>"
                    f"<br><span style='font-size:12px;color:#5a7188;'>Comparativa departamental ({sentido} · Top {safe_top})</span>"
                ),
                xaxis=dict(range=[0, max_val * 1.18]),
                yaxis=dict(categoryorder="total descending" if not descending else "total ascending"),
                height=dyn_height,
                margin=dict(l=65, r=110, t=90, b=55),
            )

        fig.update_layout(
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f7fbff",
            font=dict(family="Public Sans, Inter, sans-serif", color="#173a5e"),
        )
        return fig.to_html(full_html=True, include_plotlyjs="cdn")
