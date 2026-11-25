from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode

import polars as pl

from src.core.config import PROCESSED_DATA_DIR
from src.schemas.ai_search import AISearchRoutingPlan, DatasetId, VisualizationKind

_MUNICIPAL_CODE_RE = re.compile(r"^\d{4}$")

# Indicadores validados compatibles con las rutas de /api/v1/visualizaciones/...
_CHARTABLE_INDICATORS: frozenset[str] = frozenset(
    {
        "indice_vulnerabilidad_ivst",
        "tasa_retorno_migratorio_por_10k",
        "pct_retornados_menores",
        "pct_retornadas_mujeres",
        "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "tasa_matricula_superior_por_10k",
        "pct_mujeres_superior",
        "razon_dependencia_demografica",
        "tasa_natalidad_por_1000",
        "tasa_mortalidad_por_1000",
        "tasa_crecimiento_natural_por_1000",
        "inflacion_regional_interanual",
        "poblacion_total",
    }
)

_MUNICIPAL_CHARTABLE_INDICATORS: frozenset[str] = frozenset(
    {
        "poblacion_total",
        "tasa_mortalidad_por_1000",
        "tasa_natalidad_por_1000",
        "tasa_crecimiento_natural_por_1000",
        "tasa_necropsias_por_100k",
        "tasa_victimas_viales_por_100k",
        "tasa_mortalidad_vial_por_100k",
        "tasa_matricula_superior_por_10k",
        "pct_mujeres_superior",
    }
)

# Etiquetas publicas legibles (evita exponer nombres tecnicos internos de columnas)
PUBLIC_FIELD_LABELS: Dict[str, str] = {
    "ranking": "posicion",
    "anio": "anio",
    "mes": "mes",
    "mes_nombre": "nombre_mes",
    "depto_codigo": "codigo_departamento",
    "depto_nombre": "departamento",
    "depto_iso": "iso_departamento",
    "region_id": "codigo_region",
    "region_nombre": "region",
    "mupio_codigo_str": "codigo_municipio",
    "dominio": "area",
    "tipo_canasta": "canasta",
    "division_gasto": "division_gasto",
    "cluster_id": "grupo_id",
    "cluster_nombre": "perfil_territorial",
    "nivel_vulnerabilidad": "nivel_vulnerabilidad",
    "poblacion_total": "poblacion_total",
    "poblacion_2024": "poblacion_2024",
    "poblacion_2030": "poblacion_proyectada_2030",
    "crecimiento_absoluto_2024_2030": "crecimiento_poblacional_2024_2030",
    "crecimiento_porcentual_total": "crecimiento_porcentual_2024_2030",
    "tasa_anual_crecimiento_geometrico_pct": "tasa_crecimiento_anual_pct",
    "hombres": "poblacion_hombres",
    "mujeres": "poblacion_mujeres",
    "pob_menor_15": "poblacion_menor_15",
    "pob_15_64": "poblacion_15_a_64",
    "pob_65_mas": "poblacion_65_o_mas",
    "defunciones_total": "defunciones",
    "nacimientos_total": "nacimientos",
    "tasa_mortalidad_por_1000": "tasa_mortalidad_por_1000_hab",
    "tasa_natalidad_por_1000": "tasa_natalidad_por_1000_hab",
    "crecimiento_natural_absoluto": "crecimiento_vegetativo",
    "tasa_crecimiento_natural_por_1000": "tasa_crecimiento_vegetativo_por_1000_hab",
    "indice_masculinidad": "indice_masculinidad",
    "razon_dependencia_demografica": "razon_dependencia_pct",
    "pct_poblacion_menor_15": "porcentaje_menor_15",
    "pct_poblacion_15_64": "porcentaje_15_a_64",
    "pct_poblacion_65_mas": "porcentaje_65_o_mas",
    "necropsias_total": "necropsias_registradas",
    "tasa_necropsias_por_100k": "tasa_necropsias_por_100k_hab",
    "victimas_viales_total": "victimas_accidentes_transito",
    "fallecidos_viales_total": "fallecidos_accidentes_transito",
    "lesionados_viales_total": "lesionados_accidentes_transito",
    "tasa_victimas_viales_por_100k": "tasa_victimas_viales_por_100k_hab",
    "tasa_mortalidad_vial_por_100k": "tasa_mortalidad_vial_por_100k_hab",
    "retornados_total": "personas_retornadas",
    "retornados_hombres": "hombres_retornados",
    "retornados_mujeres": "mujeres_retornadas",
    "retornados_menores": "menores_retornados",
    "tasa_retorno_migratorio_por_10k": "tasa_retorno_migratorio_por_10k_hab",
    "pct_retornados_menores": "porcentaje_menores_retornados",
    "pct_retornadas_mujeres": "porcentaje_mujeres_retornadas",
    "matriculados_superior_total": "matricula_educacion_superior",
    "mujeres_matriculadas_superior": "mujeres_educacion_superior",
    "tasa_matricula_superior_por_10k": "tasa_matricula_superior_por_10k_hab",
    "pct_mujeres_superior": "porcentaje_mujeres_educacion_superior",
    "indice_ipc": "indice_precios_consumidor",
    "indice_ipc_regional": "indice_precios_regional",
    "indice_ipc_nacional": "indice_precios_nacional",
    "inflacion_regional_interanual": "inflacion_interanual_pct",
    "variacion_intermensual_pct": "variacion_mensual_pct",
    "variacion_interanual_pct": "variacion_anual_pct",
    "poder_adquisitivo_quetzal": "poder_adquisitivo_quetzal",
    "perdida_poder_adquisitivo": "perdida_poder_adquisitivo",
    "perdida_poder_adquisitivo_quetzal": "perdida_poder_adquisitivo",
    "costo_diario_percapita": "costo_diario_percapita_gtq",
    "costo_mensual_percapita": "costo_mensual_percapita_gtq",
    "costo_actual_percapita": "costo_actual_mensual_gtq",
    "tendencia_mensual_gtq": "variacion_tendencia_mensual_gtq",
    "crecimiento_mensual_pct": "crecimiento_mensual_estimado_pct",
    "proyeccion_tasa_anual_pct": "proyeccion_anual_pct",
    "proyeccion_3_meses_gtq": "proyeccion_3_meses_gtq",
    "proyeccion_6_meses_gtq": "proyeccion_6_meses_gtq",
    "proyeccion_12_meses_gtq": "proyeccion_12_meses_gtq",
    "brecha_urbano_rural_cba_gtq": "brecha_urbano_rural_gtq",
    "brecha_urbano_rural_cba_pct": "brecha_urbano_rural_pct",
    "indice_vulnerabilidad_ivst": "indice_vulnerabilidad_territorial",
    "variable": "indicador",
    "n_observaciones": "observaciones",
    "media": "promedio",
    "desviacion_estandar": "desviacion_estandar",
    "mediana": "mediana",
    "minimo": "valor_minimo",
    "maximo": "valor_maximo",
    "coeficiente_variacion_pct": "coeficiente_variacion_pct",
    "variable_1": "indicador_a",
    "variable_2": "indicador_b",
    "pearson_r": "correlacion_pearson",
    "pearson_pvalue": "significancia_p",
    "spearman_rho": "correlacion_spearman",
    "fuerza_asociacion": "fuerza_asociacion",
}


@dataclass(frozen=True)
class DatasetSpec:
    """Metadatos internos de cada tabla estadistica agregada permitida."""

    relative_path: Tuple[str, ...]
    dimension_columns: Tuple[str, ...]
    default_metrics: Tuple[str, ...]
    default_sort: Optional[str] = None


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

    def execute_plan(self, plan: AISearchRoutingPlan) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if plan.conjunto_datos is None or plan.conjunto_datos not in DATASET_REGISTRY:
            raise DatasetUnavailableError("Conjunto de datos no especificado en el plan.")

        spec = DATASET_REGISTRY[plan.conjunto_datos]
        parquet_path = self._base_dir.joinpath(*spec.relative_path)
        if not parquet_path.exists() or not parquet_path.is_file():
            raise DatasetUnavailableError("Archivo fuente no encontrado en disco.")

        # Escaneo perezoso en modo estricto de solo lectura (cero SQL dinamico)
        lazy_frame = pl.scan_parquet(str(parquet_path))
        available_columns = set(lazy_frame.collect_schema().names())

        lazy_frame = self._apply_filters(lazy_frame, available_columns, plan)
        lazy_frame = self._apply_sorting(lazy_frame, available_columns, plan, spec)

        selected_cols = self._select_columns(available_columns, plan.columnas_metricas, spec)
        safe_limit = max(1, min(plan.limite, self._max_rows))

        df_result = lazy_frame.select([pl.col(c) for c in selected_cols]).limit(safe_limit).collect()
        public_rows = self._to_public_records(df_result.to_dicts())
        vis_url = self._build_visualization_url(plan) if public_rows else None
        return public_rows, vis_url

    @staticmethod
    def _apply_filters(
        lazy_frame: pl.LazyFrame,
        available_columns: set[str],
        plan: AISearchRoutingPlan,
    ) -> pl.LazyFrame:
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

        if plan.nivel_vulnerabilidad is not None and "nivel_vulnerabilidad" in available_columns:
            lazy_frame = lazy_frame.filter(pl.col("nivel_vulnerabilidad") == plan.nivel_vulnerabilidad)

        return lazy_frame

    @staticmethod
    def _apply_sorting(
        lazy_frame: pl.LazyFrame,
        available_columns: set[str],
        plan: AISearchRoutingPlan,
        spec: DatasetSpec,
    ) -> pl.LazyFrame:
        descending = plan.direccion_orden == "desc"
        sort_col: Optional[str] = None
        if plan.ordenar_por and plan.ordenar_por in available_columns:
            sort_col = plan.ordenar_por
        elif plan.columnas_metricas:
            for candidate in plan.columnas_metricas:
                if candidate in available_columns:
                    sort_col = candidate
                    break
        if sort_col is None and spec.default_sort and spec.default_sort in available_columns:
            sort_col = spec.default_sort

        if sort_col is not None:
            lazy_frame = lazy_frame.sort(sort_col, descending=descending, nulls_last=True)
        return lazy_frame

    @staticmethod
    def _select_columns(
        available_columns: set[str],
        requested_metrics: Sequence[str],
        spec: DatasetSpec,
    ) -> List[str]:
        ordered: List[str] = []
        for dim in spec.dimension_columns:
            if dim in available_columns and dim not in ordered:
                ordered.append(dim)

        valid_requested = [m for m in requested_metrics if m in available_columns and m not in ordered]
        if valid_requested:
            ordered.extend(valid_requested)
        else:
            for default_col in spec.default_metrics:
                if default_col in available_columns and default_col not in ordered:
                    ordered.append(default_col)

        return ordered

    @staticmethod
    def _to_public_records(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sanitized: List[Dict[str, Any]] = []
        for row in raw_rows:
            clean_row: Dict[str, Any] = {}
            for key, val in row.items():
                public_key = PUBLIC_FIELD_LABELS.get(key, key)
                if key in {"variable", "variable_1", "variable_2"} and isinstance(val, str):
                    clean_row[public_key] = PUBLIC_FIELD_LABELS.get(val, val)
                elif isinstance(val, float):
                    clean_row[public_key] = round(val, 4)
                else:
                    clean_row[public_key] = val
            sanitized.append(clean_row)
        return sanitized

    @staticmethod
    def _build_visualization_url(plan: AISearchRoutingPlan) -> Optional[str]:
        kind: VisualizationKind = plan.visualizacion_sugerida
        primary_metric = next(
            (m for m in plan.columnas_metricas if m in _CHARTABLE_INDICATORS),
            None,
        )
        if primary_metric is None and plan.ordenar_por in _CHARTABLE_INDICATORS:
            primary_metric = plan.ordenar_por

        if kind == "ranking_departamental":
            ind = primary_metric or "indice_vulnerabilidad_ivst"
            top_n = max(1, min(plan.limite, 22))
            query = urlencode({"indicador": ind, "top_n": top_n, "orden": plan.direccion_orden})
            return f"/api/v1/visualizaciones/barras/ranking-departamental?{query}"

        if kind == "ranking_municipal":
            muni_ind = next(
                (m for m in plan.columnas_metricas if m in _MUNICIPAL_CHARTABLE_INDICATORS),
                "tasa_necropsias_por_100k",
            )
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
